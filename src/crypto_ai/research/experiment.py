from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.research.config import ExperimentConfig
from crypto_ai.research.gold import TARGET_COLUMN, read_gold_dataset
from crypto_ai.research.metrics import prediction_buckets, regression_metrics
from crypto_ai.research.models import load_model, save_model, train_model
from crypto_ai.research.split import TemporalSplit, chronological_purged_split

logger = logging.getLogger(__name__)

EXPERIMENT_SCHEMA_VERSION = "1.0.0"
EXPERIMENT_CODE_VERSION = "phase3-1.0.1"

_MODEL_NOTES = {
    "zero": ("No fitting; essential error floor.", "Cannot express direction or magnitude."),
    "historical_mean": (
        "Uses training target mean only.",
        "Produces a constant forecast.",
    ),
    "momentum": ("Transparent recent-return rule.", "Uncalibrated one-feature assumption."),
    "mean_reversion": (
        "Transparent EMA-displacement rule.",
        "Uncalibrated one-feature assumption.",
    ),
    "ridge": ("Regularized multivariate linear baseline.", "Captures only linear effects."),
    "lightgbm": (
        "Nonlinear interactions with validation-only early stopping.",
        "Can overfit a short market regime.",
    ),
}


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


def _matrix(table: pa.Table, feature_columns: tuple[str, ...]) -> np.ndarray:
    missing = [name for name in feature_columns if name not in table.column_names]
    if missing:
        raise ValueError(f"Gold dataset is missing model features: {missing}")
    values = np.column_stack(
        [table.column(name).combine_chunks().to_numpy() for name in feature_columns]
    ).astype(np.float64, copy=False)
    if not np.all(np.isfinite(values)):
        raise ValueError("Gold features contain NaN or infinite values")
    return values


