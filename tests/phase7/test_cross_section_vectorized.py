"""Reference-equivalence tests for the vectorized cross-sectional statistics."""

from __future__ import annotations

import time

import numpy as np
import pytest

from crypto_ai.phase7 import cross_section as cs

MARKET_COLUMNS = cs.MARKET_CONTEXT_OUTPUTS


def reference_percentile(feature_times, values, active):
    """Legacy O(T x N) implementation, kept verbatim as the oracle."""
    result = np.full(len(values), np.nan)
    for timestamp in np.unique(feature_times):
        rows = np.flatnonzero((feature_times == timestamp) & active & np.isfinite(values))
        if not len(rows):
            continue
        order = rows[np.argsort(values[rows], kind="mergesort")]
        denominator = max(1, len(order) - 1)
        result[order] = np.arange(len(order), dtype=np.float64) / denominator
    return result


def reference_market(symbols, feature_times, active, returns, volatility, taker_flow):
    outputs = {name: np.full(len(symbols), np.nan) for name in MARKET_COLUMNS}
    membership = {}
    for timestamp in np.unique(feature_times):
        rows = np.flatnonzero((feature_times == timestamp) & active)
        membership[int(timestamp)] = tuple(sorted(str(symbols[index]) for index in rows))
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


def synthetic(rows_per_time=20, times=50, seed=0, ties=True, holes=True):
    rng = np.random.default_rng(seed)
    n = rows_per_time * times
    feature_times = np.repeat(np.arange(times, dtype=np.int64) * 300_000_000, rows_per_time)
    symbols = np.asarray([f"S{i % rows_per_time:02d}USDT" for i in range(n)], dtype=object)
    values = rng.normal(size=n)
    if ties:
        values = np.round(values, 1)  # many exact ties
    returns = rng.normal(scale=0.01, size=n)
    volatility = np.abs(rng.normal(size=n))
    flow = rng.uniform(-1, 1, size=n)
    active = np.ones(n, dtype=bool)
    if holes:
        for array in (values, returns, volatility, flow):
            array[rng.random(n) < 0.1] = np.nan
        values[rng.random(n) < 0.02] = np.inf
        active = rng.random(n) > 0.15
        # one timestamp with no active rows and one with a single member
        active[feature_times == feature_times[0]] = False
        mask = feature_times == feature_times[rows_per_time]
        active[mask] = False
        active[np.flatnonzero(mask)[0]] = True
    # shuffle so rows are not grouped by time (production order is not guaranteed)
    perm = rng.permutation(n)
    return (
        symbols[perm],
        feature_times[perm],
        active[perm],
        values[perm],
        returns[perm],
        volatility[perm],
        flow[perm],
    )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("ties", [True, False])
def test_percentile_matches_reference_exactly(seed, ties):
    _, times, active, values, *_ = synthetic(seed=seed, ties=ties)
    expected = reference_percentile(times, values, active)
    actual = cs.cross_sectional_percentile(times, values, active)
    np.testing.assert_array_equal(actual, expected)


def test_percentile_edge_cases():
    times = np.array([1, 1, 2, 3, 3, 3], dtype=np.int64)
    values = np.array([5.0, np.nan, 7.0, 1.0, 1.0, 1.0])
    active = np.array([True, True, True, True, True, True])
    expected = reference_percentile(times, values, active)
    actual = cs.cross_sectional_percentile(times, values, active)
    np.testing.assert_array_equal(actual, expected)
    # single finite member -> rank 0; three-way tie keeps original order 0, .5, 1
    assert actual[0] == 0.0 and actual[2] == 0.0
    np.testing.assert_array_equal(actual[3:], [0.0, 0.5, 1.0])
    assert np.isnan(actual[1])
    empty = cs.cross_sectional_percentile(
        np.array([], dtype=np.int64), np.array([]), np.array([], dtype=bool)
    )
    assert empty.shape == (0,)


@pytest.mark.parametrize("seed", range(6))
def test_market_context_matches_reference(seed):
    symbols, times, active, _, returns, volatility, flow = synthetic(seed=seed)
    expected, expected_membership = reference_market(
        symbols, times, active, returns, volatility, flow
    )
    actual, membership = cs.market_context(symbols, times, active, returns, volatility, flow)
    assert membership == expected_membership
    for name in MARKET_COLUMNS:
        # Counts, fractions and medians are exact; mean/std may differ by summation order.
        if name in {"market_mean_return", "market_return_dispersion"}:
            np.testing.assert_allclose(actual[name], expected[name], rtol=1e-12, atol=1e-15)
        else:
            np.testing.assert_array_equal(actual[name], expected[name])


def test_market_context_row_order_invariance():
    symbols, times, active, _, returns, volatility, flow = synthetic(seed=3)
    base, base_members = cs.market_context(symbols, times, active, returns, volatility, flow)
    perm = np.random.default_rng(9).permutation(len(symbols))
    shuffled, members = cs.market_context(
        symbols[perm], times[perm], active[perm], returns[perm], volatility[perm], flow[perm]
    )
    assert members == base_members
    for name in MARKET_COLUMNS:
        np.testing.assert_allclose(shuffled[name], base[name][perm], rtol=1e-12, equal_nan=True)


def test_benchmark_fixture_is_not_quadratic():
    """Equivalence on a larger fixture plus a generous timing bound.

    The reference is O(T x N); on 4,000 timestamps x 20 rows it already takes
    seconds, while the grouped implementation stays well under that.  The bound is
    deliberately loose so it cannot flake; measured numbers go in the report.
    """
    symbols, times, active, values, returns, volatility, flow = synthetic(
        rows_per_time=20, times=4000, seed=1
    )
    start = time.perf_counter()
    expected = reference_percentile(times, values, active)
    reference_seconds = time.perf_counter() - start
    start = time.perf_counter()
    actual = cs.cross_sectional_percentile(times, values, active)
    start_market = time.perf_counter()
    cs.market_context(symbols, times, active, returns, volatility, flow)
    vector_seconds = time.perf_counter() - start
    np.testing.assert_array_equal(actual, expected)
    assert vector_seconds < max(1.0, reference_seconds)
    del start_market
