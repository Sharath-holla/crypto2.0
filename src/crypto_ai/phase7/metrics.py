from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.research.metrics import regression_metrics


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or np.ptp(left) == 0 or np.ptp(right) == 0:
        return None
    value = float(np.corrcoef(_average_ranks(left), _average_ranks(right))[0, 1])
    return value if np.isfinite(value) else None


def _macro_average(per_symbol: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "mae",
        "rmse",
        "r2",
        "directional_accuracy",
        "pearson_ic",
        "spearman_ic",
    )
    result: dict[str, Any] = {"symbol_count": len(per_symbol)}
    for field in fields:
        values = [item[field] for item in per_symbol.values() if item.get(field) is not None]
        result[field] = float(np.mean(values)) if values else None
    return result


def cross_sectional_ic(
    feature_times_us: np.ndarray,
    symbols: np.ndarray,
    actual: np.ndarray,
    predicted: np.ndarray,
    *,
    minimum_assets: int = 3,
) -> dict[str, Any]:
    times = np.asarray(feature_times_us, dtype=np.int64)
    assets = np.asarray(symbols, dtype=object)
    actual = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)
    values: list[float] = []
    timestamp_rows: list[dict[str, Any]] = []
    for timestamp in np.unique(times):
        rows = np.flatnonzero((times == timestamp) & np.isfinite(actual) & np.isfinite(predicted))
        if len(set(assets[rows].tolist())) < minimum_assets:
            continue
        value = _spearman(actual[rows], predicted[rows])
        if value is not None:
            values.append(value)
            timestamp_rows.append(
                {"feature_time_us": int(timestamp), "asset_count": len(rows), "spearman_ic": value}
            )
    return {
        "timestamp_count": len(values),
        "mean_spearman_ic": float(np.mean(values)) if values else None,
        "median_spearman_ic": float(np.median(values)) if values else None,
        "positive_timestamp_fraction": float(np.mean(np.asarray(values) > 0)) if values else None,
        "timestamps": timestamp_rows,
    }


