from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.phase6.features import _higher_timeframe_values
from crypto_ai.phase7.config import FEATURE_VERSION, MARKET_CONTEXT_VERSION, FeatureConfig
from crypto_ai.phase7.registry import SymbolRegistry

BASE_FEATURE_COLUMNS = (
    "return_5m",
    "return_15m",
    "return_30m",
    "return_1h",
    "return_4h",
    "range_pct",
    "body_pct",
    "atr14_pct",
    "ema20_distance_pct",
    "realized_volatility_1h",
    "daily_volatility",
    "seven_day_volatility",
    "relative_quote_volume",
    "volume_zscore",
    "trade_count_zscore",
    "taker_buy_share",
    "taker_sell_share",
    "taker_flow_imbalance",
    "funding_zscore",
    "mark_index_basis",
    "contract_mark_basis",
    "return_5m_over_ex_ante_vol",
    "return_1h_over_daily_vol",
    "return_4h_over_7d_vol",
)
COIN_CONTEXT_COLUMNS = (
    "listing_age_days",
    "history_length_days",
    "trailing_liquidity_percentile",
    "trailing_volatility_percentile",
    "trade_intensity_percentile",
    "btc_beta",
    "btc_correlation",
    "eth_correlation",
    "relative_strength_vs_btc",
    "relative_strength_vs_eth",
    "beta_adjusted_residual_return",
)
ANCHOR_CONTEXT_COLUMNS = (
    "btc_return_5m",
    "btc_return_15m",
    "btc_return_30m",
    "btc_return_1h",
    "btc_return_4h",
    "btc_volatility_1h",
    "btc_taker_flow_imbalance",
    "eth_return_5m",
    "eth_return_1h",
    "eth_return_4h",
    "eth_volatility_1h",
)
MARKET_CONTEXT_COLUMNS = (
    "market_mean_return",
    "market_median_return",
    "market_pct_positive",
    "market_pct_negative",
    "market_return_dispersion",
    "market_median_volatility",
    "market_median_taker_flow_imbalance",
    "market_member_count",
)
CROSS_SECTIONAL_SOURCE_COLUMNS = (
    "cross_sectional_trailing_liquidity_source",
    "cross_sectional_volatility_source",
    "cross_sectional_trade_intensity_source",
)


@dataclass(frozen=True, slots=True)
class MultiAssetFeatureResult:
    table: pa.Table
    feature_columns: tuple[str, ...]
    feature_version: str
    market_context_version: str
    market_membership: dict[int, tuple[str, ...]]


def _float_column(table: pa.Table, name: str, *, optional: bool = False) -> np.ndarray:
    if name not in table.column_names:
        if optional:
            return np.full(table.num_rows, np.nan, dtype=np.float64)
        raise ValueError(f"missing required multi-asset column: {name}")
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _times(table: pa.Table, name: str) -> np.ndarray:
    if name not in table.column_names:
        raise ValueError(f"missing required timestamp column: {name}")
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _lag_return(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) > lag:
        earlier = values[:-lag]
        later = values[lag:]
        valid = np.isfinite(earlier) & np.isfinite(later) & (earlier > 0)
        target = result[lag:]
        target[valid] = later[valid] / earlier[valid] - 1.0
    return result


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    result = np.full(len(values), np.nan)
    if len(values) < window:
        return result
    finite = np.isfinite(values)
    safe = np.where(finite, values, 0.0)
    sums = np.concatenate(([0.0], np.cumsum(safe)))
    counts = np.concatenate(([0], np.cumsum(finite.astype(np.int64))))
    rolling_sum = sums[window:] - sums[:-window]
    rolling_count = counts[window:] - counts[:-window]
    result[window - 1 :] = np.where(rolling_count == window, rolling_sum / window, np.nan)
    return result


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    result = np.full(len(values), np.nan)
    if len(values) < window:
        return result
    finite = np.isfinite(values)
    safe = np.where(finite, values, 0.0)
    sums = np.concatenate(([0.0], np.cumsum(safe)))
    squares = np.concatenate(([0.0], np.cumsum(np.square(safe))))
    counts = np.concatenate(([0], np.cumsum(finite.astype(np.int64))))
    rolling_sum = sums[window:] - sums[:-window]
    rolling_square = squares[window:] - squares[:-window]
    rolling_count = counts[window:] - counts[:-window]
    variance = (rolling_square - np.square(rolling_sum) / window) / max(1, window - 1)
    result[window - 1 :] = np.where(
        rolling_count == window, np.sqrt(np.maximum(variance, 0.0)), np.nan
    )
    return result


