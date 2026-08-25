from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import calibration_split_time, plan_folds, slice_hardened_fold
from crypto_ai.phase7.acquisition import acquire_candle_family
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json
from crypto_ai.phase7.config import FeatureConfig, ModelConfig, Phase7Config, UniverseConfig
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import (
    fixture_universe_config,
    synthetic_candles,
    synthetic_descriptors,
    synthetic_registry,
)
from crypto_ai.phase7.folds import (
    fit_train_only_liquidity_tiers,
    plan_multiasset_folds,
)
from crypto_ai.phase7.gold import build_multiasset_gold
from crypto_ai.phase7.metrics import cross_sectional_ic, evaluate_predictions
from crypto_ai.phase7.models import fit_architecture
from crypto_ai.phase7.pipeline import _gold_stage, run_phase7_cloud
from crypto_ai.phase7.quality import build_point_in_time_descriptors
from crypto_ai.phase7.registry import build_symbol_registry
from crypto_ai.phase7.runner import phase7_plan
from crypto_ai.phase7.targets import generate_multiasset_targets
from crypto_ai.phase7.training import run_phase7_training, summarize_fold_completion
from crypto_ai.phase7.universe import (
    EligibilityStatus,
    build_expansion_policy,
    fold_local_eligibility,
    select_pilot_universe,
)

RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
HOLDOUT_START = datetime(2026, 8, 1, tzinfo=UTC)


def _feature_config() -> FeatureConfig:
    return FeatureConfig(
        correlation_window_rows=24,
        liquidity_window_rows=24,
        volatility_window_rows=24,
        daily_volatility_rows=24,
        seven_day_volatility_rows=48,
        include_12h=False,
        include_1d=False,
        include_derivatives=False,
    )


def _times(table: pa.Table, column: str) -> np.ndarray:
    return table.column(column).combine_chunks().cast(pa.int64()).to_numpy()


