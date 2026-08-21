from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pyarrow as pa

from crypto_ai.data.schema import candles_to_table
from crypto_ai.phase4.market_data import MarketDataKind, market_data_schema
from crypto_ai.phase4_1.backtest import _trade_diagnostics, run_oos_backtest_v2_1
from crypto_ai.phase4_1.config import BacktestV2_1Config
from tests.factories import make_candle


def _predictions(value: float) -> pa.Table:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    return pa.table(
        {
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "feature_time": pa.array(
                [start + timedelta(minutes=5), start + timedelta(minutes=10)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "entry_time": pa.array(
                [start + timedelta(minutes=10), start + timedelta(minutes=15)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "label_end_time": pa.array(
                [start + timedelta(minutes=70), start + timedelta(minutes=75)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "entry_reference_price": [Decimal("100"), Decimal("100")],
            "future_reference_price": [Decimal("101"), Decimal("101")],
            "future_return_60m": [0.01, 0.01],
            "taker_buy_base_share": [0.5, 0.5],
            "taker_flow_imbalance_quote": [0.0, 0.0],
            "bull_regime": [1.0, 1.0],
            "bear_regime": [0.0, 0.0],
            "sideways_regime": [0.0, 0.0],
            "high_volatility_regime": [0.0, 0.0],
            "low_volatility_regime": [1.0, 1.0],
            "split": ["test", "test"],
            "predicted_return": [value, value],
        }
    )


def _one_minute_candles() -> pa.Table:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    return candles_to_table(
        [make_candle(index, start=start, interval_minutes=1) for index in range(180)]
    )


def _funding() -> pa.Table:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    return pa.Table.from_pylist(
        [
            {
                "symbol": "BTCUSDT",
                "event_time": start + timedelta(minutes=30),
                "availability_time": start + timedelta(minutes=30),
                "funding_rate": Decimal("0.001"),
                "mark_price": Decimal("65000"),
                "rate_type": "Regular",
                "source": "binance_usdm_funding_rest",
                "ingested_at": start + timedelta(days=1),
            }
        ],
        schema=market_data_schema(MarketDataKind.FUNDING),
    )


def test_v2_1_backtest_retains_no_trade_outcome() -> None:
    trades, metrics = run_oos_backtest_v2_1(
        _predictions(0.0), BacktestV2_1Config(), execution_candles=_one_minute_candles()
    )

    assert trades.num_rows == 0
    assert metrics["trade_count"] == 0
    assert metrics["opportunity_count"] == 2
    assert metrics["no_trade_count"] == 2
    assert metrics["threshold_rejected_rows"] == 2
    assert metrics["low_trade_count_warning"] is True
    assert "NO-TRADE" in metrics["warning"]


def test_v2_1_backtest_uses_post_signal_1m_entry_and_actual_funding() -> None:
    config = BacktestV2_1Config(minimum_prediction_bps=0)
    trades, metrics = run_oos_backtest_v2_1(
        _predictions(0.02),
        config,
        execution_candles=_one_minute_candles(),
        funding=_funding(),
    )

    assert trades.num_rows == 1  # overlapping second signal is skipped
    row = trades.to_pylist()[0]
    assert row["entry_time"] == datetime(2026, 7, 1, 0, 6, tzinfo=UTC)
    assert row["exit_time"] == datetime(2026, 7, 1, 1, 6, tzinfo=UTC)
    assert row["funding_cash_flow"] == -0.001
    assert row["fee_cost"] == 0.0008
    assert row["spread_cost"] == 0.0001
    assert row["slippage_cost"] == 0.0002
    assert metrics["funding_contribution"] == -0.001
    assert metrics["no_trade_count"] == 1
    assert metrics["overlap_skipped_rows"] == 1
    assert _trade_diagnostics(trades)["by_year"]["2026"]["trades"] == 1


def test_v2_1_entry_delay_stress_moves_execution_forward() -> None:
    config = BacktestV2_1Config(minimum_prediction_bps=0)
    base, _ = run_oos_backtest_v2_1(
        _predictions(0.02), config, execution_candles=_one_minute_candles()
    )
    delayed, _ = run_oos_backtest_v2_1(
        _predictions(0.02),
        config,
        execution_candles=_one_minute_candles(),
        additional_delay_minutes=5,
    )

    assert delayed.column("entry_time")[0].as_py() - base.column("entry_time")[0].as_py() == (
        timedelta(minutes=5)
    )