def _target(table: pa.Table, target_column: str) -> np.ndarray:
    if target_column not in table.column_names:
        raise ValueError(f"Gold dataset is missing target column {target_column}")
    values = table.column(target_column).combine_chunks().to_numpy().astype(np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("Gold target contains NaN or infinite values")
    return values


def _write_predictions(
    path: Path,
    *,
    validation: pa.Table,
    test: pa.Table,
    validation_predictions: np.ndarray,
    test_predictions: np.ndarray,
    model_name: str,
    model_version: str,
    gold_manifest: dict[str, Any],
) -> str:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite prediction artifact: {path}")
    tables = []
    for split_name, source, predictions in (
        ("validation", validation, validation_predictions),
        ("test", test, test_predictions),
    ):
        tables.append(
            pa.table(
                {
                    "symbol": source.column("symbol"),
                    "feature_time": source.column("feature_time"),
                    "label_end_time": source.column("label_end_time"),
                    "actual_return": source.column(TARGET_COLUMN),
                    "predicted_return": pa.array(predictions, type=pa.float64()),
                    "model_name": pa.array([model_name] * source.num_rows, type=pa.string()),
                    "model_version": pa.array([model_version] * source.num_rows, type=pa.string()),
                    "dataset_version": pa.array(
                        [gold_manifest["dataset_version"]] * source.num_rows, type=pa.string()
                    ),
                    "feature_version": pa.array(
                        [gold_manifest["feature_version"]] * source.num_rows, type=pa.string()
                    ),
                    "label_version": pa.array(
                        [gold_manifest["label_version"]] * source.num_rows, type=pa.string()
                    ),
                    "split": pa.array([split_name] * source.num_rows, type=pa.string()),
                }
            )
        )
    predictions = pa.concat_tables(tables)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(predictions, path, compression="zstd", write_statistics=True)
    return file_sha256(path)


def _write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "model",
        "target",
        "feature_set",
        "train_rows",
        "validation_rows",
        "test_rows",
        "train_time_seconds",
        "inference_time_seconds",
        "mae",
        "rmse",
        "r2",
        "directional_accuracy",
        "pearson_ic",
        "spearman_ic",
        "advantages",
        "problems",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _split_arrays(
    split: TemporalSplit, feature_columns: tuple[str, ...], target_column: str
) -> dict[str, np.ndarray]:
    return {
        "train_x": _matrix(split.train, feature_columns),
        "train_y": _target(split.train, target_column),
        "validation_x": _matrix(split.validation, feature_columns),
        "validation_y": _target(split.validation, target_column),
        "test_x": _matrix(split.test, feature_columns),
        "test_y": _target(split.test, target_column),
    }


def train_experiment(
    gold_manifest_path: Path,
    config: ExperimentConfig,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    gold_table, gold_manifest = read_gold_dataset(gold_manifest_path)
    feature_columns = tuple(gold_manifest["feature_columns"])
    target_column = str(gold_manifest["target_column"])
    if target_column != TARGET_COLUMN:
        raise ValueError(f"Unsupported target column: {target_column}")
    forbidden = [
        name
        for name in feature_columns
        if any(token in name for token in ("future", "target", "label", "entry_reference"))
    ]
    if forbidden:
        raise ValueError(f"Target-derived columns cannot be model features: {forbidden}")
    split = chronological_purged_split(gold_table, config.split)
    arrays = _split_arrays(split, feature_columns, target_column)
    constant = [
        name
        for index, name in enumerate(feature_columns)
        if np.ptp(arrays["train_x"][:, index]) <= 1e-15
    ]
    if constant:
        raise ValueError(f"Training features are constant and require review: {constant}")

    root = (artifact_root or config.artifact_root).resolve()
    identity = {
        "experiment_schema_version": EXPERIMENT_SCHEMA_VERSION,
        "experiment_code_version": EXPERIMENT_CODE_VERSION,
        "dataset_version": gold_manifest["dataset_version"],
        "configuration_hash": config.research_hash,
        "models": config.models,
    }
    experiment_id = f"experiment-{_hash(identity)}"
    final_directory = root / "experiments" / experiment_id
    final_result = final_directory / "experiment.json"
    existing = read_manifest(final_result)
    if existing is not None:
        if existing.get("experiment_id") != experiment_id:
            raise ValueError(f"Existing experiment identity mismatch: {final_result}")
        return existing
    if final_directory.exists():
        raise FileExistsError(f"Incomplete experiment directory exists: {final_directory}")

    root.joinpath("experiments").mkdir(parents=True, exist_ok=True)
    temporary_directory = root / "experiments" / f".{experiment_id}.{uuid.uuid4().hex}.tmp"
    temporary_directory.mkdir(parents=True)
    comparison: list[dict[str, Any]] = []
    model_results: dict[str, Any] = {}
    split_metadata = split.metadata()
    try:
        for model_name in config.models:
            logger.info(
                "Model training started",
                extra={
                    "event": "model_training_started",
                    "model": model_name,
                    "dataset_version": gold_manifest["dataset_version"],
                    "rows": split.train.num_rows,
                },
            )
            trained_at = datetime.now(UTC).isoformat()
            common_metadata = {
                "trained_at": trained_at,
                "symbol": gold_manifest["symbol"],
                "target": target_column,
                "feature_version": gold_manifest["feature_version"],
                "label_version": gold_manifest["label_version"],
                "dataset_version": gold_manifest["dataset_version"],
                "training_start": split_metadata["train_period"]["start"],
                "training_end": split_metadata["train_period"]["end"],
                "validation_start": split_metadata["validation_period"]["start"],
                "validation_end": split_metadata["validation_period"]["end"],
            }
            training_started = time.perf_counter()
            trained = train_model(
                model_name,
                arrays["train_x"],
                arrays["train_y"],
                arrays["validation_x"],
                arrays["validation_y"],
                feature_columns=feature_columns,
                config=config,
                common_metadata=common_metadata,
            )
            training_duration = time.perf_counter() - training_started
            inference_started = time.perf_counter()
            validation_predictions = trained.bundle.predict(arrays["validation_x"], feature_columns)
            test_predictions = trained.bundle.predict(arrays["test_x"], feature_columns)
            inference_duration = time.perf_counter() - inference_started
            validation_metrics = regression_metrics(arrays["validation_y"], validation_predictions)
            test_metrics = regression_metrics(arrays["test_y"], test_predictions)
            buckets = prediction_buckets(arrays["test_y"], test_predictions)

            model_relative = Path("models") / f"{model_name}.joblib"
            metadata_relative = Path("models") / f"{model_name}.metadata.json"
            predictions_relative = Path("predictions") / f"{model_name}.parquet"
            metrics_relative = Path("metrics") / f"{model_name}.json"
            model_path = temporary_directory / model_relative
            save_model(trained.bundle, model_path)
            model_metadata = {
                **trained.bundle.metadata,
                "model_sha256": file_sha256(model_path),
                "feature_importance": trained.feature_importance,
            }
            write_manifest(temporary_directory / metadata_relative, model_metadata)
            prediction_sha = _write_predictions(
                temporary_directory / predictions_relative,
                validation=split.validation,
                test=split.test,
                validation_predictions=validation_predictions,
                test_predictions=test_predictions,
                model_name=model_name,
                model_version=trained.bundle.model_version,
                gold_manifest=gold_manifest,
            )
            metrics_payload = {
                "model_name": model_name,
                "validation": validation_metrics,
                "test": test_metrics,
                "test_prediction_buckets": buckets,
                "feature_importance": trained.feature_importance,
            }
            write_manifest(temporary_directory / metrics_relative, metrics_payload)

            reloaded = load_model(model_path)
            reproduced = reloaded.predict(arrays["test_x"], feature_columns)
            if not np.allclose(reproduced, test_predictions, rtol=1e-12, atol=1e-15):
                raise RuntimeError(f"Reloaded {model_name} model changed predictions")
            advantages, problems = _MODEL_NOTES[model_name]
            comparison_row = {
                "model": model_name,
                "target": target_column,
                "feature_set": gold_manifest["feature_version"],
                "train_rows": split.train.num_rows,
                "validation_rows": split.validation.num_rows,
                "test_rows": split.test.num_rows,
                "train_time_seconds": training_duration,
                "inference_time_seconds": inference_duration,
                "mae": test_metrics["mae"],
                "rmse": test_metrics["rmse"],
                "r2": test_metrics["r2"],
                "directional_accuracy": test_metrics["directional_accuracy"],
                "pearson_ic": test_metrics["pearson_ic"],
                "spearman_ic": test_metrics["spearman_ic"],
                "advantages": advantages,
                "problems": problems,
            }
            comparison.append(comparison_row)
            model_results[model_name] = {
                "status": "complete",
                "model": model_relative.as_posix(),
                "model_metadata": metadata_relative.as_posix(),
                "predictions": predictions_relative.as_posix(),
                "prediction_sha256": prediction_sha,
                "metrics": metrics_relative.as_posix(),
                "train_time_seconds": training_duration,
                "inference_time_seconds": inference_duration,
                "validation_metrics": validation_metrics,
                "test_metrics": test_metrics,
            }
            logger.info(
                "Model training completed",
                extra={
                    "event": "model_training_complete",
                    "model": model_name,
                    "dataset_version": gold_manifest["dataset_version"],
                    "duration_seconds": training_duration,
                },
            )

        write_manifest(temporary_directory / "comparison.json", {"models": comparison})
        _write_comparison_csv(temporary_directory / "comparison.csv", comparison)
        result = {
            "experiment_id": experiment_id,
            "schema_version": EXPERIMENT_SCHEMA_VERSION,
            "status": "complete",
            "created_at": datetime.now(UTC).isoformat(),
            "dataset_manifest": str(gold_manifest_path.resolve()),
            "dataset_version": gold_manifest["dataset_version"],
            "source_silver_version": gold_manifest["source_silver_version"],
            "feature_version": gold_manifest["feature_version"],
            "label_version": gold_manifest["label_version"],
            "target": target_column,
            "feature_count": len(feature_columns),
            "feature_columns": list(feature_columns),
            "configuration_hash": config.research_hash,
            "configuration": config.model_dump(mode="json"),
            "code_version": EXPERIMENT_CODE_VERSION,
            "random_seed": config.seed,
            "split": split_metadata,
            "models": model_results,
            "comparison": comparison,
            "artifacts": {
                "comparison_json": "comparison.json",
                "comparison_csv": "comparison.csv",
            },
            "git_commit": None,
        }
        write_manifest(temporary_directory / "experiment.json", result)
        os.replace(temporary_directory, final_directory)
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    logger.info(
        "Experiment saved",
        extra={
            "event": "experiment_saved",
            "experiment_id": experiment_id,
            "dataset_version": gold_manifest["dataset_version"],
            "models": list(config.models),
        },
    )
    return result


def load_experiment(experiment: Path, *, artifact_root: Path = Path("local_artifacts")) -> dict:
    candidate = experiment
    if not candidate.exists():
        candidate = artifact_root / "experiments" / str(experiment) / "experiment.json"
    elif candidate.is_dir():
        candidate = candidate / "experiment.json"
    payload = read_manifest(candidate.resolve())
    if payload is None:
        raise FileNotFoundError(candidate)
    if payload.get("status") != "complete":
        raise ValueError(f"Experiment is not complete: {candidate}")
    return payload


def comparison_text(experiment: dict[str, Any]) -> str:
    headers = ("Model", "MAE", "RMSE", "R2", "DirAcc", "Pearson", "Spearman")
    lines = [" | ".join(headers), "-" * 92]
    for row in experiment["comparison"]:
        values = [
            str(row["model"]),
            f"{row['mae']:.8f}",
            f"{row['rmse']:.8f}",
            "n/a" if row["r2"] is None else f"{row['r2']:.6f}",
            f"{row['directional_accuracy']:.4f}",
            "n/a" if row["pearson_ic"] is None else f"{row['pearson_ic']:.6f}",
            "n/a" if row["spearman_ic"] is None else f"{row['spearman_ic']:.6f}",
        ]
        lines.append(" | ".join(values))
    return "\n".join(lines)
