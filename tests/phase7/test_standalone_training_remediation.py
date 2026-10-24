from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7 import environment, models, pipeline, preflight, training
from crypto_ai.phase7.config import CostConfig, ModelConfig, load_phase7_config
from crypto_ai.phase7.economics import (
    COST_POLICY_VERSION,
    ThresholdSet,
    build_oos_trades,
    select_cal_b_thresholds,
)
from crypto_ai.phase7.runtime import RuntimePaths
from crypto_ai.phase7.training_metrics import (
    FitMetricObserver,
    TrainingMetricScope,
    training_metric_scope,
)


def _signals(rows=36, *, spacing=5, symbols=("BTCUSDT",)):
    start = datetime(2022, 5, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=spacing * i) for i in range(rows) for _ in symbols]
    return pa.table(
        {
            "symbol": list(symbols) * rows,
            "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
            "entry_time": pa.array(
                [t + timedelta(minutes=5) for t in times], type=pa.timestamp("us", tz="UTC")
            ),
            "label_end_time": pa.array(
                [t + timedelta(minutes=65) for t in times], type=pa.timestamp("us", tz="UTC")
            ),
            "raw_future_return": [0.02] * len(times),
        }
    )


@pytest.mark.parametrize("granularity", ["global", "cluster", "per_coin"])
def test_cal_b_counts_the_same_non_overlapping_trades_as_oos(granularity):
    table = _signals(symbols=("BTCUSDT", "ETHUSDT"))
    predicted = np.full(table.num_rows, 0.01)
    tiers = {"BTCUSDT": "HIGH_LIQUIDITY", "ETHUSDT": "HIGH_LIQUIDITY"}
    clusters = {"BTCUSDT": 0, "ETHUSDT": 1}
    config = CostConfig(minimum_calibration_trades=30)
    thresholds, report = select_cal_b_thresholds(
        table,
        predicted,
        target_column="raw_future_return",
        liquidity_tiers=tiers,
        cluster_mapping=clusters,
        granularity=granularity,
        config=config,
    )
    assert all(value is None for value in thresholds.values_bps.values())
    assert report["policy_version"] == COST_POLICY_VERSION
    for key, group in report["groups"].items():
        trades = build_oos_trades(
            table,
            predicted,
            ThresholdSet(granularity, {key: 2.0}),
            target_column="raw_future_return",
            liquidity_tiers=tiers,
            cluster_mapping=clusters,
            horizon_minutes=60,
            config=config,
        )
        assert group["candidates"][0]["trade_count"] == trades.num_rows
        assert trades.num_rows == (6 if granularity == "global" else 3)
        assert group["candidates"][0]["expectancy"] == pytest.approx(
            np.mean(trades["net_return"].to_numpy())
        )


def test_cal_b_adequate_nonoverlapping_trades_select_threshold_even_when_shuffled():
    table = _signals(spacing=60)
    table = table.take(pa.array(list(reversed(range(table.num_rows)))))
    thresholds, report = select_cal_b_thresholds(
        table,
        np.full(table.num_rows, 0.01),
        target_column="raw_future_return",
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
        cluster_mapping={},
        granularity="global",
        config=CostConfig(),
    )
    assert thresholds.values_bps == {"global": 10.0}
    assert {r["trade_count"] for r in report["groups"]["global"]["candidates"]} == {36}


@pytest.mark.parametrize("multiplier", [float("nan"), float("inf"), -1.0])
def test_cost_policy_rejects_nonfinite_or_negative_cost_stress(multiplier):
    table = _signals()
    with pytest.raises(ValueError, match="finite and non-negative"):
        build_oos_trades(
            table,
            np.full(table.num_rows, 0.01),
            ThresholdSet("global", {"global": 2.0}),
            target_column="raw_future_return",
            liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
            cluster_mapping={},
            horizon_minutes=60,
            config=CostConfig(),
            cost_multiplier=multiplier,
        )