def evaluate_predictions(
    table: pa.Table,
    predicted: np.ndarray,
    covered: np.ndarray,
    *,
    target_column: str,
    cluster_mapping: dict[str, int] | None = None,
    age_bucket_mapping: dict[str, str] | None = None,
    eligibility_reasons: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actual = np.asarray(table.column(target_column).combine_chunks().to_pylist(), dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)
    covered = np.asarray(covered, dtype=bool)
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    valid = covered & np.isfinite(actual) & np.isfinite(predicted)
    if not np.any(valid):
        raise ValueError("prediction evaluation has no covered finite rows")
    per_symbol: dict[str, dict[str, Any]] = {}
    for symbol in sorted(str(value) for value in np.unique(symbols[valid])):
        rows = valid & (symbols == symbol)
        per_symbol[symbol] = regression_metrics(actual[rows], predicted[rows])
    cluster_mapping = cluster_mapping or {}
    per_cluster: dict[str, dict[str, Any]] = {}
    for cluster in sorted(set(cluster_mapping.values())):
        cluster_symbols = {symbol for symbol, value in cluster_mapping.items() if value == cluster}
        rows = valid & np.asarray([str(symbol) in cluster_symbols for symbol in symbols])
        if np.any(rows):
            per_cluster[str(cluster)] = regression_metrics(actual[rows], predicted[rows])
    age_bucket_mapping = age_bucket_mapping or {}
    per_age_bucket: dict[str, dict[str, Any]] = {}
    age_bucket_coverage: dict[str, dict[str, Any]] = {}
    for bucket in sorted(set(age_bucket_mapping.values())):
        bucket_symbols = {symbol for symbol, value in age_bucket_mapping.items() if value == bucket}
        available_rows = np.asarray([str(symbol) in bucket_symbols for symbol in symbols])
        rows = valid & available_rows
        if np.any(rows):
            per_age_bucket[bucket] = regression_metrics(actual[rows], predicted[rows])
        age_bucket_coverage[bucket] = {
            "symbols": sorted(bucket_symbols & set(str(item) for item in symbols.tolist())),
            "available_rows": int(np.count_nonzero(available_rows)),
            "covered_rows": int(np.count_nonzero(rows)),
        }
    available_symbols = sorted(str(value) for value in np.unique(symbols))
    covered_symbols = sorted(per_symbol)
    excluded_symbols = [symbol for symbol in available_symbols if symbol not in per_symbol]
    eligibility_reasons = eligibility_reasons or {}
    young_symbols: set[str] = set()
    if "listing_age_days" in table.column_names:
        ages = np.asarray(
            table.column("listing_age_days").combine_chunks().to_pylist(), dtype=np.float64
        )
        for symbol in available_symbols:
            symbol_ages = ages[(symbols == symbol) & np.isfinite(ages)]
            if len(symbol_ages) and float(np.min(symbol_ages)) < 730.0:
                young_symbols.add(symbol)
    return {
        "micro": regression_metrics(actual[valid], predicted[valid]),
        "macro": _macro_average(per_symbol),
        "per_symbol": per_symbol,
        "per_cluster": per_cluster,
        "per_age_bucket": per_age_bucket,
        "cross_sectional_ic": cross_sectional_ic(
            times[valid], symbols[valid], actual[valid], predicted[valid]
        ),
        "coverage": {
            "oos_rows": int(np.count_nonzero(valid)),
            "available_rows": table.num_rows,
            "coverage_ratio": float(np.mean(valid)),
            "symbols_covered": len(per_symbol),
            "symbols_available": len(set(symbols.tolist())),
            "covered_symbol_names": covered_symbols,
            "excluded_symbols": [
                {
                    "symbol": symbol,
                    "reason": eligibility_reasons.get(symbol, {"status": "NO_ESTIMATOR_COVERAGE"}),
                }
                for symbol in excluded_symbols
            ],
            "rows_covered_by_symbol": {
                symbol: int(np.count_nonzero(valid & (symbols == symbol)))
                for symbol in available_symbols
            },
            "young_symbol_definition_days": 730,
            "young_symbols_available": sorted(young_symbols),
            "young_symbols_covered": sorted(young_symbols & set(covered_symbols)),
            "age_buckets_as_of_fold_train_end": age_bucket_coverage,
        },
    }


def asset_concentration(
    symbols: np.ndarray,
    contributions: np.ndarray,
) -> dict[str, Any]:
    symbols = np.asarray(symbols, dtype=object)
    contributions = np.asarray(contributions, dtype=np.float64)
    if symbols.shape != contributions.shape or symbols.ndim != 1:
        raise ValueError("asset concentration inputs must be matching vectors")
    totals = {
        str(symbol): float(np.sum(contributions[symbols == symbol]))
        for symbol in np.unique(symbols)
    }
    absolute_total = float(np.sum(np.abs(list(totals.values()))))
    ordered = sorted(totals.items(), key=lambda item: abs(item[1]), reverse=True)

    def share(count: int) -> float | None:
        if not absolute_total:
            return None
        return float(sum(abs(value) for _, value in ordered[:count]) / absolute_total)

    return {
        "by_symbol": totals,
        "top_1_symbol_contribution": share(1),
        "top_5_symbol_contribution": share(5),
        "negative_symbol_count": sum(value < 0 for value in totals.values()),
    }


def time_concentration(
    feature_times_us: np.ndarray,
    contributions: np.ndarray,
) -> dict[str, Any]:
    times = np.asarray(feature_times_us, dtype=np.int64)
    values = np.asarray(contributions, dtype=np.float64)
    if times.shape != values.shape or times.ndim != 1:
        raise ValueError("time concentration inputs must be matching vectors")
    by_month: dict[str, float] = {}
    by_year: dict[str, float] = {}
    for timestamp, contribution in zip(times, values, strict=True):
        current = datetime.fromtimestamp(int(timestamp) / 1_000_000, tz=UTC)
        month, year = current.strftime("%Y-%m"), str(current.year)
        by_month[month] = by_month.get(month, 0.0) + float(contribution)
        by_year[year] = by_year.get(year, 0.0) + float(contribution)

    def largest_share(items: dict[str, float]) -> float | None:
        total = float(np.sum(np.abs(list(items.values()))))
        return max((abs(value) for value in items.values()), default=0.0) / total if total else None

    return {
        "by_month": by_month,
        "by_year": by_year,
        "top_month_absolute_contribution": largest_share(by_month),
        "top_year_absolute_contribution": largest_share(by_year),
        "negative_month_count": sum(value < 0 for value in by_month.values()),
        "negative_year_count": sum(value < 0 for value in by_year.values()),
    }
