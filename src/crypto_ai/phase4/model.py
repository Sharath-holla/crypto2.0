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

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.phase4.features import FEATURE_GROUPS
from crypto_ai.phase4.gold import read_gold_v2
from crypto_ai.research.config import BASELINE_FEATURE_COLUMNS, ExperimentConfig
from crypto_ai.research.gold import TARGET_COLUMN
from crypto_ai.research.metrics import prediction_buckets, regression_metrics
from crypto_ai.research.models import save_model, train_model
from crypto_ai.research.split import chronological_purged_split

MAIN_MODEL_V2_VERSION = "2.0.0"

# A0 remains the immutable Phase 3 baseline. The final model removes exact or
# near-exact representations identified by the Phase 4 redundancy audit.
MODEL_V2_REDUNDANT_COLUMNS = {
    "log_return_5m",  # same information as return_5m at this scale
    "candle_body_pct",  # near-identical to return_5m for continuous futures bars
    "relative_quote_volume",  # near-identical to normalized base volume
    "trend_score_4h",  # exact alias of return_4h
    "taker_buy_base_share",  # algebraic transform of quote imbalance
    "taker_buy_quote_share",  # algebraic transform of quote imbalance
    "taker_sell_quote_share",  # one minus taker-buy quote share
    "taker_imbalance_base",  # near-identical to quote imbalance
}


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


def _unique(*collections: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(name for collection in collections for name in collection))


