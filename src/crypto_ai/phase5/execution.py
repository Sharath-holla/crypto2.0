from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.phase4_1.config import BacktestV2_1Config
from crypto_ai.phase5.policy import ThresholdPolicy

FIXED_POLICY_COST_STRESS = "FIXED_POLICY_COST_STRESS"
ADAPTIVE_POLICY_COST_STRESS = "ADAPTIVE_POLICY_COST_STRESS"
ExecutionArrays = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _execution_arrays(
    opportunities: pa.Table,
    execution_1m: pa.Table | None,
    config: BacktestV2_1Config,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    fallback_entry_time = _times(opportunities, "entry_time")
    fallback_entry_price = _floats(opportunities, "entry_reference_price")
    fallback_exit_time = _times(opportunities, "label_end_time")
    fallback_exit_price = _floats(opportunities, "future_reference_price")
    resolution = np.full(opportunities.num_rows, "5m", dtype=object)
    if execution_1m is None or execution_1m.num_rows == 0:
        return (
            fallback_entry_time,
            fallback_entry_price,
            fallback_exit_time,
            fallback_exit_price,
            resolution,
        )
    minute_time = _times(execution_1m, "open_time")
    minute_open = _floats(execution_1m, "open")
    feature_time = _times(opportunities, "feature_time")
    required_entry = feature_time + config.base_latency_minutes * 60_000_000
    entry_indices = np.searchsorted(minute_time, required_entry, side="left")
    safe_entry = np.minimum(entry_indices, len(minute_time) - 1)
    candidate_entry = minute_time[safe_entry]
    required_exit = candidate_entry + config.horizon_minutes * 60_000_000
    exit_indices = np.searchsorted(minute_time, required_exit, side="left")
    safe_exit = np.minimum(exit_indices, len(minute_time) - 1)
    candidate_exit = minute_time[safe_exit]
    # A distant search hit indicates a data gap, not executable one-minute coverage.
    available = (
        (entry_indices < len(minute_time))
        & (exit_indices < len(minute_time))
        & (candidate_entry >= required_entry)
        & (candidate_entry < required_entry + 60_000_000)
        & (candidate_exit >= required_exit)
        & (candidate_exit < required_exit + 60_000_000)
    )
    entry_time = fallback_entry_time.copy()
    entry_price = fallback_entry_price.copy()
    exit_time = fallback_exit_time.copy()
    exit_price = fallback_exit_price.copy()
    entry_time[available] = candidate_entry[available]
    entry_price[available] = minute_open[safe_entry[available]]
    exit_time[available] = candidate_exit[available]
    exit_price[available] = minute_open[safe_exit[available]]
    resolution[available] = "1m"
    if np.any(entry_time[available] <= feature_time[available]):
        raise ValueError("one-minute execution must be strictly after feature availability")
    return entry_time, entry_price, exit_time, exit_price, resolution


def prepare_execution_arrays(
    opportunities: pa.Table,
    execution_1m: pa.Table | None,
    config: BacktestV2_1Config,
) -> ExecutionArrays:
    """Prepare immutable execution references once for repeated cost scenarios."""

    return _execution_arrays(opportunities, execution_1m, config)


def _funding_arrays(funding: pa.Table | None) -> tuple[np.ndarray, np.ndarray]:
    if funding is None or funding.num_rows == 0:
        return np.asarray([], dtype=np.int64), np.asarray([], dtype=np.float64)
    return _times(funding, "event_time"), _floats(funding, "funding_rate")


def simulate_trades(
    opportunities: pa.Table,
    policy: ThresholdPolicy,
    config: BacktestV2_1Config,
    *,
    funding: pa.Table | None = None,
    execution_1m: pa.Table | None = None,
    cost_multiplier: float = 1.0,
    stress_type: str = ADAPTIVE_POLICY_COST_STRESS,
    prepared_execution: ExecutionArrays | None = None,
) -> tuple[pa.Table, dict[str, Any]]:
    if cost_multiplier < 0:
        raise ValueError("cost_multiplier must be non-negative")
    entry_time, entry_price, exit_time, exit_price, resolution = (
        prepare_execution_arrays(opportunities, execution_1m, config)
        if prepared_execution is None
        else prepared_execution
    )
    if any(len(values) != opportunities.num_rows for values in prepared_execution or ()):
        raise ValueError("prepared execution arrays do not match opportunities")
    predicted = _floats(opportunities, "calibrated_prediction")
    raw_predicted = _floats(opportunities, "raw_prediction")
    candidate_values = opportunities.column("candidate").to_pylist()
    family_values = opportunities.column("family").to_pylist()
    fold_values = opportunities.column("fold_id").to_pylist()
    feature_values = opportunities.column("feature_time").to_pylist()
    diagnostic_names = tuple(
        name
        for name in (
            "taker_buy_base_share",
            "taker_flow_imbalance_quote",
            "bull_regime",
            "bear_regime",
            "sideways_regime",
            "high_volatility_regime",
            "low_volatility_regime",
            "funding_rate",
        )
        if name in opportunities.column_names
    )
    diagnostic_values = {name: _floats(opportunities, name) for name in diagnostic_names}
    funding_time, funding_rate = _funding_arrays(funding)
    fee_bps = 2 * config.taker_fee_bps_per_side * cost_multiplier
    spread_bps = config.spread_bps_round_trip * cost_multiplier
    slippage_bps = 2 * config.slippage_bps_per_side * cost_multiplier
    transaction_cost_bps = fee_bps + spread_bps + slippage_bps
    required_bps = (
        None if policy.threshold_bps is None else policy.threshold_bps + transaction_cost_bps
    )
    active_until = -1
    rows: list[dict[str, Any]] = []
    threshold_rejected = 0
    overlap_skipped = 0
    for index in range(opportunities.num_rows):
        if required_bps is None or abs(predicted[index]) * 10_000 < required_bps:
            threshold_rejected += 1
            continue
        if entry_time[index] < active_until:
            overlap_skipped += 1
            continue
        direction = 1 if predicted[index] > 0 else -1 if predicted[index] < 0 else 0
        if direction == 0:
            threshold_rejected += 1
            continue
        gross = direction * (exit_price[index] / entry_price[index] - 1.0)
        left = np.searchsorted(funding_time, entry_time[index], side="right")
        right = np.searchsorted(funding_time, exit_time[index], side="right")
        funding_cash_flow = -direction * float(np.sum(funding_rate[left:right]))
        fee_cost = fee_bps / 10_000
        spread_cost = spread_bps / 10_000
        slippage_cost = slippage_bps / 10_000
        net = gross - fee_cost - spread_cost - slippage_cost + funding_cash_flow
        trade_identity = {
            "candidate": candidate_values[index],
            "fold_id": fold_values[index],
            "feature_time": str(feature_values[index]),
            "entry_time_us": int(entry_time[index]),
            "exit_time_us": int(exit_time[index]),
            "direction": direction,
        }
        trade_id = hashlib.sha256(
            json.dumps(trade_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
        row = {
            "trade_id": trade_id,
            "stress_type": stress_type,
            "candidate": candidate_values[index],
            "family": family_values[index],
            "fold_id": fold_values[index],
            "feature_time": feature_values[index],
            "entry_time": datetime.fromtimestamp(entry_time[index] / 1_000_000, tz=UTC),
            "exit_time": datetime.fromtimestamp(exit_time[index] / 1_000_000, tz=UTC),
            "execution_resolution": str(resolution[index]),
            "direction": direction,
            "raw_prediction": float(raw_predicted[index]),
            "calibrated_prediction": float(predicted[index]),
            "threshold_bps": policy.threshold_bps,
            "cost_multiplier": cost_multiplier,
            "entry_price": float(entry_price[index]),
            "exit_price": float(exit_price[index]),
            "gross_return": float(gross),
            "fee_cost": fee_cost,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "funding_cash_flow": funding_cash_flow,
            "net_return": float(net),
        }
        for name in diagnostic_names:
            row[name] = float(diagnostic_values[name][index])
        rows.append(row)
        active_until = int(exit_time[index])
    trades = pa.Table.from_pylist(rows) if rows else _empty_trades()
    metrics = economic_metrics(
        trades,
        opportunity_count=opportunities.num_rows,
        minimum_reliable_trade_count=config.minimum_reliable_trade_count,
    )
    metrics.update(
        {
            "stress_type": stress_type,
            "trade_identity_hash": trade_identity_hash(trades),
            "threshold_rejected_rows": threshold_rejected,
            "overlap_skipped_rows": overlap_skipped,
            "signal_threshold_bps": required_bps,
            "cost_multiplier": cost_multiplier,
            "execution_resolution_counts": {
                "1m": int(np.count_nonzero(resolution == "1m")),
                "5m": int(np.count_nonzero(resolution == "5m")),
            },
        }
    )
    return trades, metrics


def trade_identity_hash(trades: pa.Table) -> str:
    """Hash the ordered frozen trade identities for stress invariants."""

    trade_ids = (
        [] if "trade_id" not in trades.column_names else trades.column("trade_id").to_pylist()
    )
    payload = json.dumps(trade_ids, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def reprice_fixed_policy_trades(
    base_trades: pa.Table,
    config: BacktestV2_1Config,
    *,
    cost_multiplier: float,
) -> tuple[pa.Table, dict[str, Any]]:
    """Reprice an immutable 1x trade list without changing any trade decision."""

    if cost_multiplier < 0:
        raise ValueError("cost_multiplier must be non-negative")
    rows = base_trades.to_pylist()
    fee_cost = 2 * config.taker_fee_bps_per_side * cost_multiplier / 10_000
    spread_cost = config.spread_bps_round_trip * cost_multiplier / 10_000
    slippage_cost = 2 * config.slippage_bps_per_side * cost_multiplier / 10_000
    for row in rows:
        row["stress_type"] = FIXED_POLICY_COST_STRESS
        row["cost_multiplier"] = cost_multiplier
        row["fee_cost"] = fee_cost
        row["spread_cost"] = spread_cost
        row["slippage_cost"] = slippage_cost
        row["net_return"] = float(
            row["gross_return"] - fee_cost - spread_cost - slippage_cost + row["funding_cash_flow"]
        )
    repriced = pa.Table.from_pylist(rows) if rows else _empty_trades()
    metrics = economic_metrics(
        repriced,
        opportunity_count=base_trades.num_rows,
        minimum_reliable_trade_count=config.minimum_reliable_trade_count,
    )
    metrics.update(
        {
            "stress_type": FIXED_POLICY_COST_STRESS,
            "cost_multiplier": cost_multiplier,
            "trade_identity_hash": trade_identity_hash(repriced),
            "policy_frozen_at_cost_multiplier": 1.0,
        }
    )
    return repriced, metrics


def _empty_trades() -> pa.Table:
    return pa.table(
        {
            "trade_id": pa.array([], type=pa.string()),
            "stress_type": pa.array([], type=pa.string()),
            "candidate": pa.array([], type=pa.string()),
            "family": pa.array([], type=pa.string()),
            "fold_id": pa.array([], type=pa.string()),
            "feature_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
            "entry_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
            "exit_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
            "execution_resolution": pa.array([], type=pa.string()),
            "direction": pa.array([], type=pa.int64()),
            "gross_return": pa.array([], type=pa.float64()),
            "fee_cost": pa.array([], type=pa.float64()),
            "spread_cost": pa.array([], type=pa.float64()),
            "slippage_cost": pa.array([], type=pa.float64()),
            "funding_cash_flow": pa.array([], type=pa.float64()),
            "net_return": pa.array([], type=pa.float64()),
        }
    )


def economic_metrics(
    trades: pa.Table,
    *,
    opportunity_count: int,
    minimum_reliable_trade_count: int,
) -> dict[str, Any]:
    count = trades.num_rows
    if count == 0:
        return {
            "opportunity_count": opportunity_count,
            "trade_count": 0,
            "no_trade_count": opportunity_count,
            "total_gross_return": 0.0,
            "total_net_return": 0.0,
            "compounded_net_return": 0.0,
            "maximum_drawdown": 0.0,
            "expectancy": None,
            "hit_rate": None,
            "profit_factor": None,
            "profit_factor_raw": None,
            "ratio_metrics": {
                "profit_factor": {
                    "value": None,
                    "reliable": False,
                    "display_value": "INSUFFICIENT_SAMPLE",
                }
            },
            "exposure": 0.0,
            "reliable": False,
            "statistically_reliable": False,
            "reliability_reason": "NO_TRADE",
            "fees": 0.0,
            "spread": 0.0,
            "slippage": 0.0,
            "funding": 0.0,
            "trade_identity_hash": trade_identity_hash(trades),
        }
    net = _floats(trades, "net_return")
    gross = _floats(trades, "gross_return")
    equity = np.cumprod(1.0 + net)
    with_start = np.concatenate(([1.0], equity))
    drawdown = with_start / np.maximum.accumulate(with_start) - 1.0
    negative = net[net < 0]
    positive = net[net > 0]
    held = np.sum(_times(trades, "exit_time") - _times(trades, "entry_time"))
    span = max(1, int(_times(trades, "exit_time")[-1] - _times(trades, "entry_time")[0]))
    reliable = count >= minimum_reliable_trade_count
    profit_factor_raw = None if not len(negative) else float(np.sum(positive) / -np.sum(negative))
    reliability_reason = None if reliable else f"trade_count_below_{minimum_reliable_trade_count}"
    return {
        "opportunity_count": opportunity_count,
        "trade_count": count,
        "no_trade_count": opportunity_count - count,
        "total_gross_return": float(np.sum(gross)),
        "total_net_return": float(np.sum(net)),
        "compounded_net_return": float(equity[-1] - 1.0),
        "maximum_drawdown": float(np.min(drawdown)),
        "expectancy": float(np.mean(net)),
        "hit_rate": float(np.mean(net > 0)),
        "profit_factor": profit_factor_raw if reliable else None,
        "profit_factor_raw": profit_factor_raw,
        "ratio_metrics": {
            "profit_factor": {
                "value": profit_factor_raw,
                "reliable": reliable,
                "display_value": (profit_factor_raw if reliable else "INSUFFICIENT_SAMPLE"),
            }
        },
        "exposure": float(held / span),
        "reliable": reliable,
        "statistically_reliable": reliable,
        "reliability_reason": reliability_reason,
        "fees": float(np.sum(_floats(trades, "fee_cost"))),
        "spread": float(np.sum(_floats(trades, "spread_cost"))),
        "slippage": float(np.sum(_floats(trades, "slippage_cost"))),
        "funding": float(np.sum(_floats(trades, "funding_cash_flow"))),
        "trade_identity_hash": trade_identity_hash(trades),
    }
