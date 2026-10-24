from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_ai.phase7.acquisition import AcquisitionPaths, _promote_candles
from crypto_ai.phase7.config import PathConfig, Phase7Config
from crypto_ai.phase7.discovery_checkpoint import DiscoverySymbolCheckpointStore
from crypto_ai.phase7.segments import AcquisitionOutcome, AcquisitionStatus
from tests.phase7.test_archive_missing_reconciliation import _archive, _registry


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


def test_offline_backfill_creates_auditable_run_bound_completion(tmp_path: Path) -> None:
    config = _config(tmp_path)
    registry = _registry()
    manifest, _, source_files = _archive(tmp_path, missing=())
    source_times = {path: path.stat().st_mtime_ns for path in source_files}
    silver = _promote_candles(config, AcquisitionPaths.from_config(config), manifest)
    record = registry.records[0]
    end = datetime(2022, 3, 4, tzinfo=UTC)
    store = DiscoverySymbolCheckpointStore(config, registry, run_identity="phase7-test")

    outcome = store.backfill(
        record,
        interval="1d",
        request_start=datetime(2022, 2, 24, tzinfo=UTC),
        request_end=end,
    )

    assert outcome is not None
    assert outcome.status is AcquisitionStatus.VALID
    assert outcome.silver_manifest == str(silver.resolve())
    checkpoint = store.checkpoint_path(record.symbol, "1d")
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["backfilled_from_existing_evidence"] is True
    assert payload["identity"]["run_identity"] == "phase7-test"
    assert payload["identity"]["configuration_hash"] == config.configuration_hash
    assert payload["artifact_identity"]
    assert payload["evidence_files"]
    assert {path: path.stat().st_mtime_ns for path in source_files} == source_times

    other_run = DiscoverySymbolCheckpointStore(config, registry, run_identity="phase7-other")
    assert (
        other_run.load(
            record,
            interval="1d",
            request_start=datetime(2022, 2, 24, tzinfo=UTC),
            request_end=end,
        )
        is None
    )


def test_corrupt_or_incomplete_checkpoint_never_claims_completion(tmp_path: Path) -> None:
    config = _config(tmp_path)
    registry = _registry()
    record = registry.records[0]
    start = datetime(2022, 2, 24, tzinfo=UTC)
    end = start + timedelta(days=8)
    store = DiscoverySymbolCheckpointStore(config, registry, run_identity="phase7-test")
    checkpoint = store.checkpoint_path(record.symbol, "1d")
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"status":"COMPLETE"}\n', encoding="utf-8")

    assert store.load(record, interval="1d", request_start=start, request_end=end) is None
    assert store.backfill(record, interval="1d", request_start=start, request_end=end) is None


def test_checkpoint_hit_skips_every_network_and_promotion_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crypto_ai.phase7 import acquisition

    config = _config(tmp_path)
    registry = _registry()
    record = registry.records[0]
    cached = AcquisitionOutcome(
        symbol=record.symbol,
        interval="1d",
        status=AcquisitionStatus.VALID,
        silver_manifest=str(tmp_path / "existing-silver.json"),
    )

    class HitStore:
        def load(self, *_args: object, **_kwargs: object) -> AcquisitionOutcome:
            return cached

        def backfill(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("backfill must not run after a checkpoint hit")

    class ForbiddenNetwork:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("archive payload/CHECKSUM path must not run")

    monkeypatch.setattr(Phase7Config, "assert_cloud_execution_allowed", lambda _self: None)
    monkeypatch.setattr(acquisition, "BinanceArchiveClient", ForbiddenNetwork)
    monkeypatch.setattr(
        acquisition,
        "_promote_candles",
        lambda *_args, **_kwargs: pytest.fail("validator/Silver path must not run"),
    )

    result = acquisition.acquire_candle_family(
        config,
        registry,
        symbols=(record.symbol,),
        interval="1d",
        start=datetime(2022, 2, 24, tzinfo=UTC),
        end=datetime(2022, 3, 4, tzinfo=UTC),
        completion_store=HitStore(),  # type: ignore[arg-type]
        resume=True,
        backfill_completion=True,
    )

    assert result.outcomes == (cached,)
    assert result.manifests == {record.symbol: str(tmp_path / "existing-silver.json")}


def test_interrupted_checkpoint_write_never_leaves_false_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crypto_ai.phase7 import discovery_checkpoint

    config = _config(tmp_path)
    registry = _registry()
    manifest, _, _ = _archive(tmp_path, missing=())
    silver = _promote_candles(config, AcquisitionPaths.from_config(config), manifest)
    record = registry.records[0]
    start = datetime(2022, 2, 24, tzinfo=UTC)
    end = datetime(2022, 3, 4, tzinfo=UTC)
    store = DiscoverySymbolCheckpointStore(config, registry, run_identity="phase7-test")
    outcome = AcquisitionOutcome(
        symbol=record.symbol,
        interval="1d",
        status=AcquisitionStatus.VALID,
        silver_manifest=str(silver.resolve()),
    )

    monkeypatch.setattr(
        discovery_checkpoint,
        "atomic_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(InterruptedError()),
    )
    with pytest.raises(InterruptedError):
        store.complete(
            record,
            outcome,
            interval="1d",
            request_start=start,
            request_end=end,
        )

    assert not store.checkpoint_path(record.symbol, "1d").exists()
    assert store.load(record, interval="1d", request_start=start, request_end=end) is None