def test_environment_change_invalidates_stage_resume_and_is_not_machine_specific(monkeypatch):
    before = training.training_stage_resume_identity()
    original_version = environment.version
    monkeypatch.setattr(
        environment,
        "version",
        lambda name: "different" if name == "numpy" else original_version(name),
    )
    after = training.training_stage_resume_identity()
    assert before != after
    with pytest.raises(ValueError, match="incompatible scientific identity"):
        training.validate_training_stage_resume({"scientific_resume_identity": before})
    assert not {"hostname", "cpu", "ram", "os"}.intersection(after["scientific_environment"])


def test_dependency_file_changes_invalidate_environment_without_editing_scientific_code(tmp_path):
    for name in ("uv.lock", "pyproject.toml"):
        (tmp_path / name).write_text("locked\n", encoding="utf-8")
    before = environment.scientific_environment_identity(tmp_path)
    (tmp_path / "uv.lock").write_text("changed\n", encoding="utf-8")
    assert environment.scientific_environment_identity(tmp_path) != before


def test_one_fold_descriptor_selection_is_equivalent_and_does_not_load_other_folds(monkeypatch):
    config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    folds = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )
    registry = SimpleNamespace(
        by_symbol=lambda: {
            "BTCUSDT": SimpleNamespace(
                causal_available_from=datetime(2019, 1, 1, tzinfo=UTC), available_until=None
            )
        }
    )
    data = {"candle_silver_manifests": {"1d": {"BTCUSDT": "synthetic-manifest"}}}
    calls = []
    monkeypatch.setattr(pipeline, "load_candle_family", lambda *_a, **kw: calls.append(kw))
    monkeypatch.setattr(
        pipeline, "build_point_in_time_descriptors", lambda *_a, **kw: [kw["as_of"]]
    )
    all_values = pipeline._fold_descriptors(config, registry, data)
    assert len(calls) == 16
    calls.clear()
    selected = pipeline._fold_descriptors(config, registry, data, fold_ids=(folds[0].fold_id,))
    assert selected == all_values[:1] and len(calls) == 1
    with pytest.raises(ValueError, match="canonical fold"):
        pipeline._fold_descriptors(config, registry, data, fold_ids=("unknown",))
    assert len(calls) == 1


@pytest.mark.parametrize("weighted", [False, True])
@pytest.mark.parametrize("early_stop", [False, True])
def test_fit_metrics_do_not_change_predictions_or_early_stopping(
    tmp_path, monkeypatch, weighted, early_stop
):
    # Tiny CPU unit fixture only; never scientific acquisition/training.
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    monkeypatch.setenv("PHASE7_METRICS_EVERY", "3")
    rng = np.random.default_rng(42)
    x = rng.normal(size=(240, 3))
    y = x[:, 0] * 0.01 + rng.normal(scale=0.001, size=240)
    if early_stop:
        y[180:] = -y[180:]
    config = ModelConfig(n_estimators=20, early_stopping_rounds=5, min_child_samples=5)
    arguments = dict(
        config=config,
        model_threads=1,
        sample_weight=np.linspace(0.2, 2.0, 180) if weighted else None,
    )
    reference = models._fit(x[:180], y[:180], x[180:], y[180:], **arguments)
    with training_metric_scope(tmp_path, fold_id="fixture", target_type="raw"):
        observed = models._fit(x[:180], y[:180], x[180:], y[180:], **arguments)
    assert reference.best_iteration_ == observed.best_iteration_
    if early_stop:
        assert observed.n_iter_ < config.n_estimators
    assert np.array_equal(reference.predict(x), observed.predict(x))
    records = [
        json.loads(line) for p in tmp_path.glob("*.jsonl") for line in p.read_text().splitlines()
    ]
    assert records[0]["event"] == "FIT_STARTED" and records[-1]["event"] == "FIT_FINISHED"
    rounds = [r for r in records if r["event"] == "FIT_METRICS"]
    assert rounds[0]["iteration"] == 1
    for row in rounds:
        assert set(row["metrics"]) == {"train", "validation"}
        assert {"l2", "mae", "rmse", "directional_accuracy"} <= set(row["metrics"]["validation"])
        assert row["test_access"] == "NOT_RELEASED_DURING_FIT"
    assert list(observed.evals_result_["validation"])[0] == "l2"


