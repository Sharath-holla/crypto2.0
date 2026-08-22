from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import CostConfig

ThresholdGranularity = Literal["global", "cluster", "per_coin"]


@dataclass(frozen=True, slots=True)
class ThresholdSet:
    granularity: ThresholdGranularity
    values_bps: dict[str, float | None]
    selection_source: str = "CAL_B_ONLY"


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _values(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _tier_cost_bps(tier: str, config: CostConfig) -> float:
    mapping = {
        "HIGH_LIQUIDITY": config.high_liquidity,
        "MEDIUM_LIQUIDITY": config.medium_liquidity,
        "LOWER_LIQUIDITY": config.lower_liquidity,
    }
    if tier not in mapping:
        raise ValueError(f"unknown liquidity tier: {tier}")
    return mapping[tier].round_trip_bps


def _threshold_key(
    symbol: str,
    granularity: ThresholdGranularity,
    cluster_mapping: dict[str, int],
) -> str:
    if granularity == "global":
        return "global"
    if granularity == "cluster":
        cluster = cluster_mapping.get(symbol)
        return f"cluster:{cluster}" if cluster is not None else "cluster:missing"
    return f"symbol:{symbol}"


def select_cal_b_thresholds(
    table: pa.Table,
    predictions: np.ndarray,
    *,
    target_column: str,
    liquidity_tiers: dict[str, str],
    cluster_mapping: dict[str, int],
    granularity: ThresholdGranularity,
    config: CostConfig,
) -> tuple[ThresholdSet, dict[str, Any]]:
    predicted = np.asarray(predictions, dtype=np.float64)
    actual = _values(table, target_column)
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    if predicted.shape != actual.shape or not np.all(np.isfinite(predicted)):
        raise ValueError("Cal-B predictions must be finite and aligned")
    groups: dict[str, list[int]] = {}
    for index, symbol_value in enumerate(symbols):
        symbol = str(symbol_value)
        key = _threshold_key(symbol, granularity, cluster_mapping)
        groups.setdefault(key, []).append(index)
    values: dict[str, float | None] = {}
    diagnostics: dict[str, Any] = {}
    for key, positions in sorted(groups.items()):
        indices = np.asarray(positions, dtype=np.int64)
        candidates: list[dict[str, Any]] = []
        for threshold in config.threshold_grid_bps:
            selected: list[int] = []
            for index in indices:
                symbol = str(symbols[index])
                cost = _tier_cost_bps(liquidity_tiers[symbol], config)
                if abs(predicted[index]) * 10_000 >= cost + threshold:
                    selected.append(int(index))
            if selected:
                chosen = np.asarray(selected, dtype=np.int64)
                gross = np.sign(predicted[chosen]) * actual[chosen]
                costs = np.asarray(
                    [
                        _tier_cost_bps(liquidity_tiers[str(symbols[index])], config) / 10_000
                        for index in chosen
                    ]
                )
                expectancy = float(np.mean(gross - costs))
            else:
                expectancy = None
            candidates.append(
                {
                    "threshold_bps": threshold,
                    "trade_count": len(selected),
                    "expectancy": expectancy,
                    "eligible": len(selected) >= config.minimum_calibration_trades,
                }
            )
        eligible = [item for item in candidates if item["eligible"]]
        if eligible:
            winner = max(
                eligible,
                key=lambda item: (item["expectancy"], item["threshold_bps"]),
            )
            values[key] = float(winner["threshold_bps"])
        else:
            values[key] = None
        diagnostics[key] = {"candidates": candidates, "selected_bps": values[key]}
    return ThresholdSet(granularity=granularity, values_bps=values), {
        "selection_source": "CAL_B_ONLY",
        "cost_assumption_classification": config.assumption_classification,
        "groups": diagnostics,
    }


def build_oos_trades(
    table: pa.Table,
    predictions: np.ndarray,
    thresholds: ThresholdSet,
    *,
    target_column: str,
    liquidity_tiers: dict[str, str],
    cluster_mapping: dict[str, int],
    horizon_minutes: int,
    config: CostConfig,
    cost_multiplier: float = 1.0,
) -> pa.Table:
    if cost_multiplier < 0:
        raise ValueError("cost multiplier must be non-negative")
    predicted = np.asarray(predictions, dtype=np.float64)
    actual = _values(table, target_column)
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    feature_times = _times(table, "feature_time")
    entry_times = (
        _times(table, "entry_time") if "entry_time" in table.column_names else feature_times
    )
    label_end_times = _times(table, "label_end_time")
    rows: list[dict[str, Any]] = []
    active_until: dict[str, int] = {}
    order = np.argsort(feature_times, kind="mergesort")
    for index in order:
        if not np.isfinite(predicted[index]) or not np.isfinite(actual[index]):
            continue
        symbol = str(symbols[index])
        key = _threshold_key(symbol, thresholds.granularity, cluster_mapping)
        threshold = thresholds.values_bps.get(key)
        if threshold is None or feature_times[index] < active_until.get(symbol, -1):
            continue
        tier = liquidity_tiers[symbol]
        cost_bps = _tier_cost_bps(tier, config) * cost_multiplier
        if abs(predicted[index]) * 10_000 < cost_bps + threshold:
            continue
        direction = 1 if predicted[index] > 0 else -1
        gross = direction * actual[index]
        trade_id = hashlib.sha256(
            f"{symbol}|{int(entry_times[index])}|{int(label_end_times[index])}|{direction}".encode()
        ).hexdigest()[:24]
        rows.append(
            {
                "trade_id": trade_id,
                "symbol": symbol,
                "feature_time": int(feature_times[index]),
                "entry_time": int(entry_times[index]),
                "exit_time": int(label_end_times[index]),
                "direction": direction,
                "liquidity_tier": tier,
                "predicted_raw_return": float(predicted[index]),
                "gross_return": float(gross),
                "base_cost_bps": cost_bps,
                "net_return": float(gross - cost_bps / 10_000),
            }
        )
        active_until[symbol] = int(feature_times[index] + horizon_minutes * 60_000_000)
    return pa.Table.from_pylist(rows)


def fixed_policy_cost_stress(trades: pa.Table, config: CostConfig) -> dict[str, Any]:
    if trades.num_rows == 0:
        return {
            str(multiplier): {
                "trade_count": 0,
                "trade_identity_hash": hashlib.sha256(b"").hexdigest(),
                "summed_net_return": 0.0,
                "expectancy": None,
                "cost_assumption_classification": config.assumption_classification,
            }
            for multiplier in config.fixed_policy_multipliers
        }
    trade_ids = trades.column("trade_id").combine_chunks().to_pylist()
    identity = hashlib.sha256("|".join(trade_ids).encode()).hexdigest()
    gross = _values(trades, "gross_return")
    costs = _values(trades, "base_cost_bps") / 10_000
    result: dict[str, Any] = {}
    previous = float("inf")
    for multiplier in config.fixed_policy_multipliers:
        net = gross - costs * multiplier
        summed = float(np.sum(net))
        if summed > previous + 1e-15:
            raise AssertionError("fixed-policy net return improved under higher adverse costs")
        previous = summed
        result[str(multiplier)] = {
            "trade_count": trades.num_rows,
            "trade_identity_hash": identity,
            "summed_net_return": summed,
            "expectancy": float(np.mean(net)),
            "cost_assumption_classification": config.assumption_classification,
        }
    return result


def adaptive_policy_cost_stress(
    table: pa.Table,
    predictions: np.ndarray,
    thresholds: ThresholdSet,
    *,
    target_column: str,
    liquidity_tiers: dict[str, str],
    cluster_mapping: dict[str, int],
    horizon_minutes: int,
    config: CostConfig,
) -> dict[str, Any]:
    """Apply the frozen threshold policy when the assumed cost is known in advance."""

    result: dict[str, Any] = {}
    for multiplier in config.fixed_policy_multipliers:
        trades = build_oos_trades(
            table,
            predictions,
            thresholds,
            target_column=target_column,
            liquidity_tiers=liquidity_tiers,
            cluster_mapping=cluster_mapping,
            horizon_minutes=horizon_minutes,
            config=config,
            cost_multiplier=multiplier,
        )
        if trades.num_rows:
            trade_ids = trades.column("trade_id").combine_chunks().to_pylist()
            net = _values(trades, "net_return")
            identity = hashlib.sha256("|".join(trade_ids).encode()).hexdigest()
            summed, expectancy = float(np.sum(net)), float(np.mean(net))
        else:
            identity = hashlib.sha256(b"").hexdigest()
            summed, expectancy = 0.0, None
        result[str(multiplier)] = {
            "trade_count": trades.num_rows,
            "trade_identity_hash": identity,
            "summed_net_return": summed,
            "expectancy": expectancy,
            "policy_thresholds_retuned": False,
            "cost_assumption_classification": config.assumption_classification,
        }
    return result
