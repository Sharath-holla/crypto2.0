from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase4_1.config import BacktestV2_1Config
from crypto_ai.phase4_1.gold import read_gold_v2_1
from crypto_ai.research.config import DatasetBuildConfig, SplitConfig
from crypto_ai.research.gold import TARGET_COLUMN, _load_silver
from crypto_ai.research.split import chronological_purged_split

BACKTEST_V2_1_VERSION = "1.1.2"


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _funding_arrays(table: pa.Table | None) -> tuple[np.ndarray, np.ndarray]:
    if table is None:
        return np.asarray([], dtype=np.int64), np.asarray([], dtype=np.float64)
    return _times(table, "event_time"), _floats(table, "funding_rate")


def _execution_arrays(
    predictions: pa.Table,
    *,
    execution_candles: pa.Table | None,
    latency_minutes: int,
    horizon_minutes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    feature_time = _times(predictions, "feature_time")
    if execution_candles is None:
        return (
            _times(predictions, "entry_time"),
            _floats(predictions, "entry_reference_price"),
            _times(predictions, "label_end_time"),
            _floats(predictions, "future_reference_price"),
            np.ones(predictions.num_rows, dtype=bool),
        )
    one_minute_times = _times(execution_candles, "open_time")
    one_minute_opens = _floats(execution_candles, "open")
    required_entry = feature_time + latency_minutes * 60_000_000
    entry_indices = np.searchsorted(one_minute_times, required_entry, side="left")
    safe_entry = np.minimum(entry_indices, max(0, len(one_minute_times) - 1))
    entry_time = one_minute_times[safe_entry]
    exit_required = entry_time + horizon_minutes * 60_000_000
    exit_indices = np.searchsorted(one_minute_times, exit_required, side="left")
    safe_exit = np.minimum(exit_indices, max(0, len(one_minute_times) - 1))
    available = (
        (entry_indices < len(one_minute_times))
        & (exit_indices < len(one_minute_times))
        & (entry_time >= required_entry)
        & (one_minute_times[safe_exit] >= exit_required)
    )
    return (
        entry_time,
        one_minute_opens[safe_entry],
        one_minute_times[safe_exit],
        one_minute_opens[safe_exit],
        available,
    )


def _metrics(
    trades: pa.Table, opportunity: pa.Table, *, minimum_reliable_trade_count: int
) -> dict[str, Any]:
    count = trades.num_rows
    if count == 0:
        return {
            "trade_count": 0,
            "total_gross_return": 0.0,
            "total_net_return": 0.0,
            "compounded_net_return": 0.0,
            "maximum_drawdown": 0.0,
            "annualized_sharpe_daily": None,
            "annualized_sortino_daily": None,
            "calmar_ratio": None,
            "hit_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "exposure": 0.0,
            "turnover": 0.0,
            "fee_cost": 0.0,
            "spread_cost": 0.0,
            "slippage_cost": 0.0,
            "funding_contribution": 0.0,
            "low_trade_count_warning": True,
            "warning": "NO-TRADE is a valid outcome; economic estimates are unavailable",
        }
    net = trades.column("net_return").combine_chunks().to_numpy()
    gross = trades.column("gross_return").combine_chunks().to_numpy()
    equity = np.cumprod(1.0 + net)
    equity_with_start = np.concatenate(([1.0], equity))
    running_peak = np.maximum.accumulate(equity_with_start)
    drawdown = equity_with_start / running_peak - 1.0
    maximum_drawdown = float(np.min(drawdown))
    positives, negatives = net[net > 0], net[net < 0]
    exit_times = trades.column("exit_time").combine_chunks().to_pylist()
    by_day: dict[str, float] = {}
    for timestamp, value in zip(exit_times, net, strict=True):
        key = timestamp.date().isoformat()
        by_day[key] = by_day.get(key, 0.0) + float(value)
    daily = np.asarray(list(by_day.values()), dtype=np.float64)
    sharpe = None
    sortino = None
    if len(daily) >= 2 and np.std(daily, ddof=1) > 0:
        sharpe = float(np.mean(daily) / np.std(daily, ddof=1) * np.sqrt(365.0))
    downside = daily[daily < 0]
    if len(downside) >= 2 and np.std(downside, ddof=1) > 0:
        sortino = float(np.mean(daily) / np.std(downside, ddof=1) * np.sqrt(365.0))
    entry_us = _times(trades, "entry_time")
    exit_us = _times(trades, "exit_time")
    years = max((int(exit_us[-1]) - int(entry_us[0])) / (365.0 * 86_400_000_000), 1 / 365)
    annualized_return = float(equity[-1] ** (1.0 / years) - 1.0) if equity[-1] > 0 else -1.0
    opportunity_start = _times(opportunity, "entry_time")[0]
    opportunity_end = _times(opportunity, "label_end_time")[-1]
    held_us = np.sum(exit_us - entry_us)
    span_us = max(1, int(opportunity_end - opportunity_start))
    low_count = count < minimum_reliable_trade_count
    return {
        "trade_count": count,
        "total_gross_return": float(np.sum(gross)),
        "total_net_return": float(np.sum(net)),
        "compounded_net_return": float(equity[-1] - 1.0),
        "maximum_drawdown": maximum_drawdown,
        "annualized_return": annualized_return,
        "annualized_sharpe_daily": sharpe,
        "annualized_sortino_daily": sortino,
        "calmar_ratio": (
            None if maximum_drawdown >= 0 else annualized_return / abs(maximum_drawdown)
        ),
        "hit_rate": float(np.mean(net > 0)),
        "profit_factor": (
            None if not len(negatives) else float(np.sum(positives) / -np.sum(negatives))
        ),
        "expectancy": float(np.mean(net)),
        "exposure": float(held_us / span_us),
        "turnover": float(2 * count),
        "fee_cost": float(np.sum(trades.column("fee_cost").to_numpy())),
        "spread_cost": float(np.sum(trades.column("spread_cost").to_numpy())),
        "slippage_cost": float(np.sum(trades.column("slippage_cost").to_numpy())),
        "funding_contribution": float(np.sum(trades.column("funding_cash_flow").to_numpy())),
        "low_trade_count_warning": low_count,
        "warning": (
            f"Only {count} trades; below reliability threshold {minimum_reliable_trade_count}"
            if low_count
            else None
        ),
    }


def run_oos_backtest_v2_1(
    predictions: pa.Table,
    config: BacktestV2_1Config,
    *,
    funding: pa.Table | None = None,
    execution_candles: pa.Table | None = None,
    cost_multiplier: float = 1.0,
    additional_delay_minutes: int = 0,
) -> tuple[pa.Table, dict[str, Any]]:
    if cost_multiplier < 0 or additional_delay_minutes < 0:
        raise ValueError("cost multiplier and additional delay must be non-negative")
    splits = set(predictions.column("split").combine_chunks().to_pylist())
    if not splits or not splits.issubset({"validation", "test"}):
        raise ValueError("Backtests accept validation/test OOS predictions only")
    feature_time = _times(predictions, "feature_time")
    entry_time, entry_price, exit_time, exit_price, execution_available = _execution_arrays(
        predictions,
        execution_candles=execution_candles,
        latency_minutes=config.base_latency_minutes + additional_delay_minutes,
        horizon_minutes=config.horizon_minutes,
    )
    if np.any(entry_time[execution_available] <= feature_time[execution_available]):
        raise ValueError("Execution must occur strictly after feature availability")
    predicted = _floats(predictions, "predicted_return")
    funding_time, funding_rate = _funding_arrays(funding)
    fee_bps = 2 * config.taker_fee_bps_per_side * cost_multiplier
    spread_bps = config.spread_bps_round_trip * cost_multiplier
    slippage_bps = 2 * config.slippage_bps_per_side * cost_multiplier
    threshold_bps = (
        config.minimum_prediction_bps
        + config.minimum_expected_net_edge_bps
        + fee_bps
        + spread_bps
        + slippage_bps
    )
    active_until = -1
    threshold_rejected_rows = 0
    overlap_skipped_rows = 0
    rows: list[dict[str, Any]] = []
    for index in range(predictions.num_rows):
        if not execution_available[index]:
            continue
        direction = 1 if predicted[index] > 0 else -1 if predicted[index] < 0 else 0
        if direction == 0 or abs(predicted[index]) * 10_000 < threshold_bps:
            threshold_rejected_rows += 1
            continue
        if entry_time[index] < active_until:
            overlap_skipped_rows += 1
            continue
        gross = direction * (exit_price[index] / entry_price[index] - 1.0)
        left = np.searchsorted(funding_time, entry_time[index], side="right")
        right = np.searchsorted(funding_time, exit_time[index], side="right")
        funding_cash_flow = -direction * float(np.sum(funding_rate[left:right]))
        fee_cost = fee_bps / 10_000
        spread_cost = spread_bps / 10_000
        slippage_cost = slippage_bps / 10_000
        net = gross - fee_cost - spread_cost - slippage_cost + funding_cash_flow
        rows.append(
            {
                "split": predictions.column("split")[index].as_py(),
                "feature_time": predictions.column("feature_time")[index].as_py(),
                "entry_time": datetime.fromtimestamp(entry_time[index] / 1_000_000, tz=UTC),
                "exit_time": datetime.fromtimestamp(exit_time[index] / 1_000_000, tz=UTC),
                "direction": direction,
                "predicted_return": float(predicted[index]),
                "entry_price": float(entry_price[index]),
                "exit_price": float(exit_price[index]),
                "gross_return": float(gross),
                "fee_cost": fee_cost,
                "spread_cost": spread_cost,
                "slippage_cost": slippage_cost,
                "funding_cash_flow": funding_cash_flow,
                "net_return": float(net),
                "taker_buy_base_share": float(
                    predictions.column("taker_buy_base_share")[index].as_py()
                ),
                "taker_flow_imbalance_quote": float(
                    predictions.column("taker_flow_imbalance_quote")[index].as_py()
                ),
                "bull_regime": float(predictions.column("bull_regime")[index].as_py()),
                "bear_regime": float(predictions.column("bear_regime")[index].as_py()),
                "sideways_regime": float(predictions.column("sideways_regime")[index].as_py()),
                "high_volatility_regime": float(
                    predictions.column("high_volatility_regime")[index].as_py()
                ),
                "low_volatility_regime": float(
                    predictions.column("low_volatility_regime")[index].as_py()
                ),
            }
        )
        active_until = int(exit_time[index])
    trades = (
        pa.Table.from_pylist(rows)
        if rows
        else pa.table(
            {
                "split": pa.array([], type=pa.string()),
                "feature_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "entry_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "exit_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "net_return": pa.array([], type=pa.float64()),
            }
        )
    )
    metrics = _metrics(
        trades,
        predictions,
        minimum_reliable_trade_count=config.minimum_reliable_trade_count,
    )
    metrics["opportunity_count"] = predictions.num_rows
    metrics["no_trade_count"] = predictions.num_rows - trades.num_rows
    metrics["execution_unavailable_rows"] = int(np.count_nonzero(~execution_available))
    metrics["threshold_rejected_rows"] = threshold_rejected_rows
    metrics["overlap_skipped_rows"] = overlap_skipped_rows
    metrics["signal_threshold_bps"] = threshold_bps
    return trades, metrics


def _replace_predictions(source: pa.Table, values: np.ndarray) -> pa.Table:
    index = source.schema.get_field_index("predicted_return")
    return source.set_column(index, "predicted_return", pa.array(values, type=pa.float64()))


def _trade_diagnostics(trades: pa.Table) -> dict[str, Any]:
    if not trades.num_rows:
        return {"by_year": {}, "regime": {}, "taker_flow": []}
    net = trades.column("net_return").combine_chunks().to_numpy()
    years = np.asarray([item.year for item in trades.column("entry_time").to_pylist()])
    by_year = {}
    for year in np.unique(years):
        mask = years == year
        count = int(np.count_nonzero(mask))
        by_year[str(year)] = {
            "trades": count,
            "expectancy": float(np.mean(net[mask])),
            "net_return": float(np.sum(net[mask])),
            "hit_rate": float(np.mean(net[mask] > 0)),
            "small_sample_warning": count < 30,
        }
    regime: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ):
        mask = trades.column(name).combine_chunks().to_numpy().astype(bool)
        if np.any(mask):
            regime[name] = {
                "trades": int(np.count_nonzero(mask)),
                "expectancy": float(np.mean(net[mask])),
                "net_return": float(np.sum(net[mask])),
                "hit_rate": float(np.mean(net[mask] > 0)),
            }
    flow = trades.column("taker_flow_imbalance_quote").combine_chunks().to_numpy()
    buckets = []
    for number, indices in enumerate(
        np.array_split(np.argsort(flow, kind="mergesort"), min(5, len(flow))), start=1
    ):
        buckets.append(
            {
                "bucket": number,
                "trades": len(indices),
                "mean_taker_flow_imbalance_quote": float(np.mean(flow[indices])),
                "expectancy": float(np.mean(net[indices])),
                "net_return": float(np.sum(net[indices])),
            }
        )
    return {"by_year": by_year, "regime": regime, "taker_flow": buckets}