def test_fit_observer_rejects_test_metrics(tmp_path):
    observer = FitMetricObserver(TrainingMetricScope(tmp_path, {}), "fixture")
    with pytest.raises(ValueError, match="refuses"):
        observer(SimpleNamespace(evaluation_result_list=[("test", "l2", 0.1, False)]))


def test_partition_workers_inherit_fit_metric_scope(tmp_path, monkeypatch):
    from crypto_ai.phase7.training_metrics import fit_observer

    def fake_fit(*_a, **kw):
        observer = fit_observer(kw["estimator_key"])
        assert observer is not None
        return observer.estimator_key

    monkeypatch.setattr(models, "_fit", fake_fit)
    with training_metric_scope(tmp_path, fold_id="fixture"):
        result = models._fit_partitioned_estimators(
            [
                ("symbol:BTC", np.ones(2, dtype=bool), np.ones(2, dtype=bool), None),
                ("symbol:ETH", np.ones(2, dtype=bool), np.ones(2, dtype=bool), None),
            ],
            train_x=np.ones((2, 1)),
            train_y=np.ones(2),
            validation_x=np.ones((2, 1)),
            validation_y=np.ones(2),
            config=ModelConfig(),
            model_threads=1,
            estimator_workers=2,
        )
    assert result == {"symbol:BTC": "symbol:BTC", "symbol:ETH": "symbol:ETH"}
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


def test_preflight_never_claims_ready_without_explicit_ram_and_read_only_cache(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PHASE7_MIN_FREE_RAM_GIB", raising=False)
    monkeypatch.delenv("PHASE7_MIN_AVAILABLE_RAM_GB", raising=False)
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    monkeypatch.setattr(RuntimePaths, "validate", lambda *_a, **_kw: [])
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        preflight, "validate_gold_manifest", lambda *_a: (manifest, {"dataset_id": "fixture"}, [])
    )
    monkeypatch.setattr(preflight, "_validated_gold_report", lambda *_a, **_kw: {"status": "PASS"})
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_a: {"status": "PASS"})
    monkeypatch.setattr(preflight, "backend_metadata", lambda *_a: {"name": "cpu"})
    monkeypatch.setattr(preflight, "telemetry", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        preflight,
        "system_snapshot",
        lambda *_a: {
            "ram_available_bytes": 64 * 1024**3,
            "disk_free_bytes": 100 * 1024**3,
        },
    )
    config = Path("configs/phase7/research_core20_primary_v1.toml")
    report = preflight.build_preflight_report(config, gold_validation_report=manifest)
    assert report["training_readiness"] == "NOT_READY"
    assert any("workload floor" in e for e in report["blocking_errors"])
    assert any("read_only" in e for e in report["blocking_errors"])
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "8")
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    assert (
        preflight.build_preflight_report(config, gold_validation_report=manifest)["status"]
        == "PASS"
    )


def test_direct_training_cli_cannot_bypass_preflight_or_prepare_data(monkeypatch):
    import sys

    from crypto_ai.phase7.phase7a import pipeline_dispatcher

    dispatcher = pipeline_dispatcher()
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")  # Isolated startup test; no fit.
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    monkeypatch.delenv("PHASE7_MIN_FREE_RAM_GIB", raising=False)
    monkeypatch.delenv("PHASE7_MIN_AVAILABLE_RAM_GB", raising=False)
    monkeypatch.setattr(sys, "argv", ["phase7a", "--stage", "train", "--resume"])
    monkeypatch.setattr(dispatcher, "run_stage", lambda *_a, **_k: pytest.fail("training started"))
    calls = []
    monkeypatch.setattr(
        preflight,
        "build_preflight_report",
        lambda *_a, **_k: calls.append(1) or {"status": "FAIL", "blocking_errors": ["fixture"]},
    )
    with pytest.raises(ValueError, match="explicit positive"):
        dispatcher.main()
    assert not calls
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "8")
    with pytest.raises(RuntimeError, match="training preflight failed"):
        dispatcher.main()
    assert calls == [1]


