from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_ai.config import BinanceSettings
from crypto_ai.data.ingestion import DownloadRequest
from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.quality.models import (
    DatasetQualityReport,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import acquisition
from crypto_ai.phase7.acquisition import QualityGateRejected, ReconciliationAttempt
from crypto_ai.phase7.config import PathConfig, Phase7Config
from crypto_ai.phase7.discovery_checkpoint import DiscoverySymbolCheckpointStore
from crypto_ai.phase7.registry import build_symbol_registry
from crypto_ai.phase7.segments import (
    AcquisitionStatus,
    CausalDataGap,
    ReconciliationStatus,
)

START = datetime(2023, 11, 30, tzinfo=UTC)
END = START + timedelta(days=1)
PARTITION = f"{int(START.timestamp() * 1000)}-{int(END.timestamp() * 1000)}"


def _config(tmp_path: Path) -> Phase7Config:
    root = Path(__file__).resolve().parents[2]
    return Phase7Config(
        binance_config=root / "configs/data/binance.toml",
        quality_config=root / "configs/data_quality/default.toml",
        paths=PathConfig(
            data_root=tmp_path,
            artifact_root=tmp_path / "artifacts",
            gold_root=tmp_path / "gold",
            checkpoint_root=tmp_path / "checkpoints",
        ),
    )


def _registry():
    rows = []
    exchange = []
    for symbol in ("BADUSDT", "GOODUSDT"):
        exchange.append(
            {
                "symbol": symbol,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }
        )
        rows.append(
            {
                "symbol": symbol,
                "first_market_data_time": START,
                "last_market_data_time": END,
                "available_intervals": ["1d"],
            }
        )
    return build_symbol_registry(
        {"symbols": exchange},
        rows,
        observed_at=END,
        research_cutoff=END,
    )


def test_unrecoverable_symbol_is_evidenced_checkpointed_and_next_symbol_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = _registry()
    paths = acquisition.AcquisitionPaths.from_config(config)
    bad_manifest = paths.bronze / "manifests/bad.json"
    good_manifest = paths.bronze / "manifests/good.json"
    good_silver = paths.silver / "manifests/good.json"
    for path, symbol in ((bad_manifest, "BADUSDT"), (good_manifest, "GOODUSDT")):
        write_manifest(
            path,
            {
                "run_id": f"archive-{symbol.lower()}",
                "source": "binance_public_archive",
                "market": "usdm",
                "symbol": symbol,
                "interval": "1d",
                "start": START.isoformat(),
                "end": END.isoformat(),
                "status": "completed",
                "partitions": [],
            },
        )
    write_manifest(good_silver, {"quality_status": "PASS"})

    report = DatasetQualityReport(
        dataset_version="invalid-source",
        source="binance_public_archive",
        market="usdm",
        symbol="BADUSDT",
        interval="1d",
        range_start=START,
        range_end=END,
        source_files=[],
        source_manifest=str(bad_manifest.resolve()),
        checks=[
            ValidationResult(
                check_name="taker_buy_base_exceeds_volume",
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message="official row is structurally impossible",
                symbol="BADUSDT",
                interval="1d",
                partition=PARTITION,
                affected_rows=1,
            )
        ],
        summary={},
        policy={},
    )
    quality = paths.quality / f"{report.report_id}.json"
    quarantine = paths.quarantine / f"{report.report_id}.json"
    write_manifest(quality, report.to_dict())
    write_manifest(quarantine, {"report_id": report.report_id, "status": "QUARANTINED"})
    rest = paths.bronze / "manifests/rest.json"
    comparison = paths.reconciliation / "comparison.json"
    write_manifest(rest, {"source": "binance", "source_transport": "rest"})
    write_manifest(comparison, {"equivalent": True, "timestamps_equal": True})
    gap = CausalDataGap(
        symbol="BADUSDT",
        interval="1d",
        start=START,
        end=END,
        partition=PARTITION,
        failed_checks=("taker_buy_base_exceeds_volume",),
        source_manifest=str(bad_manifest.resolve()),
        source_manifest_sha256=file_sha256(bad_manifest),
        quality_report=str(quality.resolve()),
        quality_report_sha256=file_sha256(quality),
        quarantine=str(quarantine.resolve()),
        quarantine_sha256=file_sha256(quarantine),
        rest_manifest=str(rest.resolve()),
        rest_manifest_sha256=file_sha256(rest),
        comparison_report=str(comparison.resolve()),
        comparison_report_sha256=file_sha256(comparison),
        reconciliation_status=ReconciliationStatus.IDENTICAL_INVALID,
    )

    class FakeArchiveClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def inspect_interval_bounds(self, **_kwargs: object):
            return SimpleNamespace(first_open_time=START, end_exclusive=END)

    class FakeDownloader:
        def __init__(self, settings: BinanceSettings, _client: object) -> None:
            self.symbol = settings.symbol

        def download(self, _request: DownloadRequest) -> Path:
            return bad_manifest if self.symbol == "BADUSDT" else good_manifest

    def promote(_config: Phase7Config, _paths: object, manifest: Path) -> Path:
        if manifest == bad_manifest:
            raise QualityGateRejected(manifest, report)
        return good_silver

    monkeypatch.setattr(Phase7Config, "assert_cloud_execution_allowed", lambda _self: None)
    monkeypatch.setattr(acquisition, "BinanceArchiveClient", FakeArchiveClient)
    monkeypatch.setattr(acquisition, "HistoricalDownloader", FakeDownloader)
    monkeypatch.setattr(acquisition, "_promote_candles", promote)
    monkeypatch.setattr(
        acquisition,
        "_attempt_archive_reconciliation",
        lambda *_args: ReconciliationAttempt(
            segment_source_manifest=bad_manifest,
            gaps=(gap,),
        ),
    )

    class TestStore(DiscoverySymbolCheckpointStore):
        def complete(self, record, outcome, **kwargs):  # type: ignore[no-untyped-def]
            if outcome.status is AcquisitionStatus.VALID:
                return tmp_path / "ignored-valid-checkpoint.json"
            return super().complete(record, outcome, **kwargs)

    store = TestStore(config, registry, run_identity="phase7-test")
    result = acquisition.acquire_candle_family(
        config,
        registry,
        symbols=("BADUSDT", "GOODUSDT"),
        interval="1d",
        start=START,
        end=END,
        completion_store=store,
        exclude_unrecoverable=True,
    )

    bad, good = result.outcomes
    assert bad.status is AcquisitionStatus.SYMBOL_EXCLUDED_DATA_QUALITY
    assert good.status is AcquisitionStatus.VALID
    assert result.manifests == {"GOODUSDT": str(good_silver.resolve())}
    evidence = json.loads(Path(bad.exclusion_evidence).read_text(encoding="utf-8"))
    assert evidence["symbol"] == "BADUSDT"
    assert evidence["failed_checks"][0]["check_name"] == "taker_buy_base_exceeds_volume"
    assert evidence["rest_evidence"]
    assert evidence["raw_sources_mutated"] is False
    assert evidence["fabricated_rows"] is False
    assert (
        store.load(
            registry.by_symbol()["BADUSDT"],
            interval="1d",
            request_start=START,
            request_end=END,
        )
        == bad
    )
