from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_ai.phase5.config import CalibrationConfig, ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.artifacts import CheckpointStore
from crypto_ai.phase7.config import CostConfig, FeatureConfig, ModelConfig, Phase7Config
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import (
    fixture_universe_config,
    synthetic_candles,
    synthetic_descriptors,
    synthetic_registry,
)
from crypto_ai.phase7.folds import slice_multiasset_fold
from crypto_ai.phase7.gold import build_multiasset_gold
from crypto_ai.phase7.models import load_model
from crypto_ai.phase7.targets import generate_multiasset_targets
from crypto_ai.phase7.training import (
    ExperimentSpec,
    _run_one,
    _validate_complete_orphan_report,
)
from crypto_ai.phase7.universe import build_expansion_policy, select_core_universe


def _table_hash(table: pa.Table) -> str:
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()


def _fixture_config() -> Phase7Config:
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


def _build_fold(tmp_path: Path):
    config = _fixture_config()
    universe_config = fixture_universe_config()
    start = datetime(2022, 3, 28, tzinfo=UTC)
    candles = synthetic_candles(rows_per_symbol=1_800, start=start)
    features = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=config.features
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=config.targets,
        research_cutoff=config.research_cutoff,
    )
    registry = synthetic_registry()
    descriptors = synthetic_descriptors(as_of=universe_config.selection_cutoff)
    universe = select_core_universe(
        registry,
        descriptors,
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    expansion = build_expansion_policy(universe, universe_config)
    gold = build_multiasset_gold(
        features,
        targets,
        output_root=tmp_path / "gold",
        universe_version=universe.version,
        universe_hash=universe.universe_hash,
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        research_cutoff=config.research_cutoff,
        prospective_holdout_start=config.prospective_holdout_start,
        lineage={"fixture": "pretraining-integration"},
    )
    gold_table = pa.concat_tables([pq.ParquetFile(path).read() for path in gold.partition_paths])
    gold_60m = gold_table.filter(pa.compute.equal(gold_table["horizon_minutes"], 60))
    plan = FoldPlan(
        fold_id="fold-mini-integration",
        index=0,
        train_start=start,
        train_end=datetime(2022, 4, 1, tzinfo=UTC),
        validation_start=datetime(2022, 4, 1, tzinfo=UTC),
        validation_end=datetime(2022, 4, 1, 18, tzinfo=UTC),
        calibration_start=datetime(2022, 4, 1, 18, tzinfo=UTC),
        calibration_end=datetime(2022, 4, 2, 12, tzinfo=UTC),
        test_start=datetime(2022, 4, 2, 12, tzinfo=UTC),
        test_end=datetime(2022, 4, 3, 6, tzinfo=UTC),
    )
    fold = slice_multiasset_fold(
        gold_60m,
        plan,
        registry=registry,
        universe=universe,
        expansion_policy=expansion,
        research_view="CORE",
        descriptors=descriptors,
        universe_config=universe_config,
        schedule=config.schedule,
        holdout_start=config.prospective_holdout_start,
        cluster_count=config.models.cluster_count,
        seed=config.models.seed,
    )
    return config, features, targets, universe, plan, fold


def test_tiny_pipeline_connects_and_is_reproducible(tmp_path: Path) -> None:
    first = _build_fold(tmp_path / "first")
    second = _build_fold(tmp_path / "second")
    config, features, targets, universe, plan, fold = first
    _, features_2, targets_2, universe_2, plan_2, fold_2 = second

    assert _table_hash(features.table) == _table_hash(features_2.table)
    assert _table_hash(targets.table) == _table_hash(targets_2.table)
    assert plan.to_dict() == plan_2.to_dict()
    assert universe.universe_hash == universe_2.universe_hash
    assert (
        fold.eligibility_manifest["fold_membership_hash"]
        == (fold_2.eligibility_manifest["fold_membership_hash"])
    )
    for segment in (
        fold.train,
        fold.validation,
        fold.calibration_a,
        fold.calibration_b,
        fold.release_test(frozen_identity="integration-sentinel"),
    ):
        assert segment.num_rows > 0
        assert max(segment["label_end_time"].to_pylist()) < config.research_cutoff

    spec = ExperimentSpec(
        name="architecture-G0-A6-60m-raw",
        architecture="G0",
        feature_group="A6",
        horizon_minutes=60,
        target_type="raw",
        symbol_balanced=True,
    )
    identity = {"fixture": "pretraining-integration-v1"}
    reports = []
    stores = []
    for name, current_fold in (("run-a", fold), ("run-b", fold_2)):
        report, files = _run_one(
            spec,
            current_fold,
            ("return_5m", "range_pct"),
            config,
            tmp_path / name,
            identity,
        )
        store = CheckpointStore(tmp_path / "checkpoints", name)
        store.complete("train/fold-mini", files, identity)
        assert store.is_complete("train/fold-mini", expected_metadata=identity)
        assert report["status"] == "COMPLETE"
        assert report["test_used_for_selection"] is False
        reports.append(report)
        stores.append(store)

    assert reports[0] == reports[1]
    assert json.loads((tmp_path / "run-a" / "report.json").read_text()) == reports[0]

    model_path = tmp_path / "run-a" / "model.joblib"
    model = load_model(model_path)
    _validate_complete_orphan_report(reports[0], model)
    for missing_path in (
        ("calibrator_identity",),
        ("threshold_identity",),
        ("frozen_identity_components",),
        ("calibration", "selected"),
        ("thresholds",),
    ):
        malformed = deepcopy(reports[0])
        target = malformed
        for key in missing_path[:-1]:
            target = target[key]
        del target[missing_path[-1]]
        with pytest.raises(ValueError, match="missing frozen training artifacts"):
            _validate_complete_orphan_report(malformed, model)

    corrupted_calibrator = deepcopy(reports[0])
    corrupted_calibrator["calibration"]["selected"]["slope"] += 1.0
    with pytest.raises(ValueError, match="frozen training identity mismatch"):
        _validate_complete_orphan_report(corrupted_calibrator, model)
    corrupted_threshold = deepcopy(reports[0])
    corrupted_threshold["thresholds"]["values_bps"]["global"] = 999.0
    with pytest.raises(ValueError, match="frozen training identity mismatch"):
        _validate_complete_orphan_report(corrupted_threshold, model)

    model_path.write_bytes(b"corrupt-model-artifact")
    assert not stores[0].is_complete("train/fold-mini", expected_metadata=identity)
