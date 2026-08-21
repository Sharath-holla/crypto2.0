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
import pyarrow.parquet as pq
from sklearn.inspection import permutation_importance

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase4_1.features import FEATURE_GROUPS_V2_1
from crypto_ai.phase4_1.gold import read_gold_v2_1
from crypto_ai.research.config import ExperimentConfig
from crypto_ai.research.gold import TARGET_COLUMN
from crypto_ai.research.metrics import prediction_buckets, regression_metrics
from crypto_ai.research.models import ModelBundle, save_model
from crypto_ai.research.split import TemporalSplit, chronological_purged_split

MAIN_MODEL_V2_1_VERSION = "2.1.1"

BASELINE_V2_1_COLUMNS = (
    "return_5m",
    "return_15m",
    "return_30m",
    "return_1h",
    "log_return_5m",
    "candle_range_pct",
    "candle_body_pct",
    "relative_base_volume",
    "realized_volatility_1h",
    "realized_volatility_4h",
    "ema20_distance",
    "ema50_distance",
    "rsi14",
)

MODEL_V2_1_REDUNDANT_COLUMNS = {
    "log_return_5m",
    "taker_sell_base_share",
    "taker_buy_quote_share",
    "taker_sell_quote_share",
    "taker_flow_imbalance_base",
    "sideways_regime",
}


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _unique(*collections: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(name for collection in collections for name in collection))


def long_history_ablation_sets() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {"L0": BASELINE_V2_1_COLUMNS}
    current = _unique(FEATURE_GROUPS_V2_1["price"], FEATURE_GROUPS_V2_1["trend"])
    result["L1"] = current
    current = _unique(
        current,
        FEATURE_GROUPS_V2_1["momentum"],
        FEATURE_GROUPS_V2_1["volatility"],
    )
    result["L2"] = current
    current = _unique(current, FEATURE_GROUPS_V2_1["volume"])
    result["L3"] = current
    current = _unique(current, FEATURE_GROUPS_V2_1["taker_flow"])
    result["L4"] = current
    current = _unique(current, FEATURE_GROUPS_V2_1["regime"], FEATURE_GROUPS_V2_1["time"])
    result["L5"] = tuple(name for name in current if name not in MODEL_V2_1_REDUNDANT_COLUMNS)
    return result


def derivatives_ablation_sets(*, include_open_interest: bool) -> dict[str, tuple[str, ...]]:
    core = long_history_ablation_sets()["L5"]
    result = {
        "D0": core,
        "D1": _unique(core, FEATURE_GROUPS_V2_1["funding"]),
        "D2": _unique(
            core,
            FEATURE_GROUPS_V2_1["funding"],
            FEATURE_GROUPS_V2_1["mark_index_basis"],
        ),
    }
    if include_open_interest:
        result["D3"] = _unique(result["D2"], FEATURE_GROUPS_V2_1["open_interest"])
    return result


def _matrix(table: pa.Table, columns: tuple[str, ...]) -> np.ndarray:
    missing = sorted(set(columns) - set(table.column_names))
    if missing:
        raise ValueError(f"Gold V2.1 is missing model features: {missing}")
    matrix = np.column_stack(
        [table.column(name).combine_chunks().to_numpy() for name in columns]
    ).astype(np.float64, copy=False)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Main Model V2.1 features contain non-finite values")
    return matrix


def _target(table: pa.Table) -> np.ndarray:
    values = table.column(TARGET_COLUMN).combine_chunks().to_numpy().astype(np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("Main Model V2.1 target contains non-finite values")
    return values


def _fit_lightgbm(
    split: TemporalSplit,
    columns: tuple[str, ...],
    config: ExperimentConfig,
    metadata: dict[str, Any],
) -> tuple[ModelBundle, dict[str, Any], np.ndarray, np.ndarray]:
    import lightgbm as lgb

    train_x, validation_x, test_x = (
        _matrix(split.train, columns),
        _matrix(split.validation, columns),
        _matrix(split.test, columns),
    )
    train_y, validation_y = _target(split.train), _target(split.validation)
    parameters = config.lightgbm.model_dump()
    early_stopping_rounds = parameters.pop("early_stopping_rounds")
    estimator = lgb.LGBMRegressor(
        objective="regression",
        random_state=config.seed,
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
        model_version="1.0.0",
        feature_columns=columns,
        estimator=estimator,
        metadata={
            **metadata,
            "main_model_version": MAIN_MODEL_V2_1_VERSION,
            "feature_columns": list(columns),
            "random_seed": config.seed,
            "hyperparameters": config.lightgbm.model_dump(),
            "best_iteration": int(estimator.best_iteration_),
            "hyperparameter_search": "none; single conservative preregistered configuration",
        },
    )
    validation_predictions = bundle.predict(validation_x, columns)
    test_predictions = bundle.predict(test_x, columns)
    sample_size = min(10_000, len(validation_y))
    sample_indices = np.linspace(0, len(validation_y) - 1, sample_size, dtype=np.int64)
    permutation = permutation_importance(
        estimator,
        validation_x[sample_indices],
        validation_y[sample_indices],
        scoring="neg_mean_absolute_error",
        n_repeats=3,
        random_state=config.seed,
        n_jobs=1,
    )
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
        "validation_permutation_mae": {
            name: {"mean": float(mean), "std": float(std)}
            for name, mean, std in zip(
                columns,
                permutation.importances_mean,
                permutation.importances_std,
                strict=True,
            )
        },
        "permutation_sample_policy": {
            "rows": sample_size,
            "selection": "deterministic evenly spaced validation rows",
            "repeats": 3,
        },
    }
    return bundle, importance, validation_predictions, test_predictions


