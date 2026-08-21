from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase4_1.config import load_backtest_v2_1_config
from crypto_ai.phase4_1.gold import read_gold_v2_1
from crypto_ai.phase4_1.model import derivatives_ablation_sets, long_history_ablation_sets
from crypto_ai.phase5.calibration import fit_calibrator
from crypto_ai.phase5.config import WalkForwardConfig
from crypto_ai.phase5.execution import economic_metrics, simulate_trades
from crypto_ai.phase5.folds import FoldData, FoldPlan, plan_folds, slice_fold, validate_fold_plan
from crypto_ai.phase5.policy import ThresholdPolicy, select_threshold
from crypto_ai.research.config import DatasetBuildConfig, load_experiment_config
from crypto_ai.research.gold import TARGET_COLUMN, _load_silver
from crypto_ai.research.metrics import prediction_buckets, regression_metrics
from crypto_ai.research.models import ModelBundle, save_model

WALK_FORWARD_VERSION = "1.0.0"


def _hash(payload: Any, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _matrix(table: pa.Table, columns: tuple[str, ...]) -> np.ndarray:
    missing = sorted(set(columns) - set(table.column_names))
    if missing:
        raise ValueError(f"Gold V2.1 is missing frozen candidate features: {missing}")
    values = np.column_stack([_floats(table, name) for name in columns])
    if not np.all(np.isfinite(values)):
        raise ValueError("candidate feature matrix contains non-finite values")
    return values


def _target(table: pa.Table) -> np.ndarray:
    values = _floats(table, TARGET_COLUMN)
    if not np.all(np.isfinite(values)):
        raise ValueError("candidate target contains non-finite values")
    return values


def _candidate_columns(config: WalkForwardConfig) -> dict[str, tuple[str, ...]]:
    if config.family == "primary":
        available = long_history_ablation_sets()
    else:
        available = derivatives_ablation_sets(include_open_interest=False)
    return {name: available[name] for name in config.candidates}


def _feature_schema(columns: tuple[str, ...]) -> dict[str, Any]:
    return {
        "columns": list(columns),
        "feature_count": len(columns),
        "sha256": hashlib.sha256("\n".join(columns).encode()).hexdigest(),
    }


def _fit_model(
    fold: FoldData,
    columns: tuple[str, ...],
    candidate: str,
    model_config_path: Path,
    seed: int,
) -> tuple[ModelBundle, np.ndarray, dict[str, Any]]:
    import lightgbm as lgb

    config = load_experiment_config(model_config_path)
    train_x, validation_x = _matrix(fold.train, columns), _matrix(fold.validation, columns)
    train_y, validation_y = _target(fold.train), _target(fold.validation)
    parameters = config.lightgbm.model_dump()
    early_stopping_rounds = parameters.pop("early_stopping_rounds")
    estimator = lgb.LGBMRegressor(
        objective="regression",
        random_state=seed,
        n_jobs=1,
        verbosity=-1,
        subsample_freq=1,
        deterministic=True,
        force_col_wise=True,
        importance_type="gain",
        **parameters,
    )
    estimator.fit(
        train_x,
        train_y,
        eval_X=validation_x,
        eval_y=validation_y,
        eval_metric="l2",
        callbacks=[
            lgb.early_stopping(early_stopping_rounds, first_metric_only=True, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    bundle = ModelBundle(
        model_name="lightgbm",
        model_version=WALK_FORWARD_VERSION,
        feature_columns=columns,
        estimator=estimator,
        metadata={
            "phase": 5,
            "candidate": candidate,
            "feature_schema": _feature_schema(columns),
            "seed": seed,
            "hyperparameters": config.lightgbm.model_dump(),
            "best_iteration": int(estimator.best_iteration_),
            "selection": "fixed Phase 4.1 configuration; validation early stopping only",
        },
    )
    validation_predictions = bundle.predict(validation_x, columns)
    importance = {
        "gain": {
            name: float(value)
            for name, value in zip(
                columns,
                estimator.booster_.feature_importance(importance_type="gain"),
                strict=True,
            )
        },
        "split": {
            name: int(value)
            for name, value in zip(
                columns,
                estimator.booster_.feature_importance(importance_type="split"),
                strict=True,
            )
        },
        "permutation_importance": "not repeated per fold; Phase 4.1 artifacts remain canonical",
    }
    return bundle, validation_predictions, importance


def _negative_control(
    fold: FoldData,
    test: pa.Table,
    columns: tuple[str, ...],
    model_config_path: Path,
    seed: int,
) -> dict[str, Any]:
    """Train one fold with labels shuffled strictly inside the training segment."""
    import lightgbm as lgb

    config = load_experiment_config(model_config_path)
    parameters = config.lightgbm.model_dump()
    early_stopping_rounds = parameters.pop("early_stopping_rounds")
    shuffled_train_target = np.random.default_rng(seed).permutation(_target(fold.train))
    estimator = lgb.LGBMRegressor(
        objective="regression",
        random_state=seed,
        n_jobs=1,
        verbosity=-1,
        subsample_freq=1,
        deterministic=True,
        force_col_wise=True,
        **parameters,
    )
    estimator.fit(
        _matrix(fold.train, columns),
        shuffled_train_target,
        eval_X=_matrix(fold.validation, columns),
        eval_y=_target(fold.validation),
        eval_metric="l2",
        callbacks=[
            lgb.early_stopping(early_stopping_rounds, first_metric_only=True, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    predictions = estimator.predict(_matrix(test, columns))
    return {
        "status": "complete",
        "training_labels_shuffled_within_training_only": True,
        "selection_use": "none; negative control only",
        "seed": seed,
        "best_iteration": int(estimator.best_iteration_),
        "test_predictive": regression_metrics(_target(test), predictions),
    }


def _fold_model_identity(
    plan: FoldPlan,
    candidate: str,
    columns: tuple[str, ...],
    fold: FoldData,
    config: WalkForwardConfig,
) -> str:
    digest = hashlib.sha256()
    digest.update(config.configuration_hash.encode())
    digest.update(plan.fold_id.encode())
    digest.update(candidate.encode())
    digest.update(_feature_schema(columns)["sha256"].encode())
    for table in (fold.train, fold.validation):
        digest.update(_times(table, "feature_time").tobytes())
        digest.update(_target(table).tobytes())
    return digest.hexdigest()[:24]


def _opportunity_table(
    table: pa.Table,
    raw_predictions: np.ndarray,
    calibrated_predictions: np.ndarray,
    *,
    candidate: str,
    family: str,
    fold_id: str,
    calibrator_method: str,
    threshold_bps: float | None,
    feature_schema_hash: str,
) -> pa.Table:
    names = [
        "symbol",
        "feature_time",
        "entry_time",
        "label_end_time",
        "entry_reference_price",
        "future_reference_price",
        TARGET_COLUMN,
        "return_1h",
        "ema20_distance",
        "taker_buy_base_share",
        "taker_flow_imbalance_quote",
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ]
    if "funding_rate" in table.column_names:
        names.append("funding_rate")
    result = table.select(names)
    count = table.num_rows
    for name, values in (
        ("candidate", [candidate] * count),
        ("family", [family] * count),
        ("fold_id", [fold_id] * count),
        ("raw_prediction", raw_predictions),
        ("calibrated_prediction", calibrated_predictions),
        ("calibration_method", [calibrator_method] * count),
        ("threshold_bps", [threshold_bps] * count),
        ("feature_schema_hash", [feature_schema_hash] * count),
        ("model_version", [WALK_FORWARD_VERSION] * count),
    ):
        result = result.append_column(name, pa.array(values))
    return result


def _psi(train: np.ndarray, test: np.ndarray) -> float:
    edges = np.unique(np.quantile(train, np.linspace(0, 1, 11)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    left = np.histogram(train, bins=edges)[0] / len(train)
    right = np.histogram(test, bins=edges)[0] / len(test)
    left, right = np.maximum(left, 1e-6), np.maximum(right, 1e-6)
    return float(np.sum((right - left) * np.log(right / left)))


def _feature_drift(train: pa.Table, test: pa.Table, columns: tuple[str, ...]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for name in columns:
        left, right = _floats(train, name), _floats(test, name)
        q25, median, q75 = np.percentile(left, [25, 50, 75])
        scale = max(float(q75 - q25), 1e-12)
        details[name] = {
            "psi": _psi(left, right),
            "train_median": float(median),
            "test_median": float(np.median(right)),
            "median_shift_train_iqr": float((np.median(right) - median) / scale),
            "train_iqr": scale,
            "test_iqr": float(np.percentile(right, 75) - np.percentile(right, 25)),
        }
    ranking = sorted(details, key=lambda name: details[name]["psi"], reverse=True)
    return {"features": details, "highest_psi_features": ranking[:10]}


def _artifact_files_valid(directory: Path, manifest: dict[str, Any], identity: str) -> bool:
    if manifest.get("status") != "complete" or manifest.get("identity") != identity:
        return False
    files = manifest.get("files")
    if not isinstance(files, dict):
        return False
    return all(
        (directory / name).exists() and file_sha256(directory / name) == checksum
        for name, checksum in files.items()
    )


def _empty_table_like(path: Path) -> pa.Table:
    return pq.ParquetFile(path).read()


def _load_fold(directory: Path, config: WalkForwardConfig) -> dict[str, Any]:
    payload = read_manifest(directory / "fold_manifest.json")
    if payload is None:
        raise ValueError(f"missing completed fold manifest: {directory}")
    backtest = read_manifest(directory / "backtest.json")
    if backtest is None:
        raise ValueError(f"missing fold backtest: {directory}")
    stress_trades = {
        str(multiplier): _empty_table_like(directory / f"test_trades_{multiplier:g}x.parquet")
        for multiplier in config.cost_multipliers
    }
    return {
        "manifest": payload,
        "backtest": backtest,
        "predictions": _empty_table_like(directory / "test_predictions.parquet"),
        "stress_trades": stress_trades,
        "threshold": read_manifest(directory / "threshold.json"),
        "calibration": read_manifest(directory / "calibrator.json"),
    }


def _run_fold(
    fold: FoldData,
    plan: FoldPlan,
    candidate: str,
    columns: tuple[str, ...],
    config: WalkForwardConfig,
    run_directory: Path,
    funding: pa.Table | None,
    execution_1m: pa.Table | None,
    *,
    resume: bool,
) -> dict[str, Any]:
    backtest_config = load_backtest_v2_1_config(config.backtest_config)
    model_identity = _fold_model_identity(plan, candidate, columns, fold, config)
    final = run_directory / "candidates" / candidate / "folds" / plan.fold_id
    existing = read_manifest(final / "fold_manifest.json")
    if resume and existing is not None and _artifact_files_valid(final, existing, model_identity):
        return _load_fold(final, config)
    if final.exists():
        raise FileExistsError(f"refusing to overwrite invalid immutable fold artifact: {final}")
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        bundle, validation_raw, importance = _fit_model(
            fold, columns, candidate, config.experiment_config, config.seed
        )
        validation_metrics = regression_metrics(_target(fold.validation), validation_raw)
        calibration_raw = bundle.predict(_matrix(fold.calibration, columns), columns)
        calibrator, calibration_diagnostics = fit_calibrator(
            calibration_raw, _target(fold.calibration), config.calibration
        )
        calibration_predictions = calibrator.apply(calibration_raw)
        policy, threshold_diagnostics = select_threshold(
            calibration_predictions,
            _target(fold.calibration),
            _times(fold.calibration, "feature_time"),
            config.threshold,
            cost_bps=backtest_config.non_funding_round_trip_bps,
            horizon_minutes=backtest_config.horizon_minutes,
        )
        frozen_identity = _hash(
            {
                "model": model_identity,
                "calibrator": calibrator.identity_hash,
                "policy": policy.identity_hash,
            }
        )
        test = fold.release_test(frozen_identity=frozen_identity)
        test_raw = bundle.predict(_matrix(test, columns), columns)
        test_calibrated = calibrator.apply(test_raw)
        predictions = _opportunity_table(
            test,
            test_raw,
            test_calibrated,
            candidate=candidate,
            family=config.family,
            fold_id=plan.fold_id,
            calibrator_method=calibrator.method,
            threshold_bps=policy.threshold_bps,
            feature_schema_hash=_feature_schema(columns)["sha256"],
        )
        test_predictive_raw = regression_metrics(_target(test), test_raw)
        test_predictive_calibrated = regression_metrics(_target(test), test_calibrated)
        negative_control = (
            _negative_control(fold, test, columns, config.experiment_config, config.seed)
            if plan.index == 0
            else {
                "status": "not_scheduled",
                "policy": "training-only shuffled-label control runs on first fold per candidate",
            }
        )
        stress_trades: dict[str, pa.Table] = {}
        cost_stress: dict[str, Any] = {}
        for multiplier in config.cost_multipliers:
            trades, metrics = simulate_trades(
                predictions,
                policy,
                backtest_config,
                funding=funding,
                execution_1m=execution_1m,
                cost_multiplier=multiplier,
            )
            key = str(multiplier)
            stress_trades[key] = trades
            cost_stress[key] = metrics
            pq.write_table(
                trades,
                temporary / f"test_trades_{multiplier:g}x.parquet",
                compression="zstd",
            )
        pq.write_table(predictions, temporary / "test_predictions.parquet", compression="zstd")
        save_model(bundle, temporary / "model.joblib")
        write_manifest(temporary / "feature_importance.json", importance)
        write_manifest(
            temporary / "calibrator.json",
            {
                "frozen_before_test": True,
                "calibrator": calibrator.to_dict(),
                "diagnostics": calibration_diagnostics,
            },
        )
        write_manifest(
            temporary / "threshold.json",
            {
                "frozen_before_test": True,
                "policy": policy.to_dict(),
                "diagnostics": threshold_diagnostics,
            },
        )
        backtest = {
            "fold_id": plan.fold_id,
            "candidate": candidate,
            "validation_predictive": validation_metrics,
            "calibration_predictive_raw": regression_metrics(
                _target(fold.calibration), calibration_raw
            ),
            "calibration_predictive_calibrated": regression_metrics(
                _target(fold.calibration), calibration_predictions
            ),
            "test_predictive_raw": test_predictive_raw,
            "test_predictive_calibrated": test_predictive_calibrated,
            "negative_control": negative_control,
            "test_reliability_curve": prediction_buckets(
                _target(test),
                test_calibrated,
                bucket_count=config.calibration.reliability_buckets,
            ),
            "cost_stress": cost_stress,
            "purging_and_embargo": fold.report,
            "feature_drift": _feature_drift(fold.train, test, columns),
            "test_access": {
                "released_after_frozen_identity": frozen_identity,
                "early_stopping_used_test": False,
                "calibration_used_test": False,
                "threshold_selection_used_test": False,
            },
        }
        write_manifest(temporary / "backtest.json", backtest)
        file_names = [
            "model.joblib",
            "feature_importance.json",
            "calibrator.json",
            "threshold.json",
            "test_predictions.parquet",
            "backtest.json",
            *[f"test_trades_{multiplier:g}x.parquet" for multiplier in config.cost_multipliers],
        ]
        manifest = {
            "status": "complete",
            "identity": model_identity,
            "frozen_identity": frozen_identity,
            "candidate": candidate,
            "fold": plan.to_dict(),
            "feature_schema": _feature_schema(columns),
            "files": {name: file_sha256(temporary / name) for name in file_names},
            "created_at": datetime.now(UTC).isoformat(),
            "prospective_holdout_used": False,
            "version": WALK_FORWARD_VERSION,
        }
        write_manifest(temporary / "fold_manifest.json", manifest)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _load_fold(final, config)


def _concat(tables: list[pa.Table]) -> pa.Table:
    nonempty = [table for table in tables if table.num_rows]
    if nonempty:
        return pa.concat_tables(nonempty, promote_options="default")
    if not tables:
        return pa.table({})
    return tables[0]


def _block_bootstrap_predictive(
    actual: np.ndarray,
    predicted: np.ndarray,
    *,
    samples: int,
    block_rows: int,
    confidence: float,
    seed: int,
) -> dict[str, Any]:
    blocks: list[tuple[float, ...]] = []
    for start in range(0, len(actual), block_rows):
        left, right = actual[start : start + block_rows], predicted[start : start + block_rows]
        blocks.append(
            (
                len(left),
                float(np.sum(left)),
                float(np.sum(right)),
                float(np.sum(left * left)),
                float(np.sum(right * right)),
                float(np.sum(left * right)),
                float(np.sum(np.abs(right - left))),
                float(np.sum((right - left) ** 2)),
                float(np.sum(np.sign(left) == np.sign(right))),
            )
        )
    matrix = np.asarray(blocks, dtype=np.float64)
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {
        name: [] for name in ("mae", "rmse", "pearson_ic", "directional_accuracy")
    }
    for _ in range(samples):
        totals = np.sum(matrix[rng.integers(0, len(matrix), len(matrix))], axis=0)
        count, sum_y, sum_p, sum_y2, sum_p2, sum_yp, absolute, squared, direction = totals
        covariance = sum_yp - sum_y * sum_p / count
        variance_y = sum_y2 - sum_y**2 / count
        variance_p = sum_p2 - sum_p**2 / count
        correlation = covariance / np.sqrt(max(variance_y * variance_p, 1e-30))
        draws["mae"].append(float(absolute / count))
        draws["rmse"].append(float(np.sqrt(squared / count)))
        draws["pearson_ic"].append(float(correlation))
        draws["directional_accuracy"].append(float(direction / count))
    alpha = (1 - confidence) / 2
    return {
        "method": "moving/non-overlapping block resampling with additive sufficient statistics",
        "samples": samples,
        "block_rows": block_rows,
        "confidence": confidence,
        "intervals": {
            name: {
                "lower": float(np.quantile(values, alpha)),
                "upper": float(np.quantile(values, 1 - alpha)),
            }
            for name, values in draws.items()
        },
    }


def _economic_bootstrap(
    trades: pa.Table, *, samples: int, confidence: float, seed: int
) -> dict[str, Any]:
    if trades.num_rows < 100:
        return {"status": "insufficient_trades", "trade_count": trades.num_rows}
    values = _floats(trades, "net_return")
    rng = np.random.default_rng(seed)
    expectancy = np.empty(samples, dtype=np.float64)
    for index in range(samples):
        expectancy[index] = np.mean(values[rng.integers(0, len(values), len(values))])
    alpha = (1 - confidence) / 2
    return {
        "status": "complete",
        "method": "trade-level resampling; predictive inference remains primary",
        "expectancy": {
            "lower": float(np.quantile(expectancy, alpha)),
            "upper": float(np.quantile(expectancy, 1 - alpha)),
        },
    }


def _concentration(trades: pa.Table) -> dict[str, Any]:
    if trades.num_rows == 0:
        return {"trade_count": 0, "top_1_pct": None, "top_5_pct": None, "top_10_pct": None}
    values = _floats(trades, "net_return")
    positive_total = float(np.sum(np.clip(values, 0, None)))
    ordered = np.sort(np.clip(values, 0, None))[::-1]
    result: dict[str, Any] = {"trade_count": len(values), "positive_pnl_total": positive_total}
    for percentage in (1, 5, 10):
        count = max(1, int(np.ceil(len(values) * percentage / 100)))
        result[f"top_{percentage}_pct"] = (
            None if positive_total == 0 else float(np.sum(ordered[:count]) / positive_total)
        )
    return result


def _group_trade_metrics(trades: pa.Table) -> dict[str, Any]:
    if trades.num_rows == 0:
        return {"year": {}, "regime": {}, "direction": {}}
    net = _floats(trades, "net_return")
    times = trades.column("entry_time").to_pylist()
    year: dict[str, Any] = {}
    for value in sorted({item.year for item in times}):
        mask = np.asarray([item.year == value for item in times])
        year[str(value)] = {
            "trades": int(np.sum(mask)),
            "expectancy": float(np.mean(net[mask])),
            "net_return": float(np.sum(net[mask])),
        }
    regime: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ):
        if name not in trades.column_names:
            continue
        mask = _floats(trades, name).astype(bool)
        if np.any(mask):
            regime[name] = {
                "trades": int(np.sum(mask)),
                "expectancy": float(np.mean(net[mask])),
                "net_return": float(np.sum(net[mask])),
            }
    directions = trades.column("direction").to_numpy()
    direction = {}
    for value, label in ((1, "long"), (-1, "short")):
        mask = directions == value
        direction[label] = {
            "trades": int(np.sum(mask)),
            "expectancy": float(np.mean(net[mask])) if np.any(mask) else None,
            "net_return": float(np.sum(net[mask])),
        }
    taker_flow: list[dict[str, Any]] = []
    if "taker_flow_imbalance_quote" in trades.column_names:
        flow = _floats(trades, "taker_flow_imbalance_quote")
        for number, indices in enumerate(
            np.array_split(np.argsort(flow, kind="mergesort"), min(5, len(flow))), start=1
        ):
            taker_flow.append(
                {
                    "bucket": number,
                    "trades": len(indices),
                    "mean_flow": float(np.mean(flow[indices])),
                    "expectancy": float(np.mean(net[indices])),
                    "net_return": float(np.sum(net[indices])),
                }
            )
    funding: list[dict[str, Any]] = []
    if "funding_rate" in trades.column_names:
        rates = _floats(trades, "funding_rate")
        for number, indices in enumerate(
            np.array_split(np.argsort(rates, kind="mergesort"), min(5, len(rates))), start=1
        ):
            funding.append(
                {
                    "bucket": number,
                    "trades": len(indices),
                    "mean_funding_rate": float(np.mean(rates[indices])),
                    "expectancy": float(np.mean(net[indices])),
                    "net_return": float(np.sum(net[indices])),
                }
            )
    return {
        "year": year,
        "regime": regime,
        "direction": direction,
        "taker_flow": taker_flow,
        "funding": funding,
    }


def _top_positive_group_share(groups: dict[str, Any]) -> float | None:
    values = np.asarray(
        [max(0.0, float(item["net_return"])) for item in groups.values()], dtype=np.float64
    )
    total = float(np.sum(values))
    return None if total == 0 else float(np.max(values) / total)


def _prediction_year_metrics(predictions: pa.Table) -> dict[str, Any]:
    years = np.asarray([item.year for item in predictions.column("feature_time").to_pylist()])
    actual = _floats(predictions, TARGET_COLUMN)
    predicted = _floats(predictions, "calibrated_prediction")
    return {
        str(year): regression_metrics(actual[years == year], predicted[years == year])
        for year in np.unique(years)
    }


def _aggregate_feature_drift(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_feature: dict[str, list[dict[str, float]]] = {}
    for record in records:
        for name, values in record["backtest"]["feature_drift"]["features"].items():
            by_feature.setdefault(name, []).append(values)
    aggregate = {
        name: {
            "mean_psi": float(np.mean([item["psi"] for item in values])),
            "maximum_psi": float(np.max([item["psi"] for item in values])),
            "mean_absolute_median_shift_train_iqr": float(
                np.mean([abs(item["median_shift_train_iqr"]) for item in values])
            ),
        }
        for name, values in by_feature.items()
    }
    ranking = sorted(aggregate, key=lambda name: aggregate[name]["mean_psi"], reverse=True)
    return {"features": aggregate, "highest_mean_psi_features": ranking[:10]}


def _fold_pnl_concentration(records: list[dict[str, Any]]) -> float | None:
    pnl = np.asarray(
        [record["backtest"]["cost_stress"]["1.0"]["total_net_return"] for record in records],
        dtype=np.float64,
    )
    positive = np.clip(pnl, 0, None)
    total = float(np.sum(positive))
    return None if total == 0 else float(np.max(positive) / total)


def _qualify(aggregate: dict[str, Any], config: WalkForwardConfig) -> dict[str, Any]:
    rules = config.qualification
    fold_expectancy = [
        item["base_expectancy"]
        for item in aggregate["folds"]
        if item["base_expectancy"] is not None
    ]
    median_expectancy = float(np.median(fold_expectancy)) if fold_expectancy else None
    base = aggregate["economic"]["1.0"]
    stress_key = str(rules.required_cost_multiplier)
    stress = aggregate["economic"].get(stress_key, {})
    gates = {
        "minimum_test_folds": aggregate["fold_count"] >= rules.minimum_test_folds,
        "minimum_total_trades": base["trade_count"] >= rules.minimum_total_trades,
        "minimum_reliable_folds": aggregate["reliable_fold_count"] >= rules.minimum_reliable_folds,
        "positive_median_fold_expectancy": median_expectancy is not None and median_expectancy > 0,
        "positive_pooled_base_expectancy": base["expectancy"] is not None
        and base["expectancy"] > 0,
        "maximum_drawdown": abs(base["maximum_drawdown"]) <= rules.maximum_drawdown,
        "positive_required_cost_stress": stress.get("expectancy") is not None
        and stress["expectancy"] > 0,
        "fold_concentration": aggregate["top_fold_positive_pnl_share"] is not None
        and aggregate["top_fold_positive_pnl_share"] <= rules.maximum_top_fold_pnl_share,
        "year_concentration": aggregate["top_year_positive_pnl_share"] is not None
        and aggregate["top_year_positive_pnl_share"] <= rules.maximum_top_year_pnl_share,
        "regime_concentration": aggregate["top_regime_positive_pnl_share"] is not None
        and aggregate["top_regime_positive_pnl_share"] <= rules.maximum_top_regime_pnl_share,
    }
    insufficient = not gates["minimum_total_trades"] or not gates["minimum_reliable_folds"]
    status = "INCONCLUSIVE" if insufficient else "PASS" if all(gates.values()) else "FAIL"
    return {
        "status": status,
        "qualified": status == "PASS",
        "gates": gates,
        "median_fold_expectancy": median_expectancy,
    }


def _fold_metric_row(candidate: str, record: dict[str, Any]) -> dict[str, Any]:
    manifest, backtest = record["manifest"], record["backtest"]
    base = backtest["cost_stress"]["1.0"]
    predictive = backtest["test_predictive_calibrated"]
    return {
        "candidate": candidate,
        "fold_id": manifest["fold"]["fold_id"],
        "test_start": manifest["fold"]["test_start"],
        "test_end": manifest["fold"]["test_end"],
        "test_count": predictive["count"],
        "mae": predictive["mae"],
        "rmse": predictive["rmse"],
        "r2": predictive["r2"],
        "directional_accuracy": predictive["directional_accuracy"],
        "pearson_ic": predictive["pearson_ic"],
        "spearman_ic": predictive["spearman_ic"],
        "trade_count": base["trade_count"],
        "expectancy": base["expectancy"],
        "net_return": base["total_net_return"],
        "maximum_drawdown": base["maximum_drawdown"],
        "reliable": base["reliable"],
        "threshold_bps": record["threshold"]["policy"]["threshold_bps"],
        "threshold_decision": record["threshold"]["policy"]["decision"],
        "calibration_method": record["calibration"]["calibrator"]["method"],
        "prediction_mean": predictive["prediction_mean"],
        "prediction_std": predictive["prediction_std"],
    }


def _summarize_candidate(
    candidate: str,
    records: list[dict[str, Any]],
    config: WalkForwardConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    predictions = _concat([record["predictions"] for record in records])
    times = _times(predictions, "feature_time")
    if len(times) != len(np.unique(times)):
        raise ValueError(f"{candidate} has duplicate OOS feature_time rows")
    actual, predicted = (
        _floats(predictions, TARGET_COLUMN),
        _floats(predictions, "calibrated_prediction"),
    )
    fold_rows = [_fold_metric_row(candidate, record) for record in records]
    economic: dict[str, Any] = {}
    trades_by_cost: dict[str, pa.Table] = {}
    for multiplier in config.cost_multipliers:
        key = str(multiplier)
        trades = _concat([record["stress_trades"][key] for record in records])
        trades_by_cost[key] = trades
        economic[key] = economic_metrics(
            trades,
            opportunity_count=predictions.num_rows,
            minimum_reliable_trade_count=config.qualification.minimum_reliable_trades_per_fold,
        )
    base_trades = trades_by_cost["1.0"]
    grouped = _group_trade_metrics(base_trades)
    thresholds = [record["threshold"]["policy"]["threshold_bps"] for record in records]
    aggregate = {
        "candidate": candidate,
        "fold_count": len(records),
        "reliable_fold_count": sum(row["reliable"] for row in fold_rows),
        "zero_trade_fold_count": sum(row["trade_count"] == 0 for row in fold_rows),
        "positive_ic_fold_count": sum(
            row["pearson_ic"] is not None and row["pearson_ic"] > 0 for row in fold_rows
        ),
        "negative_ic_fold_count": sum(
            row["pearson_ic"] is not None and row["pearson_ic"] < 0 for row in fold_rows
        ),
        "positive_net_fold_count": sum(row["net_return"] > 0 for row in fold_rows),
        "negative_net_fold_count": sum(row["net_return"] < 0 for row in fold_rows),
        "predictive": regression_metrics(actual, predicted),
        "predictive_by_year": _prediction_year_metrics(predictions),
        "predictive_bootstrap": _block_bootstrap_predictive(
            actual,
            predicted,
            samples=config.bootstrap.samples,
            block_rows=config.bootstrap.block_rows,
            confidence=config.bootstrap.confidence,
            seed=config.seed,
        ),
        "economic": economic,
        "economic_bootstrap": _economic_bootstrap(
            base_trades,
            samples=config.bootstrap.samples,
            confidence=config.bootstrap.confidence,
            seed=config.seed,
        ),
        "folds": [
            {
                "fold_id": row["fold_id"],
                "pearson_ic": row["pearson_ic"],
                "base_expectancy": row["expectancy"],
                "base_net_return": row["net_return"],
                "trade_count": row["trade_count"],
                "reliable": row["reliable"],
            }
            for row in fold_rows
        ],
        "threshold_history": thresholds,
        "threshold_stability": {
            "no_trade_policy_folds": sum(value is None for value in thresholds),
            "mean_bps": (
                float(np.mean([value for value in thresholds if value is not None]))
                if any(value is not None for value in thresholds)
                else None
            ),
            "std_bps": (
                float(np.std([value for value in thresholds if value is not None]))
                if any(value is not None for value in thresholds)
                else None
            ),
        },
        "top_fold_positive_pnl_share": _fold_pnl_concentration(records),
        "trade_concentration": _concentration(base_trades),
        "diagnostics": grouped,
        "top_year_positive_pnl_share": _top_positive_group_share(grouped["year"]),
        "top_regime_positive_pnl_share": _top_positive_group_share(grouped["regime"]),
        "feature_drift": _aggregate_feature_drift(records),
        "prediction_stability": {
            "fold_prediction_means": [row["prediction_mean"] for row in fold_rows],
            "fold_prediction_stds": [row["prediction_std"] for row in fold_rows],
        },
    }
    aggregate["qualification"] = _qualify(aggregate, config)
    aggregate["_predictions"] = predictions
    aggregate["_trades"] = trades_by_cost
    return aggregate, fold_rows


def _strip_runtime(aggregate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in aggregate.items() if not key.startswith("_")}


def _threshold_rows(candidate: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate": candidate,
            "fold_id": record["manifest"]["fold"]["fold_id"],
            "calibration_method": record["calibration"]["calibrator"]["method"],
            "calibration_slope": record["calibration"]["calibrator"]["slope"],
            "calibration_intercept": record["calibration"]["calibrator"]["intercept"],
            **record["threshold"]["policy"],
        }
        for record in records
    ]


def _replace_baseline_predictions(predictions: pa.Table, values: np.ndarray, name: str) -> pa.Table:
    result = predictions.set_column(
        predictions.schema.get_field_index("calibrated_prediction"),
        "calibrated_prediction",
        pa.array(values, type=pa.float64()),
    )
    return result.set_column(
        result.schema.get_field_index("candidate"),
        "candidate",
        pa.array([name] * result.num_rows),
    )


def _baseline_summary(
    predictions: pa.Table,
    backtest_config: Any,
    funding: pa.Table | None,
    execution_1m: pa.Table | None,
) -> dict[str, Any]:
    actual = _floats(predictions, TARGET_COLUMN)
    flat = regression_metrics(actual, np.zeros(len(actual)))
    first_entry = float(predictions.column("entry_reference_price")[0].as_py())
    last_exit = float(predictions.column("future_reference_price")[-1].as_py())
    buy_hold = last_exit / first_entry - 1 - backtest_config.non_funding_round_trip_bps / 10_000
    policy = ThresholdPolicy(2.0, "FIXED_BASELINE", 0, None)
    rule_results: dict[str, Any] = {}
    for name, values in {
        "momentum": _floats(predictions, "return_1h"),
        "mean_reversion": -_floats(predictions, "ema20_distance"),
    }.items():
        _, metrics = simulate_trades(
            _replace_baseline_predictions(predictions, values, name),
            policy,
            backtest_config,
            funding=funding,
            execution_1m=execution_1m,
        )
        rule_results[name] = {
            "predictive": regression_metrics(actual, values),
            "economic": metrics,
        }
    return {
        "flat_predictive": flat,
        "flat_economic": {
            "trade_count": 0,
            "net_return": 0.0,
            "policy": "NO_TRADE",
        },
        "buy_and_hold_net_return": float(buy_hold),
        "buy_and_hold_leverage": 1.0,
        "momentum": rule_results["momentum"],
        "mean_reversion": rule_results["mean_reversion"],
        "note": (
            "Rule baselines share the identical pooled test timestamps; "
            "no threshold was tuned on test."
        ),
    }


def walk_forward_plan(config: WalkForwardConfig) -> dict[str, Any]:
    table, manifest = read_gold_v2_1(config.dataset_manifest)
    start = table.column("feature_time")[0].as_py()
    data_end = min(
        config.prospective_holdout_start,
        table.column("feature_time")[-1].as_py() + timedelta(minutes=5),
    )
    plans = plan_folds(start, data_end, config.prospective_holdout_start, config.schedule)
    validate_fold_plan(plans, config.prospective_holdout_start)
    schemas = {
        candidate: _feature_schema(columns)
        for candidate, columns in _candidate_columns(config).items()
    }
    return {
        "name": config.name,
        "family": config.family,
        "configuration_hash": config.configuration_hash,
        "dataset_version": manifest["dataset_version"],
        "prospective_holdout_start": config.prospective_holdout_start.isoformat(),
        "prospective_holdout_used": False,
        "schedule": config.schedule.model_dump(mode="json"),
        "candidate_feature_schemas": schemas,
        "fold_count": len(plans),
        "folds": [plan.to_dict() for plan in plans],
    }


def run_walk_forward(
    config: WalkForwardConfig,
    *,
    resume: bool = False,
    plan_only: bool = False,
) -> dict[str, Any]:
    plan_payload = walk_forward_plan(config)
    if plan_only:
        return plan_payload
    gold, gold_manifest = read_gold_v2_1(config.dataset_manifest)
    expected_family = "core_long_history" if config.family == "primary" else "derivatives_overlap"
    if gold_manifest.get("dataset_family") != expected_family:
        raise ValueError(f"{config.family} walk-forward requires {expected_family} Gold")
    holdout_us = int(config.prospective_holdout_start.timestamp() * 1_000_000)
    if np.any(_times(gold, "feature_time") >= holdout_us):
        gold = gold.filter(pa.array(_times(gold, "feature_time") < holdout_us))
    plans = tuple(
        FoldPlan(
            **{
                key: datetime.fromisoformat(value) if key.endswith(("start", "end")) else value
                for key, value in item.items()
            }
        )
        for item in plan_payload["folds"]
    )
    identity = {
        "version": WALK_FORWARD_VERSION,
        "configuration": config.model_dump(mode="json"),
        "dataset_version": gold_manifest["dataset_version"],
        "dataset_sha256": gold_manifest["sha256"],
        "model_config_sha256": file_sha256(config.experiment_config),
        "backtest_config_sha256": file_sha256(config.backtest_config),
        "feature_schemas": plan_payload["candidate_feature_schemas"],
    }
    run_id = f"wf-{config.name}-{_hash(identity)}"
    run_directory = config.artifact_root.resolve() / run_id
    summary_path = run_directory / "walkforward_summary.json"
    existing_summary = read_manifest(summary_path)
    if resume and existing_summary is not None:
        if existing_summary.get("identity_hash") != _hash(identity):
            raise ValueError("completed walk-forward identity does not match requested run")
        return existing_summary
    if summary_path.exists():
        raise FileExistsError(f"refusing to overwrite completed walk-forward: {run_directory}")
    funding = None
    funding_version = None
    if config.funding_manifest is not None:
        funding, funding_metadata = read_market_dataset(
            config.funding_manifest, MarketDataKind.FUNDING
        )
        funding_version = funding_metadata["dataset_version"]
    execution_1m = None
    execution_version = None
    if config.execution_1m_silver_manifest is not None:
        execution_1m, execution_metadata, _ = _load_silver(
            DatasetBuildConfig(
                silver_manifest=config.execution_1m_silver_manifest,
                symbol="BTCUSDT",
                interval="1m",
            )
        )
        execution_version = execution_metadata["silver_dataset_version"]
    run_directory.mkdir(parents=True, exist_ok=True)
    schemas = _candidate_columns(config)
    candidate_records: dict[str, list[dict[str, Any]]] = {
        candidate: [] for candidate in config.candidates
    }
    for plan in plans:
        fold = slice_fold(gold, plan, config.schedule, config.prospective_holdout_start)
        for candidate, columns in schemas.items():
            candidate_records[candidate].append(
                _run_fold(
                    fold,
                    plan,
                    candidate,
                    columns,
                    config,
                    run_directory,
                    funding,
                    execution_1m,
                    resume=resume,
                )
            )
    aggregates: dict[str, dict[str, Any]] = {}
    fold_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    all_predictions: list[pa.Table] = []
    all_trades: list[pa.Table] = []
    for candidate in config.candidates:
        aggregate, rows = _summarize_candidate(candidate, candidate_records[candidate], config)
        aggregates[candidate] = aggregate
        fold_rows.extend(rows)
        threshold_rows.extend(_threshold_rows(candidate, candidate_records[candidate]))
        all_predictions.append(aggregate["_predictions"])
        all_trades.append(aggregate["_trades"]["1.0"])
    first = aggregates[config.candidates[0]]
    backtest_config = load_backtest_v2_1_config(config.backtest_config)
    comparison = {
        "left": config.candidates[0],
        "right": config.candidates[1],
        "matched_test_rows": first["_predictions"].num_rows
        == aggregates[config.candidates[1]]["_predictions"].num_rows,
        "matched_test_feature_times": np.array_equal(
            _times(first["_predictions"], "feature_time"),
            _times(aggregates[config.candidates[1]]["_predictions"], "feature_time"),
        ),
        "pearson_ic_delta_right_minus_left": (
            aggregates[config.candidates[1]]["predictive"]["pearson_ic"]
            - first["predictive"]["pearson_ic"]
        ),
        "base_expectancy_delta_right_minus_left": (
            (aggregates[config.candidates[1]]["economic"]["1.0"]["expectancy"] or 0.0)
            - (first["economic"]["1.0"]["expectancy"] or 0.0)
        ),
    }
    if config.family == "derivatives":
        left = aggregates["D0"]
        right = aggregates["D2"]
        enough = all(
            candidate["economic"]["1.0"]["trade_count"] >= config.qualification.minimum_total_trades
            and candidate["reliable_fold_count"] >= config.qualification.minimum_reliable_folds
            for candidate in (left, right)
        )
        improved = (
            comparison["pearson_ic_delta_right_minus_left"] > 0
            and comparison["base_expectancy_delta_right_minus_left"] > 0
        )
        comparison["D2_value_classification"] = (
            "INCONCLUSIVE" if not enough else "VALUE ADDED" if improved else "NO VALUE"
        )
    pq.write_table(
        _concat(all_predictions), run_directory / "oos_predictions.parquet", compression="zstd"
    )
    pq.write_table(_concat(all_trades), run_directory / "oos_trades.parquet", compression="zstd")
    pq.write_table(
        pa.Table.from_pylist(fold_rows), run_directory / "fold_metrics.parquet", compression="zstd"
    )
    pq.write_table(
        pa.Table.from_pylist(threshold_rows),
        run_directory / "threshold_history.parquet",
        compression="zstd",
    )
    summary = {
        "run_id": run_id,
        "status": "complete",
        "phase": 5,
        "result_type": "RETROSPECTIVE WALK-FORWARD OOS",
        "created_at": datetime.now(UTC).isoformat(),
        "identity_hash": _hash(identity),
        "identity": identity,
        "configuration_hash": config.configuration_hash,
        "family": config.family,
        "dataset_manifest": str(config.dataset_manifest.resolve()),
        "dataset_version": gold_manifest["dataset_version"],
        "funding_dataset_version": funding_version,
        "execution_1m_dataset_version": execution_version,
        "prospective_holdout_start": config.prospective_holdout_start.isoformat(),
        "prospective_holdout_used": False,
        "walk_forward_design": plan_payload,
        "candidates": {
            candidate: _strip_runtime(aggregates[candidate]) for candidate in config.candidates
        },
        "candidate_comparison": comparison,
        "baselines": _baseline_summary(
            first["_predictions"], backtest_config, funding, execution_1m
        ),
        "machine_readable_outputs": {
            "fold_metrics": "fold_metrics.parquet",
            "oos_predictions": "oos_predictions.parquet",
            "oos_trades": "oos_trades.parquet",
            "threshold_history": "threshold_history.parquet",
        },
        "known_limitations": [
            "Retrospective OOS folds are not the untouched prospective holdout.",
            (
                "Execution is bar-based: one-minute next-open where covered, "
                "conservative next-5m-open fallback elsewhere."
            ),
            (
                "Costs are frozen conservative research assumptions, "
                "not account-specific current terms."
            ),
            "Economic bootstrap is secondary and suppressed below 100 trades.",
            (
                "No leverage, portfolio, market-impact, live order, "
                "or private-account behavior is modeled."
            ),
        ],
        "version": WALK_FORWARD_VERSION,
    }
    write_manifest(summary_path, summary)
    return summary


def compare_walk_forward_candidates(
    primary_summary_path: Path, derivatives_summary_path: Path, *, output: Path | None = None
) -> dict[str, Any]:
    primary = read_manifest(primary_summary_path.resolve())
    derivatives = read_manifest(derivatives_summary_path.resolve())
    if primary is None or derivatives is None:
        raise FileNotFoundError("both completed walk-forward summaries are required")
    if primary.get("family") != "primary" or derivatives.get("family") != "derivatives":
        raise ValueError("candidate comparison requires primary then derivatives summaries")
    if primary.get("prospective_holdout_used") or derivatives.get("prospective_holdout_used"):
        raise ValueError("prospective holdout contamination detected")
    candidates = {**primary["candidates"], **derivatives["candidates"]}
    qualification = derivatives["identity"]["configuration"]["qualification"]
    derivatives_evidence = all(
        candidates[name]["economic"]["1.0"]["trade_count"] >= qualification["minimum_total_trades"]
        and candidates[name]["reliable_fold_count"] >= qualification["minimum_reliable_folds"]
        for name in ("D0", "D2")
    )
    derivatives_comparison = dict(derivatives["candidate_comparison"])
    if not derivatives_evidence:
        derivatives_comparison["D2_value_classification"] = "INCONCLUSIVE"
        derivatives_comparison["classification_reason"] = (
            "matched candidates do not both meet total-trade and reliable-fold minima"
        )
    qualified = [
        name for name, result in candidates.items() if result["qualification"]["qualified"]
    ]
    if qualified:
        winner = max(
            qualified,
            key=lambda name: candidates[name]["economic"]["1.0"]["expectancy"],
        )
        decision = f"{winner} RESEARCH CHAMPION"
    else:
        decision = "NO QUALIFIED MODEL"
    result = {
        "status": "complete",
        "result_type": "RETROSPECTIVE WALK-FORWARD OOS",
        "prospective_holdout_used": False,
        "prospective_holdout_start": primary["prospective_holdout_start"],
        "primary_run_id": primary["run_id"],
        "derivatives_run_id": derivatives["run_id"],
        "candidate_qualification": {
            name: value["qualification"] for name, value in candidates.items()
        },
        "L0_vs_L5": primary["candidate_comparison"],
        "D0_vs_D2": derivatives_comparison,
        "champion_decision": decision,
    }
    if output is not None:
        write_manifest(output.resolve(), result)
    return result
