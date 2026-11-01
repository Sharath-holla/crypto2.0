"""Grouped, vectorized cross-sectional statistics for Phase 7 (pure NumPy).

These replace per-timestamp Python loops that scanned the whole array once per
unique timestamp (O(unique_timestamps x rows)).  Everything here is
O(rows log rows) and keeps the legacy semantics exactly:

* percentile rank = position / max(1, n - 1) after a *stable* ascending sort,
  so ties are broken by original row order (identical to ``mergesort``);
* non-finite and inactive rows are excluded and receive NaN;
* medians use the same middle-element / mean-of-two-middle arithmetic;
* ``market_member_count`` counts every active row at the timestamp, finite or not;
* membership is the sorted tuple of active symbols per timestamp.

The module deliberately imports only NumPy so it can be unit-tested and
benchmarked without pyarrow.
"""

from __future__ import annotations

import numpy as np

MARKET_CONTEXT_OUTPUTS = (
    "market_mean_return",
    "market_median_return",
    "market_pct_positive",
    "market_pct_negative",
    "market_return_dispersion",
    "market_median_volatility",
    "market_median_taker_flow_imbalance",
    "market_member_count",
)


def _stable_group_order(group: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Indices ordering by (group, value) with ties kept in original order."""
    return np.lexsort((values, group))


def cross_sectional_percentile(
    feature_times: np.ndarray, values: np.ndarray, active: np.ndarray
) -> np.ndarray:
    result = np.full(len(values), np.nan)
    eligible = np.flatnonzero(active & np.isfinite(values))
    if not len(eligible):
        return result
    _, group = np.unique(feature_times[eligible], return_inverse=True)
    group = group.reshape(-1)
    order = _stable_group_order(group, values[eligible])
    sorted_group = group[order]
    counts = np.bincount(sorted_group)
    starts = np.cumsum(counts) - counts
    position = np.arange(len(order), dtype=np.float64) - starts[sorted_group]
    denominator = np.maximum(1, counts - 1).astype(np.float64)[sorted_group]
    result[eligible[order]] = position / denominator
    return result


def _group_median(
    group: np.ndarray, values: np.ndarray, group_count: int
) -> tuple[np.ndarray, np.ndarray]:
    """Median per group for finite ``values``; returns (median, count)."""
    median = np.full(group_count, np.nan)
    if not len(values):
        return median, np.zeros(group_count, dtype=np.int64)
    order = _stable_group_order(group, values)
    sorted_values = values[order]
    counts = np.bincount(group, minlength=group_count)
    starts = np.cumsum(counts) - counts
    present = counts > 0
    low = starts[present] + (counts[present] - 1) // 2
    high = starts[present] + counts[present] // 2
    median[present] = (sorted_values[low] + sorted_values[high]) / 2.0
    return median, counts


def market_context(
    symbols: np.ndarray,
    feature_times: np.ndarray,
    active: np.ndarray,
    returns: np.ndarray,
    volatility: np.ndarray,
    taker_flow: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[int, tuple[str, ...]]]:
    rows_total = len(symbols)
    outputs = {name: np.full(rows_total, np.nan) for name in MARKET_CONTEXT_OUTPUTS}
    membership: dict[int, tuple[str, ...]] = {}
    unique_times, inverse = np.unique(feature_times, return_inverse=True)
    inverse = inverse.reshape(-1)
    group_count = len(unique_times)
    active_rows = np.flatnonzero(active)

    # Membership: sorted symbols of active rows per timestamp.  Symbols are mapped
    # to integer codes whose order equals ``sorted(str)`` order; identical
    # memberships (the common case) share one tuple object.
    for position in range(group_count):
        membership[int(unique_times[position])] = ()
    if len(active_rows):
        names = np.asarray([str(item) for item in symbols[active_rows]], dtype=object) if (
            symbols.dtype != object
        ) else symbols[active_rows]
        vocabulary, codes = np.unique(names.astype(str), return_inverse=True)
        codes = codes.reshape(-1)
        active_group = inverse[active_rows]
        order = np.lexsort((codes, active_group))
        sorted_group = active_group[order]
        sorted_codes = codes[order]
        counts = np.bincount(sorted_group, minlength=group_count)
        starts = np.cumsum(counts) - counts
        vocabulary_list = vocabulary.tolist()
        cache: dict[bytes, tuple[str, ...]] = {}
        for position in np.flatnonzero(counts):
            start = int(starts[position])
            chunk = sorted_codes[start : start + int(counts[position])]
            key = chunk.tobytes()
            members = cache.get(key)
            if members is None:
                members = tuple(vocabulary_list[code] for code in chunk.tolist())
                cache[key] = members
            membership[int(unique_times[position])] = members
    member_count = np.bincount(inverse[active_rows], minlength=group_count).astype(np.float64)
    outputs["market_member_count"][active_rows] = member_count[inverse[active_rows]]

    def finite_rows(source: np.ndarray) -> np.ndarray:
        return active_rows[np.isfinite(source[active_rows])]

    valid_return = finite_rows(returns)
    if len(valid_return):
        group = inverse[valid_return]
        values = returns[valid_return]
        counts = np.bincount(group, minlength=group_count)
        has = counts > 0
        safe = np.where(has, counts, 1).astype(np.float64)
        mean = np.bincount(group, weights=values, minlength=group_count) / safe
        median, _ = _group_median(group, values, group_count)
        positive = np.bincount(group, weights=(values > 0).astype(np.float64), minlength=group_count)
        negative = np.bincount(group, weights=(values < 0).astype(np.float64), minlength=group_count)
        deviation = values - mean[group]
        variance = np.bincount(group, weights=deviation * deviation, minlength=group_count) / safe
        stats = {
            "market_mean_return": mean,
            "market_median_return": median,
            "market_pct_positive": positive / safe,
            "market_pct_negative": negative / safe,
            "market_return_dispersion": np.sqrt(variance),
        }
        target_rows = active_rows[has[inverse[active_rows]]]
        for name, per_group in stats.items():
            per_group = np.where(has, per_group, np.nan)
            outputs[name][target_rows] = per_group[inverse[target_rows]]
    for name, source in (
        ("market_median_volatility", volatility),
        ("market_median_taker_flow_imbalance", taker_flow),
    ):
        valid = finite_rows(source)
        if not len(valid):
            continue
        median, counts = _group_median(inverse[valid], source[valid], group_count)
        has = counts > 0
        target_rows = active_rows[has[inverse[active_rows]]]
        outputs[name][target_rows] = median[inverse[target_rows]]
    return outputs, membership