def _prediction_table(
    split: TemporalSplit,
    validation_predictions: np.ndarray,
    test_predictions: np.ndarray,
) -> pa.Table:
    source = pa.concat_tables([split.validation, split.test])
    names = [
        "symbol",
        "feature_time",
        "entry_time",
        "label_end_time",
        "entry_reference_price",
        "future_reference_price",
        TARGET_COLUMN,
        "taker_buy_base_share",
        "taker_flow_imbalance_quote",
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ]
    if "funding_rate" in source.column_names:
        names.extend(("funding_rate", "funding_age_hours"))
    data = {name: source.column(name) for name in names}
    data["split"] = ["validation"] * split.validation.num_rows + ["test"] * split.test.num_rows
    data["predicted_return"] = np.concatenate([validation_predictions, test_predictions])
    return pa.table(data)


def _row_identity(split: TemporalSplit) -> str:
    digest = hashlib.sha256()
    for subset in (split.train, split.validation, split.test):
        digest.update(
            subset.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy().tobytes()
        )
        digest.update(_target(subset).tobytes())
    return digest.hexdigest()


def _block_bootstrap(
    actual: np.ndarray,
    predicted: np.ndarray,
    *,
    seed: int,
    samples: int = 200,
    block_rows: int = 288,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    estimates: dict[str, list[float]] = {
        "pearson_ic": [],
        "directional_accuracy": [],
        "mae": [],
    }
    block_count = int(np.ceil(len(actual) / block_rows))
    offsets = np.arange(block_rows)
    for _ in range(samples):
        starts = rng.integers(0, len(actual), size=block_count)
        indices = ((starts[:, None] + offsets) % len(actual)).ravel()[: len(actual)]
        selected_actual, selected_predicted = actual[indices], predicted[indices]
        correlation = np.corrcoef(selected_actual, selected_predicted)[0, 1]
        estimates["pearson_ic"].append(float(correlation))
        estimates["directional_accuracy"].append(
            float(np.mean(np.sign(selected_actual) == np.sign(selected_predicted)))
        )
        estimates["mae"].append(float(np.mean(np.abs(selected_actual - selected_predicted))))
    return {
        "method": "moving-block bootstrap with circular blocks",
        "samples": samples,
        "block_rows": block_rows,
        "seed": seed,
        "intervals_95pct": {
            name: {
                "lower": float(np.percentile(values, 2.5)),
                "median": float(np.percentile(values, 50.0)),
                "upper": float(np.percentile(values, 97.5)),
            }
            for name, values in estimates.items()
        },
    }


def _group_metrics(table: pa.Table, predictions: np.ndarray) -> dict[str, Any]:
    actual = _target(table)
    result: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ):
        mask = table.column(name).combine_chunks().to_numpy().astype(bool)
        count = int(np.count_nonzero(mask))
        if count >= 2:
            result[name] = {
                **regression_metrics(actual[mask], predictions[mask]),
                "small_sample_warning": count < 1_000,
            }
    return result


def _year_metrics(table: pa.Table, predictions: np.ndarray) -> dict[str, Any]:
    actual = _target(table)
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    years = times.astype("datetime64[us]").astype("datetime64[Y]").astype(np.int64) + 1970
    return {
        str(year): {
            **regression_metrics(actual[years == year], predictions[years == year]),
            "small_sample_warning": int(np.count_nonzero(years == year)) < 1_000,
        }
        for year in np.unique(years)
    }


