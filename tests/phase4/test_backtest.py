from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase4.backtest import run_oos_backtest
from crypto_ai.phase4.config import BacktestConfig


def _predictions(split: str = "test") -> pa.Table:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(30):
        entry = start + timedelta(minutes=5 * index)
        rows.append(
            {
                "split": split,
                "feature_time": entry,
                "entry_time": entry,
                "label_end_time": entry + timedelta(minutes=60),
                "entry_reference_price": 100.0,
                "future_reference_price": 101.0,
                "predicted_return": 0.02,
                "taker_imbalance_quote": 0.1,
                "bull_regime": 1.0,
                "bear_regime": 0.0,
                "sideways_regime": 0.0,
                "high_volatility_regime": 0.0,
            }
        )
    return pa.Table.from_pylist(rows)


def test_backtest_uses_next_open_one_position_and_all_costs() -> None:
    config = BacktestConfig(
        taker_fee_bps_per_side=4,
        spread_bps_round_trip=1,
        slippage_bps_per_side=1,
        minimum_prediction_bps=0,
    )
    trades, metrics = run_oos_backtest(_predictions(), config)

    assert trades.num_rows == 3
    assert np.allclose(trades.column("non_funding_cost").to_numpy(), 0.0011)
    assert trades.column("net_return")[0].as_py() == pytest.approx(0.01 - 0.0011)
    assert metrics["turnover"] == 6
    assert metrics["trade_count"] == 3


def test_backtest_rejects_training_predictions() -> None:
    with pytest.raises(ValueError, match="OOS"):
        run_oos_backtest(_predictions("train"), BacktestConfig())


def test_cost_stress_cannot_improve_same_trade_returns() -> None:
    predictions = _predictions()
    base, _ = run_oos_backtest(predictions, BacktestConfig(minimum_prediction_bps=0))
    stress, _ = run_oos_backtest(
        predictions,
        BacktestConfig(minimum_prediction_bps=0),
        cost_multiplier=2,
    )
    assert np.all(stress.column("net_return").to_numpy() < base.column("net_return").to_numpy())
