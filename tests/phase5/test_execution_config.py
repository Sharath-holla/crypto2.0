from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pytest

from crypto_ai.phase4_1.config import BacktestV2_1Config
from crypto_ai.phase4_1.model import derivatives_ablation_sets, long_history_ablation_sets
from crypto_ai.phase5.config import WalkForwardConfig, load_walk_forward_config
from crypto_ai.phase5.execution import (
    ADAPTIVE_POLICY_COST_STRESS,
    FIXED_POLICY_COST_STRESS,
    economic_metrics,
    prepare_execution_arrays,
    reprice_fixed_policy_trades,
    simulate_trades,
)
from crypto_ai.phase5.policy import ThresholdPolicy


def _opportunities(count: int = 5) -> pa.Table:
    start = datetime(2025, 7, 1, tzinfo=UTC)
    feature = [start + timedelta(hours=index * 2) for index in range(count)]
    return pa.table(
        {
            "candidate": ["L0"] * count,
            "family": ["primary"] * count,
            "fold_id": ["fold-000"] * count,
            "feature_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "entry_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [value + timedelta(minutes=60) for value in feature],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "entry_reference_price": [100.0] * count,
            "future_reference_price": [101.0] * count,
            "raw_prediction": [0.01] * count,
            "calibrated_prediction": [0.01] * count,
            "taker_buy_base_share": [0.5] * count,
            "taker_flow_imbalance_quote": [0.0] * count,
            "bull_regime": [1.0] * count,
            "bear_regime": [0.0] * count,
            "sideways_regime": [0.0] * count,
            "high_volatility_regime": [0.0] * count,
            "low_volatility_regime": [1.0] * count,
        }
    )


def test_config_freezes_exact_candidate_pairs() -> None:
    common = {
        "name": "test",
        "dataset_manifest": Path("manifest.json"),
        "prospective_holdout_start": datetime(2026, 8, 1, tzinfo=UTC),
    }
    with pytest.raises(ValueError, match="frozen"):
        WalkForwardConfig(family="primary", candidates=("L5",), **common)
    config = WalkForwardConfig(family="derivatives", candidates=("D0", "D2"), **common)
    assert config.candidates == ("D0", "D2")


def test_repository_configs_load_with_expected_holdout() -> None:
    primary = load_walk_forward_config(Path("configs/walkforward/btc_primary_v1.toml"))
    derivatives = load_walk_forward_config(Path("configs/walkforward/btc_derivatives_v1.toml"))
    assert primary.prospective_holdout_start == datetime(2026, 8, 1, tzinfo=UTC)
    assert derivatives.prospective_holdout_start == primary.prospective_holdout_start


def test_candidate_schemas_are_frozen_and_matched_for_fairness() -> None:
    long = long_history_ablation_sets()
    derivatives = derivatives_ablation_sets(include_open_interest=False)
    assert len(long["L0"]) == 13
    assert len(long["L5"]) == 46
    assert derivatives["D0"] == long["L5"]
    assert len(derivatives["D2"]) == 55


def test_one_minute_execution_is_strictly_after_feature_time() -> None:
    opportunities = _opportunities(1)
    start = opportunities.column("feature_time")[0].as_py()
    minute_times = [start + timedelta(minutes=index) for index in range(62)]
    execution = pa.table(
        {
            "open_time": pa.array(minute_times, type=pa.timestamp("us", tz="UTC")),
            "open": [100.0 + index / 100 for index in range(62)],
        }
    )
    trades, metrics = simulate_trades(
        opportunities,
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        BacktestV2_1Config(),
        execution_1m=execution,
    )
    assert trades.column("entry_time")[0].as_py() > start
    assert trades.column("execution_resolution")[0].as_py() == "1m"
    assert metrics["execution_resolution_counts"]["1m"] == 1


def test_execution_falls_back_to_next_five_minute_reference() -> None:
    opportunities = _opportunities(1)
    trades, metrics = simulate_trades(
        opportunities,
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        BacktestV2_1Config(),
    )
    assert trades.column("execution_resolution")[0].as_py() == "5m"
    assert metrics["execution_resolution_counts"]["5m"] == 1


def test_five_trades_are_machine_readable_but_unreliable() -> None:
    trades, _ = simulate_trades(
        _opportunities(5),
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        BacktestV2_1Config(),
    )
    metrics = economic_metrics(trades, opportunity_count=5, minimum_reliable_trade_count=30)
    assert metrics["trade_count"] == 5
    assert metrics["reliable"] is False
    assert metrics["statistically_reliable"] is False
    assert metrics["reliability_reason"] == "trade_count_below_30"
    assert metrics["profit_factor"] is None
    assert metrics["ratio_metrics"]["profit_factor"]["reliable"] is False
    assert metrics["ratio_metrics"]["profit_factor"]["display_value"] == "INSUFFICIENT_SAMPLE"


def test_no_trade_policy_is_preserved_in_execution() -> None:
    trades, metrics = simulate_trades(
        _opportunities(),
        ThresholdPolicy(None, "NO_TRADE", 0, None),
        BacktestV2_1Config(),
    )
    assert trades.num_rows == 0
    assert metrics["reliability_reason"] == "NO_TRADE"


def test_fixed_policy_cost_stress_preserves_exact_trade_identity_and_timing() -> None:
    config = BacktestV2_1Config()
    base, _ = simulate_trades(
        _opportunities(5),
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        config,
        cost_multiplier=1.0,
    )
    one, one_metrics = reprice_fixed_policy_trades(base, config, cost_multiplier=1.0)
    stressed, stressed_metrics = reprice_fixed_policy_trades(base, config, cost_multiplier=1.5)
    for name in ("trade_id", "entry_time", "exit_time", "direction"):
        assert one.column(name).to_pylist() == stressed.column(name).to_pylist()
    assert one_metrics["trade_identity_hash"] == stressed_metrics["trade_identity_hash"]
    assert one_metrics["stress_type"] == FIXED_POLICY_COST_STRESS
    assert stressed_metrics["trade_count"] == one_metrics["trade_count"]
    assert stressed.column("gross_return").to_pylist() == one.column("gross_return").to_pylist()
    assert stressed.column("net_return").to_pylist() != one.column("net_return").to_pylist()


def test_adaptive_cost_stress_is_separate_and_may_change_trade_set() -> None:
    opportunities = _opportunities(5).set_column(
        _opportunities(5).schema.get_field_index("calibrated_prediction"),
        "calibrated_prediction",
        pa.array([0.0014] * 5),
    )
    policy = ThresholdPolicy(2.0, "TRADE", 30, 0.1)
    low, low_metrics = simulate_trades(
        opportunities,
        policy,
        BacktestV2_1Config(),
        cost_multiplier=1.0,
    )
    high, high_metrics = simulate_trades(
        opportunities,
        policy,
        BacktestV2_1Config(),
        cost_multiplier=1.5,
    )
    assert low_metrics["stress_type"] == ADAPTIVE_POLICY_COST_STRESS
    assert high_metrics["stress_type"] == ADAPTIVE_POLICY_COST_STRESS
    assert low.num_rows > high.num_rows


def test_prepared_execution_reuse_is_result_equivalent() -> None:
    opportunities = _opportunities(5)
    config = BacktestV2_1Config()
    prepared = prepare_execution_arrays(opportunities, None, config)
    direct, direct_metrics = simulate_trades(
        opportunities,
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        config,
    )
    cached, cached_metrics = simulate_trades(
        opportunities,
        ThresholdPolicy(2.0, "TRADE", 30, 0.1),
        config,
        prepared_execution=prepared,
    )
    assert cached.equals(direct)
    assert cached_metrics == direct_metrics