def _deciles(table: pa.Table, predictions: np.ndarray, feature_name: str) -> list[dict[str, Any]]:
    feature = table.column(feature_name).combine_chunks().to_numpy()
    actual = _target(table)
    order = np.argsort(feature, kind="mergesort")
    result: list[dict[str, Any]] = []
    for number, indices in enumerate(np.array_split(order, 10), start=1):
        result.append(
            {
                "decile": number,
                "count": len(indices),
                "minimum_feature": float(np.min(feature[indices])),
                "maximum_feature": float(np.max(feature[indices])),
                "mean_future_return": float(np.mean(actual[indices])),
                "median_future_return": float(np.median(actual[indices])),
                "positive_return_probability": float(np.mean(actual[indices] > 0)),
                "mean_model_prediction": float(np.mean(predictions[indices])),
                "small_sample_warning": len(indices) < 1_000,
            }
        )
    return result


def _funding_buckets(
    train: pa.Table, test: pa.Table, predictions: np.ndarray
) -> dict[str, Any] | None:
    if "funding_rate" not in test.column_names:
        return None
    training = train.column("funding_rate").combine_chunks().to_numpy()
    thresholds = np.quantile(training, [0.1, 0.4, 0.6, 0.9])
    values = test.column("funding_rate").combine_chunks().to_numpy()
    actual = _target(test)
    names = (
        "lowest_training_quantile",
        "lower_middle_training_quantile",
        "middle_training_quantile",
        "upper_middle_training_quantile",
        "highest_training_quantile",
    )
    assignments = np.digitize(values, thresholds, right=True)
    buckets: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        mask = assignments == index
        count = int(np.count_nonzero(mask))
        if count:
            buckets.append(
                {
                    "bucket": name,
                    "count": count,
                    "mean_funding_rate": float(np.mean(values[mask])),
                    "mean_future_return": float(np.mean(actual[mask])),
                    "mean_model_prediction": float(np.mean(predictions[mask])),
                    "small_sample_warning": count < 1_000,
                }
            )
    return {
        "threshold_source": "training rows only",
        "bucket_semantics": (
            "relative funding-rate quantile; labels do not imply an absolute sign"
        ),
        "quantiles": [0.1, 0.4, 0.6, 0.9],
        "thresholds": thresholds.tolist(),
        "buckets": buckets,
    }


def _run_family(
    table: pa.Table,
    manifest: dict[str, Any],
    config: ExperimentConfig,
    ablations: dict[str, tuple[str, ...]],
    temporary: Path,
    family: str,
) -> dict[str, Any]:
    split = chronological_purged_split(table, config.split)
    row_identity = _row_identity(split)
    family_dir = temporary / family
    family_dir.mkdir(parents=True)
    results: dict[str, Any] = {}
    selected_predictions: tuple[np.ndarray, np.ndarray] | None = None
    for name, columns in ablations.items():
        training_matrix = _matrix(split.train, columns)
        constant = [
            column
            for index, column in enumerate(columns)
            if np.ptp(training_matrix[:, index]) <= 1e-15
        ]
        if constant:
            raise ValueError(f"{family}/{name} has constant training features: {constant}")
        bundle, importance, validation_predictions, test_predictions = _fit_lightgbm(
            split,
            columns,
            config,
            {
                "phase": "4.1",
                "family": family,
                "ablation": name,
                "dataset_version": manifest["dataset_version"],
            },
        )
        directory = family_dir / name
        directory.mkdir()
        model_path = directory / "model.joblib"
        save_model(bundle, model_path)
        predictions = _prediction_table(split, validation_predictions, test_predictions)
        predictions_path = directory / "predictions.parquet"
        pq.write_table(predictions, predictions_path, compression="zstd")
        write_manifest(directory / "feature_importance.json", importance)
        results[name] = {
            "feature_count": len(columns),
            "feature_columns": list(columns),
            "same_row_identity_sha256": row_identity,
            "validation_metrics": regression_metrics(
                _target(split.validation), validation_predictions
            ),
            "test_metrics": regression_metrics(_target(split.test), test_predictions),
            "test_prediction_buckets": prediction_buckets(_target(split.test), test_predictions),
            "best_iteration": bundle.metadata["best_iteration"],
            "model": f"{family}/{name}/model.joblib",
            "model_sha256": file_sha256(model_path),
            "predictions": f"{family}/{name}/predictions.parquet",
            "predictions_sha256": file_sha256(predictions_path),
            "feature_importance": f"{family}/{name}/feature_importance.json",
        }
        selected_predictions = (validation_predictions, test_predictions)
    if selected_predictions is None:  # pragma: no cover
        raise AssertionError("family must contain at least one ablation")
    validation_predictions, test_predictions = selected_predictions
    oos = pa.concat_tables([split.validation, split.test])
    oos_predictions = np.concatenate([validation_predictions, test_predictions])
    selected_name = next(reversed(ablations))
    diagnostics = {
        "selected_ablation": selected_name,
        "confidence_intervals": _block_bootstrap(
            _target(split.test), test_predictions, seed=config.seed
        ),
        "by_year_oos": _year_metrics(oos, oos_predictions),
        "by_causal_regime_test": _group_metrics(split.test, test_predictions),
        "taker_flow_test": {
            "taker_buy_base_share_deciles": _deciles(
                split.test, test_predictions, "taker_buy_base_share"
            ),
            "taker_flow_imbalance_quote_deciles": _deciles(
                split.test, test_predictions, "taker_flow_imbalance_quote"
            ),
        },
        "funding_test": _funding_buckets(split.train, split.test, test_predictions),
    }
    write_manifest(family_dir / "diagnostics.json", diagnostics)
    return {
        "dataset_version": manifest["dataset_version"],
        "dataset_family": manifest["dataset_family"],
        "split": split.metadata(),
        "same_overlap_for_all_ablations": True,
        "same_row_identity_sha256": row_identity,
        "ablations": results,
        "selected_ablation": selected_name,
        "selection_rule": "predeclared most-complete family model; test not used for selection",
        "diagnostics": f"{family}/diagnostics.json",
    }