def _rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    mean = _rolling_mean(values, window)
    std = _rolling_std(values, window)
    result = np.full(len(values), np.nan)
    valid = np.isfinite(values) & np.isfinite(mean) & np.isfinite(std) & (std > 0)
    result[valid] = (values[valid] - mean[valid]) / std[valid]
    return result


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    result = np.full(len(numerator), np.nan)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 0)
    result[valid] = numerator[valid] / denominator[valid]
    return result


def _ema(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) < window or not np.all(np.isfinite(values[:window])):
        return result
    result[window - 1] = float(np.mean(values[:window]))
    alpha = 2.0 / (window + 1)
    for index in range(window, len(values)):
        if np.isfinite(values[index]) and np.isfinite(result[index - 1]):
            result[index] = alpha * values[index] + (1.0 - alpha) * result[index - 1]
    return result


def _atr_pct(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, *, window: int = 14
) -> np.ndarray:
    previous = np.concatenate(([np.nan], close[:-1]))
    true_range = np.maximum.reduce([high - low, np.abs(high - previous), np.abs(low - previous)])
    atr = _rolling_mean(true_range, window)
    return _safe_divide(atr, close)


_PAIR_STATS_VAR_TOL = 1e-8
# Maximum (mean^2 + var) / var window ratio on the vectorized path. Above
# this, cumulative-sum cancellation could exceed 1e-9 even with extended
# precision, so the window is recomputed exactly. Real return data has
# window means near zero (ratio ~ 1); 1e5 leaves enormous headroom.
_PAIR_STATS_CONDITION_LIMIT = 1e5


