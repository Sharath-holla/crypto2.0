from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.models import (
    DatasetQualityReport,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION, candles_to_table
from crypto_ai.data.storage import file_sha256, write_immutable
from crypto_ai.phase7 import acquisition
from crypto_ai.phase7.acquisition import (
    AcquisitionPaths,
    QualityGateRejected,
    _attempt_archive_reconciliation,
    _missing_archive_records,
    _promote_candles,
)
from crypto_ai.phase7.config import PathConfig, Phase7Config
from crypto_ai.phase7.registry import build_symbol_registry
from crypto_ai.phase7.segments import ReconciliationStatus
from tests.factories import make_candle

ROOT = Path(__file__).resolve().parents[2]
START = datetime(2022, 2, 24, tzinfo=UTC)
DAY = timedelta(days=1)
SYMBOL = "TESTUSDT"


def _key(start: datetime, end: datetime) -> str:
    return f"{int(start.timestamp() * 1_000)}-{int(end.timestamp() * 1_000)}"


def _config(tmp_path: Path) -> Phase7Config:
    return Phase7Config(
        binance_config=ROOT / "configs/data/binance.toml",
        quality_config=ROOT / "configs/data_quality/default.toml",
        paths=PathConfig(data_root=tmp_path),
    )


def _registry(*, available_from: datetime = START - DAY):
    end = START + 10 * DAY
    return build_symbol_registry(
        {
            "symbols": [
                {
                    "symbol": SYMBOL,
                    "baseAsset": "TEST",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "onboardDate": int(available_from.timestamp() * 1_000),
                }
            ]
        },
        [
            {
                "symbol": SYMBOL,
                "base_asset": "TEST",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": available_from,
                "last_market_data_time": end,
                "available_from": available_from,
                "available_intervals": ["5m", "12h", "1d"],
            }
        ],
        observed_at=end,
        research_cutoff=end + DAY,
    )


def _archive(
    tmp_path: Path,
    *,
    missing: tuple[int, ...],
    day_count: int = 8,
) -> tuple[Path, dict[datetime, object], tuple[Path, ...]]:
    bronze = tmp_path / "phase7/bronze/binance"
    records: list[dict[str, object]] = []
    rest_rows: dict[datetime, object] = {}
    archive_files: list[Path] = []
    for index in range(day_count):
        start = START + index * DAY
        end = start + DAY
        partition_key = _key(start, end)
        rest_rows[start] = replace(
            make_candle(
                start=start,
                interval_minutes=1_440,
                symbol=SYMBOL,
                source="binance_usdm_futures_rest",
            ),
            open=Decimal(str(10 + index)),
            high=Decimal(str(12 + index)),
            low=Decimal(str(9 + index)),
            close=Decimal(str(11 + index)),
        )
        if index in missing:
            records.append(
                {
                    "partition_key": partition_key,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "status": "empty",
                    "row_count": 0,
                    "file": None,
                    "sha256": None,
                    "quality": {"is_valid": False},
                }
            )
            continue
        relative = Path(
            "klines/transport=archive/market=usdm",
            f"symbol={SYMBOL}",
            "interval=1d",
            f"date={start.date().isoformat()}",
            f"part-{partition_key}.parquet",
        )
        path = bronze / relative
        archive_candle = replace(rest_rows[start], source="binance_usdm_futures_archive")
        checksum = write_immutable(
            path,
            candles_to_table([archive_candle]),
            metadata={
                "source": "binance_public_archive",
                "market": "usdm",
                "symbol": SYMBOL,
                "interval": "1d",
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "ingestion_version": "0.1.0",
            },
        )
        archive_files.append(path)
        records.append(
            {
                "partition_key": partition_key,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": "complete",
                "row_count": 1,
                "file": relative.as_posix(),
                "sha256": checksum,
                "quality": {"is_valid": True},
            }
        )
    manifest_path = bronze / "manifests/archive-gap.json"
    write_manifest(
        manifest_path,
        {
            "run_id": "archive-gap-test",
            "source": "binance_public_archive",
            "source_transport": "archive",
            "row_source": "binance_usdm_futures_archive",
            "market": "usdm",
            "symbol": SYMBOL,
            "interval": "1d",
            "start": START.isoformat(),
            "end": (START + day_count * DAY).isoformat(),
            "row_count": day_count - len(missing),
            "file_locations": [str(record["file"]) for record in records if record.get("file")],
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": "0.1.0",
            "status": "completed_with_quality_errors",
            "partitions": records,
        },
    )
    return manifest_path, rest_rows, tuple(archive_files)


def _rejection(config: Phase7Config, manifest: Path) -> QualityGateRejected:
    with pytest.raises(QualityGateRejected) as caught:
        _promote_candles(config, AcquisitionPaths.from_config(config), manifest)
    return caught.value


def _install_rest(
    monkeypatch: pytest.MonkeyPatch,
    rows: dict[datetime, object],
    *,
    mode: str = "valid",
) -> list[tuple[datetime, datetime]]:
    calls: list[tuple[datetime, datetime]] = []

    class FakeRestClient:
        def __init__(self, _settings: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def fetch_klines(self, **kwargs: object):
            start = kwargs["start"]
            end = kwargs["end"]
            assert isinstance(start, datetime) and isinstance(end, datetime)
            calls.append((start, end))
            row = rows[start]
            if mode == "missing":
                return []
            if mode == "extra":
                return [row, replace(row, open_time=end, close_time=end + DAY)]
            if mode == "duplicate":
                return [row, row]
            if mode == "conflict":
                return [row, replace(row, close=Decimal("999"))]
            if mode == "invalid":
                return [replace(row, taker_buy_base_volume=Decimal("999999999"))]
            if mode == "symbol":
                return [replace(row, symbol="OTHERUSDT")]
            if mode == "boundary":
                return [replace(row, open_time=start + timedelta(hours=12))]
            return [row]

    monkeypatch.setattr(acquisition, "BinanceRestClient", FakeRestClient)
    return calls


@pytest.mark.parametrize(
    ("missing", "expected_ranges"),
    [
        ((2,), 1),
        ((2, 3, 4), 1),
        ((2, 3, 6), 2),
    ],
)
def test_exact_missing_archive_rows_compose_validate_and_preserve_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: tuple[int, ...],
    expected_ranges: int,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest, rows, archive_files = _archive(tmp_path, missing=missing)
    archive_before = manifest.read_bytes()
    file_hashes = {path: file_sha256(path) for path in archive_files}
    rejection = _rejection(config, manifest)
    report_path = paths.quality / f"{rejection.report.report_id}.json"
    quarantine_path = paths.quarantine / f"{rejection.report.report_id}.json"
    report_before = report_path.read_bytes()
    quarantine_before = quarantine_path.read_bytes()
    calls = _install_rest(monkeypatch, rows)

    attempt = _attempt_archive_reconciliation(config, paths, _registry(), rejection)
    assert attempt.corrected_manifest is not None
    composed = read_manifest(attempt.corrected_manifest)
    assert composed is not None
    assert composed["source_transport"] == "archive_primary_rest_missing_rows"
    assert composed["reconciliation"]["filled_partition_count"] == len(missing)
    assert len(composed["reconciliation"]["rest_overlays"]) == expected_ranges
    rest_records = [
        record
        for record in composed["partitions"]
        if record["row_source"] == "binance_usdm_futures_rest"
    ]
    assert [record["partition_key"] for record in rest_records] == [
        _key(START + index * DAY, START + (index + 1) * DAY) for index in missing
    ]
    assert all(
        record["reconciliation"]["archive_evidence"]["status"] == "empty" for record in rest_records
    )
    assert calls == [(START + index * DAY, START + (index + 1) * DAY) for index in missing]

    silver_path = _promote_candles(config, paths, attempt.corrected_manifest)
    silver = read_manifest(silver_path)
    assert silver is not None and silver["quality_status"] in {"PASS", "WARN"}
    assert silver["source_manifest"] == str(attempt.corrected_manifest.resolve())
    assert manifest.read_bytes() == archive_before
    assert {path: file_sha256(path) for path in archive_files} == file_hashes
    assert report_path.read_bytes() == report_before
    assert quarantine_path.read_bytes() == quarantine_before

    resumed = _attempt_archive_reconciliation(config, paths, _registry(), rejection)
    assert resumed.corrected_manifest == attempt.corrected_manifest


@pytest.mark.parametrize(
    "mode", ["missing", "extra", "duplicate", "conflict", "invalid", "symbol", "boundary"]
)
def test_inexact_or_invalid_rest_gap_recovery_fails_closed_into_causal_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest, rows, _ = _archive(tmp_path, missing=(2,))
    rejection = _rejection(config, manifest)
    _install_rest(monkeypatch, rows, mode=mode)

    attempt = _attempt_archive_reconciliation(config, paths, _registry(), rejection)
    assert attempt.corrected_manifest is None
    assert attempt.segment_source_manifest == manifest.resolve()
    assert len(attempt.gaps) == 1
    assert attempt.gaps[0].reconciliation_status is ReconciliationStatus.NOT_PROVEN
    assert not list(manifest.parent.glob("reconciled-gap-*.json"))


def test_rest_missing_one_row_from_consecutive_gap_rejects_whole_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest, rows, _ = _archive(tmp_path, missing=(2, 3, 4))
    rejection = _rejection(config, manifest)
    omitted = START + 3 * DAY

    class PartialRestClient:
        def __init__(self, _settings: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def fetch_klines(self, **kwargs: object):
            start = kwargs["start"]
            assert isinstance(start, datetime)
            return [] if start == omitted else [rows[start]]

    monkeypatch.setattr(acquisition, "BinanceRestClient", PartialRestClient)
    attempt = _attempt_archive_reconciliation(config, paths, _registry(), rejection)
    assert attempt.corrected_manifest is None
    assert len(attempt.gaps) == 3
    assert all(gap.reconciliation_status is ReconciliationStatus.NOT_PROVEN for gap in attempt.gaps)
    assert not list(manifest.parent.glob("reconciled-gap-*.json"))


def test_lifecycle_absence_and_existing_archive_rows_are_not_gap_reconciled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest, rows, _ = _archive(tmp_path, missing=(2,))
    rejection = _rejection(config, manifest)

    class ForbiddenRestClient:
        def __init__(self, _settings: object) -> None:
            raise AssertionError("REST must not be called for lifecycle absence")

    monkeypatch.setattr(acquisition, "BinanceRestClient", ForbiddenRestClient)
    lifecycle_attempt = _attempt_archive_reconciliation(
        config,
        paths,
        _registry(available_from=START + 3 * DAY),
        rejection,
    )
    assert lifecycle_attempt.corrected_manifest is None
    assert lifecycle_attempt.gaps == ()

    payload = read_manifest(manifest)
    assert payload is not None
    complete_key = payload["partitions"][1]["partition_key"]
    synthetic_report = DatasetQualityReport(
        dataset_version="test",
        source="binance_public_archive",
        market="usdm",
        symbol=SYMBOL,
        interval="1d",
        range_start=START,
        range_end=START + 8 * DAY,
        source_files=[],
        source_manifest=str(manifest),
        checks=[
            ValidationResult(
                check_name="empty_partition",
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message="contrived",
                symbol=SYMBOL,
                interval="1d",
                partition=complete_key,
            ),
            ValidationResult(
                check_name="cross_partition_gap",
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message="contrived",
                symbol=SYMBOL,
                interval="1d",
                affected_rows=1,
            ),
        ],
        summary={},
        policy={},
    )
    assert _missing_archive_records(payload, synthetic_report, _registry()) == ()
    assert rows