def train_main_model_v2_1(
    core_gold_manifest: Path,
    config: ExperimentConfig,
    *,
    derivatives_gold_manifest: Path | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    core_table, core_manifest = read_gold_v2_1(core_gold_manifest)
    if core_manifest.get("dataset_family") != "core_long_history":
        raise ValueError("Core experiment requires a core_long_history Gold V2.1 dataset")
    derivatives: tuple[pa.Table, dict[str, Any]] | None = None
    if derivatives_gold_manifest is not None:
        derivatives = read_gold_v2_1(derivatives_gold_manifest)
        if derivatives[1].get("dataset_family") != "derivatives_overlap":
            raise ValueError("Derivatives experiment requires derivatives_overlap Gold V2.1")
    identity = {
        "core_dataset": core_manifest["dataset_version"],
        "derivatives_dataset": derivatives[1]["dataset_version"] if derivatives else None,
        "configuration": config.model_dump(mode="json"),
        "model_version": MAIN_MODEL_V2_1_VERSION,
        "long_ablations": long_history_ablation_sets(),
        "derivatives_ablations": (
            derivatives_ablation_sets(
                include_open_interest="open_interest" in derivatives[1]["feature_groups"]
            )
            if derivatives
            else None
        ),
    }
    experiment_id = f"main-model-v2-1-{_hash(identity)}"
    root = (artifact_root or config.artifact_root).resolve()
    final = root / "phase4_1" / "experiments" / experiment_id
    experiment_path = final / "experiment.json"
    existing = read_manifest(experiment_path)
    if existing is not None:
        return existing
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        long_family = _run_family(
            core_table,
            core_manifest,
            config,
            long_history_ablation_sets(),
            temporary,
            "long_history",
        )
        long_family["dataset_manifest"] = str(core_gold_manifest.resolve())
        families = {"long_history": long_family}
        if derivatives is not None:
            table, manifest = derivatives
            derivatives_family = _run_family(
                table,
                manifest,
                config,
                derivatives_ablation_sets(
                    include_open_interest="open_interest" in manifest["feature_groups"]
                ),
                temporary,
                "derivatives_overlap",
            )
            derivatives_family["dataset_manifest"] = str(derivatives_gold_manifest.resolve())
            families["derivatives_overlap"] = derivatives_family
        payload = {
            "experiment_id": experiment_id,
            "status": "complete",
            "created_at": datetime.now(UTC).isoformat(),
            "phase": "4.1",
            "model_name": "LightGBM",
            "model_version": MAIN_MODEL_V2_1_VERSION,
            "configuration": config.model_dump(mode="json"),
            "configuration_hash": config.research_hash,
            "hyperparameter_search": "none",
            "families": families,
            "no_cross_family_metric_claim": True,
            "code_version": "phase4.1-1.0.0",
        }
        write_manifest(temporary / "experiment.json", payload)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return payload