def test_research_cutoff_excludes_july_and_august_from_gold(tmp_path: Path) -> None:
    june = synthetic_candles(
        rows_per_symbol=600,
        start=datetime(2026, 6, 29, tzinfo=UTC),
    )
    august = synthetic_candles(
        rows_per_symbol=40,
        start=HOLDOUT_START,
    )
    candles = pa.concat_tables([june, august]).sort_by(
        [("symbol", "ascending"), ("open_time", "ascending")]
    )
    features = generate_multiasset_features(
        candles,
        registry=synthetic_registry(),
        config=_feature_config(),
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=Phase7Config().targets,
        research_cutoff=RESEARCH_CUTOFF,
    )
    registry = synthetic_registry()
    result = build_multiasset_gold(
        features,
        targets,
        output_root=tmp_path,
        universe_version="universe_v1",
        universe_hash="audit-universe",
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        research_cutoff=RESEARCH_CUTOFF,
        prospective_holdout_start=HOLDOUT_START,
        lineage={"fixture": "boundary-audit"},
    )
    dataset = pa.concat_tables([pq.ParquetFile(path).read() for path in result.partition_paths])
    cutoff_us = int(RESEARCH_CUTOFF.timestamp() * 1_000_000)
    assert np.max(_times(dataset, "feature_time")) < cutoff_us
    assert np.max(_times(dataset, "label_end_time")) < cutoff_us
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["july_2026_used"] is False
    assert manifest["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert manifest["prospective_holdout_used"] is False
    assert manifest["prospective_holdout_evaluation_authorized"] is False


def test_universe_cutoff_is_first_train_end_and_fold_count_is_derived() -> None:
    config = Phase7Config()
    folds = plan_multiasset_folds(
        data_start=config.data_start,
        research_cutoff=config.research_cutoff,
        holdout_start=config.prospective_holdout_start,
        schedule=config.schedule,
    )
    plan = phase7_plan(config)
    assert len(folds) == plan["calendar_fold_count"] == 16
    assert config.universe.selection_cutoff == folds[0].train_end
    assert plan["fold_count_source"] == "DERIVED_FROM_CONFIGURED_CALENDAR_BOUNDARIES"
    assert plan["folds"][0]["cal_a_end"] == "2022-05-16T12:00:00+00:00"
    with pytest.raises(ValidationError, match="first walk-forward TRAIN end"):
        Phase7Config(
            universe=UniverseConfig(core_selection_cutoff=datetime(2022, 4, 1, tzinfo=UTC))
        )


def test_valid_fold_counts_are_distinct_from_calendar_fold_count() -> None:
    reports = [
        {
            "status": "COMPLETE",
            "fold_id": "f0",
            "spec": {
                "architecture": "G0",
                "horizon_minutes": 60,
                "target_type": "raw",
            },
        },
        {
            "status": "INELIGIBLE",
            "fold_id": "f1",
            "reason": "insufficient_calibration_rows",
            "spec": {
                "architecture": "P0",
                "horizon_minutes": 60,
                "target_type": "raw",
            },
        },
    ]
    summary = summarize_fold_completion(
        ("f0", "f1", "f2"),
        {"BTCUSDT": {"f0", "f1"}, "YOUNGUSDT": {"f1"}},
        reports,
    )
    assert summary["calendar_fold_count"] == 3
    assert summary["eligible_fold_count_by_symbol"] == {"BTCUSDT": 2, "YOUNGUSDT": 1}
    assert summary["eligible_fold_count_by_architecture"] == {"G0": 1}
    assert summary["completed_fold_count"] == 1
    assert summary["skipped_fold_count"] == 2
    assert summary["skip_reasons"] == {"insufficient_calibration_rows": 1}


def test_selection_descriptors_use_strictly_pre_cutoff_rows() -> None:
    cutoff = datetime(2022, 1, 1, tzinfo=UTC)
    registry = synthetic_registry()
    rows: list[dict[str, object]] = []
    for symbol, base in (("BTCUSDT", 100.0), ("ETHUSDT", 10.0)):
        for offset in range(4):
            rows.append(
                {
                    "symbol": symbol,
                    "open_time": cutoff - timedelta(days=4 - offset),
                    "close": base + offset,
                    "quote_volume": 1_000.0 + offset,
                    "trade_count": 100.0 + offset,
                }
            )
    baseline = pa.Table.from_pylist(rows)
    changed_rows = rows + [
        {
            "symbol": symbol,
            "open_time": cutoff,
            "close": base * 1_000,
            "quote_volume": 1_000_000_000.0,
            "trade_count": 1_000_000.0,
        }
        for symbol, base in (("BTCUSDT", 100.0), ("ETHUSDT", 10.0))
    ]
    before = build_point_in_time_descriptors(baseline, registry, as_of=cutoff, lookback_days=30)
    after = build_point_in_time_descriptors(
        pa.Table.from_pylist(changed_rows), registry, as_of=cutoff, lookback_days=30
    )
    assert before == after


def test_onboard_date_never_creates_pre_market_data_availability() -> None:
    first_verified = datetime(2020, 1, 1, tzinfo=UTC)
    registry = build_symbol_registry(
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "onboardDate": int(datetime(2019, 1, 1, tzinfo=UTC).timestamp() * 1_000),
                }
            ]
        },
        [
            {
                "symbol": "BTCUSDT",
                "first_market_data_time": first_verified,
                "last_market_data_time": RESEARCH_CUTOFF - timedelta(minutes=5),
                "available_intervals": ["5m", "12h", "1d"],
            }
        ],
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=RESEARCH_CUTOFF,
    )
    record = registry.records[0]
    assert record.onboard_date == datetime(2019, 1, 1, tzinfo=UTC)
    assert record.available_from == first_verified
    assert not record.exists_at(first_verified - timedelta(microseconds=1))


def _survival_registry(available_until: datetime):
    return build_symbol_registry(
        {"symbols": []},
        [
            {
                "symbol": "OLDUSDT",
                "base_asset": "OLD",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": datetime(2020, 1, 1, tzinfo=UTC),
                "last_market_data_time": available_until - timedelta(minutes=5),
                "available_until": available_until,
                "available_intervals": ["5m", "12h", "1d"],
            }
        ],
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=RESEARCH_CUTOFF,
    )


