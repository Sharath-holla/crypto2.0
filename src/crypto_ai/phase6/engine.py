from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase4.features import ExternalTables
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase6.config import (
    FEATURE_RESEARCH_VERSION,
    LABEL_RESEARCH_VERSION,
    PHASE6_VERSION,
    Phase6Config,
)
from crypto_ai.phase6.data import (
    aggregate_candles,
    coverage_report,
    load_silver_family,
    reconcile_direct_vs_derived,
)
from crypto_ai.phase6.features import (
    FEATURE_GROUPS_V3_RESEARCH,
    NEW_FEATURE_GROUPS,
    generate_features_v3_research,
)
from crypto_ai.phase6.labels import HORIZON_STEPS, generate_research_labels
from crypto_ai.research.gold import _atomic_write_parquet
from crypto_ai.research.metrics import (
    distribution_summary,
    feature_distribution,
    regression_metrics,
)


def _hash(payload: Any, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def _write_json_immutable(path: Path, payload: dict[str, Any]) -> str:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise FileExistsError(f"Refusing to overwrite Phase 6 artifact: {path}")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{_hash(datetime.now(UTC).isoformat())}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return digest


def _filter_market(table: pa.Table, cutoff: datetime) -> pa.Table:
    cutoff_us = int(cutoff.timestamp() * 1_000_000)
    event = table.column("event_time").combine_chunks().cast(pa.int64()).to_numpy()
    available = table.column("availability_time").combine_chunks().cast(pa.int64()).to_numpy()
    return table.filter(pa.array((event < cutoff_us) & (available < cutoff_us)))


def _external(config: Phase6Config) -> tuple[ExternalTables, dict[str, Any]]:
    tables: dict[str, pa.Table | None] = {"funding": None, "mark": None, "index": None}
    lineage: dict[str, Any] = {}
    for name, path, kind in (
        ("funding", config.funding_manifest, MarketDataKind.FUNDING),
        ("mark", config.mark_manifest, MarketDataKind.MARK_KLINE),
        ("index", config.index_manifest, MarketDataKind.INDEX_KLINE),
    ):
        if path is None:
            continue
        table, manifest = read_market_dataset(path, kind)
        table = _filter_market(table, config.phase6_research_cutoff)
        tables[name] = table
        lineage[name] = {
            "manifest": str(path.resolve()),
            "dataset_version": manifest["dataset_version"],
            "sha256": manifest["sha256"],
            "rows_before_cutoff": table.num_rows,
        }
    return ExternalTables(
        funding=tables["funding"], mark=tables["mark"], index=tables["index"]
    ), lineage


def _timestamp(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC).isoformat()


def _correlation(left: np.ndarray, right: np.ndarray) -> tuple[float | None, float | None]:
    finite = np.isfinite(left) & np.isfinite(right)
    if np.count_nonzero(finite) < 3:
        return None, None
    metrics = regression_metrics(left[finite], right[finite])
    return metrics["pearson_ic"], metrics["spearman_ic"]


def _balanced_directional_accuracy(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    positive = actual > 0
    negative = actual < 0
    if not np.any(positive) or not np.any(negative):
        return None
    true_positive_rate = float(np.mean(predicted[positive] > 0))
    true_negative_rate = float(np.mean(predicted[negative] < 0))
    return (true_positive_rate + true_negative_rate) / 2.0


def _model_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    return regression_metrics(actual, predicted) | {
        "balanced_directional_accuracy": _balanced_directional_accuracy(actual, predicted)
    }


def _prediction_deciles(actual: np.ndarray, predicted: np.ndarray) -> list[dict[str, Any]]:
    ordered = np.argsort(predicted, kind="mergesort")
    result: list[dict[str, Any]] = []
    for bucket, indices in enumerate(np.array_split(ordered, min(10, len(ordered))), start=1):
        selected_actual = actual[indices]
        selected_predicted = predicted[indices]
        result.append(
            {
                "decile": bucket,
                "count": int(len(indices)),
                "mean_predicted_return": float(np.mean(selected_predicted)),
                "mean_actual_return": float(np.mean(selected_actual)),
                "median_actual_return": float(np.median(selected_actual)),
                "positive_rate": float(np.mean(selected_actual > 0)),
                "minimum_prediction": float(np.min(selected_predicted)),
                "maximum_prediction": float(np.max(selected_predicted)),
            }
        )
    return result


def _table_range(table: pa.Table | None, time_column: str) -> dict[str, Any] | None:
    if table is None or not table.num_rows:
        return None
    times = table.column(time_column).combine_chunks().cast(pa.int64()).to_numpy()
    return {
        "row_count": table.num_rows,
        "first_timestamp": _timestamp(int(times[0])),
        "last_timestamp": _timestamp(int(times[-1])),
    }


def _feature_reports(
    values: dict[str, np.ndarray],
    columns: tuple[str, ...],
    groups: tuple[str, ...],
    times: np.ndarray,
    targets: dict[str, np.ndarray],
    sample: np.ndarray,
    redundancy_threshold: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    years = times.astype("datetime64[us]").astype("datetime64[Y]").astype(np.int64) + 1970
    months = times.astype("datetime64[us]").astype("datetime64[M]").astype(str)
    coverage: dict[str, Any] = {}
    stability: dict[str, Any] = {}
    for name in columns:
        raw = values[name]
        finite = np.isfinite(raw)
        positions = np.flatnonzero(finite)
        coverage[name] = feature_distribution(raw) | {
            "group": next(group for group in groups if name in FEATURE_GROUPS_V3_RESEARCH[group]),
            "first_available_time": _timestamp(int(times[positions[0]]))
            if len(positions)
            else None,
            "last_available_time": _timestamp(int(times[positions[-1]]))
            if len(positions)
            else None,
            "warmup_rows": int(positions[0]) if len(positions) else len(raw),
        }
        finite_values = raw[finite]
        if not len(finite_values):
            stability[name] = {"monthly": {}, "yearly": {}}
            continue
        global_median = float(np.median(finite_values))
        q25, q75 = np.percentile(finite_values, [25, 75])
        scale = max(float(q75 - q25), 1e-12)
        stability[name] = {
            "monthly": {
                str(period): {
                    "count": int(np.count_nonzero((months == period) & finite)),
                    "median_shift_global_iqr": float(
                        (np.median(raw[(months == period) & finite]) - global_median) / scale
                    ),
                }
                for period in np.unique(months[finite])
            },
            "yearly": {
                str(int(year)): {
                    "count": int(np.count_nonzero((years == year) & finite)),
                    "median_shift_global_iqr": float(
                        (np.median(raw[(years == year) & finite]) - global_median) / scale
                    ),
                }
                for year in np.unique(years[finite])
            },
        }

    selected_matrix = np.column_stack([values[name][sample] for name in columns])
    finite_rows = np.all(np.isfinite(selected_matrix), axis=1)
    matrix = selected_matrix[finite_rows]
    correlation = np.corrcoef(matrix, rowvar=False)
    redundant: list[dict[str, Any]] = []
    for left in range(len(columns)):
        for right in range(left + 1, len(columns)):
            value = float(correlation[left, right])
            if abs(value) >= redundancy_threshold:
                redundant.append({"left": columns[left], "right": columns[right], "pearson": value})
    redundant.sort(key=lambda row: abs(row["pearson"]), reverse=True)

    ic: dict[str, Any] = {}
    for name in columns:
        ic[name] = {}
        for horizon, target in targets.items():
            pearson, spearman = _correlation(values[name][sample], target[sample])
            ic[name][horizon] = {"pearson_ic": pearson, "spearman_ic": spearman}
    return (
        {"feature_version": FEATURE_RESEARCH_VERSION, "features": coverage},
        {
            "feature_version": FEATURE_RESEARCH_VERSION,
            "drift_metric": "median shift divided by full-sample IQR",
            "features": stability,
        },
        {
            "threshold": redundancy_threshold,
            "sample_rows": int(np.count_nonzero(finite_rows)),
            "redundant_pairs": redundant,
            "feature_target_information_decay": ic,
        },
    )


def _target_reports(
    labels: dict[str, np.ndarray],
    mask: np.ndarray,
    times: np.ndarray,
    regimes: dict[str, np.ndarray],
    daily_volatility: np.ndarray,
) -> tuple[dict[str, Any], dict[str, Any]]:
    years = times.astype("datetime64[us]").astype("datetime64[Y]").astype(np.int64) + 1970
    targets: dict[str, Any] = {}
    excursion: dict[str, Any] = {}
    for horizon in HORIZON_STEPS:
        target = labels[f"forward_return_{horizon}"]
        selected = target[mask]
        auto = [
            float(np.corrcoef(selected[:-lag], selected[lag:])[0, 1])
            for lag in (1, 3, 12)
            if len(selected) > lag and np.std(selected[:-lag]) > 0 and np.std(selected[lag:]) > 0
        ]
        targets[horizon] = {
            "overall": distribution_summary(selected, near_zero_threshold=0.0001),
            "by_year": {
                str(int(year)): distribution_summary(
                    target[mask & (years == year)], near_zero_threshold=0.0001
                )
                for year in np.unique(years[mask])
            },
            "by_regime": {
                name: distribution_summary(target[mask & regime], near_zero_threshold=0.0001)
                for name, regime in regimes.items()
                if np.count_nonzero(mask & regime)
            },
            "autocorrelation_lags_1_3_12": auto,
        }
        mfe, mae = labels[f"mfe_long_{horizon}"], labels[f"mae_long_{horizon}"]
        excursion[horizon] = {
            "mfe": distribution_summary(mfe[mask], near_zero_threshold=0.0),
            "mae": distribution_summary(mae[mask], near_zero_threshold=0.0),
            "mfe_mae_ratio": distribution_summary(
                mfe[mask] / np.maximum(mae[mask], 1e-12), near_zero_threshold=0.0
            ),
            "relationship_to_daily_volatility": {
                "mfe_pearson_ic": _correlation(mfe[mask], daily_volatility[mask])[0],
                "mfe_spearman_ic": _correlation(mfe[mask], daily_volatility[mask])[1],
                "mae_pearson_ic": _correlation(mae[mask], daily_volatility[mask])[0],
                "mae_spearman_ic": _correlation(mae[mask], daily_volatility[mask])[1],
            },
            "by_regime": {
                name: {
                    "mfe": distribution_summary(mfe[mask & regime], near_zero_threshold=0.0),
                    "mae": distribution_summary(mae[mask & regime], near_zero_threshold=0.0),
                }
                for name, regime in regimes.items()
                if np.count_nonzero(mask & regime)
            },
        }
    return (
        {"label_version": LABEL_RESEARCH_VERSION, "targets": targets},
        {"label_version": LABEL_RESEARCH_VERSION, "long_oriented_excursions": excursion},
    )


def _attach_excursion_prediction_relationships(
    report: dict[str, Any],
    predictions: pa.Table,
    labels: dict[str, np.ndarray],
    feature_times: np.ndarray,
) -> None:
    selected = predictions.filter(
        pc.and_(
            pc.equal(predictions.column("model"), "lightgbm"),
            pc.equal(predictions.column("feature_set"), "full_context"),
        )
    )
    for horizon in HORIZON_STEPS:
        horizon_rows = selected.filter(pc.equal(selected.column("target_horizon"), horizon))
        predicted = horizon_rows.column("prediction").combine_chunks().to_numpy()
        prediction_times = (
            horizon_rows.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
        )
        indices = np.searchsorted(feature_times, prediction_times)
        if np.any(indices >= len(feature_times)) or np.any(
            feature_times[indices] != prediction_times
        ):
            raise ValueError("OOS predictions do not align with label feature times")
        mfe = labels[f"mfe_long_{horizon}"][indices]
        mae = labels[f"mae_long_{horizon}"][indices]
        report["long_oriented_excursions"][horizon]["relationship_to_model_prediction"] = {
            "model": "fixed LightGBM full_context pooled OOS",
            "sample_size": len(predicted),
            "predicted_return_vs_mfe": {
                "pearson_ic": _correlation(predicted, mfe)[0],
                "spearman_ic": _correlation(predicted, mfe)[1],
            },
            "predicted_return_vs_mae": {
                "pearson_ic": _correlation(predicted, mae)[0],
                "spearman_ic": _correlation(predicted, mae)[1],
            },
        }


def _barrier_report(
    labels: dict[str, np.ndarray],
    resolution: dict[str, dict[str, int]],
    mask: np.ndarray,
    regimes: dict[str, np.ndarray],
) -> dict[str, Any]:
    codes = {"tp": 1, "sl": -1, "timeout": 0, "ambiguous": 2}

    def summarize(values: np.ndarray, selected: np.ndarray) -> dict[str, Any]:
        count = int(np.count_nonzero(selected))
        return {
            name: {
                "count": int(np.count_nonzero(selected & (values == code))),
                "percentage": float(np.mean(values[selected] == code) * 100.0),
            }
            for name, code in codes.items()
        } | {"total": count}

    barriers: dict[str, Any] = {}
    for name in resolution:
        values = labels[name]
        barriers[name] = {
            "eligible_research_rows": summarize(values, mask),
            "by_regime": {
                regime_name: summarize(values, mask & regime)
                for regime_name, regime in regimes.items()
                if np.count_nonzero(mask & regime)
            },
            "full_label_resolution_audit": resolution[name],
        }
    return {
        "label_version": LABEL_RESEARCH_VERSION,
        "outcome_codes": {name.upper(): value for name, value in codes.items()},
        "barriers": barriers,
        "limitations": (
            "5m coarse ordering; validated 1m resolves overlap only where minute coverage exists; "
            "same-minute ambiguity remains"
        ),
        "execution_setting_claim": False,
    }


def _folds(times: np.ndarray) -> list[dict[str, Any]]:
    boundaries = [
        (datetime(2022, 1, 1, tzinfo=UTC), datetime(2023, 1, 1, tzinfo=UTC)),
        (datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC)),
        (datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)),
        (datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 7, 1, tzinfo=UTC)),
    ]
    result = []
    for number, (test_start, test_end) in enumerate(boundaries, start=1):
        start_us = int(test_start.timestamp() * 1_000_000)
        end_us = int(test_end.timestamp() * 1_000_000)
        train = times < start_us - int(timedelta(hours=4).total_seconds() * 1_000_000)
        test = (times >= start_us + int(timedelta(hours=1).total_seconds() * 1_000_000)) & (
            times < end_us
        )
        if np.count_nonzero(train) and np.count_nonzero(test):
            result.append(
                {
                    "fold": number,
                    "train": train,
                    "test": test,
                    "test_start": test_start.isoformat(),
                    "test_end": test_end.isoformat(),
                    "purge_minutes": 240,
                    "embargo_minutes": 60,
                }
            )
    return result


