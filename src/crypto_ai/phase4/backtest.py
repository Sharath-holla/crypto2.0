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
from crypto_ai.phase4.config import BacktestConfig
from crypto_ai.phase4.gold import read_gold_v2
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.research.config import SplitConfig
from crypto_ai.research.gold import TARGET_COLUMN
from crypto_ai.research.split import chronological_purged_split

BACKTEST_VERSION = "1.0.0"


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _funding_arrays(table: pa.Table | None) -> tuple[np.ndarray, np.ndarray]:
    if table is None:
        return np.asarray([], dtype=np.int64), np.asarray([], dtype=np.float64)
    return _times(table, "event_time"), _floats(table, "funding_rate")


def _metrics(trades: pa.Table, opportunity: pa.Table) -> dict[str, Any]:
    count = trades.num_rows
    if count == 0:
        return {
            "trade_count": 0,
            "total_net_return": 0.0,
            "compounded_net_return": 0.0,
            "maximum_drawdown": 0.0,
            "annualized_sharpe_daily": None,
            "hit_rate": None,
            "profit_factor": None,
            "average_trade": None,
            "exposure": 0.0,
            "turnover": 0.0,
            "funding_contribution": 0.0,
        }
    net = trades.column("net_return").combine_chunks().to_numpy()
    gross = trades.column("gross_return").combine_chunks().to_numpy()
    funding = trades.column("funding_cash_flow").combine_chunks().to_numpy()
    equity = np.cumprod(1.0 + net)
    running_peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))
    drawdown = np.concatenate(([1.0], equity)) / running_peak - 1.0
    positives = net[net > 0]
    negatives = net[net < 0]

    exit_times = trades.column("exit_time").combine_chunks().to_pylist()
    by_day: dict[str, float] = {}
    for timestamp, value in zip(exit_times, net, strict=True):
        key = timestamp.date().isoformat()
        by_day[key] = by_day.get(key, 0.0) + float(value)
    daily = np.asarray(list(by_day.values()), dtype=np.float64)
    sharpe = None
    if len(daily) >= 2 and np.std(daily, ddof=1) > 0:
        sharpe = float(np.mean(daily) / np.std(daily, ddof=1) * np.sqrt(365.0))

    opportunity_start = _times(opportunity, "entry_time")[0]
    opportunity_end = _times(opportunity, "label_end_time")[-1]
    held_us = np.sum(_times(trades, "exit_time") - _times(trades, "entry_time"))
    span_us = max(1, int(opportunity_end - opportunity_start))
    return {
        "trade_count": count,
        "total_gross_return": float(np.sum(gross)),
        "total_net_return": float(np.sum(net)),
        "compounded_net_return": float(equity[-1] - 1.0),
        "maximum_drawdown": float(np.min(drawdown)),
        "annualized_sharpe_daily": sharpe,
        "hit_rate": float(np.mean(net > 0)),
        "profit_factor": (
            None if not len(negatives) else float(np.sum(positives) / -np.sum(negatives))
        ),
        "average_trade": float(np.mean(net)),
        "exposure": float(held_us / span_us),
        "turnover": float(2 * count),
        "funding_contribution": float(np.sum(funding)),
    }