def test_future_survival_does_not_change_earlier_fold_eligibility() -> None:
    as_of = datetime(2022, 1, 1, tzinfo=UTC)
    descriptor = synthetic_descriptors(as_of=as_of)[0].model_copy(update={"symbol": "OLDUSDT"})
    config = UniverseConfig(
        core_target_size=2,
        fixture_mode=True,
        minimum_history_days=90,
        age_bucket_edges_days=(90, 180, 365),
        selection_lookback_days=30,
    )
    decisions = []
    for future_end in (
        datetime(2023, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 1, tzinfo=UTC),
    ):
        result = fold_local_eligibility(
            _survival_registry(future_end),
            [descriptor],
            train_end=as_of,
            config=config,
            candidate_symbols={"OLDUSDT"},
        )
        decisions.append(result[0].status)
    assert decisions == [EligibilityStatus.ELIGIBLE, EligibilityStatus.ELIGIBLE]


def test_fold_eligibility_is_intersection_with_frozen_universe() -> None:
    registry = synthetic_registry()
    universe_config = fixture_universe_config()
    universe = select_pilot_universe(
        registry,
        synthetic_descriptors(as_of=universe_config.selection_cutoff),
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    candidates = set(universe.symbols) - {"XRPUSDT"}
    decisions = fold_local_eligibility(
        registry,
        synthetic_descriptors(as_of=universe_config.selection_cutoff),
        train_end=universe_config.selection_cutoff,
        config=universe_config,
        candidate_symbols=candidates,
    )
    assert {item.symbol for item in decisions} == candidates


def test_future_listed_symbol_cannot_change_historical_market_context() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    evidence = []
    exchange_symbols = []
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"):
        first = (
            datetime(2024, 1, 1, tzinfo=UTC)
            if symbol == "XRPUSDT"
            else datetime(2019, 1, 1, tzinfo=UTC)
        )
        exchange_symbols.append(
            {
                "symbol": symbol,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }
        )
        evidence.append(
            {
                "symbol": symbol,
                "first_market_data_time": first,
                "last_market_data_time": RESEARCH_CUTOFF - timedelta(minutes=5),
                "available_intervals": ["5m", "12h", "1d"],
            }
        )
    registry = build_symbol_registry(
        {"symbols": exchange_symbols},
        evidence,
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=RESEARCH_CUTOFF,
    )
    candle_symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    baseline = generate_multiasset_features(
        candles.filter(pa.array(candle_symbols != "XRPUSDT")),
        registry=registry,
        config=_feature_config(),
    ).table
    changed = generate_multiasset_features(
        candles,
        registry=registry,
        config=_feature_config(),
    ).table
    changed_symbols = np.asarray(changed.column("symbol").to_pylist(), dtype=object)
    changed = changed.filter(pa.array(changed_symbols != "XRPUSDT"))
    for column in (
        "market_member_count",
        "market_mean_return",
        "market_return_dispersion",
        "trailing_liquidity_percentile",
    ):
        left = np.asarray(baseline.column(column).to_pylist(), dtype=np.float64)
        right = np.asarray(changed.column(column).to_pylist(), dtype=np.float64)
        assert np.allclose(left, right, equal_nan=True)


def test_future_liquidity_does_not_change_historical_tiers() -> None:
    cutoff = datetime(2022, 1, 1, tzinfo=UTC)
    descriptors = synthetic_descriptors(as_of=cutoff)
    eligible = {item.symbol for item in descriptors}
    baseline = fit_train_only_liquidity_tiers(
        descriptors, train_end=cutoff, eligible_symbols=eligible
    )
    future = descriptors + [
        item.model_copy(
            update={
                "as_of": datetime(2025, 1, 1, tzinfo=UTC),
                "trailing_quote_volume": item.trailing_quote_volume * 1_000_000,
            }
        )
        for item in descriptors
    ]
    assert baseline == fit_train_only_liquidity_tiers(
        future, train_end=cutoff, eligible_symbols=eligible
    )


def test_multiasset_purge_uses_each_rows_label_end_time() -> None:
    config = Phase7Config()
    plan = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )[0]
    split = calibration_split_time(plan)
    rows: list[dict[str, object]] = []
    points = (
        (plan.train_end - timedelta(hours=4), plan.train_end - timedelta(hours=3)),
        (plan.train_end - timedelta(hours=1), plan.validation_start + timedelta(minutes=30)),
        (plan.validation_end - timedelta(hours=4), plan.validation_end - timedelta(hours=3)),
        (
            plan.validation_end - timedelta(hours=1),
            plan.calibration_start + timedelta(minutes=30),
        ),
        (split - timedelta(hours=4), split - timedelta(hours=3)),
        (split - timedelta(minutes=30), split + timedelta(minutes=30)),
        (plan.calibration_end - timedelta(hours=4), plan.calibration_end - timedelta(hours=3)),
        (
            plan.calibration_end - timedelta(minutes=30),
            plan.test_start + timedelta(minutes=30),
        ),
        (plan.test_start + timedelta(hours=4), plan.test_start + timedelta(hours=5)),
    )
    for symbol in ("BTCUSDT", "ETHUSDT"):
        rows.extend(
            {
                "symbol": symbol,
                "feature_time": feature_time,
                "label_end_time": label_end_time,
            }
            for feature_time, label_end_time in points
        )
    sliced = slice_hardened_fold(
        pa.Table.from_pylist(rows).sort_by(
            [("feature_time", "ascending"), ("symbol", "ascending")]
        ),
        plan,
        ScheduleConfig(
            train_months=24,
            validation_months=3,
            calibration_months=3,
            test_months=3,
            step_months=3,
            embargo_minutes=120,
            minimum_rows_per_segment=1,
        ),
        config.prospective_holdout_start,
    )
    assert sliced.report["segments"]["train"]["purged"] == 2
    assert sliced.report["segments"]["validation"]["purged"] == 2
    assert sliced.report["segments"]["calibration_a"]["purged"] == 2
    assert sliced.report["segments"]["calibration_b"]["purged"] == 2