def _pair_stats(
    values: np.ndarray, anchor: np.ndarray, window: int
) -> tuple[np.ndarray, np.ndarray]:
    """Rolling beta/correlation of ``values`` against ``anchor``.

    Vectorized equivalent of :func:`_pair_stats_reference` (kept for
    equivalence tests). Exact semantics:

    - output is NaN until ``window`` full rows are available;
    - every row in the window must be finite, otherwise NaN;
    - skipped when the anchor has zero (ddof=1) variance or either series
      is constant inside the window;
    - beta = cov(x, y, ddof=1) / var(y, ddof=1);
    - correlation = cov(x, y, ddof=1) / sqrt(var(x, ddof=1) * var(y, ddof=1)).
    """
    count = len(values)
    correlation = np.full(count, np.nan)
    beta = np.full(count, np.nan)
    if count < window or window <= 1:
        return correlation, beta
    if values.ndim != 1 or anchor.ndim != 1 or len(values) != len(anchor):
        raise ValueError("_pair_stats requires aligned 1-D values and anchor arrays")
    finite_x = np.isfinite(values)
    finite_y = np.isfinite(anchor)
    cumulative_x = np.concatenate(([0], np.cumsum(finite_x)))
    cumulative_y = np.concatenate(([0], np.cumsum(finite_y)))
    # A window ending at index i is fully finite when the finite-count
    # delta over [i-window+1, i] equals the window length.
    valid = np.zeros(count, dtype=bool)
    valid[window - 1 :] = (cumulative_x[window:] - cumulative_x[: count - window + 1] == window) & (
        cumulative_y[window:] - cumulative_y[: count - window + 1] == window
    )
    if not valid.any():
        return correlation, beta
    clean_x = np.where(finite_x, values, 0.0)
    clean_y = np.where(finite_y, anchor, 0.0)
    # Extended-precision cumulative sums: window sums are differences of
    # partial sums, so a large constant block in either series would otherwise
    # erode float64 precision for every later window (~eps * partial-magnitude
    # per window). longdouble (80-bit on Linux x86-64) keeps the error ~1000x
    # below float64. On platforms where longdouble == float64 the code still
    # works correctly, just with float64 precision.
    extended = np.longdouble
    zero = extended(0)
    # Cast BEFORE multiplication: float64 products could otherwise overflow
    # to inf for large-but-finite inputs (extended exponent range keeps the
    # products and their cumulative sums finite).
    clean_x_ext = clean_x.astype(extended, copy=False)
    clean_y_ext = clean_y.astype(extended, copy=False)
    sums = {
        "x": np.concatenate(([zero], np.cumsum(clean_x_ext))),
        "y": np.concatenate(([zero], np.cumsum(clean_y_ext))),
        "xx": np.concatenate(([zero], np.cumsum(clean_x_ext * clean_x_ext))),
        "yy": np.concatenate(([zero], np.cumsum(clean_y_ext * clean_y_ext))),
        "xy": np.concatenate(([zero], np.cumsum(clean_x_ext * clean_y_ext))),
    }
    # Window sums for every ending index i >= window-1, vectorized over i.
    sx = sums["x"][window:] - sums["x"][: count - window + 1]
    sy = sums["y"][window:] - sums["y"][: count - window + 1]
    sxx = sums["xx"][window:] - sums["xx"][: count - window + 1]
    syy = sums["yy"][window:] - sums["yy"][: count - window + 1]
    sxy = sums["xy"][window:] - sums["xy"][: count - window + 1]
    variance_x = (sxx - sx * sx / window) / (window - 1)
    variance_y = (syy - sy * sy / window) / (window - 1)
    covariance = (sxy - sx * sy / window) / (window - 1)
    fully_finite = valid[window - 1 :]
    # Vectorized path only for well-conditioned windows: strictly positive,
    # finite variance above the tolerance, AND variance large relative to the
    # window's second-moment scale (a huge window mean would otherwise drown
    # the variance in cumulative-sum cancellation). EVERY other fully-finite
    # window is recomputed with the exact reference algorithm, so NaN
    # placement and values match the reference bit-for-bit there and a
    # cancellation artifact can never turn a finite reference output into NaN
    # (or vice versa). Real return data (window means near zero) keeps every
    # window on the vectorized path; the exact path only catches pathological
    # or adversarial scales.
    with np.errstate(divide="ignore", invalid="ignore"):
        moment_scale_x = sxx / (variance_x * window)  # ~ (mean^2 + var) / var
        moment_scale_y = syy / (variance_y * window)
        cross_scale = np.abs(sxy) / (window * np.sqrt(variance_x * variance_y) + 1e-300)
    # Non-finite moment scales (zero/negative variance) compare False below
    # and therefore route the window to the exact recompute path.
    well_conditioned = fully_finite & (
        (variance_x > _PAIR_STATS_VAR_TOL)
        & (variance_y > _PAIR_STATS_VAR_TOL)
        & np.isfinite(variance_x)
        & np.isfinite(variance_y)
        & (moment_scale_x < _PAIR_STATS_CONDITION_LIMIT)
        & (moment_scale_y < _PAIR_STATS_CONDITION_LIMIT)
        & (cross_scale < _PAIR_STATS_CONDITION_LIMIT)
    )
    suspicious = fully_finite & ~well_conditioned
    if suspicious.any():
        for relative in np.flatnonzero(suspicious):
            index = window - 1 + int(relative)
            x = values[index - window + 1 : index + 1]
            y = anchor[index - window + 1 : index + 1]
            variance = float(np.var(y, ddof=1))
            if variance <= 0 or np.ptp(x) == 0 or np.ptp(y) == 0:
                continue
            covariance_exact = float(np.cov(x, y, ddof=1)[0, 1])
            beta[index] = covariance_exact / variance
            correlation[index] = float(np.corrcoef(x, y)[0, 1])
    if well_conditioned.any():
        beta[window - 1 :][well_conditioned] = (
            covariance[well_conditioned] / variance_y[well_conditioned]
        )
        correlation[window - 1 :][well_conditioned] = covariance[well_conditioned] / np.sqrt(
            variance_x[well_conditioned] * variance_y[well_conditioned]
        )
    return correlation, beta


def _pair_stats_reference(
    values: np.ndarray, anchor: np.ndarray, window: int
) -> tuple[np.ndarray, np.ndarray]:
    """Original per-index loop implementation of :func:`_pair_stats`.

    Retained exclusively as the equivalence-test reference for the
    vectorized production implementation.
    """
    correlation = np.full(len(values), np.nan)
    beta = np.full(len(values), np.nan)
    for index in range(window - 1, len(values)):
        left = values[index - window + 1 : index + 1]
        right = anchor[index - window + 1 : index + 1]
        valid = np.isfinite(left) & np.isfinite(right)
        if np.count_nonzero(valid) < window:
            continue
        x, y = left[valid], right[valid]
        variance = float(np.var(y, ddof=1))
        if variance <= 0 or np.ptp(x) == 0 or np.ptp(y) == 0:
            continue
        covariance = float(np.cov(x, y, ddof=1)[0, 1])
        beta[index] = covariance / variance
        correlation[index] = float(np.corrcoef(x, y)[0, 1])
    return correlation, beta