def ablation_feature_sets(groups: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    available = set(groups)
    result: dict[str, tuple[str, ...]] = {"A0": tuple(BASELINE_FEATURE_COLUMNS)}
    current = _unique(result["A0"], FEATURE_GROUPS["price"], FEATURE_GROUPS["trend"])
    result["A1"] = current
    current = _unique(current, FEATURE_GROUPS["momentum"], FEATURE_GROUPS["volatility"])
    result["A2"] = current
    current = _unique(current, FEATURE_GROUPS["volume"])
    result["A3"] = current
    current = _unique(current, FEATURE_GROUPS["pressure"])
    result["A4"] = current
    if "funding" in available:
        current = _unique(current, FEATURE_GROUPS["funding"])
        result["A5"] = current
    if "basis" in available:
        current = _unique(current, FEATURE_GROUPS["basis"])
        result["A6"] = current
    if "open_interest" in available:
        current = _unique(current, FEATURE_GROUPS["open_interest"])
        result["A7"] = current
    current = _unique(current, FEATURE_GROUPS["regime"], FEATURE_GROUPS["time"])
    result["A8"] = tuple(name for name in current if name not in MODEL_V2_REDUNDANT_COLUMNS)
    return result


def _matrix(table: pa.Table, columns: tuple[str, ...]) -> np.ndarray:
    missing = [name for name in columns if name not in table.column_names]
    if missing:
        raise ValueError(f"Gold V2 is missing model features: {missing}")
    result = np.column_stack(
        [table.column(name).combine_chunks().to_numpy() for name in columns]
    ).astype(np.float64, copy=False)
    if not np.all(np.isfinite(result)):
        raise ValueError("Main Model V2 features contain non-finite values")
    return result


def _target(table: pa.Table) -> np.ndarray:
    result = table.column(TARGET_COLUMN).combine_chunks().to_numpy().astype(np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError("Main Model V2 target contains non-finite values")
    return result


def _predictions_table(
    validation: pa.Table,
    test: pa.Table,
    validation_predictions: np.ndarray,
    test_predictions: np.ndarray,
) -> pa.Table:
    source = pa.concat_tables([validation, test])
    splits = ["validation"] * validation.num_rows + ["test"] * test.num_rows
    predicted = np.concatenate([validation_predictions, test_predictions])
    names = (
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
    data = {name: source.column(name) for name in names}
    data["split"] = splits
    data["predicted_return"] = predicted
    return pa.table(data)


def _regime_metrics(table: pa.Table, predictions: np.ndarray) -> dict[str, Any]:
    actual = _target(table)
    result: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
    ):
        mask = table.column(name).combine_chunks().to_numpy().astype(bool)
        if np.count_nonzero(mask) >= 2:
            result[name] = regression_metrics(actual[mask], predictions[mask])
    return result


def _pressure_analysis(table: pa.Table, predictions: np.ndarray) -> dict[str, Any]:
    pressure = table.column("taker_imbalance_quote").combine_chunks().to_numpy()
    actual = _target(table)
    order = np.argsort(pressure, kind="mergesort")
    buckets: list[dict[str, Any]] = []
    for number, indices in enumerate(np.array_split(order, min(10, len(order))), start=1):
        buckets.append(
            {
                "bucket": number,
                "count": int(len(indices)),
                "mean_pressure": float(np.mean(pressure[indices])),
                "mean_prediction": float(np.mean(predictions[indices])),
                "mean_realized_return": float(np.mean(actual[indices])),
            }
        )
    return {"buckets": buckets}


def _redundancy_audit(table: pa.Table, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    matrix = _matrix(table, columns)
    correlations = np.corrcoef(matrix, rowvar=False)
    findings: list[dict[str, Any]] = []
    for left in range(len(columns)):
        for right in range(left + 1, len(columns)):
            value = correlations[left, right]
            if np.isfinite(value) and abs(value) >= 0.995:
                findings.append(
                    {"left": columns[left], "right": columns[right], "correlation": float(value)}
                )
    return findings


def train_main_model_v2(
    gold_manifest_path: Path,
    config: ExperimentConfig,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    table, manifest = read_gold_v2(gold_manifest_path)
    groups = tuple(manifest["feature_groups"])
    ablations = ablation_feature_sets(groups)
    missing = {
        name: sorted(set(columns) - set(table.column_names))
        for name, columns in ablations.items()
        if set(columns) - set(table.column_names)
    }
    if missing:
        raise ValueError(f"Ablation schema mismatch: {missing}")
    split = chronological_purged_split(table, config.split)
    identity = {
        "dataset_version": manifest["dataset_version"],
        "configuration": config.model_dump(mode="json"),
        "ablations": ablations,
        "model_version": MAIN_MODEL_V2_VERSION,
    }
    experiment_id = f"main-model-v2-{_hash(identity)}"
    root = (artifact_root or config.artifact_root).resolve()
    final = root / "phase4" / "experiments" / experiment_id
    experiment_path = final / "experiment.json"
    existing = read_manifest(experiment_path)
    if existing is not None:
        return existing
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}
    try:
        for ablation, columns in ablations.items():
            trained = train_model(
                "lightgbm",
                _matrix(split.train, columns),
                _target(split.train),
                _matrix(split.validation, columns),
                _target(split.validation),
                feature_columns=columns,
                config=config,
                common_metadata={
                    "phase": 4,
                    "main_model_version": MAIN_MODEL_V2_VERSION,
                    "ablation": ablation,
                    "dataset_version": manifest["dataset_version"],
                },
            )
            validation_predictions = trained.bundle.predict(
                _matrix(split.validation, columns), columns
            )
            test_predictions = trained.bundle.predict(_matrix(split.test, columns), columns)
            importance = trained.feature_importance or {}
            importance["split"] = {
                name: int(value)
                for name, value in zip(
                    columns,
                    trained.bundle.estimator.booster_.feature_importance(importance_type="split"),
                    strict=True,
                )
            }
            ablation_dir = temporary / ablation
            ablation_dir.mkdir()
            save_model(trained.bundle, ablation_dir / "model.joblib")
            predictions = _predictions_table(
                split.validation,
                split.test,
                validation_predictions,
                test_predictions,
            )
            pq.write_table(predictions, ablation_dir / "predictions.parquet", compression="zstd")
            write_manifest(ablation_dir / "feature_importance.json", importance)
            results[ablation] = {
                "feature_count": len(columns),
                "feature_columns": list(columns),
                "validation_metrics": regression_metrics(
                    _target(split.validation), validation_predictions
                ),
                "test_metrics": regression_metrics(_target(split.test), test_predictions),
                "test_prediction_buckets": prediction_buckets(
                    _target(split.test), test_predictions
                ),
                "best_iteration": trained.bundle.metadata.get("best_iteration"),
                "model": f"{ablation}/model.joblib",
                "predictions": f"{ablation}/predictions.parquet",
                "feature_importance": f"{ablation}/feature_importance.json",
            }

        final_name = "A8"
        final_columns = ablations[final_name]
        final_bundle_path = temporary / final_name / "model.joblib"
        import joblib

        final_bundle = joblib.load(final_bundle_path)
        final_test_predictions = final_bundle.predict(
            _matrix(split.test, final_columns), final_columns
        )
        payload = {
            "experiment_id": experiment_id,
            "status": "complete",
            "created_at": datetime.now(UTC).isoformat(),
            "phase": 4,
            "model_name": "LightGBM",
            "model_version": MAIN_MODEL_V2_VERSION,
            "dataset_manifest": str(gold_manifest_path.resolve()),
            "dataset_version": manifest["dataset_version"],
            "configuration": config.model_dump(mode="json"),
            "configuration_hash": config.research_hash,
            "split": split.metadata(),
            "same_overlap_for_all_ablations": True,
            "ablations": results,
            "selected_model": final_name,
            "selection_rule": (
                "A8 is the predeclared complete available-feature model; "
                "test was not used for selection"
            ),
            "test_regime_metrics": _regime_metrics(split.test, final_test_predictions),
            "test_pressure_analysis": _pressure_analysis(split.test, final_test_predictions),
            "redundancy_audit": _redundancy_audit(split.train, final_columns),
            "code_version": "phase4-1.0.0",
        }
        write_manifest(temporary / "experiment.json", payload)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return payload
