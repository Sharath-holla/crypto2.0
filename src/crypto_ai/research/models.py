from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crypto_ai.research.config import ExperimentConfig

MODEL_VERSION = "1.0.0"


class ZeroPredictor:
    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.zeros(features.shape[0], dtype=np.float64)


@dataclass(slots=True)
class ConstantPredictor:
    value: float

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.full(features.shape[0], self.value, dtype=np.float64)


@dataclass(slots=True)
class ColumnPredictor:
    index: int
    multiplier: float = 1.0

    def predict(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(features[:, self.index] * self.multiplier, dtype=np.float64)


@dataclass(slots=True)
class ModelBundle:
    model_name: str
    model_version: str
    feature_columns: tuple[str, ...]
    estimator: Any
    metadata: dict[str, Any]

    def predict(
        self,
        features: np.ndarray,
        feature_columns: tuple[str, ...] | list[str],
    ) -> np.ndarray:
        provided = tuple(feature_columns)
        if provided != self.feature_columns:
            missing = [name for name in self.feature_columns if name not in provided]
            extra = [name for name in provided if name not in self.feature_columns]
            raise ValueError(
                "Incompatible feature schema; "
                f"expected={list(self.feature_columns)}, missing={missing}, extra={extra}, "
                f"provided_order={list(provided)}"
            )
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_columns):
            raise ValueError(
                f"Feature matrix must have {len(self.feature_columns)} columns; "
                f"got shape {matrix.shape}"
            )
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Feature matrix contains NaN or infinite values")
        predictions = np.asarray(self.estimator.predict(matrix), dtype=np.float64)
        if predictions.shape != (matrix.shape[0],) or not np.all(np.isfinite(predictions)):
            raise ValueError("Model produced invalid predictions")
        return predictions


@dataclass(frozen=True, slots=True)
class TrainedModel:
    bundle: ModelBundle
    feature_importance: dict[str, Any] | None = None


def _validate_training_arrays(
    train_features: np.ndarray,
    train_target: np.ndarray,
    validation_features: np.ndarray,
    validation_target: np.ndarray,
    feature_columns: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    train_features = np.asarray(train_features, dtype=np.float64)
    validation_features = np.asarray(validation_features, dtype=np.float64)
    train_target = np.asarray(train_target, dtype=np.float64)
    validation_target = np.asarray(validation_target, dtype=np.float64)
    if train_features.ndim != 2 or train_features.shape[1] != len(feature_columns):
        raise ValueError("Training feature matrix does not match the official feature schema")
    if validation_features.ndim != 2 or validation_features.shape[1] != len(feature_columns):
        raise ValueError("Validation feature matrix does not match the official feature schema")
    if train_target.shape != (train_features.shape[0],):
        raise ValueError("Training target shape is invalid")
    if validation_target.shape != (validation_features.shape[0],):
        raise ValueError("Validation target shape is invalid")
    for name, values in (
        ("training features", train_features),
        ("validation features", validation_features),
        ("training target", train_target),
        ("validation target", validation_target),
    ):
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} contains NaN or infinite values")
    if not len(train_target) or not len(validation_target):
        raise ValueError("Training and validation data must be non-empty")
    return train_features, train_target, validation_features, validation_target


def train_model(
    model_name: str,
    train_features: np.ndarray,
    train_target: np.ndarray,
    validation_features: np.ndarray,
    validation_target: np.ndarray,
    *,
    feature_columns: tuple[str, ...],
    config: ExperimentConfig,
    common_metadata: dict[str, Any],
) -> TrainedModel:
    train_features, train_target, validation_features, validation_target = (
        _validate_training_arrays(
            train_features,
            train_target,
            validation_features,
            validation_target,
            feature_columns,
        )
    )
    metadata = {
        **common_metadata,
        "model_name": model_name,
        "model_version": MODEL_VERSION,
        "feature_columns": list(feature_columns),
        "random_seed": config.seed,
        "library_versions": {
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "lightgbm": version("lightgbm"),
        },
    }
    importance: dict[str, Any] | None = None
    if model_name == "zero":
        estimator: Any = ZeroPredictor()
        metadata["hyperparameters"] = {}
    elif model_name == "historical_mean":
        training_mean = float(np.mean(train_target))
        estimator = ConstantPredictor(training_mean)
        metadata["hyperparameters"] = {"training_target_mean": training_mean}
    elif model_name == "momentum":
        index = feature_columns.index("return_1h")
        estimator = ColumnPredictor(index=index)
        metadata["hyperparameters"] = {"source_feature": "return_1h", "multiplier": 1.0}
    elif model_name == "mean_reversion":
        index = feature_columns.index("ema20_distance")
        estimator = ColumnPredictor(index=index, multiplier=-1.0)
        metadata["hyperparameters"] = {
            "source_feature": "ema20_distance",
            "multiplier": -1.0,
        }
    elif model_name == "ridge":
        estimator = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("ridge", Ridge(alpha=config.ridge.alpha)),
            ]
        )
        estimator.fit(train_features, train_target)
        scaler = estimator.named_steps["scaler"]
        metadata["hyperparameters"] = {"alpha": config.ridge.alpha, "scale": True}
        metadata["training_only_scaler_mean"] = scaler.mean_.tolist()
        metadata["training_only_scaler_scale"] = scaler.scale_.tolist()
    elif model_name == "lightgbm":
        import lightgbm as lgb

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
            train_features,
            train_target,
            eval_X=validation_features,
            eval_y=validation_target,
            eval_metric="l2",
            callbacks=[
                lgb.early_stopping(early_stopping_rounds, first_metric_only=True, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )
        gain = estimator.booster_.feature_importance(importance_type="gain")
        permutation = permutation_importance(
            estimator,
            validation_features,
            validation_target,
            scoring="neg_mean_absolute_error",
            n_repeats=5,
            random_state=config.seed,
            n_jobs=1,
        )
        importance = {
            "gain": {name: float(value) for name, value in zip(feature_columns, gain, strict=True)},
            "validation_permutation_mae": {
                name: {
                    "mean": float(mean),
                    "std": float(std),
                }
                for name, mean, std in zip(
                    feature_columns,
                    permutation.importances_mean,
                    permutation.importances_std,
                    strict=True,
                )
            },
        }
        metadata["hyperparameters"] = config.lightgbm.model_dump()
        metadata["best_iteration"] = int(estimator.best_iteration_)
    else:
        raise ValueError(f"Unsupported model: {model_name}")
    return TrainedModel(
        bundle=ModelBundle(
            model_name=model_name,
            model_version=MODEL_VERSION,
            feature_columns=feature_columns,
            estimator=estimator,
            metadata=metadata,
        ),
        feature_importance=importance,
    )


def save_model(bundle: ModelBundle, path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite model artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        joblib.dump(bundle, temporary)
        if path.exists():
            raise FileExistsError(f"Model artifact appeared during save: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_model(path: Path) -> ModelBundle:
    payload = joblib.load(path)
    if not isinstance(payload, ModelBundle):
        raise ValueError(f"Unsupported model artifact: {path}")
    return payload