def _contiguous_segments(times: np.ndarray, step_us: int) -> tuple[np.ndarray, ...]:
    """Split a symbol history so rolling state cannot cross reported data gaps."""

    if not len(times):
        return ()
    boundaries = np.flatnonzero(np.diff(times) != step_us) + 1
    return tuple(segment for segment in np.split(np.arange(len(times)), boundaries) if len(segment))


def _segmented_higher_timeframe_values(
    table: pa.Table,
    interval: str,
) -> dict[str, np.ndarray]:
    """Reset every higher-timeframe transform at explicit source gaps."""

    times = _times(table, "open_time")
    outputs: dict[str, np.ndarray] = {}
    for segment in _contiguous_segments(times, interval_milliseconds(interval) * 1_000):
        selected = table.take(pa.array(segment, type=pa.int64()))
        values = _higher_timeframe_values(selected, interval)
        for name, value in values.items():
            outputs.setdefault(name, np.full(table.num_rows, np.nan))[segment] = value
    return outputs


def _asof_higher_context(
    symbols: np.ndarray,
    feature_times: np.ndarray,
    context: pa.Table | None,
) -> tuple[dict[str, np.ndarray], tuple[str, ...]]:
    if context is None:
        return {}, ()
    required = {"symbol", "availability_time"}
    if not required.issubset(context.column_names):
        raise ValueError("higher-timeframe context requires symbol and availability_time")
    columns = tuple(
        name
        for name in context.column_names
        if name.startswith("htf_12h_") or name.startswith("htf_1d_")
    )
    outputs = {name: np.full(len(symbols), np.nan) for name in columns}
    context_symbols = np.asarray(
        context.column("symbol").combine_chunks().to_pylist(), dtype=object
    )
    availability = _times(context, "availability_time")
    valid_until = (
        _times(context, "valid_until")
        if "valid_until" in context.column_names
        else np.full(context.num_rows, np.iinfo(np.int64).max, dtype=np.int64)
    )
    for symbol in sorted(set(symbols.tolist())):
        target_rows = np.flatnonzero(symbols == symbol)
        for name in columns:
            present = np.asarray(
                context.column(name).combine_chunks().is_valid().to_numpy(zero_copy_only=False)
            )
            source_rows = np.flatnonzero((context_symbols == symbol) & present)
            if not len(source_rows):
                continue
            order = source_rows[np.argsort(availability[source_rows], kind="mergesort")]
            source_times = availability[order]
            positions = np.searchsorted(source_times, feature_times[target_rows], side="right") - 1
            valid = positions >= 0
            positioned = np.maximum(positions, 0)
            valid &= feature_times[target_rows] < valid_until[order][positioned]
            source = _float_column(context, name)[order]
            outputs[name][target_rows[valid]] = source[positions[valid]]
            if np.any(source_times[positions[valid]] > feature_times[target_rows[valid]]):
                raise AssertionError("higher-timeframe as-of join crossed feature time")
    return outputs, columns


def build_higher_timeframe_context(
    candles_12h: pa.Table | None,
    candles_1d: pa.Table | None,
) -> pa.Table | None:
    """Build completed-candle context rows; feature joins remain causal as-of joins."""

    tables: list[pa.Table] = []
    for interval, source in (("12h", candles_12h), ("1d", candles_1d)):
        if source is None or not source.num_rows:
            continue
        if not {"symbol", "open_time"}.issubset(source.column_names):
            raise ValueError(f"{interval} context requires symbol and open_time")
        source_symbols = np.asarray(
            source.column("symbol").combine_chunks().to_pylist(), dtype=object
        )
        for symbol in sorted(set(source_symbols.tolist())):
            rows = np.flatnonzero(source_symbols == symbol)
            selected = source.take(pa.array(rows, type=pa.int64())).sort_by(
                [("open_time", "ascending")]
            )
            source_times = _times(selected, "open_time")
            values = _segmented_higher_timeframe_values(selected, interval)
            payload: dict[str, Any] = {
                "symbol": [str(symbol)] * selected.num_rows,
                "source_time": pa.array(source_times, type=pa.timestamp("us", tz="UTC")),
                "availability_time": pa.array(
                    source_times + interval_milliseconds(interval) * 1_000,
                    type=pa.timestamp("us", tz="UTC"),
                ),
                "valid_until": pa.array(
                    source_times + interval_milliseconds(interval) * 2_000,
                    type=pa.timestamp("us", tz="UTC"),
                ),
            }
            payload.update(values)
            tables.append(pa.table(payload))
    if not tables:
        return None
    return pa.concat_tables(tables, promote_options="default").sort_by(
        [("symbol", "ascending"), ("availability_time", "ascending")]
    )