def _buy_and_hold(
    predictions: pa.Table,
    config: BacktestV2_1Config,
    execution_candles: pa.Table | None,
) -> dict[str, Any]:
    entry_time, entry, exit_time, exit_price, available = _execution_arrays(
        predictions,
        execution_candles=execution_candles,
        latency_minutes=config.base_latency_minutes,
        horizon_minutes=config.horizon_minutes,
    )
    valid = np.flatnonzero(available)
    if not len(valid):
        return {"status": "unavailable", "reason": "no executable observations"}
    first, last = int(valid[0]), int(valid[-1])
    gross = float(exit_price[last] / entry[first] - 1.0)
    cost = config.non_funding_round_trip_bps / 10_000
    return {
        "status": "complete",
        "entry_time": datetime.fromtimestamp(entry_time[first] / 1_000_000, tz=UTC).isoformat(),
        "exit_time": datetime.fromtimestamp(exit_time[last] / 1_000_000, tz=UTC).isoformat(),
        "gross_return": gross,
        "assumed_round_trip_cost": cost,
        "net_return": gross - cost,
        "leverage": 1.0,
    }


def run_backtest_suite_v2_1(
    experiment_path: Path,
    config: BacktestV2_1Config,
    *,
    artifact_root: Path = Path("local_artifacts"),
    funding_manifest: Path | None = None,
    execution_1m_silver_manifest: Path | None = None,
) -> dict[str, Any]:
    experiment_path = experiment_path.resolve()
    experiment = read_manifest(experiment_path)
    if experiment is None or experiment.get("status") != "complete":
        raise ValueError("A complete Main Model V2.1 experiment is required")
    families = experiment["families"]
    family_name = "derivatives_overlap" if "derivatives_overlap" in families else "long_history"
    family = families[family_name]
    gold_path = Path(family["dataset_manifest"])
    gold, gold_manifest = read_gold_v2_1(gold_path)
    split = chronological_purged_split(
        gold, SplitConfig.model_validate(experiment["configuration"]["split"])
    )
    selected = family["selected_ablation"]
    prediction_path = experiment_path.parent / family["ablations"][selected]["predictions"]
    model_predictions = pq.ParquetFile(prediction_path).read()
    model_test = model_predictions.filter(pc.equal(model_predictions.column("split"), "test"))
    if model_test.num_rows != split.test.num_rows:
        raise ValueError("Model prediction rows do not match reconstructed test split")

    funding = None
    funding_version = None
    if funding_manifest is not None:
        funding, funding_metadata = read_market_dataset(funding_manifest, MarketDataKind.FUNDING)
        funding_version = funding_metadata["dataset_version"]
    execution = None
    execution_version = None
    if execution_1m_silver_manifest is not None:
        execution, execution_metadata, _ = _load_silver(
            DatasetBuildConfig(
                silver_manifest=execution_1m_silver_manifest,
                symbol="BTCUSDT",
                interval="1m",
            )
        )
        execution_version = execution_metadata["silver_dataset_version"]

    identity = {
        "experiment": experiment["experiment_id"],
        "family": family_name,
        "selected_ablation": selected,
        "config": config.model_dump(mode="json"),
        "funding_version": funding_version,
        "execution_1m_version": execution_version,
        "version": BACKTEST_V2_1_VERSION,
    }
    backtest_id = f"backtest-v2-1-{_hash(identity)}"
    final = artifact_root.resolve() / "phase4_1" / "backtests" / backtest_id
    result_path = final / "backtest.json"
    existing = read_manifest(result_path)
    if existing is not None:
        return existing
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        train_mean = float(np.mean(_floats(split.train, TARGET_COLUMN)))
        strategies = {
            "zero": _replace_predictions(model_test, np.zeros(model_test.num_rows)),
            "historical_mean": _replace_predictions(
                model_test, np.full(model_test.num_rows, train_mean)
            ),
            "momentum": _replace_predictions(model_test, _floats(split.test, "return_1h")),
            "mean_reversion": _replace_predictions(
                model_test, -_floats(split.test, "ema20_distance")
            ),
            "main_model_v2_1": model_test,
        }
        strategy_results: dict[str, Any] = {}
        for name, predictions in strategies.items():
            trades, metrics = run_oos_backtest_v2_1(
                predictions,
                config,
                funding=funding,
                execution_candles=execution,
            )
            path = temporary / f"{name}_trades.parquet"
            pq.write_table(trades, path, compression="zstd")
            strategy_results[name] = {
                "metrics": metrics,
                "diagnostics": _trade_diagnostics(trades),
                "trades": path.name,
            }
        cost_stress: dict[str, Any] = {}
        for multiplier in (0.0, 1.0, 1.25, 1.5, 2.0):
            _, metrics = run_oos_backtest_v2_1(
                model_test,
                config,
                funding=funding,
                execution_candles=execution,
                cost_multiplier=multiplier,
            )
            cost_stress[f"{multiplier:g}x"] = metrics
        delay_stress: dict[str, Any] = {}
        if execution is not None:
            for delay in (1, 5):
                _, metrics = run_oos_backtest_v2_1(
                    model_test,
                    config,
                    funding=funding,
                    execution_candles=execution,
                    additional_delay_minutes=delay,
                )
                delay_stress[f"plus_{delay}m"] = metrics
        payload = {
            "backtest_id": backtest_id,
            "status": "complete",
            "created_at": datetime.now(UTC).isoformat(),
            "version": BACKTEST_V2_1_VERSION,
            "experiment": str(experiment_path),
            "experiment_id": experiment["experiment_id"],
            "family": family_name,
            "selected_ablation": selected,
            "dataset_manifest": str(gold_path),
            "dataset_version": gold_manifest["dataset_version"],
            "funding_manifest": str(funding_manifest.resolve()) if funding_manifest else None,
            "funding_dataset_version": funding_version,
            "execution_1m_silver_manifest": (
                str(execution_1m_silver_manifest.resolve())
                if execution_1m_silver_manifest
                else None
            ),
            "execution_1m_dataset_version": execution_version,
            "oos_split": "test",
            "execution": {
                "signal_time": "feature_time after completed 5m prediction candle",
                "entry": (
                    "first 1m open at or after feature_time plus configured latency"
                    if execution is not None
                    else "Gold Label V1 next 5m open fallback"
                ),
                "same_close_entry_forbidden": True,
                "base_latency_minutes": config.base_latency_minutes,
                "exit": f"first executable open at/after entry plus {config.horizon_minutes}m",
                "position_policy": "one normalized position; overlapping signals skipped",
                "funding": "actual funding events in (entry_time, exit_time]",
                "compounding": "sequential normalized returns; no leverage",
            },
            "cost_assumptions": {
                **config.model_dump(mode="json"),
                "maker_fee_bps": config.maker_fee_bps_per_side,
                "taker_fee_bps": config.taker_fee_bps_per_side,
                "fee_source": config.fee_source,
                "assumption_or_account_specific": config.assumption_or_account_specific,
            },
            "strategies": strategy_results,
            "buy_and_hold_baseline": _buy_and_hold(model_test, config, execution),
            "cost_stress": cost_stress,
            "entry_delay_stress": delay_stress,
            "limitations": [
                "bar-level execution has no queue-position or market-impact model",
                "spread/slippage/fees are explicit assumptions, not current account terms",
                "NO-TRADE is retained and thresholds were not lowered to manufacture trades",
            ],
            "code_version": "phase4.1-1.0.0",
        }
        write_manifest(temporary / "backtest.json", payload)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return payload
