"""The opt-in low-memory profile must be output-identical to the standard Phase 7 path.

ADDED BY CLAUDE (2026-11-13). Every comparison below is exact: schema, row order, values
(bitwise for floats, NaN included), purge/embargo reports, matrices, cache file bytes and model
predictions. The standard path is the reference and is not modified by this profile.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from crypto_ai.phase5.config import CalibrationConfig, ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase5.folds import slice_hardened_fold as phase5_slice
from crypto_ai.phase7 import low_memory, staged_fold, training
from crypto_ai.phase7.config import CostConfig, FeatureConfig, ModelConfig, Phase7Config
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import (
    fixture_universe_config,
    synthetic_candles,
    synthetic_descriptors,
    synthetic_registry,
)
from crypto_ai.phase7.folds import _filter_symbols, slice_multiasset_fold
from crypto_ai.phase7.gold import build_multiasset_gold, feature_ablation_sets
from crypto_ai.phase7.low_memory_validation import _differences, prepared_digest
from crypto_ai.phase7.models import _floats, _matrix, fit_architecture
from crypto_ai.phase7.prepared_cache import PreparedDataCache
from crypto_ai.phase7.targets import generate_multiasset_targets
from crypto_ai.phase7.universe import build_expansion_policy, select_core_universe

START = datetime(2022, 3, 28, tzinfo=UTC)
PLAN = FoldPlan(
    fold_id="fold-low-memory-equivalence",
    index=0,
    train_start=START,
    train_end=datetime(2022, 4, 1, tzinfo=UTC),
    validation_start=datetime(2022, 4, 1, tzinfo=UTC),
    validation_end=datetime(2022, 4, 1, 18, tzinfo=UTC),
    calibration_start=datetime(2022, 4, 1, 18, tzinfo=UTC),
    calibration_end=datetime(2022, 4, 2, 12, tzinfo=UTC),
    test_start=datetime(2022, 4, 2, 12, tzinfo=UTC),
    test_end=datetime(2022, 4, 3, 6, tzinfo=UTC),
)


def _config() -> Phase7Config:
    return Phase7Config(
        features=FeatureConfig(
            correlation_window_rows=24,
            liquidity_window_rows=24,
            volatility_window_rows=24,
            daily_volatility_rows=24,
            seven_day_volatility_rows=48,
            include_12h=False,
            include_1d=False,
            include_derivatives=False,
        ),
        models=ModelConfig(
            cluster_count=3,
            minimum_train_rows_per_coin=100,
            minimum_validation_rows_per_coin=20,
            minimum_calibration_rows_per_coin=20,
            n_estimators=20,
            early_stopping_rounds=5,
            min_child_samples=5,
        ),
        calibration=CalibrationConfig(minimum_samples=20, reliability_buckets=5),
        costs=CostConfig(minimum_calibration_trades=1),
        schedule=ScheduleConfig(embargo_minutes=120, minimum_rows_per_segment=100),
    )


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("low-memory-world")
    config = _config()
    candles = synthetic_candles(rows_per_symbol=1_800, start=START)
    registry = synthetic_registry()
    features = generate_multiasset_features(candles, registry=registry, config=config.features)
    targets = generate_multiasset_targets(
        candles, features.table, config=config.targets, research_cutoff=config.research_cutoff
    )
    universe_config = fixture_universe_config()
    descriptors = synthetic_descriptors(as_of=universe_config.selection_cutoff)
    universe = select_core_universe(
        registry,
        descriptors,
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    gold = build_multiasset_gold(
        features,
        targets,
        output_root=root / "gold",
        universe_version=universe.version,
        universe_hash=universe.universe_hash,
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        research_cutoff=config.research_cutoff,
        prospective_holdout_start=config.prospective_holdout_start,
        lineage={"fixture": "low-memory-equivalence"},
    )
    paths = [str(path) for path in gold.partition_paths]
    table = pa.concat_tables([pq.ParquetFile(path).read() for path in paths])
    a6 = feature_ablation_sets(
        tuple(
            name
            for name in table.column_names
            if pa.types.is_floating(table.schema.field(name).type)
        )
    )["A6"]
    # The fixture has no derivative data, so those A6 columns are entirely null; keep every
    # column that has at least one finite value so the finite filter has real (warm-up) gaps.
    feature_columns = tuple(name for name in a6 if pc.sum(pc.is_finite(table[name])).as_py())
    assert len(feature_columns) >= 40
    return {
        "root": root,
        "config": config,
        "registry": registry,
        "descriptors": descriptors,
        "universe": universe,
        "universe_config": universe_config,
        "expansion": build_expansion_policy(universe, universe_config),
        "paths": paths,
        "table": table,
        "feature_columns": feature_columns,
    }


def _column_digest(column: pa.ChunkedArray | pa.Array) -> str:
    array = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    if pa.types.is_timestamp(array.type):
        payload = array.cast(pa.int64()).to_numpy(zero_copy_only=False).tobytes()
    elif pa.types.is_floating(array.type) or pa.types.is_integer(array.type):
        payload = (
            array.to_numpy(zero_copy_only=False).tobytes()
            + array.is_null().to_numpy(zero_copy_only=False).tobytes()
        )
    else:
        payload = json.dumps(array.to_pylist(), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def assert_tables_identical(left: pa.Table, right: pa.Table) -> None:
    assert left.schema == right.schema
    assert left.num_rows == right.num_rows
    for name in left.column_names:
        assert _column_digest(left.column(name)) == _column_digest(right.column(name)), name


@pytest.fixture
def low_memory_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    yield
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)


def test_profile_defaults_to_standard_and_rejects_unknown_values() -> None:
    assert low_memory.memory_profile({}) == "standard"
    assert low_memory.enabled({}) is False
    assert low_memory.enabled({low_memory.PROFILE_ENV: "low_memory"}) is True
    with pytest.raises(ValueError, match="UNKNOWN_MEMORY_PROFILE"):
        low_memory.memory_profile({low_memory.PROFILE_ENV: "tiny"})


@pytest.mark.parametrize(
    "pattern", ["all", "none", "prefix", "suffix", "middle", "scattered", "nulls"]
)
def test_filter_rows_matches_table_filter(world: dict, pattern: str) -> None:
    table = world["table"]
    rows = table.num_rows
    rng = np.random.default_rng(11)
    mask = {
        "all": np.ones(rows, dtype=bool),
        "none": np.zeros(rows, dtype=bool),
        "prefix": np.arange(rows) < rows // 3,
        "suffix": np.arange(rows) >= rows // 2,
        "middle": (np.arange(rows) >= 100) & (np.arange(rows) < rows - 100),
        "scattered": rng.random(rows) < 0.7,
    }.get(pattern)
    if pattern == "nulls":
        arrow_mask = pa.array([None if i % 5 == 0 else bool(i % 2) for i in range(rows)])
        assert_tables_identical(table.filter(arrow_mask), low_memory.filter_rows(table, arrow_mask))
        return
    assert_tables_identical(table.filter(pa.array(mask)), low_memory.filter_rows(table, mask))


def test_symbol_filter_matches_standard(world: dict, low_memory_profile: None) -> None:
    table = world["table"]
    symbols = sorted(set(pc.unique(table["symbol"]).to_pylist()))
    for subset in (set(symbols), set(symbols[:2]), {symbols[-1]}, set()):
        expected = table.filter(
            pa.array([value in subset for value in table["symbol"].to_pylist()])
        )
        assert_tables_identical(expected, _filter_symbols(table, subset))


@pytest.mark.parametrize("embargo", [0, 120])
@pytest.mark.parametrize("order", ["sorted", "shuffled"])
def test_zero_copy_slicer_matches_phase5(world: dict, embargo: int, order: str) -> None:
    table = world["table"].filter(pc.equal(world["table"]["horizon_minutes"], 60))
    table = table.sort_by([("feature_time", "ascending"), ("symbol", "ascending")])
    if order == "shuffled":
        table = table.take(pa.array(np.random.default_rng(5).permutation(table.num_rows)))
    schedule = ScheduleConfig(embargo_minutes=embargo, minimum_rows_per_segment=100)
    holdout = world["config"].prospective_holdout_start
    expected = phase5_slice(table, PLAN, schedule, holdout)
    actual = low_memory.slice_hardened_fold(table, PLAN, schedule, holdout)
    assert actual.report == expected.report
    for name in ("train", "validation", "calibration_a", "calibration_b", "_test"):
        assert_tables_identical(getattr(expected, name), getattr(actual, name))


def test_column_group_fold_read_matches_single_table_read(
    world: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = ds.dataset(world["paths"], format="parquet", partitioning="hive")
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)
    expected = training._load_fold_rows({}, PLAN, 60, dataset=dataset)
    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    for group_size in (1, 7, 16, 1000):
        monkeypatch.setattr(low_memory, "COLUMN_GROUP_SIZE", group_size)
        actual = low_memory.read_sorted_fold_rows(
            dataset,
            _fold_condition(dataset),
            None,
            group_size=group_size,
        )
        assert_tables_identical(expected, actual)
    assert_tables_identical(expected, training._load_fold_rows({}, PLAN, 60, dataset=dataset))


def _fold_condition(dataset: ds.Dataset) -> ds.Expression:
    condition = (
        (ds.field("feature_time") >= pa.scalar(PLAN.train_start))
        & (ds.field("feature_time") < pa.scalar(PLAN.test_end))
        & (ds.field("horizon_minutes") == 60)
    )
    if "year" in dataset.schema.names:
        condition = (ds.field("year") >= 2022) & (ds.field("year") <= 2022) & condition
    return condition


def test_row_block_memmap_matrix_is_identical_and_np_save_compatible(
    world: dict, tmp_path: Path
) -> None:
    table = world["table"].slice(0, 5_000)
    columns = world["feature_columns"]
    finite = training._finite(table, columns, "raw_future_return")
    expected = _matrix(finite, columns)
    for block_rows in (1, 333, 4096, 1_000_000):
        matrix = low_memory.build_matrix(
            finite, columns, tmp_path / f"blocks-{block_rows}", _floats, block_rows=block_rows
        )
        assert matrix.dtype == np.float64
        assert np.array_equal(np.asarray(matrix), expected)
        reference = tmp_path / f"np-save-{block_rows}.npy"
        np.save(reference, expected, allow_pickle=False)
        assert Path(matrix.filename).read_bytes() == reference.read_bytes()


def test_build_matrix_rejects_non_finite_values(world: dict, tmp_path: Path) -> None:
    table = world["table"].slice(0, 500)
    columns = world["feature_columns"]
    if all(pc.all(pc.is_finite(table[name])).as_py() for name in columns):
        pytest.skip("fixture slice has no non-finite feature")
    with pytest.raises(ValueError, match="finite matrix"):
        low_memory.build_matrix(table, columns, tmp_path, _floats)


def _context_source(world: dict) -> pa.Table:
    """All-horizon feature-only source, as the production sidecar provides (M-01)."""

    from crypto_ai.phase7.features import FOLD_CONTEXT_SOURCE_COLUMNS

    return world["table"].select(list(FOLD_CONTEXT_SOURCE_COLUMNS))


def _slice(world: dict, staged_window: timedelta | None = None):
    config = world["config"]
    common = {
        "registry": world["registry"],
        "universe": world["universe"],
        "expansion_policy": world["expansion"],
        "research_view": "CORE",
        "descriptors": world["descriptors"],
        "universe_config": world["universe_config"],
        "schedule": config.schedule,
        "holdout_start": config.prospective_holdout_start,
        "cluster_count": config.models.cluster_count,
        "seed": config.models.seed,
    }
    if staged_window is not None:
        dataset = ds.dataset(world["paths"], format="parquet", partitioning="hive")
        return staged_fold.slice_fold_staged(
            dataset,
            PLAN,
            60,
            context_source=_context_source(world),
            window=staged_window,
            directory=low_memory.active_spill_directory(),
            **common,
        )
    # Exactly the production read (hive dataset, year partition column, sorted), per profile.
    dataset = ds.dataset(world["paths"], format="parquet", partitioning="hive")
    table = training._load_fold_rows({}, PLAN, 60, dataset=dataset)
    fold = slice_multiasset_fold(table, PLAN, context_source=_context_source(world), **common)
    return low_memory.spill_fold(fold)


def _prepare(
    world: dict, cache_root: Path, *, fit: bool, staged_window: timedelta | None = None
) -> dict:
    config = world["config"]
    fold = _slice(world, staged_window)
    prepared = training._prepare_training_segments(
        fold, world["feature_columns"], "raw_future_return"
    )
    uncached = prepared_digest(fold, prepared)
    identity = {
        "test": "low-memory-equivalence",
        "feature_columns": list(world["feature_columns"]),
        "target_column": "raw_future_return",
        "research_view": "CORE",
        "fold_membership_hash": fold.eligibility_manifest["fold_membership_hash"],
    }
    cache = PreparedDataCache(cache_root, "rebuild")
    path = cache.write(identity, fold, prepared)
    files = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.name != "manifest.json" and item.name != "CACHE_COMPLETE"
    }
    loaded = PreparedDataCache(cache_root, "read_only").load(identity, PLAN)
    predictions = None
    if fit:
        model = fit_architecture(
            "G0",
            loaded.prepared.train,
            loaded.prepared.validation,
            feature_columns=world["feature_columns"],
            target_column="raw_future_return",
            config=config.models,
            model_threads=1,
            cluster_mapping=loaded.fold.cluster_mapping,
            eligibility_calibration_a=loaded.prepared.calibration_a,
            prepared_inputs=loaded.prepared.model_inputs,
        )
        predictions = {}
        for name in ("calibration_a", "calibration_b"):
            raw, covered = model.predict(getattr(loaded.prepared, name))
            predictions[name] = hashlib.sha256(
                np.asarray(raw, dtype=np.float64).tobytes() + np.asarray(covered).tobytes()
            ).hexdigest()
    assert prepared.train.num_rows > 1_000 and prepared.validation.num_rows > 100
    assert prepared.train.num_rows < fold.train.num_rows, "finite filter must drop warm-up rows"
    return {
        "fold": fold,
        "prepared": prepared,
        "files": files,
        "report": fold.report,
        "eligibility": fold.eligibility_manifest,
        "predictions": predictions,
        "uncached_digest": uncached,
        "reloaded_digest": prepared_digest(loaded.fold, loaded.prepared),
    }


def _assert_same_preparation(standard: dict, other: dict) -> None:
    assert other["report"] == standard["report"]
    assert other["eligibility"] == standard["eligibility"]
    for name in ("train", "validation", "calibration_a", "calibration_b"):
        assert_tables_identical(
            getattr(standard["prepared"], name), getattr(other["prepared"], name)
        )
    assert_tables_identical(standard["fold"]._test, other["fold"]._test)
    for name in ("train_x", "validation_x", "train_y", "validation_y"):
        assert np.array_equal(
            getattr(standard["prepared"].model_inputs, name),
            np.asarray(getattr(other["prepared"].model_inputs, name)),
        )
    assert _differences(standard["uncached_digest"], other["uncached_digest"]) == []
    assert _differences(other["uncached_digest"], other["reloaded_digest"]) == []


def test_low_memory_preparation_and_cache_bytes_are_identical_without_fitting(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)
    standard = _prepare(world, tmp_path / "standard-cache", fit=False)
    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    with low_memory.spill_session(tmp_path / "low-cache") as spill:
        assert spill is not None and spill.is_dir()
        low = _prepare(world, tmp_path / "low-cache", fit=False)
        assert isinstance(low["prepared"].model_inputs.train_x, np.memmap)
    assert not spill.exists(), "spill directory must be removed when the session ends"
    assert low["files"] == standard["files"], "cache file bytes differ"
    _assert_same_preparation(standard, low)


@pytest.mark.model_fit
def test_end_to_end_preparation_cache_and_fit_are_identical(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)
    standard = _prepare(world, tmp_path / "standard-cache", fit=True)
    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    with low_memory.spill_session(tmp_path / "low-cache"):
        low = _prepare(world, tmp_path / "low-cache", fit=True)
    assert low["files"] == standard["files"], "cache file bytes differ"
    assert low["predictions"] == standard["predictions"]
    _assert_same_preparation(standard, low)


@pytest.mark.parametrize(
    "window",
    [
        timedelta(hours=5),
        timedelta(days=1),
        timedelta(days=3),
        timedelta(days=7),
        timedelta(days=30),
    ],
)
def test_batch_staged_preparation_equals_standard_without_fitting(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: timedelta
) -> None:
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)
    monkeypatch.delenv(staged_fold.STAGING_ENV, raising=False)
    standard = _prepare(world, tmp_path / "standard-cache", fit=False)
    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    monkeypatch.setenv(staged_fold.STAGING_ENV, "7")
    with low_memory.spill_session(tmp_path / "staged-cache"):
        staged = _prepare(world, tmp_path / "staged-cache", fit=False, staged_window=window)
        assert staged["fold"].train.column("symbol").num_chunks >= 1
    _assert_same_preparation(standard, staged)
    # Matrices are byte-identical files; Arrow tables are logically identical (batch layout may
    # differ because staged segments are appended per window).
    for name in ("train_x.npy", "validation_x.npy", "train_y.npy", "validation_y.npy"):
        assert staged["files"][name] == standard["files"][name]


def test_staging_windows_partition_the_fold_and_cut_at_year_boundaries() -> None:
    plan = FoldPlan(
        fold_id="fold-window-check",
        index=0,
        train_start=datetime(2020, 12, 20, tzinfo=UTC),
        train_end=datetime(2021, 1, 10, tzinfo=UTC),
        validation_start=datetime(2021, 1, 10, tzinfo=UTC),
        validation_end=datetime(2021, 1, 12, tzinfo=UTC),
        calibration_start=datetime(2021, 1, 12, tzinfo=UTC),
        calibration_end=datetime(2021, 1, 14, tzinfo=UTC),
        test_start=datetime(2021, 1, 14, tzinfo=UTC),
        test_end=datetime(2021, 1, 20, tzinfo=UTC),
    )
    for days in staged_fold.SUPPORTED_STAGING_DAYS:
        parts = staged_fold.windows(plan, timedelta(days=days))
        assert parts[0][0] == plan.train_start and parts[-1][1] == plan.test_end
        assert all(a[1] == b[0] for a, b in zip(parts, parts[1:], strict=False))
        assert all(
            start < end and start.year == (end - timedelta(microseconds=1)).year
            for start, end in parts
        )
        assert datetime(2021, 1, 1, tzinfo=UTC) in {start for start, _ in parts}


def test_staging_configuration_is_explicit_and_bounded() -> None:
    assert staged_fold.staging_days({}) is None
    with pytest.raises(ValueError, match="requires PHASE7_MEMORY_PROFILE=low_memory"):
        staged_fold.staging_days({staged_fold.STAGING_ENV: "7"})
    low = {low_memory.PROFILE_ENV: "low_memory"}
    assert staged_fold.staging_days({**low, staged_fold.STAGING_ENV: "14"}) == 14
    for bad in ("0", "2", "365", "seven"):
        with pytest.raises(ValueError):
            staged_fold.staging_days({**low, staged_fold.STAGING_ENV: bad})


def test_streamed_filter_matches_table_filter(world: dict, tmp_path: Path) -> None:
    table = world["table"]
    mask = np.random.default_rng(3).random(table.num_rows) < 0.6
    streamed = low_memory.stream_filter_to_file(table, mask, tmp_path, block_rows=777)
    assert_tables_identical(table.filter(pa.array(mask)), streamed)
    empty = low_memory.stream_filter_to_file(table, np.zeros(table.num_rows, bool), tmp_path)
    assert empty.num_rows == 0 and empty.schema == table.schema


def test_standard_profile_never_spills_or_memmaps(world: dict, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(low_memory.PROFILE_ENV, raising=False)
    with low_memory.spill_session(tmp_path) as spill:
        assert spill is None
        assert low_memory.active_spill_directory() is None
        assert low_memory.matrix_storage_directory() is None
    assert not any(tmp_path.iterdir())


def test_stale_spill_directories_of_dead_processes_are_removed(tmp_path: Path) -> None:
    import os

    stale = tmp_path / f"{low_memory.SPILL_DIRECTORY_PREFIX}999999-dead"
    stale.mkdir()
    (stale / "OWNER.json").write_text(
        json.dumps({"pid": 2**22 + 12345, "host": os.uname().nodename}), encoding="utf-8"
    )
    live = tmp_path / f"{low_memory.SPILL_DIRECTORY_PREFIX}live"
    live.mkdir()
    (live / "OWNER.json").write_text(
        json.dumps({"pid": os.getpid(), "host": os.uname().nodename}), encoding="utf-8"
    )
    assert low_memory.remove_stale_spill_directories(tmp_path) == [stale.name]
    assert live.exists() and not stale.exists()


def test_prepared_digest_matches_after_read_only_reload_and_detects_changes(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from crypto_ai.phase7.low_memory_validation import _differences, prepared_digest

    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    with low_memory.spill_session(tmp_path / "cache"):
        result = _prepare(world, tmp_path / "cache", fit=False)
        uncached = prepared_digest(result["fold"], result["prepared"])
        cache_dir = next(p for p in (tmp_path / "cache").iterdir() if len(p.name) == 64)
        identity = json.loads((cache_dir / "manifest.json").read_text())["identity"]
        loaded = PreparedDataCache(tmp_path / "cache", "read_only").load(identity, PLAN)
        assert _differences(uncached, prepared_digest(loaded.fold, loaded.prepared)) == []
        altered = loaded.prepared.model_inputs.train_x.copy()
        altered[0, 0] = np.nextafter(altered[0, 0], np.inf)
        changed = prepared_digest(
            loaded.fold,
            type(loaded.prepared)(
                **{
                    **{name: getattr(loaded.prepared, name) for name in loaded.prepared.__slots__},
                    "model_inputs": type(loaded.prepared.model_inputs)(
                        **{
                            **{
                                name: getattr(loaded.prepared.model_inputs, name)
                                for name in loaded.prepared.model_inputs.__slots__
                            },
                            "train_x": altered,
                        }
                    ),
                }
            ),
        )
        assert _differences(uncached, changed) == ["/arrays/train_x/sha256"]


def test_chronology_checks_pass_on_reloaded_fixture_and_detect_leakage(
    world: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from crypto_ai.phase7.low_memory_validation import chronology_checks

    monkeypatch.setenv(low_memory.PROFILE_ENV, low_memory.LOW_MEMORY)
    with low_memory.spill_session(tmp_path / "cache"):
        fold = _slice(world)
        checks = chronology_checks(fold, world["config"])
        assert checks["all_passed"] is True, checks
        leaked = replace(fold, train=pa.concat_tables([fold.train, fold.validation.slice(0, 5)]))
        bad = chronology_checks(leaked, world["config"])
        assert bad["all_passed"] is False
        assert bad["train"]["inside_segment"] is False