def run_oos_backtest(
    predictions: pa.Table,
    config: BacktestConfig,
    *,
    funding: pa.Table | None = None,
    cost_multiplier: float = 1.0,
) -> tuple[pa.Table, dict[str, Any]]:
    if cost_multiplier < 0:
        raise ValueError("cost_multiplier must be non-negative")
    splits = set(predictions.column("split").combine_chunks().to_pylist())
    if not splits or not splits.issubset({"validation", "test"}):
        raise ValueError("Backtests accept validation/test OOS predictions only")
    feature_time = _times(predictions, "feature_time")
    entry_time = _times(predictions, "entry_time")
    exit_time = _times(predictions, "label_end_time")
    if np.any(entry_time < feature_time) or np.any(exit_time <= entry_time):
        raise ValueError("Backtest timestamp semantics are invalid")
    predicted = _floats(predictions, "predicted_return")
    entry_price = _floats(predictions, "entry_reference_price")
    exit_price = _floats(predictions, "future_reference_price")
    funding_time, funding_rate = _funding_arrays(funding)
    threshold_bps = (
        config.minimum_prediction_bps
        + config.minimum_expected_net_edge_bps
        + config.non_funding_round_trip_bps * cost_multiplier
    )
    active_until = -1
    rows: list[dict[str, Any]] = []
    for index in range(predictions.num_rows):
        direction = 1 if predicted[index] > 0 else -1 if predicted[index] < 0 else 0
        if direction == 0 or abs(predicted[index]) * 10_000 < threshold_bps:
            continue
        if entry_time[index] < active_until:
            continue
        gross = direction * (exit_price[index] / entry_price[index] - 1.0)
        left = np.searchsorted(funding_time, entry_time[index], side="right")
        right = np.searchsorted(funding_time, exit_time[index], side="right")
        # Positive funding is a long cost and a short credit. Store cash flow
        # from the strategy perspective, so costs are negative.
        funding_cash_flow = -direction * float(np.sum(funding_rate[left:right]))
        non_funding_cost = config.non_funding_round_trip_bps * cost_multiplier / 10_000
        net = gross - non_funding_cost + funding_cash_flow
        rows.append(
            {
                "split": predictions.column("split")[index].as_py(),
                "feature_time": predictions.column("feature_time")[index].as_py(),
                "entry_time": predictions.column("entry_time")[index].as_py(),
                "exit_time": predictions.column("label_end_time")[index].as_py(),
                "direction": direction,
                "predicted_return": float(predicted[index]),
                "entry_price": float(entry_price[index]),
                "exit_price": float(exit_price[index]),
                "gross_return": float(gross),
                "non_funding_cost": float(non_funding_cost),
                "funding_cash_flow": funding_cash_flow,
                "net_return": float(net),
                "taker_imbalance_quote": float(
                    predictions.column("taker_imbalance_quote")[index].as_py()
                ),
                "bull_regime": float(predictions.column("bull_regime")[index].as_py()),
                "bear_regime": float(predictions.column("bear_regime")[index].as_py()),
                "sideways_regime": float(predictions.column("sideways_regime")[index].as_py()),
                "high_volatility_regime": float(
                    predictions.column("high_volatility_regime")[index].as_py()
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
    return trades, _metrics(trades, predictions)


def _strategy_predictions(test: pa.Table, name: str, training_mean: float) -> np.ndarray:
    if name == "zero":
        return np.zeros(test.num_rows)
    if name == "historical_mean":
        return np.full(test.num_rows, training_mean)
    if name == "momentum":
        return _floats(test, "return_1h")
    if name == "mean_reversion":
        return -_floats(test, "ema20_distance")
    raise ValueError(f"Unknown strategy: {name}")


def _prediction_frame(table: pa.Table, values: np.ndarray, split: str = "test") -> pa.Table:
    columns = {
        name: table.column(name)
        for name in (
            "symbol",
            "feature_time",
            "entry_time",
            "label_end_time",
            "entry_reference_price",
            "future_reference_price",
            TARGET_COLUMN,
            "taker_imbalance_quote",
            "bull_regime",
            "bear_regime",
            "sideways_regime",
            "high_volatility_regime",
        )
    }
    columns["split"] = [split] * table.num_rows
    columns["predicted_return"] = values
    return pa.table(columns)


def _trade_diagnostics(trades: pa.Table) -> dict[str, Any]:
    if not trades.num_rows:
        return {"regime": {}, "pressure": []}
    net = trades.column("net_return").combine_chunks().to_numpy()
    regime: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
    ):
        mask = trades.column(name).combine_chunks().to_numpy().astype(bool)
        if np.any(mask):
            regime[name] = {
                "trades": int(np.count_nonzero(mask)),
                "mean_net_return": float(np.mean(net[mask])),
                "hit_rate": float(np.mean(net[mask] > 0)),
            }
    pressure = trades.column("taker_imbalance_quote").combine_chunks().to_numpy()
    pressure_rows = []
    for number, indices in enumerate(
        np.array_split(np.argsort(pressure, kind="mergesort"), min(5, len(pressure))), start=1
    ):
        pressure_rows.append(
            {
                "bucket": number,
                "trades": int(len(indices)),
                "mean_pressure": float(np.mean(pressure[indices])),
                "mean_net_return": float(np.mean(net[indices])),
            }
        )
    return {"regime": regime, "pressure": pressure_rows}


def run_backtest_suite(
    experiment_path: Path,
    config: BacktestConfig,
    *,
    artifact_root: Path = Path("local_artifacts"),
    funding_manifest: Path | None = None,
) -> dict[str, Any]:
    experiment = read_manifest(experiment_path.resolve())
    if experiment is None or experiment.get("status") != "complete":
        raise ValueError("A complete Main Model V2 experiment is required")
    gold, _ = read_gold_v2(Path(experiment["dataset_manifest"]))
    split_config = SplitConfig.model_validate(experiment["configuration"]["split"])
    split = chronological_purged_split(gold, split_config)
    funding = None
    funding_version = None
    if funding_manifest is not None:
        funding, funding_metadata = read_market_dataset(funding_manifest, MarketDataKind.FUNDING)
        funding_version = funding_metadata["dataset_version"]
    identity = {
        "experiment": experiment["experiment_id"],
        "config": config.model_dump(mode="json"),
        "funding_version": funding_version,
        "backtest_version": BACKTEST_VERSION,
    }
    backtest_id = f"backtest-v1-{_hash(identity)}"
    final = artifact_root.resolve() / "phase4" / "backtests" / backtest_id
    result_path = final / "backtest.json"
    existing = read_manifest(result_path)
    if existing is not None:
        return existing
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        train_mean = float(np.mean(_floats(split.train, TARGET_COLUMN)))
        strategies: dict[str, pa.Table] = {
            name: _prediction_frame(split.test, _strategy_predictions(split.test, name, train_mean))
            for name in ("zero", "historical_mean", "momentum", "mean_reversion")
        }
        selected = str(experiment["selected_model"])
        prediction_path = experiment_path.parent / experiment["ablations"][selected]["predictions"]
        model_predictions = pq.ParquetFile(prediction_path).read()
        strategies["main_model_v2"] = model_predictions.filter(
            pc.equal(model_predictions.column("split"), "test")
        )

        strategy_results: dict[str, Any] = {}
        base_trades: dict[str, pa.Table] = {}
        for name, predictions in strategies.items():
            trades, metrics = run_oos_backtest(predictions, config, funding=funding)
            base_trades[name] = trades
            pq.write_table(trades, temporary / f"{name}_trades.parquet", compression="zstd")
            strategy_results[name] = {
                "metrics": metrics,
                "diagnostics": _trade_diagnostics(trades),
                "trades": f"{name}_trades.parquet",
            }

        stress: dict[str, Any] = {}
        for multiplier in (1.0, 1.5, 2.0, 3.0):
            _, metrics = run_oos_backtest(
                strategies["main_model_v2"],
                config,
                funding=funding,
                cost_multiplier=multiplier,
            )
            stress[f"{multiplier:.1f}x"] = metrics
        payload = {
            "backtest_id": backtest_id,
            "status": "complete",
            "created_at": datetime.now(UTC).isoformat(),
            "version": BACKTEST_VERSION,
            "experiment": str(experiment_path.resolve()),
            "experiment_id": experiment["experiment_id"],
            "dataset_version": experiment["dataset_version"],
            "funding_manifest": str(funding_manifest.resolve()) if funding_manifest else None,
            "funding_dataset_version": funding_version,
            "oos_split": "test",
            "execution": {
                "signal_time": "feature_time after prediction candle close",
                "entry": "next available 5m candle open",
                "exit": f"entry plus {config.horizon_minutes} minutes at candle open",
                "position_policy": "one normalized position; overlapping signals skipped",
                "costs": config.model_dump(mode="json"),
                "funding": "actual funding events in (entry_time, exit_time]",
                "compounding": "sequential realized trade returns; no leverage",
            },
            "strategies": strategy_results,
            "cost_stress": stress,
            "limitations": [
                "bar-level execution has no queue-position or market-impact model",
                (
                    "spread and slippage are configurable assumptions because replay-quality "
                    "depth is unavailable"
                ),
                "fees are assumptions and are not a claim about a user's current Binance tier",
            ],
            "code_version": "phase4-1.0.0",
        }
        write_manifest(temporary / "backtest.json", payload)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return payload
