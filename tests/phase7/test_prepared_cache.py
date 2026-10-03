from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.folds import MultiAssetFoldData
from crypto_ai.phase7.models import prepare_architecture_inputs
from crypto_ai.phase7.prepared_cache import (
    PREPROCESSING_VERSION,
    PreparedCacheCapacityError,
    PreparedCacheMissError,
    PreparedCacheReadOnlyError,
    PreparedDataCache,
    PreparedTrainingSegments,
    cache_size_report,
    cleanup_cache_entries,
    referenced_cache_ids,
)


def _fixture() -> tuple[FoldPlan, MultiAssetFoldData, PreparedTrainingSegments, dict[str, object]]:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    plan = FoldPlan(
        "fold-cache",
        0,
        start,
        start + timedelta(days=1),
        start + timedelta(days=1),
        start + timedelta(days=2),
        start + timedelta(days=2),
        start + timedelta(days=3),
        start + timedelta(days=3),
        start + timedelta(days=4),
    )

    def table(offset: int, rows: int = 6) -> pa.Table:
        times = [start + timedelta(minutes=5 * (offset + index)) for index in range(rows)]
        return pa.table(
            {
                "symbol": ["BTCUSDT", "HNTUSDT"] * (rows // 2),
                "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
                "entry_time": pa.array(
                    [item + timedelta(minutes=5) for item in times],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "label_end_time": pa.array(
                    [item + timedelta(minutes=65) for item in times],
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "horizon_minutes": [60] * rows,
                "cross_sectional_context_scope": ["FOLD_ACTIVE_SYMBOLS"] * rows,
                "f1": np.linspace(0.0, 1.0, rows),
                "raw_future_return": np.linspace(-0.1, 0.1, rows),
            }
        )

    train, validation, cal_a, cal_b, test = [table(index * 10) for index in range(5)]
    fold = MultiAssetFoldData(
        plan=plan,
        train=train,
        validation=validation,
        calibration_a=cal_a,
        calibration_b=cal_b,
        _test=test,
        eligibility_manifest={
            "fold_id": plan.fold_id,
            "fold_membership_hash": "members",
            "eligible_symbols": ["BTCUSDT", "HNTUSDT"],
        },
        cluster_mapping={"BTCUSDT": 0, "HNTUSDT": 1},
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY", "HNTUSDT": "LOWER_LIQUIDITY"},
        age_buckets={"BTCUSDT": "MATURE", "HNTUSDT": "YOUNG"},
        research_view="CORE",
        report={"status": "fixture"},
    )
    inputs = prepare_architecture_inputs(
        train,
        validation,
        feature_columns=("f1",),
        target_column="raw_future_return",
        eligibility_calibration_a=cal_a,
    )
    prepared = PreparedTrainingSegments(
        plan.fold_id,
        "CORE",
        ("f1",),
        "raw_future_return",
        train,
        validation,
        cal_a,
        cal_b,
        inputs,
    )
    identity: dict[str, object] = {
        "gold_dataset_id": "gold-fixture",
        "gold_manifest_sha256": "gold-sha",
        "gold_partition_manifest_sha256": "partitions-sha",
        "configuration_hash": "config",
        "source_fingerprint": "source",
        "fold_id": plan.fold_id,
        "research_view": "CORE",
        "horizon_minutes": 60,
        "target_type": "raw",
        "target_column": "raw_future_return",
        "feature_group": "A6",
        "feature_columns": ["f1"],
        "fold_membership_hash": "members",
        "universe_hash": "universe",
        "purge": "actual_label_end_time",
        "embargo_minutes": 120,
        "preprocessing_version": PREPROCESSING_VERSION,
        "feature_version": "features",
        "target_version": "targets",
        "matrix_dtype": "float64",
        "matrix_code_identity": "code",
    }
    return plan, fold, prepared, identity


def test_prepared_cache_atomic_round_trip_and_memmap(tmp_path: Path) -> None:
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    path = cache.write(identity, fold, prepared)
    assert path is not None and (path / "CACHE_COMPLETE").is_file()
    assert not list(tmp_path.glob(".*.tmp.*"))
    loaded = cache.load(identity, plan)
    assert isinstance(loaded.prepared.model_inputs.train_x, np.memmap)
    assert loaded.prepared.model_inputs.train_x.dtype == np.float64
    assert np.array_equal(loaded.prepared.model_inputs.train_x, prepared.model_inputs.train_x)
    assert loaded.fold.eligibility_manifest == fold.eligibility_manifest


def test_prepared_cache_rejects_corruption(tmp_path: Path) -> None:
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    path = cache.write(identity, fold, prepared)
    assert path is not None
    with (path / "train_x.npy").open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(PreparedCacheMissError, match="quarantined"):
        cache.load(identity, plan)
    assert not path.exists()
    assert list(tmp_path.glob(".*.invalid.*"))
    rebuilt = cache.write(identity, fold, prepared)
    assert rebuilt is not None
    assert cache.load(identity, plan).cache_id == rebuilt.name


def test_prepared_cache_identity_mismatch_is_a_miss(tmp_path: Path) -> None:
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    cache.write(identity, fold, prepared)
    changed = {**identity, "configuration_hash": "different"}
    with pytest.raises(PreparedCacheMissError):
        cache.load(changed, plan)


def test_read_only_cache_fails_when_absent(tmp_path: Path) -> None:
    plan, _, _, identity = _fixture()
    with pytest.raises(PreparedCacheReadOnlyError, match="read_only"):
        PreparedDataCache(tmp_path, "read_only").load(identity, plan)


def test_read_only_cache_never_rebuilds_invalid_content(tmp_path: Path) -> None:
    plan, fold, prepared, identity = _fixture()
    path = PreparedDataCache(tmp_path, "auto").write(identity, fold, prepared)
    assert path is not None
    (path / "CACHE_COMPLETE").write_text("wrong\n", encoding="ascii")
    cache = PreparedDataCache(tmp_path, "read_only")
    with pytest.raises(PreparedCacheReadOnlyError, match="invalid"):
        cache.load(identity, plan)
    with pytest.raises(PreparedCacheReadOnlyError, match="forbids"):
        cache.write(identity, fold, prepared)
    assert path.exists()
    assert not list(tmp_path.glob(".*.invalid.*"))


def test_rebuild_mode_replaces_valid_cache_and_disabled_mode_writes_nothing(
    tmp_path: Path,
) -> None:
    plan, fold, prepared, identity = _fixture()
    auto = PreparedDataCache(tmp_path, "auto")
    original = auto.write(identity, fold, prepared)
    assert original is not None
    with pytest.raises(PreparedCacheMissError):
        PreparedDataCache(tmp_path, "rebuild").load(identity, plan)
    rebuilt = PreparedDataCache(tmp_path, "rebuild").write(identity, fold, prepared)
    assert rebuilt == original
    assert auto.load(identity, plan).cache_id == original.name

    disabled_root = tmp_path / "disabled"
    assert PreparedDataCache(disabled_root, "disabled").write(identity, fold, prepared) is None
    assert not disabled_root.exists()


def test_cache_capacity_is_reported_and_fails_without_eviction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fold, prepared, identity = _fixture()
    monkeypatch.setenv("PHASE7_CACHE_MAX_GB", "0.000000001")
    cache = PreparedDataCache(tmp_path, "auto")
    with pytest.raises(PreparedCacheCapacityError, match="would exceed"):
        cache.write(identity, fold, prepared)
    assert cache_size_report(tmp_path)["entry_count"] == 0
    assert not list(tmp_path.glob(".*.tmp.*"))


def test_explicit_cleanup_refuses_referenced_cache_and_removes_only_named_entry(
    tmp_path: Path,
) -> None:
    _, fold, prepared, identity = _fixture()
    cache_root = tmp_path / "cache"
    path = PreparedDataCache(cache_root, "auto").write(identity, fold, prepared)
    assert path is not None
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    report = artifacts / "report.json"
    report.write_text(
        '{"prepared_cache_id": "' + path.name + '"}\n',
        encoding="utf-8",
    )
    assert path.name in referenced_cache_ids(artifacts)
    with pytest.raises(PreparedCacheReadOnlyError, match="referenced"):
        cleanup_cache_entries(cache_root, (path.name,), reference_roots=(artifacts,), offline=True)
    assert path.exists()

    report.unlink()
    assert cleanup_cache_entries(
        cache_root, (path.name, path.name), reference_roots=(artifacts,), offline=True
    ) == [path.name]
    assert not path.exists()


def test_cleanup_requires_offline_mode_and_valid_reference_roots(tmp_path: Path) -> None:
    _, fold, prepared, identity = _fixture()
    path = PreparedDataCache(tmp_path, "auto").write(identity, fold, prepared)
    assert path is not None
    with pytest.raises(PreparedCacheReadOnlyError, match="offline"):
        cleanup_cache_entries(tmp_path, (path.name,), reference_roots=())
    assert path.exists()


def test_cache_concurrent_publication_accepts_only_a_valid_winner(tmp_path: Path) -> None:
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(cache.write, identity, fold, prepared) for _ in range(2)]
        assert futures[0].result() == futures[1].result()
    assert np.array_equal(
        cache.load(identity, plan).prepared.model_inputs.train_x, prepared.model_inputs.train_x
    )
    assert not list(tmp_path.glob(".*.tmp.*"))
    assert not list(tmp_path.glob("*.lock"))


@pytest.mark.parametrize("bad_manifest", [[], {"files": None}])
def test_auto_cache_quarantines_malformed_manifest_types(
    tmp_path: Path, bad_manifest: object
) -> None:
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    path = cache.write(identity, fold, prepared)
    assert path is not None
    manifest = path / "manifest.json"
    manifest.write_text(json.dumps(bad_manifest), encoding="utf-8")
    (path / "CACHE_COMPLETE").write_text(file_sha256(manifest), encoding="ascii")
    with pytest.raises(PreparedCacheMissError, match="quarantined"):
        cache.load(identity, plan)
    assert not path.exists()
    assert cache.write(identity, fold, prepared) is not None


def test_cleanup_cannot_delete_a_referenced_entry_through_an_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, fold, prepared, identity = _fixture()
    cache_root = tmp_path / "cache"
    actual = PreparedDataCache(cache_root, "auto").write(identity, fold, prepared)
    assert actual is not None
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "report.json").write_text(
        json.dumps({"prepared_cache_id": actual.name}), encoding="utf-8"
    )
    alias_id = "f" * 64
    alias = cache_root / alias_id
    original_resolve = Path.resolve

    def simulate_alias(path: Path, *args: object, **kwargs: object) -> Path:
        return actual if path == alias else original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulate_alias)
    with pytest.raises(ValueError, match="aliased"):
        cleanup_cache_entries(cache_root, (alias_id,), reference_roots=(artifacts,), offline=True)
    assert actual.exists()