def _anchor_array(
    symbols: np.ndarray,
    feature_times: np.ndarray,
    values: np.ndarray,
    anchor: str,
) -> np.ndarray:
    anchor_rows = np.flatnonzero(symbols == anchor)
    mapping = {int(feature_times[index]): float(values[index]) for index in anchor_rows}
    return np.asarray([mapping.get(int(timestamp), np.nan) for timestamp in feature_times])


def _cross_sectional_percentile(
    feature_times: np.ndarray, values: np.ndarray, active: np.ndarray
) -> np.ndarray:
    result = np.full(len(values), np.nan)
    for timestamp in np.unique(feature_times):
        rows = np.flatnonzero((feature_times == timestamp) & active & np.isfinite(values))
        if not len(rows):
            continue
        order = rows[np.argsort(values[rows], kind="mergesort")]
        denominator = max(1, len(order) - 1)
        result[order] = np.arange(len(order), dtype=np.float64) / denominator
    return result


def _market_context(
    symbols: np.ndarray,
    feature_times: np.ndarray,
    active: np.ndarray,
    returns: np.ndarray,
    volatility: np.ndarray,
    taker_flow: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[int, tuple[str, ...]]]:
    outputs = {name: np.full(len(symbols), np.nan) for name in MARKET_CONTEXT_COLUMNS}
    membership: dict[int, tuple[str, ...]] = {}
    for timestamp in np.unique(feature_times):
        rows = np.flatnonzero((feature_times == timestamp) & active)
        member_symbols = tuple(sorted(str(symbols[index]) for index in rows))
        membership[int(timestamp)] = member_symbols
        valid_return = rows[np.isfinite(returns[rows])]
        valid_volatility = rows[np.isfinite(volatility[rows])]
        valid_flow = rows[np.isfinite(taker_flow[rows])]
        if len(valid_return):
            values = returns[valid_return]
            outputs["market_mean_return"][rows] = float(np.mean(values))
            outputs["market_median_return"][rows] = float(np.median(values))
            outputs["market_pct_positive"][rows] = float(np.mean(values > 0))
            outputs["market_pct_negative"][rows] = float(np.mean(values < 0))
            outputs["market_return_dispersion"][rows] = float(np.std(values, ddof=0))
        if len(valid_volatility):
            outputs["market_median_volatility"][rows] = float(
                np.median(volatility[valid_volatility])
            )
        if len(valid_flow):
            outputs["market_median_taker_flow_imbalance"][rows] = float(
                np.median(taker_flow[valid_flow])
            )
        outputs["market_member_count"][rows] = len(rows)
    return outputs, membership


