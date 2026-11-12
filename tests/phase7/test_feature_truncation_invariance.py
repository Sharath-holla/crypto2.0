"""CHANGED BY CLAUDE (2026-11-06, closure): truncation-invariance leakage test for features.

Features at timestamps <= T must be identical whether the generator saw only data through T or
also the following days. This covers native 5m features, 12h/1d higher-timeframe context,
cross-sectional/market context across several symbols, and gaps before and after T.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.config import FeatureConfig
from crypto_ai.phase7.features import build_higher_timeframe_context, generate_multiasset_features
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry

START = datetime(2021, 12, 25, tzinfo=UTC)
BARS = 2_000
BAR = timedelta(minutes=5)


def _config(*, htf: bool) -> FeatureConfig:
    return FeatureConfig(
        correlation_window_rows=24,
        liquidity_window_rows=24,
        volatility_window_rows=24,
        daily_volatility_rows=24,
        seven_day_volatility_rows=48,
        include_12h=htf,
        include_1d=htf,
        include_derivatives=False,
    )


def _drop(candles: pa.Table, symbol: str, first_bar: int, count: int) -> pa.Table:
    gap_start, gap_end = START + first_bar * BAR, START + (first_bar + count) * BAR
    symbols = candles.column("symbol").to_pylist()
    opens = candles.column("open_time").to_pylist()
    keep = [
        not (s == symbol and gap_start <= o < gap_end) for s, o in zip(symbols, opens, strict=True)
    ]
    return candles.filter(pa.array(keep))


def _htf_candles(interval: timedelta) -> pa.Table:
    rows = []
    for index, symbol in enumerate(("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")):
        for step in range(int(timedelta(minutes=5 * BARS) / interval) + 2):
            open_price = 100.0 * (index + 1) * (1.0 + 0.01 * np.sin(step / 3.0) + step * 0.002)
            close_price = open_price * (1.0 + 0.004 * np.cos(step / 2.0))
            volume = 1e6 * (index + 1) * (1.0 + 0.1 * np.sin(step))
            rows.append(
                {
                    "symbol": symbol,
                    "open_time": START + step * interval,
                    "open": open_price,
                    "high": max(open_price, close_price) * 1.002,
                    "low": min(open_price, close_price) * 0.998,
                    "close": close_price,
                    "base_volume": volume / open_price,
                    "quote_volume": volume,
                    "trade_count": 1000 + step,
                    "taker_buy_base_volume": volume * 0.5 / open_price,
                    "taker_buy_quote_volume": volume * 0.5,
                }
            )
    return pa.Table.from_pylist(rows)


def _before(table: pa.Table, limit: datetime, width: timedelta) -> pa.Table:
    """Rows whose candle is complete (open_time + width <= limit)."""

    opens = table.column("open_time").to_pylist()
    return table.filter(pa.array([o + width <= limit for o in opens]))


def _by_key(result, name: str) -> dict[tuple[str, datetime], object]:
    table = result.table
    return dict(
        zip(
            zip(
                table.column("symbol").to_pylist(),
                table.column("feature_time").to_pylist(),
                strict=True,
            ),
            table.column(name).to_pylist(),
            strict=True,
        )
    )


def _assert_invariant(full, truncated, cutoff: datetime) -> None:
    assert full.feature_columns == truncated.feature_columns
    columns = (*full.feature_columns, "market_membership_hash")

    # Convert invariant row keys once, preserving the same per-key scalar assertions.
    # Repeating Arrow timestamp conversion for every feature is needlessly expensive.
    def keys(table):
        return list(
            zip(table["symbol"].to_pylist(), table["feature_time"].to_pylist(), strict=True)
        )

    full_keys, truncated_keys = keys(full.table), keys(truncated.table)
    compared = 0
    for name in columns:
        left = dict(zip(full_keys, full.table[name].to_pylist(), strict=True))
        right = dict(zip(truncated_keys, truncated.table[name].to_pylist(), strict=True))
        selected_keys = [key for key in right if key[1] <= cutoff]
        assert selected_keys, "the truncated run must contain rows at or before the cutoff"
        assert all(key in left for key in selected_keys)
        for key in selected_keys:
            a, b = left[key], right[key]
            if isinstance(a, float) or isinstance(b, float) or a is None or b is None:
                a_nan = a is None or (isinstance(a, float) and np.isnan(a))
                b_nan = b is None or (isinstance(b, float) and np.isnan(b))
                assert a_nan == b_nan, f"{name} at {key}: {a!r} != {b!r}"
                if not a_nan:
                    assert a == pytest.approx(b, rel=1e-9, abs=1e-12), f"{name} at {key}"
            else:
                assert a == b, f"{name} at {key}: {a!r} != {b!r}"
            compared += 1
    assert compared > 1_000


@pytest.mark.parametrize("cutoff_bar", [700, 1_000, 1_500])
@pytest.mark.parametrize("htf", [False, True], ids=["native_5m", "with_12h_and_1d"])
@pytest.mark.parametrize("gaps", [False, True], ids=["no_gaps", "gaps_before_and_after_T"])
def test_features_through_T_do_not_depend_on_data_after_T(
    cutoff_bar: int, htf: bool, gaps: bool
) -> None:
    candles = synthetic_candles(rows_per_symbol=BARS, start=START)
    if gaps:
        candles = _drop(candles, "SOLUSDT", 400, 25)  # gap before every cutoff
        candles = _drop(candles, "XRPUSDT", 1_700, 10)  # gap after every cutoff
        candles = _drop(candles, "ETHUSDT", cutoff_bar - 2, 6)  # gap straddling T
    cutoff = START + cutoff_bar * BAR  # feature_time of the last bar kept is <= cutoff
    truncated_candles = candles.filter(
        pa.array([o + BAR <= cutoff for o in candles.column("open_time").to_pylist()])
    )
    context_full = context_cut = None
    if htf:
        half_day, day = timedelta(hours=12), timedelta(days=1)
        full_12h, full_1d = _htf_candles(half_day), _htf_candles(day)
        context_full = build_higher_timeframe_context(full_12h, full_1d)
        context_cut = build_higher_timeframe_context(
            _before(full_12h, cutoff, half_day), _before(full_1d, cutoff, day)
        )
    registry = synthetic_registry()
    full = generate_multiasset_features(
        candles, registry=registry, config=_config(htf=htf), higher_timeframe_context=context_full
    )
    truncated = generate_multiasset_features(
        truncated_candles,
        registry=registry,
        config=_config(htf=htf),
        higher_timeframe_context=context_cut,
    )
    _assert_invariant(full, truncated, cutoff)


def test_the_comparison_detects_a_changed_past_value() -> None:
    """Negative control: tampering with a bar BEFORE the cutoff must make the check fail."""

    candles = synthetic_candles(rows_per_symbol=BARS, start=START)
    cutoff = START + 1_000 * BAR
    kept = candles.filter(
        pa.array([o + BAR <= cutoff for o in candles.column("open_time").to_pylist()])
    )
    rows = kept.to_pylist()
    for row in rows:
        if row["symbol"] == "BTCUSDT" and row["open_time"] == START + 990 * BAR:
            row["close"] = float(row["close"]) * 1.5
    registry = synthetic_registry()
    full = generate_multiasset_features(candles, registry=registry, config=_config(htf=False))
    tampered = generate_multiasset_features(
        pa.Table.from_pylist(rows), registry=registry, config=_config(htf=False)
    )
    with pytest.raises(AssertionError):
        _assert_invariant(full, tampered, cutoff)