def test_normalization_scale_is_unchanged_by_future_price_perturbation() -> None:
    candles = synthetic_candles(rows_per_symbol=220)
    baseline_features = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=_feature_config()
    )
    symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    split = int(np.unique(times)[160])
    changed_rows = candles.to_pylist()
    for index, row in enumerate(changed_rows):
        if symbols[index] == "SOLUSDT" and times[index] >= split:
            for column in ("open", "high", "low", "close"):
                row[column] = float(row[column]) * 3.0
    changed_candles = pa.Table.from_pylist(changed_rows)
    changed_features = generate_multiasset_features(
        changed_candles, registry=synthetic_registry(), config=_feature_config()
    )
    baseline_targets = generate_multiasset_targets(
        candles,
        baseline_features.table,
        config=Phase7Config().targets,
        research_cutoff=RESEARCH_CUTOFF,
    ).table
    changed_targets = generate_multiasset_targets(
        changed_candles,
        changed_features.table,
        config=Phase7Config().targets,
        research_cutoff=RESEARCH_CUTOFF,
    ).table
    baseline_keys = list(
        zip(
            baseline_targets.column("symbol").to_pylist(),
            _times(baseline_targets, "feature_time"),
            baseline_targets.column("horizon_minutes").to_pylist(),
            strict=True,
        )
    )
    changed_by_key = {
        key: (scale, raw)
        for key, scale, raw in zip(
            zip(
                changed_targets.column("symbol").to_pylist(),
                _times(changed_targets, "feature_time"),
                changed_targets.column("horizon_minutes").to_pylist(),
                strict=True,
            ),
            changed_targets.column("ex_ante_volatility_scale").to_pylist(),
            changed_targets.column("raw_future_return").to_pylist(),
            strict=True,
        )
    }
    baseline_scales = baseline_targets.column("ex_ante_volatility_scale").to_pylist()
    baseline_raw = baseline_targets.column("raw_future_return").to_pylist()
    baseline_label_ends = _times(baseline_targets, "label_end_time")
    for key, scale, raw, label_end in zip(
        baseline_keys, baseline_scales, baseline_raw, baseline_label_ends, strict=True
    ):
        if key[0] == "SOLUSDT" and key[1] < split:
            assert changed_by_key[key][0] == pytest.approx(scale)
            if label_end < split:
                assert changed_by_key[key][1] == pytest.approx(raw)


