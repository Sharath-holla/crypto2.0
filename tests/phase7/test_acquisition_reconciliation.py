from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.models import (
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
    _failed_market_value_partitions,
    _promote_candles,
    _reconcile_failed_archive_partitions,
)
from crypto_ai.phase7.config import PathConfig, Phase7Config
from crypto_ai.phase7.registry import build_symbol_registry
from tests.factories import make_candle

ROOT = Path(__file__).resolve().parents[2]
START = datetime(2023, 9, 19, tzinfo=UTC)
END = START + timedelta(days=1)
PARTITION_KEY = "1695081600000-1695168000000"
SYMBOL = "TESTUSDT"


def _config(tmp_path: Path) -> Phase7Config:
    return Phase7Config(
        binance_config=ROOT / "configs/data/binance.toml",
        quality_config=ROOT / "configs/data_quality/default.toml",
        paths=PathConfig(data_root=tmp_path),
    )


def _registry():
    return build_symbol_registry(
        {
            "symbols": [
                {
                    "symbol": SYMBOL,
                    "baseAsset": "TEST",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                }
            ]
        },
        [
            {
                "symbol": SYMBOL,
                "base_asset": "TEST",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": START,
                "last_market_data_time": datetime(2026, 6, 30, tzinfo=UTC),
                "available_intervals": ["5m", "12h", "1d"],
            }
        ],
        observed_at=datetime(2026, 6, 30, tzinfo=UTC),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _archive_fixture(tmp_path: Path) -> tuple[Path, object, object, Path]:
    root = tmp_path / "phase7/bronze/binance"
    relative = Path(
        "klines/transport=archive/market=usdm",
        f"symbol={SYMBOL}",
        "interval=1d",
        f"date={START.date().isoformat()}",
        f"part-{PARTITION_KEY}.parquet",
    )
    archive_file = root / relative
    base = make_candle(
        start=START,
        interval_minutes=1_440,
        symbol=SYMBOL,
        source="binance_usdm_futures_archive",
    )
    archive_candle = replace(
        base,
        base_volume=Decimal("53196965"),
        quote_volume=Decimal("125481457.9673600"),
        trade_count=340097,
        taker_buy_base_volume=Decimal("75647001.6"),
        taker_buy_quote_volume=Decimal("63666192.6916500"),
    )
    rest_candle = replace(
        archive_candle,
        base_volume=Decimal("149111968.4"),
        source="binance_usdm_futures_rest",
    )
    checksum = write_immutable(
        archive_file,
        candles_to_table([archive_candle]),
        metadata={
            "source": "binance_public_archive",
            "market": "usdm",
            "symbol": SYMBOL,
            "interval": "1d",
            "requested_start": START.isoformat(),
            "requested_end": END.isoformat(),
            "ingestion_version": "0.1.0",
        },
    )
    manifest_path = root / "manifests/archive.json"
    write_manifest(
        manifest_path,
        {
            "run_id": "archive-testusdt-1d",
            "source": "binance_public_archive",
            "source_transport": "archive",
            "row_source": "binance_usdm_futures_archive",
            "market": "usdm",
            "symbol": SYMBOL,
            "interval": "1d",
            "start": START.isoformat(),
            "end": END.isoformat(),
            "row_count": 1,
            "file_locations": [relative.as_posix()],
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": "0.1.0",
            "status": "completed",
            "partitions": [
                {
                    "partition_key": PARTITION_KEY,
                    "start": START.isoformat(),
                    "end": END.isoformat(),
                    "status": "complete",
                    "row_count": 1,
                    "file": relative.as_posix(),
                    "sha256": checksum,
                    "quality": {"is_valid": True},
                }
            ],
        },
    )
    return manifest_path, archive_candle, rest_candle, archive_file


def _rejection(config: Phase7Config, manifest_path: Path) -> QualityGateRejected:
    paths = AcquisitionPaths.from_config(config)
    with pytest.raises(QualityGateRejected) as caught:
        _promote_candles(config, paths, manifest_path)
    rejection = caught.value
    assert rejection.report.overall_status is ValidationStatus.FAIL
    assert _failed_market_value_partitions(rejection.report) == (PARTITION_KEY,)
    assert (paths.quarantine / f"{rejection.report.report_id}.json").is_file()
    return rejection


def test_proven_rest_market_value_correction_preserves_sources_and_promotes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest_path, _, rest_candle, archive_file = _archive_fixture(tmp_path)
    archive_manifest_before = manifest_path.read_bytes()
    archive_checksum_before = file_sha256(archive_file)
    rejection = _rejection(config, manifest_path)

    class FakeRestClient:
        def __init__(self, _settings: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def fetch_klines(self, **kwargs: object):
            assert kwargs["start"] == START
            assert kwargs["end"] == END
            return [rest_candle]

    monkeypatch.setattr(acquisition, "BinanceRestClient", FakeRestClient)
    reconciled_path = _reconcile_failed_archive_partitions(
        config,
        paths,
        _registry(),
        rejection,
    )

    assert reconciled_path is not None
    reconciled = read_manifest(reconciled_path)
    assert reconciled is not None
    assert reconciled["source"] == "binance_official_public_reconciled"
    assert reconciled["reconciliation"]["raw_sources_mutated"] is False
    assert reconciled["reconciliation"]["replaced_partition_count"] == 1
    assert reconciled["partitions"][0]["row_source"] == "binance_usdm_futures_rest"
    reports = list(paths.reconciliation.glob("archive-rest-*.json"))
    assert len(reports) == 1
    comparison = json.loads(reports[0].read_text(encoding="utf-8"))
    assert comparison["timestamps_equal"] is True
    assert comparison["fields"]["base_volume"]["mismatch_count"] == 1
    assert comparison["fields"]["quote_volume"]["mismatch_count"] == 0

    silver_manifest = _promote_candles(config, paths, reconciled_path)
    silver = read_manifest(silver_manifest)
    assert silver is not None
    assert silver["quality_status"] == "PASS"
    assert silver["source_manifest"] == str(reconciled_path.resolve())
    assert manifest_path.read_bytes() == archive_manifest_before
    assert file_sha256(archive_file) == archive_checksum_before


def test_identical_invalid_rest_row_cannot_bypass_quality_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    paths = AcquisitionPaths.from_config(config)
    manifest_path, archive_candle, _, _ = _archive_fixture(tmp_path)
    rejection = _rejection(config, manifest_path)
    identical_rest = replace(archive_candle, source="binance_usdm_futures_rest")

    class FakeRestClient:
        def __init__(self, _settings: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def fetch_klines(self, **_kwargs: object):
            return [identical_rest]

    monkeypatch.setattr(acquisition, "BinanceRestClient", FakeRestClient)

    source_before = manifest_path.read_bytes()
    report_path = paths.quality / f"{rejection.report.report_id}.json"
    quarantine_path = paths.quarantine / f"{rejection.report.report_id}.json"
    report_before = report_path.read_bytes()
    quarantine_before = quarantine_path.read_bytes()
    attempt = _attempt_archive_reconciliation(config, paths, _registry(), rejection)

    assert attempt.corrected_manifest is None
    assert attempt.segment_source_manifest == manifest_path.resolve()
    assert len(attempt.gaps) == 1
    gap = attempt.gaps[0]
    assert gap.failed_checks == ("taker_buy_base_exceeds_volume",)
    assert gap.start == START
    assert gap.end == END
    assert gap.unusable_data_gap is True
    assert _reconcile_failed_archive_partitions(config, paths, _registry(), rejection) is None
    assert not list(manifest_path.parent.glob("reconciled-*.json"))
    assert manifest_path.read_bytes() == source_before
    assert report_path.read_bytes() == report_before
    assert quarantine_path.read_bytes() == quarantine_before


def test_non_market_value_failure_is_never_reconciled(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest_path, _, _, _ = _archive_fixture(tmp_path)
    rejection = _rejection(config, manifest_path)
    rejection.report.checks.append(
        ValidationResult(
            check_name="gaps",
            status=ValidationStatus.FAIL,
            severity=ValidationSeverity.ERROR,
            message="missing candle",
            symbol=SYMBOL,
            interval="1d",
            partition=PARTITION_KEY,
        )
    )

    assert _failed_market_value_partitions(rejection.report) == ()