def _fit_predict(
    model: str,
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    config: Phase6Config,
) -> tuple[np.ndarray, dict[str, Any], Any | None]:
    if model == "zero":
        return np.zeros(len(test_x)), {}, None
    if model == "historical_mean":
        mean = float(np.mean(train_y))
        return np.full(len(test_x), mean), {"training_mean": mean}, None
    if model == "ridge":
        estimator = Pipeline(
            [("scaler", StandardScaler()), ("ridge", Ridge(alpha=config.ridge_alpha))]
        )
        estimator.fit(train_x, train_y)
        return estimator.predict(test_x), {"alpha": config.ridge_alpha}, estimator
    if model == "lightgbm":
        import lightgbm as lgb

        estimator = lgb.LGBMRegressor(
            objective="regression",
            n_estimators=config.lightgbm_estimators,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=5,
            min_child_samples=100,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=config.seed,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        estimator.fit(train_x, train_y)
        return estimator.predict(test_x), estimator.get_params(), estimator
    raise ValueError(model)


def _probe_models(
    values: dict[str, np.ndarray],
    feature_groups: tuple[str, ...],
    labels: dict[str, np.ndarray],
    mask: np.ndarray,
    times: np.ndarray,
    regimes: dict[str, np.ndarray],
    config: Phase6Config,
    experiment_id: str,
    dataset_version: str,
) -> tuple[dict[str, Any], pa.Table, dict[str, Any]]:
    base_groups = tuple(group for group in feature_groups if group not in NEW_FEATURE_GROUPS)
    base = tuple(name for group in base_groups for name in FEATURE_GROUPS_V3_RESEARCH[group])
    h12 = FEATURE_GROUPS_V3_RESEARCH["higher_timeframe_12h"]
    h1d = FEATURE_GROUPS_V3_RESEARCH["higher_timeframe_1d"]
    cross = FEATURE_GROUPS_V3_RESEARCH["cross_timeframe"]
    stress = FEATURE_GROUPS_V3_RESEARCH["market_stress_research"]
    sets = {
        "without_12h_1d": base,
        "with_12h": base + h12,
        "with_1d": base + h1d,
        "with_12h_1d": base + h12 + h1d,
        "with_12h_1d_cross": base + h12 + h1d + cross,
        "with_12h_1d_stress": base + h12 + h1d + stress,
        "full_context": base + h12 + h1d + cross + stress,
    }
    sample_positions = np.flatnonzero(mask)[:: config.sample_every_n_rows]
    sampled_times = times[sample_positions]
    folds = _folds(sampled_times)
    comparisons = (
        [("1h", name) for name in ("without_12h_1d", "with_12h", "with_1d", "with_12h_1d")]
        + [
            ("1h", "with_12h_1d_cross"),
            ("1h", "with_12h_1d_stress"),
        ]
        + [(horizon, "full_context") for horizon in HORIZON_STEPS]
    )
    models = ("zero", "historical_mean", "ridge", "lightgbm")
    records: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    importance: dict[str, list[float]] = {}
    permutation: dict[str, float] = {}
    sampled_regimes = {name: values[sample_positions] for name, values in regimes.items()}
    for horizon, set_name in comparisons:
        key = f"{horizon}:{set_name}"
        columns = sets[set_name]
        matrix = np.column_stack([values[name][sample_positions] for name in columns])
        target = labels[f"forward_return_{horizon}"][sample_positions]
        results[key] = {
            "experiment_id": experiment_id,
            "dataset_version": dataset_version,
            "feature_research_version": FEATURE_RESEARCH_VERSION,
            "target_version": LABEL_RESEARCH_VERSION,
            "target_horizon": horizon,
            "feature_set": set_name,
            "feature_groups": [
                group
                for group in feature_groups
                if any(name in columns for name in FEATURE_GROUPS_V3_RESEARCH[group])
            ],
            "research_cutoff": config.phase6_research_cutoff.isoformat(),
            "prospective_holdout_boundary": config.prospective_holdout_start.isoformat(),
            "seed": config.seed,
            "code_version": f"phase6-{PHASE6_VERSION}",
            "folds": [],
        }
        for fold in folds:
            train, test = fold["train"], fold["test"]
            fold_result = {
                name: fold[name]
                for name in ("fold", "test_start", "test_end", "purge_minutes", "embargo_minutes")
            } | {
                "train_rows": int(np.count_nonzero(train)),
                "test_rows": int(np.count_nonzero(test)),
                "models": {},
            }
            for model in models:
                predicted, parameters, estimator = _fit_predict(
                    model, matrix[train], target[train], matrix[test], config
                )
                metrics = _model_metrics(target[test], predicted)
                fold_result["models"][model] = {
                    "metrics": metrics,
                    "parameters": parameters,
                    "prediction_deciles": _prediction_deciles(target[test], predicted),
                }
                if model == "lightgbm" and estimator is not None:
                    for name, gain in zip(columns, estimator.feature_importances_, strict=True):
                        importance.setdefault(name, []).append(float(gain))
                    if horizon == "1h" and set_name == "full_context" and fold["fold"] == 4:
                        test_positions = np.flatnonzero(test)
                        test_positions = test_positions[-min(3000, len(test_positions)) :]
                        measured = permutation_importance(
                            estimator,
                            matrix[test_positions],
                            target[test_positions],
                            n_repeats=2,
                            random_state=config.seed,
                            scoring="neg_mean_absolute_error",
                            n_jobs=1,
                        )
                        permutation.update(
                            {
                                name: float(value)
                                for name, value in zip(
                                    columns, measured.importances_mean, strict=True
                                )
                            }
                        )
                for sampled_index, row_time, actual, prediction in zip(
                    np.flatnonzero(test),
                    sampled_times[test],
                    target[test],
                    predicted,
                    strict=True,
                ):
                    records.append(
                        {
                            "feature_time": datetime.fromtimestamp(
                                int(row_time) / 1_000_000, tz=UTC
                            ),
                            "fold": int(fold["fold"]),
                            "target_horizon": horizon,
                            "feature_set": set_name,
                            "model": model,
                            "actual": float(actual),
                            "prediction": float(prediction),
                            **{
                                f"regime_{name}": bool(values[sampled_index])
                                for name, values in sampled_regimes.items()
                            },
                        }
                    )
            results[key]["folds"].append(fold_result)
        for model in models:
            rows = [
                row
                for row in records
                if row["target_horizon"] == horizon
                and row["feature_set"] == set_name
                and row["model"] == model
            ]
            actual = np.asarray([row["actual"] for row in rows])
            prediction = np.asarray([row["prediction"] for row in rows])
            row_times = np.asarray(
                [int(row["feature_time"].timestamp() * 1_000_000) for row in rows],
                dtype=np.int64,
            )
            years = (
                row_times.astype("datetime64[us]").astype("datetime64[Y]").astype(np.int64) + 1970
            )
            results[key].setdefault("pooled_oos", {})[model] = {
                "overall": _model_metrics(actual, prediction),
                "by_year": {
                    str(int(year)): _model_metrics(actual[years == year], prediction[years == year])
                    for year in np.unique(years)
                },
                "by_regime": {
                    name: _model_metrics(
                        actual[np.asarray([row[f"regime_{name}"] for row in rows])],
                        prediction[np.asarray([row[f"regime_{name}"] for row in rows])],
                    )
                    for name in regimes
                    if any(row[f"regime_{name}"] for row in rows)
                },
            }
    return (
        {
            "research_design": "fixed retrospective probes; not champion selection",
            "same_row_fairness": True,
            "sample_every_n_rows": config.sample_every_n_rows,
            "fold_count": len(folds),
            "feature_groups": list(feature_groups),
            "feature_sets": {name: list(columns) for name, columns in sets.items()},
            "experiments": results,
        },
        pa.Table.from_pylist(records),
        {
            "lightgbm_mean_gain": {
                name: {"mean_gain": float(np.mean(gains)), "fold_models": len(gains)}
                for name, gains in importance.items()
            },
            "lightgbm_permutation_mae_degradation": permutation,
            "permutation_scope": "1h full_context fold 4, latest 3,000 OOS rows, 2 repeats",
        },
    )


def _scorecards(
    probes: dict[str, Any],
    feature_coverage: dict[str, Any],
    feature_stability: dict[str, Any],
    feature_redundancy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    experiments = probes["experiments"]
    coverage = feature_coverage["features"]
    stability = feature_stability["features"]
    redundant_pairs = feature_redundancy["redundant_pairs"]
    base_key = "1h:without_12h_1d"
    comparison_map = {
        "higher_timeframe_12h": (base_key, "1h:with_12h"),
        "higher_timeframe_1d": (base_key, "1h:with_1d"),
        "cross_timeframe": ("1h:with_12h_1d", "1h:with_12h_1d_cross"),
        "market_stress_research": ("1h:with_12h_1d", "1h:with_12h_1d_stress"),
    }
    families: dict[str, Any] = {}
    feature_status: dict[str, str] = {}
    for group in probes["feature_groups"]:
        names = FEATURE_GROUPS_V3_RESEARCH[group]
        group_coverage = float(
            np.mean([100.0 - coverage[name]["missing_percentage"] for name in names])
        )
        drift_values = [
            abs(period["median_shift_global_iqr"])
            for name in names
            for period in stability[name]["yearly"].values()
        ]
        redundant_count = sum(
            pair["left"] in names or pair["right"] in names for pair in redundant_pairs
        )
        payload: dict[str, Any] = {
            "coverage_percentage_mean": group_coverage,
            "incremental_predictive_value": None,
            "fold_stability": "NOT_INDIVIDUALLY_ABLATED_IN_PHASE6",
            "year_stability": "see feature_stability.json",
            "regime_stability": "NOT_INDIVIDUALLY_ABLATED_IN_PHASE6",
            "maximum_absolute_yearly_median_shift_iqr": max(drift_values, default=None),
            "redundant_pair_count": redundant_count,
            "computational_cost": (
                "low-to-moderate causal rolling/as-of computation"
                if group in NEW_FEATURE_GROUPS
                else "existing Feature V2.1 computation"
            ),
            "recommended_status": "RESEARCH_ONLY",
        }
        if group in comparison_map:
            reference_key, candidate_key = comparison_map[group]
            reference = experiments[reference_key]["pooled_oos"]["lightgbm"]["overall"]
            candidate = experiments[candidate_key]["pooled_oos"]["lightgbm"]["overall"]
            delta = (candidate["spearman_ic"] or 0.0) - (reference["spearman_ic"] or 0.0)
            fold_ic = [
                fold["models"]["lightgbm"]["metrics"]["spearman_ic"]
                for fold in experiments[candidate_key]["folds"]
            ]
            status = "KEEP_CANDIDATE" if delta >= 0.002 else "WEAK" if delta >= -0.002 else "REJECT"
            if status == "KEEP_CANDIDATE" and sum((value or 0) > 0 for value in fold_ic) < 3:
                status = "UNSTABLE"
            by_year = experiments[candidate_key]["pooled_oos"]["lightgbm"]["by_year"]
            by_regime = experiments[candidate_key]["pooled_oos"]["lightgbm"]["by_regime"]
            reference_by_year = experiments[reference_key]["pooled_oos"]["lightgbm"]["by_year"]
            reference_by_regime = experiments[reference_key]["pooled_oos"]["lightgbm"]["by_regime"]
            payload.update(
                {
                    "incremental_predictive_value": {
                        "metric": "pooled_oos_lightgbm_spearman_ic",
                        "reference_experiment": reference_key,
                        "candidate_experiment": candidate_key,
                        "delta": delta,
                    },
                    "fold_stability": {
                        "spearman_ic": fold_ic,
                        "positive_folds": sum((value or 0) > 0 for value in fold_ic),
                    },
                    "year_stability": {
                        year: {
                            "candidate_spearman_ic": metrics["spearman_ic"],
                            "incremental_spearman_ic": (metrics["spearman_ic"] or 0.0)
                            - (reference_by_year[year]["spearman_ic"] or 0.0),
                        }
                        for year, metrics in by_year.items()
                    },
                    "regime_stability": {
                        name: {
                            "candidate_spearman_ic": metrics["spearman_ic"],
                            "incremental_spearman_ic": (metrics["spearman_ic"] or 0.0)
                            - (reference_by_regime[name]["spearman_ic"] or 0.0),
                        }
                        for name, metrics in by_regime.items()
                    },
                    "recommended_status": status,
                }
            )
        families[group] = payload
        for name in names:
            feature_status[name] = (
                "REDUNDANT"
                if any(pair["left"] == name or pair["right"] == name for pair in redundant_pairs)
                else payload["recommended_status"]
            )

    combined = experiments["1h:with_12h_1d"]["pooled_oos"]["lightgbm"]["overall"]
    baseline = experiments[base_key]["pooled_oos"]["lightgbm"]["overall"]
    targets: dict[str, Any] = {}
    for horizon in HORIZON_STEPS:
        experiment = experiments[f"{horizon}:full_context"]
        pooled = experiment["pooled_oos"]["lightgbm"]
        metrics = pooled["overall"]
        fold_ic = [
            fold["models"]["lightgbm"]["metrics"]["spearman_ic"] for fold in experiment["folds"]
        ]
        stable = sum((value or 0) > 0 for value in fold_ic) >= 3
        promising = (
            (metrics["spearman_ic"] or 0) >= 0.01
            and stable
            and metrics["r2"] is not None
            and metrics["r2"] > -0.01
        )
        targets[horizon] = {
            "sample_size": metrics["count"],
            "predictability": metrics,
            "fold_spearman_ic": fold_ic,
            "fold_stability": "STABLE" if stable else "UNSTABLE",
            "year_stability": {
                year: values["spearman_ic"] for year, values in pooled["by_year"].items()
            },
            "regime_stability": {
                name: values["spearman_ic"] for name, values in pooled["by_regime"].items()
            },
            "economic_interpretation": (
                "retrospective research horizon; no fee, slippage, turnover, capacity, or "
                "execution qualification"
            ),
            "turnover_implication": "shorter horizons imply higher potential turnover",
            "cost_sensitivity": "not evaluated; required before any economic claim",
            "recommended_status": "TARGET_CANDIDATE" if promising else "RESEARCH_ONLY",
        }
    return (
        {
            "feature_version": FEATURE_RESEARCH_VERSION,
            "families": families,
            "individual_feature_status": feature_status,
            "combined_12h_1d_comparison": {
                "reference": base_key,
                "candidate": "1h:with_12h_1d",
                "incremental_spearman_ic": (combined["spearman_ic"] or 0.0)
                - (baseline["spearman_ic"] or 0.0),
            },
        },
        {"label_version": LABEL_RESEARCH_VERSION, "targets": targets},
    )


def run_phase6_research(config: Phase6Config) -> dict[str, Any]:
    cutoff = config.phase6_research_cutoff
    candles5, lineage5 = load_silver_family(
        config.silver_5m_manifests,
        symbol=config.symbol,
        interval="5m",
        end=cutoff,
    )
    candles12, lineage12 = load_silver_family(
        config.silver_12h_manifests,
        symbol=config.symbol,
        interval="12h",
        end=cutoff,
    )
    candles1d, lineage1d = load_silver_family(
        config.silver_1d_manifests,
        symbol=config.symbol,
        interval="1d",
        end=cutoff,
    )
    minute = None
    lineage1m: list[dict[str, Any]] = []
    if config.silver_1m_manifest is not None:
        minute, lineage1m = load_silver_family(
            (config.silver_1m_manifest,), symbol=config.symbol, interval="1m", end=cutoff
        )
    external, external_lineage = _external(config)
    derived12 = aggregate_candles(candles5, "12h")
    derived1d = aggregate_candles(derived12, "1d")
    reconciliation = {
        "12h": reconcile_direct_vs_derived(candles12, derived12, "12h"),
        "1d": reconcile_direct_vs_derived(candles1d, derived1d, "1d"),
    }
    features = generate_features_v3_research(candles5, candles12, candles1d, external=external)
    labels = generate_research_labels(
        candles5, atr_pct=features.values["atr14_pct"], minute_candles=minute
    )
    cutoff_us = int(cutoff.timestamp() * 1_000_000)
    mask = features.valid_mask.copy()
    for horizon in HORIZON_STEPS:
        name = f"forward_return_{horizon}"
        mask &= labels.valid[name] & (labels.label_end_time_us[name] < cutoff_us)
    mask &= labels.feature_time_us < cutoff_us
    if not np.count_nonzero(mask):
        raise ValueError("No Phase 6 rows survive causal feature/target rules")
    if np.any(
        labels.feature_time_us[mask]
        >= int(config.prospective_holdout_start.timestamp() * 1_000_000)
    ):
        raise ValueError("prospective holdout contamination")

    rows = np.flatnonzero(mask)
    columns: dict[str, Any] = {
        "symbol": [config.symbol] * len(rows),
        "feature_time": pa.array(labels.feature_time_us[rows], type=pa.timestamp("us", tz="UTC")),
        "entry_time": pa.array(labels.entry_time_us[rows], type=pa.timestamp("us", tz="UTC")),
        "source_time_12h": pa.array(
            features.source_time_12h_us[rows], type=pa.timestamp("us", tz="UTC")
        ),
        "availability_time_12h": pa.array(
            features.availability_time_12h_us[rows], type=pa.timestamp("us", tz="UTC")
        ),
        "source_time_1d": pa.array(
            features.source_time_1d_us[rows], type=pa.timestamp("us", tz="UTC")
        ),
        "availability_time_1d": pa.array(
            features.availability_time_1d_us[rows], type=pa.timestamp("us", tz="UTC")
        ),
        "feature_version": [FEATURE_RESEARCH_VERSION] * len(rows),
        "label_version": [LABEL_RESEARCH_VERSION] * len(rows),
    }
    for name in features.columns:
        columns[name] = features.values[name][rows]
    for name, value in labels.values.items():
        columns[name] = value[rows]
    for horizon in HORIZON_STEPS:
        columns[f"label_end_time_{horizon}"] = pa.array(
            labels.label_end_time_us[f"forward_return_{horizon}"][rows],
            type=pa.timestamp("us", tz="UTC"),
        )
    gold = pa.Table.from_pydict(columns)

    identity = {
        "config_hash": config.config_hash,
        "feature_version": FEATURE_RESEARCH_VERSION,
        "label_version": LABEL_RESEARCH_VERSION,
        "lineage": lineage5 + lineage12 + lineage1d + lineage1m,
        "external_lineage": external_lineage,
        "phase6_version": PHASE6_VERSION,
    }
    research_id = f"phase6-btc-{_hash(identity)}"
    output = config.output_root.resolve() / research_id
    gold_dir = config.gold_root.resolve() / f"gold-{research_id}"
    gold_path = gold_dir / "dataset.parquet"
    gold_manifest_path = gold_dir / "manifest.json"
    if gold_manifest_path.exists():
        existing = read_manifest(gold_manifest_path)
        if (
            existing is None
            or not gold_path.exists()
            or file_sha256(gold_path) != existing["sha256"]
        ):
            raise ValueError("Existing Phase 6 Gold artifact failed checksum validation")
    else:
        gold_sha = _atomic_write_parquet(gold_path, gold)
        _write_json_immutable(
            gold_manifest_path,
            {
                "dataset_version": f"gold-{research_id}",
                "dataset_classification": "RETROSPECTIVE_RESEARCH",
                "file": gold_path.name,
                "sha256": gold_sha,
                "row_count": gold.num_rows,
                "feature_count": len(features.columns),
                "feature_columns": list(features.columns),
                "feature_groups": list(features.groups),
                "feature_version": FEATURE_RESEARCH_VERSION,
                "label_version": LABEL_RESEARCH_VERSION,
                "research_cutoff_exclusive": cutoff.isoformat(),
                "prospective_holdout_start": config.prospective_holdout_start.isoformat(),
                "prospective_holdout_used": False,
                "lineage": identity,
            },
        )

    times = labels.feature_time_us
    target_arrays = {h: labels.values[f"forward_return_{h}"] for h in HORIZON_STEPS}
    sample = np.flatnonzero(mask)[:: config.sample_every_n_rows]
    feature_coverage, feature_stability, feature_redundancy = _feature_reports(
        features.values,
        features.columns,
        features.groups,
        times,
        target_arrays,
        sample,
        config.redundancy_threshold,
    )
    regimes = {
        "bull": features.values["bull_regime"] > 0,
        "bear": features.values["bear_regime"] > 0,
        "sideways": features.values["sideways_regime"] > 0,
        "high_volatility": features.values["high_volatility_regime"] > 0,
        "low_volatility": features.values["low_volatility_regime"] > 0,
    }
    target_report, excursion_report = _target_reports(
        labels.values,
        mask,
        times,
        regimes,
        features.values["htf_1d_realized_vol_30d"],
    )
    probes, predictions, importance = _probe_models(
        features.values,
        features.groups,
        labels.values,
        mask,
        times,
        regimes,
        config,
        research_id,
        f"gold-{research_id}",
    )
    _attach_excursion_prediction_relationships(
        excursion_report, predictions, labels.values, labels.feature_time_us
    )
    feature_scorecard, target_scorecard = _scorecards(
        probes, feature_coverage, feature_stability, feature_redundancy
    )
    prediction_path = output / "oos_predictions.parquet"
    if prediction_path.exists():
        pq.read_table(prediction_path)
        prediction_sha = file_sha256(prediction_path)
    else:
        prediction_sha = _atomic_write_parquet(prediction_path, predictions)
    _write_json_immutable(
        output / "oos_predictions.manifest.json",
        {
            "artifact_version": "1.0.0",
            "classification": "RETROSPECTIVE_RESEARCH",
            "experiment_id": research_id,
            "dataset_version": f"gold-{research_id}",
            "file": prediction_path.name,
            "sha256": prediction_sha,
            "row_count": predictions.num_rows,
            "columns": predictions.column_names,
            "feature_version": FEATURE_RESEARCH_VERSION,
            "label_version": LABEL_RESEARCH_VERSION,
            "research_cutoff_exclusive": cutoff.isoformat(),
            "prospective_holdout_start": config.prospective_holdout_start.isoformat(),
            "prospective_holdout_used": False,
            "models": ["zero", "historical_mean", "ridge", "lightgbm"],
            "code_version": f"phase6-{PHASE6_VERSION}",
        },
    )

    reports = {
        "historical_data_ranges.json": {
            "research_cutoff_exclusive": cutoff.isoformat(),
            "5m": _table_range(candles5, "open_time"),
            "12h": _table_range(candles12, "open_time"),
            "1d": _table_range(candles1d, "open_time"),
            "1m_overlap": _table_range(minute, "open_time"),
            "funding": _table_range(external.funding, "event_time"),
            "mark": _table_range(external.mark, "event_time"),
            "index": _table_range(external.index, "event_time"),
        },
        "data_quality.json": {
            "5m": coverage_report(candles5, "5m")
            | {"invalid_rows": 0, "quality_statuses": [row["quality_status"] for row in lineage5]},
            "12h": coverage_report(candles12, "12h")
            | {
                "invalid_rows": 0,
                "quality_statuses": [row["quality_status"] for row in lineage12],
                "source": "official Binance USD-M direct klines (REST bridge + archive)",
            },
            "1d": coverage_report(candles1d, "1d")
            | {
                "invalid_rows": 0,
                "quality_statuses": [row["quality_status"] for row in lineage1d],
                "source": "official Binance USD-M direct klines (REST bridge + archive)",
            },
            "1m": (
                coverage_report(minute, "1m")
                | {
                    "invalid_rows": 0,
                    "quality_statuses": [row["quality_status"] for row in lineage1m],
                }
                if minute is not None
                else None
            ),
        },
        "direct_vs_derived_reconciliation.json": reconciliation,
        "feature_coverage.json": feature_coverage,
        "feature_stability.json": feature_stability,
        "feature_redundancy_and_ic.json": feature_redundancy,
        "target_analysis.json": target_report,
        "mfe_mae_analysis.json": excursion_report,
        "barrier_analysis.json": _barrier_report(
            labels.values, labels.barrier_resolution, mask, regimes
        ),
        "research_probes.json": probes,
        "feature_importance.json": importance | {"causal_claim": False},
        "feature_scorecard.json": feature_scorecard,
        "target_scorecard.json": target_scorecard,
    }
    artifact_hashes = {
        name: _write_json_immutable(output / name, payload) for name, payload in reports.items()
    }
    summary = {
        "experiment_id": research_id,
        "status": "complete",
        "classification": "RETROSPECTIVE_RESEARCH",
        "dataset_version": f"gold-{research_id}",
        "feature_research_version": FEATURE_RESEARCH_VERSION,
        "target_version": LABEL_RESEARCH_VERSION,
        "target_horizons": list(HORIZON_STEPS),
        "feature_groups": list(features.groups),
        "fold_configuration": {
            "count": probes["fold_count"],
            "purge_minutes": 240,
            "embargo_minutes": 60,
        },
        "research_cutoff": cutoff.isoformat(),
        "prospective_holdout_boundary": config.prospective_holdout_start.isoformat(),
        "rows_used_from_holdout": 0,
        "prospective_holdout_used": False,
        "models": ["zero", "historical_mean", "ridge", "lightgbm"],
        "parameters": {
            "ridge_alpha": config.ridge_alpha,
            "lightgbm_estimators": config.lightgbm_estimators,
        },
        "seed": config.seed,
        "code_version": f"phase6-{PHASE6_VERSION}",
        "gold_manifest": str(gold_manifest_path),
        "gold_rows": gold.num_rows,
        "feature_count": len(features.columns),
        "prediction_rows": predictions.num_rows,
        "artifacts": {
            name: {"file": name, "sha256": digest} for name, digest in artifact_hashes.items()
        },
        "no_champion_promotion": True,
        "current_model_status": "NO QUALIFIED MODEL",
    }
    _write_json_immutable(output / "phase6_summary.json", summary)
    return summary