def validate_multiasset_primary_key(table: pa.Table) -> None:
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    times = _times(table, "feature_time")
    identities = [
        (str(symbol), int(timestamp)) for symbol, timestamp in zip(symbols, times, strict=True)
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate multi-asset primary key (symbol, feature_time)")


def bind_fold_cross_sectional_context(table: pa.Table) -> pa.Table:
    """Rebuild model-facing cross-sectional context from one frozen fold universe.

    The acquisition dataset can contain symbols admitted by later folds.  Its
    preview context must therefore never be consumed by a model.  This binding
    runs after fold eligibility filtering and replaces every universe-dependent
    value using only rows from that fold's frozen active-symbol set.
    """

    required = {
        "symbol",
        "feature_time",
        "return_5m",
        "realized_volatility_1h",
        "taker_flow_imbalance",
        *CROSS_SECTIONAL_SOURCE_COLUMNS,
        *MARKET_CONTEXT_COLUMNS,
        "trailing_liquidity_percentile",
        "trailing_volatility_percentile",
        "trade_intensity_percentile",
        "market_membership_hash",
    }
    missing = required - set(table.column_names)
    if missing:
        raise ValueError(f"fold context binding missing columns: {sorted(missing)}")
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    feature_times = _times(table, "feature_time")
    active = np.ones(table.num_rows, dtype=bool)
    replacements: dict[str, np.ndarray | list[str]] = {
        "trailing_liquidity_percentile": _cross_sectional_percentile(
            feature_times,
            _float_column(table, CROSS_SECTIONAL_SOURCE_COLUMNS[0]),
            active,
        ),
        "trailing_volatility_percentile": _cross_sectional_percentile(
            feature_times,
            _float_column(table, CROSS_SECTIONAL_SOURCE_COLUMNS[1]),
            active,
        ),
        "trade_intensity_percentile": _cross_sectional_percentile(
            feature_times,
            _float_column(table, CROSS_SECTIONAL_SOURCE_COLUMNS[2]),
            active,
        ),
    }
    market, membership = _market_context(
        symbols,
        feature_times,
        active,
        _float_column(table, "return_5m"),
        _float_column(table, "realized_volatility_1h"),
        _float_column(table, "taker_flow_imbalance"),
    )
    replacements.update(market)
    replacements["market_membership_hash"] = [
        hashlib.sha256("|".join(membership[int(timestamp)]).encode()).hexdigest()[:16]
        for timestamp in feature_times
    ]
    result = table
    for name, values in replacements.items():
        result = result.set_column(result.schema.get_field_index(name), name, pa.array(values))
    scope = pa.array(["FOLD_ACTIVE_SYMBOLS"] * result.num_rows)
    if "cross_sectional_context_scope" in result.column_names:
        result = result.set_column(
            result.schema.get_field_index("cross_sectional_context_scope"),
            "cross_sectional_context_scope",
            scope,
        )
    else:
        result = result.append_column("cross_sectional_context_scope", scope)
    validate_multiasset_primary_key(result)
    return result


def generate_multiasset_features(
    candles: pa.Table,
    *,
    registry: SymbolRegistry,
    config: FeatureConfig,
    higher_timeframe_context: pa.Table | None = None,
) -> MultiAssetFeatureResult:
    required = {
        "symbol",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        "trade_count",
        "taker_buy_quote_volume",
    }
    missing = required - set(candles.column_names)
    if missing:
        raise ValueError(f"multi-asset candles missing required columns: {sorted(missing)}")
    table = candles.sort_by([("symbol", "ascending"), ("open_time", "ascending")])
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    open_times = _times(table, "open_time")
    feature_times = open_times + interval_milliseconds("5m") * 1_000
    opens = _float_column(table, "open")
    highs = _float_column(table, "high")
    lows = _float_column(table, "low")
    closes = _float_column(table, "close")
    quote_volume = _float_column(table, "quote_volume")
    trade_count = _float_column(table, "trade_count")
    taker_buy_quote = _float_column(table, "taker_buy_quote_volume")
    if (
        np.any(quote_volume < 0)
        or np.any(taker_buy_quote < 0)
        or np.any(taker_buy_quote > quote_volume)
    ):
        raise ValueError("invalid quote/taker volume relationship")
    funding_all = _float_column(table, "funding_rate", optional=True)
    mark_all = _float_column(table, "mark_price", optional=True)
    index_all = _float_column(table, "index_price", optional=True)
    arrays = {name: np.full(table.num_rows, np.nan) for name in BASE_FEATURE_COLUMNS}
    trailing_liquidity = np.full(table.num_rows, np.nan)
    trade_intensity = np.full(table.num_rows, np.nan)
    for symbol in sorted(set(symbols.tolist())):
        rows = np.flatnonzero(symbols == symbol)
        if np.any(np.diff(open_times[rows]) <= 0):
            raise ValueError(f"{symbol} candle timestamps must be strictly increasing")
        for segment in _contiguous_segments(open_times[rows], interval_milliseconds("5m") * 1_000):
            selected = rows[segment]
            close = closes[selected]
            returns_5m = _lag_return(close, 1)
            returns_15m = _lag_return(close, 3)
            returns_30m = _lag_return(close, 6)
            returns_1h = _lag_return(close, 12)
            returns_4h = _lag_return(close, 48)
            log_returns = np.full(len(selected), np.nan)
            valid_log = np.isfinite(returns_5m) & (returns_5m > -1)
            log_returns[valid_log] = np.log1p(returns_5m[valid_log])
            vol_1h = _rolling_std(log_returns, 12)
            daily_vol = _rolling_std(log_returns, config.daily_volatility_rows)
            seven_day_vol = _rolling_std(log_returns, config.seven_day_volatility_rows)
            volume_mean = _rolling_mean(quote_volume[selected], config.liquidity_window_rows)
            trade_mean = _rolling_mean(trade_count[selected], config.liquidity_window_rows)
            volume_std = _rolling_std(quote_volume[selected], config.liquidity_window_rows)
            trade_std = _rolling_std(trade_count[selected], config.liquidity_window_rows)
            buy_share = _safe_divide(taker_buy_quote[selected], quote_volume[selected])
            sell_share = 1.0 - buy_share
            taker_flow = buy_share - sell_share
            ema20 = _ema(close, 20)
            values = {
                "return_5m": returns_5m,
                "return_15m": returns_15m,
                "return_30m": returns_30m,
                "return_1h": returns_1h,
                "return_4h": returns_4h,
                "range_pct": _safe_divide(highs[selected] - lows[selected], opens[selected]),
                "body_pct": _safe_divide(closes[selected] - opens[selected], opens[selected]),
                "atr14_pct": _atr_pct(highs[selected], lows[selected], close),
                "ema20_distance_pct": _safe_divide(close, ema20) - 1.0,
                "realized_volatility_1h": vol_1h,
                "daily_volatility": daily_vol,
                "seven_day_volatility": seven_day_vol,
                "relative_quote_volume": _safe_divide(quote_volume[selected], volume_mean),
                "volume_zscore": _safe_divide(quote_volume[selected] - volume_mean, volume_std),
                "trade_count_zscore": _safe_divide(trade_count[selected] - trade_mean, trade_std),
                "taker_buy_share": buy_share,
                "taker_sell_share": sell_share,
                "taker_flow_imbalance": taker_flow,
                "funding_zscore": _rolling_zscore(
                    funding_all[selected], config.liquidity_window_rows
                ),
                "mark_index_basis": _safe_divide(mark_all[selected], index_all[selected]) - 1.0,
                "contract_mark_basis": _safe_divide(close, mark_all[selected]) - 1.0,
                "return_5m_over_ex_ante_vol": _safe_divide(returns_5m, vol_1h),
                "return_1h_over_daily_vol": _safe_divide(returns_1h, daily_vol),
                "return_4h_over_7d_vol": _safe_divide(returns_4h, seven_day_vol),
            }
            for name, value in values.items():
                arrays[name][selected] = value
            trailing_liquidity[selected] = volume_mean
            trade_intensity[selected] = _safe_divide(trade_count[selected], trade_mean)
    registry_by_symbol = registry.by_symbol()
    active = np.asarray(
        [
            str(symbol) in registry_by_symbol
            and registry_by_symbol[str(symbol)].exists_at(
                datetime.fromtimestamp(int(timestamp) / 1_000_000, tz=UTC)
            )
            for symbol, timestamp in zip(symbols, feature_times, strict=True)
        ],
        dtype=bool,
    )
    coin_context = {name: np.full(table.num_rows, np.nan) for name in COIN_CONTEXT_COLUMNS}
    for index, (symbol, timestamp) in enumerate(zip(symbols, feature_times, strict=True)):
        record = registry_by_symbol.get(str(symbol))
        if record is None or not active[index]:
            continue
        current = datetime.fromtimestamp(int(timestamp) / 1_000_000, tz=UTC)
        coin_context["listing_age_days"][index] = (
            current - record.causal_available_from
        ).total_seconds() / 86_400
        coin_context["history_length_days"][index] = (
            current - record.causal_available_from
        ).total_seconds() / 86_400
    coin_context["trailing_liquidity_percentile"] = _cross_sectional_percentile(
        feature_times, trailing_liquidity, active
    )
    coin_context["trailing_volatility_percentile"] = _cross_sectional_percentile(
        feature_times, arrays["seven_day_volatility"], active
    )
    coin_context["trade_intensity_percentile"] = _cross_sectional_percentile(
        feature_times, trade_intensity, active
    )
    anchor_context = {name: np.full(table.num_rows, np.nan) for name in ANCHOR_CONTEXT_COLUMNS}
    anchor_mapping = {
        "btc_return_5m": ("return_5m", "BTCUSDT"),
        "btc_return_15m": ("return_15m", "BTCUSDT"),
        "btc_return_30m": ("return_30m", "BTCUSDT"),
        "btc_return_1h": ("return_1h", "BTCUSDT"),
        "btc_return_4h": ("return_4h", "BTCUSDT"),
        "btc_volatility_1h": ("realized_volatility_1h", "BTCUSDT"),
        "btc_taker_flow_imbalance": ("taker_flow_imbalance", "BTCUSDT"),
        "eth_return_5m": ("return_5m", "ETHUSDT"),
        "eth_return_1h": ("return_1h", "ETHUSDT"),
        "eth_return_4h": ("return_4h", "ETHUSDT"),
        "eth_volatility_1h": ("realized_volatility_1h", "ETHUSDT"),
    }
    for name, (source, anchor) in anchor_mapping.items():
        anchor_context[name] = _anchor_array(symbols, feature_times, arrays[source], anchor)
    for symbol in sorted(set(symbols.tolist())):
        rows = np.flatnonzero(symbols == symbol)
        btc_corr, btc_beta = _pair_stats(
            arrays["return_5m"][rows],
            anchor_context["btc_return_5m"][rows],
            config.correlation_window_rows,
        )
        eth_corr, _ = _pair_stats(
            arrays["return_5m"][rows],
            anchor_context["eth_return_5m"][rows],
            config.correlation_window_rows,
        )
        coin_context["btc_correlation"][rows] = btc_corr
        coin_context["btc_beta"][rows] = btc_beta
        coin_context["eth_correlation"][rows] = eth_corr
        coin_context["relative_strength_vs_btc"][rows] = (
            arrays["return_1h"][rows] - anchor_context["btc_return_1h"][rows]
        )
        coin_context["relative_strength_vs_eth"][rows] = (
            arrays["return_1h"][rows] - anchor_context["eth_return_1h"][rows]
        )
        coin_context["beta_adjusted_residual_return"][rows] = arrays["return_1h"][rows] - (
            btc_beta * anchor_context["btc_return_1h"][rows]
        )
    market_context, membership = _market_context(
        symbols,
        feature_times,
        active,
        arrays["return_5m"],
        arrays["realized_volatility_1h"],
        arrays["taker_flow_imbalance"],
    )
    higher, higher_columns = _asof_higher_context(symbols, feature_times, higher_timeframe_context)
    if not config.include_12h:
        higher_columns = tuple(name for name in higher_columns if not name.startswith("htf_12h_"))
    if not config.include_1d:
        higher_columns = tuple(name for name in higher_columns if not name.startswith("htf_1d_"))
    feature_columns = (
        BASE_FEATURE_COLUMNS
        + COIN_CONTEXT_COLUMNS
        + ANCHOR_CONTEXT_COLUMNS
        + MARKET_CONTEXT_COLUMNS
        + higher_columns
    )
    payload: dict[str, Any] = {
        "symbol": symbols.tolist(),
        "open_time": pa.array(open_times, type=pa.timestamp("us", tz="UTC")),
        "feature_time": pa.array(feature_times, type=pa.timestamp("us", tz="UTC")),
        "feature_version": [FEATURE_VERSION] * table.num_rows,
        "market_context_version": [MARKET_CONTEXT_VERSION] * table.num_rows,
        "cross_sectional_context_scope": ["ACQUISITION_UNION_PREVIEW"] * table.num_rows,
        "market_membership_hash": [
            hashlib.sha256("|".join(membership[int(timestamp)]).encode()).hexdigest()[:16]
            for timestamp in feature_times
        ],
    }
    payload[CROSS_SECTIONAL_SOURCE_COLUMNS[0]] = trailing_liquidity
    payload[CROSS_SECTIONAL_SOURCE_COLUMNS[1]] = arrays["seven_day_volatility"]
    payload[CROSS_SECTIONAL_SOURCE_COLUMNS[2]] = trade_intensity
    for name in BASE_FEATURE_COLUMNS:
        payload[name] = arrays[name]
    payload.update(coin_context)
    payload.update(anchor_context)
    payload.update(market_context)
    for name in higher_columns:
        payload[name] = higher[name]
    result = pa.table(payload).sort_by([("feature_time", "ascending"), ("symbol", "ascending")])
    validate_multiasset_primary_key(result)
    return MultiAssetFeatureResult(
        table=result,
        feature_columns=feature_columns,
        feature_version=FEATURE_VERSION,
        market_context_version=MARKET_CONTEXT_VERSION,
        market_membership=membership,
    )