def test_cross_sectional_ic_is_grouped_by_timestamp() -> None:
    report = cross_sectional_ic(
        np.asarray([1, 1, 1, 2, 2, 2], dtype=np.int64),
        np.asarray(["A", "B", "C", "A", "B", "C"], dtype=object),
        np.asarray([1, 2, 3, 1, 2, 3], dtype=np.float64),
        np.asarray([1, 2, 3, 3, 2, 1], dtype=np.float64),
    )
    assert report["timestamp_count"] == 2
    assert report["mean_spearman_ic"] == pytest.approx(0.0)


def _model_tables() -> tuple[pa.Table, pa.Table, pa.Table, dict[str, int]]:
    train: list[dict[str, object]] = []
    validation: list[dict[str, object]] = []
    calibration: list[dict[str, object]] = []
    mapping = {"A": 0, "B": 1}
    for symbol_index, symbol in enumerate(mapping):
        for index in range(160):
            row = {
                "symbol": symbol,
                "feature_time": datetime(2022, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * index),
                "f1": index / 100.0,
                "target": index / 200.0 + symbol_index * 0.01,
            }
            if index < 110:
                train.append(row)
            elif index < 140:
                validation.append(row)
            elif symbol == "A" or index < 145:
                calibration.append(row)
    return (
        pa.Table.from_pylist(train),
        pa.Table.from_pylist(validation),
        pa.Table.from_pylist(calibration),
        mapping,
    )


def test_per_coin_minimum_calibration_and_hybrid_global_fallback() -> None:
    train, validation, calibration, mapping = _model_tables()
    config = ModelConfig(
        minimum_train_rows_per_coin=100,
        minimum_validation_rows_per_coin=20,
        minimum_calibration_rows_per_coin=20,
        n_estimators=20,
        early_stopping_rounds=5,
        min_child_samples=5,
    )
    per_coin = fit_architecture(
        "P0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=config,
        model_threads=1,
        cluster_mapping=mapping,
        eligibility_calibration_a=calibration,
    )
    assert sorted(per_coin.estimators) == ["symbol:A"]
    assert per_coin.metadata["per_symbol_eligibility"]["B"]["status"] == ("PER_COIN_INELIGIBLE")
    p0_predictions, p0_covered = per_coin.predict(validation)
    coverage = evaluate_predictions(
        validation,
        p0_predictions,
        p0_covered,
        target_column="target",
        eligibility_reasons=per_coin.metadata["per_symbol_eligibility"],
    )["coverage"]
    assert coverage["covered_symbol_names"] == ["A"]
    assert coverage["excluded_symbols"][0]["symbol"] == "B"
    assert coverage["excluded_symbols"][0]["reason"]["status"] == "PER_COIN_INELIGIBLE"
    hybrid_config = config.model_copy(update={"minimum_calibration_rows_per_coin": 1_000})
    hybrid = fit_architecture(
        "H0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=hybrid_config,
        model_threads=1,
        cluster_mapping=mapping,
        hybrid_calibration=validation,
        eligibility_calibration_a=calibration,
    )
    predicted, covered = hybrid.predict(validation)
    global_only = hybrid.estimators["global"].predict(
        np.asarray(validation.column("f1").to_pylist(), dtype=np.float64).reshape(-1, 1)
    )
    assert np.all(covered)
    assert np.allclose(predicted, global_only)
    assert hybrid.metadata["hybrid_fallback_order"][-1] == "global_prediction"