def test_benchmark_rejects_missing_budget_before_gold_or_checkpoint_work(tmp_path, monkeypatch):
    import sys

    from crypto_ai.phase7 import benchmark_one_spec

    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    monkeypatch.delenv("PHASE7_MIN_FREE_RAM_GIB", raising=False)
    monkeypatch.delenv("PHASE7_MIN_AVAILABLE_RAM_GB", raising=False)
    monkeypatch.setattr(
        benchmark_one_spec, "validate_phase7_gold", lambda *_a: pytest.fail("Gold scanned")
    )
    output = tmp_path / "benchmark"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--spec-id",
            "architecture-G0-A6-60m-raw",
            "--output-root",
            str(output),
            "--execute",
        ],
    )
    with pytest.raises(ValueError, match="explicit positive"):
        benchmark_one_spec.main()
    assert not output.exists()


@pytest.mark.parametrize(
    "name", ["artifact_root", "cache_root", "model_root", "report_root", "log_root"]
)
def test_output_paths_cannot_write_into_protected_gold_or_silver(tmp_path, name):
    from dataclasses import replace

    from crypto_ai.phase7.config import PathConfig

    paths = RuntimePaths.resolve(PathConfig())
    protected = tmp_path / "immutable"
    protected.mkdir()
    sentinel = protected / "source.txt"
    sentinel.write_bytes(b"unchanged")
    paths = replace(paths, gold_root=protected, **{name: protected / "unsafe-output"})
    errors = paths.validate(require_gold=False, create_outputs=True)
    assert any("protected Gold/Silver" in e for e in errors)
    assert list(protected.iterdir()) == [sentinel] and sentinel.read_bytes() == b"unchanged"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "1.5"])
def test_invalid_metric_period_fails_before_any_model_work(monkeypatch, value):
    from crypto_ai.phase7.resources import require_training_runtime_contract

    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "8")
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    monkeypatch.setenv("PHASE7_METRICS_EVERY", value)
    with pytest.raises(ValueError):
        require_training_runtime_contract()


@pytest.mark.parametrize("last_iteration,expected", [(20, "ROUND_LIMIT"), (8, "EARLY_STOPPING")])
def test_fit_stop_reason_uses_observed_rounds_not_rolled_back_booster(
    tmp_path, last_iteration, expected
):
    observer = FitMetricObserver(TrainingMetricScope(tmp_path, {}), "fixture")
    observer.last = {"iteration": last_iteration, "round_limit": 20, "metrics": {}}
    observer.finish(SimpleNamespace(best_iteration_=3, best_score_={}, n_iter_=3, n_estimators=20))
    record = json.loads(observer.path.read_text().splitlines()[-1])
    assert record["stop_reason"] == expected
    assert record["best_iteration"] == 3


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, "2"])
def test_thresholds_reject_nonfinite_negative_or_untyped_values(value):
    with pytest.raises(ValueError, match="finite and non-negative"):
        ThresholdSet("global", {"global": value})


@pytest.mark.parametrize(
    "change", [{"granularity": "unknown"}, {"selection_source": "TEST"}, {"policy_version": "old"}]
)
def test_thresholds_reject_unknown_or_unowned_policy(change):
    with pytest.raises(ValueError, match="policy identity"):
        ThresholdSet(**({"granularity": "global", "values_bps": {"global": 2.0}} | change))


def test_trade_builder_revalidates_mutated_threshold_mapping():
    table = _signals()
    thresholds = ThresholdSet("global", {"global": 2.0})
    thresholds.values_bps["global"] = float("nan")
    with pytest.raises(ValueError, match="finite and non-negative"):
        build_oos_trades(
            table,
            np.full(table.num_rows, 0.01),
            thresholds,
            target_column="raw_future_return",
            liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
            cluster_mapping={},
            horizon_minutes=60,
            config=CostConfig(),
        )


@pytest.mark.parametrize("column", ["feature_time", "entry_time", "label_end_time"])
def test_cost_policy_refuses_missing_timing_instead_of_silent_nonoverlap_bypass(column):
    table = _signals()
    table = table.set_column(
        table.schema.get_field_index(column),
        column,
        pa.nulls(table.num_rows, type=table.schema.field(column).type),
    )
    with pytest.raises(ValueError, match="timestamp cannot be null"):
        select_cal_b_thresholds(
            table,
            np.full(table.num_rows, 0.01),
            target_column="raw_future_return",
            liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
            cluster_mapping={},
            granularity="global",
            config=CostConfig(),
        )