def test_global_symbol_id_ablation_changes_estimator_input_schema() -> None:
    train, validation, calibration, mapping = _model_tables()
    config = ModelConfig(
        minimum_train_rows_per_coin=100,
        minimum_validation_rows_per_coin=20,
        minimum_calibration_rows_per_coin=20,
        n_estimators=20,
        early_stopping_rounds=5,
        min_child_samples=5,
    )
    without_id = fit_architecture(
        "G0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=config,
        model_threads=1,
        cluster_mapping=mapping,
        eligibility_calibration_a=calibration,
    )
    with_id = fit_architecture(
        "G0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=config,
        model_threads=1,
        cluster_mapping=mapping,
        explicit_symbol_id=True,
        eligibility_calibration_a=calibration,
    )
    assert without_id.estimators["global"].n_features_in_ == 1
    assert with_id.estimators["global"].n_features_in_ == 3
    assert without_id.metadata["explicit_symbol_id"] is False
    assert with_id.metadata["explicit_symbol_id"] is True


def test_cloud_guard_passes_before_mocked_heavy_work(monkeypatch: pytest.MonkeyPatch) -> None:
    class GatePassed(RuntimeError):
        pass

    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")

    def stop_after_gate(_: Path) -> dict[str, object]:
        raise GatePassed("guard passed")

    monkeypatch.setattr("crypto_ai.phase7.pipeline.resource_snapshot", stop_after_gate)
    with pytest.raises(GatePassed, match="guard passed"):
        run_phase7_cloud(Phase7Config(), stage="registry", resume=False)


def test_each_heavy_entry_point_is_guarded_before_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PHASE7_ALLOW_CLOUD_RESEARCH", raising=False)
    config = Phase7Config()
    registry = synthetic_registry()
    universe_config = fixture_universe_config()
    universe = select_pilot_universe(
        registry,
        synthetic_descriptors(as_of=universe_config.selection_cutoff),
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    with pytest.raises(RuntimeError, match="training VM"):
        acquire_candle_family(
            config,
            registry,
            symbols=(),
            interval="5m",
            start=config.data_start,
            end=config.research_cutoff,
        )
    with pytest.raises(RuntimeError, match="training VM"):
        _gold_stage(
            config,
            tmp_path,
            registry,
            universe,
            build_expansion_policy(universe, universe_config),
            {},
        )
    with pytest.raises(RuntimeError, match="training VM"):
        run_phase7_training(
            config,
            gold_manifest_path=tmp_path / "missing.json",
            registry=registry,
            universe=universe,
            expansion_policy=build_expansion_policy(universe, universe_config),
            descriptors=[],
            checkpoint_store=CheckpointStore(tmp_path / "checkpoints", "guard"),
            run_root=tmp_path,
            resume=False,
        )


def test_checkpoint_identity_and_partial_resume_safety(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints", "run-audit")
    stage_a = atomic_json(tmp_path / "stage-a.json", {"status": "complete"})
    identity_a = {"config_hash": "a", "data_hash": "one"}
    store.complete("stage-a", [stage_a], identity_a)
    assert store.is_complete("stage-a", expected_metadata=identity_a)
    assert not store.is_complete(
        "stage-a", expected_metadata={"config_hash": "a", "data_hash": "two"}
    )

    partial = tmp_path / ".stage-b.json.interrupted.tmp"
    partial.write_text('{"partial": true}\n', encoding="utf-8")
    assert not store.is_complete("stage-b")
    stage_b = atomic_json(tmp_path / "stage-b.json", {"status": "recomputed"})
    identity_b = {"experiment_id": "b", "fold": "fold-000", "data_hash": "one"}
    store.complete("stage-b", [stage_b], identity_b)
    assert store.is_complete("stage-b", expected_metadata=identity_b)


def test_config_rejects_holdout_or_anchor_unlock_attempts() -> None:
    with pytest.raises(ValidationError):
        Phase7Config(prospective_holdout_used=True)
    with pytest.raises(ValidationError):
        Phase7Config(prospective_holdout_evaluation_authorized=True)
    with pytest.raises(ValidationError, match="BTCUSDT and ETHUSDT"):
        Phase7Config(universe=UniverseConfig(required_anchor_symbols=("BTCUSDT", "SOLUSDT")))
