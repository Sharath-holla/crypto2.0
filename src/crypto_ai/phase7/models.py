from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import ModelConfig, stable_hash
from crypto_ai.phase7.folds import IneligibleFoldError

Architecture = Literal["G0", "C0", "P0", "H0"]


def _symbols(table: pa.Table) -> np.ndarray:
    return np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _matrix(table: pa.Table, columns: tuple[str, ...]) -> np.ndarray:
    missing = [name for name in columns if name not in table.column_names]
    if missing:
        raise ValueError(f"Phase 7 model input is missing features: {missing}")
    matrix = np.column_stack([_floats(table, name) for name in columns])
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise ValueError("Phase 7 model features must be a finite matrix")
    return matrix


def symbol_balanced_weights(symbols: np.ndarray) -> np.ndarray:
    values = np.asarray(symbols, dtype=object)
    if values.ndim != 1 or not len(values):
        raise IneligibleFoldError("symbol-balanced weighting needs non-empty symbols")
    unique, counts = np.unique(values, return_counts=True)
    count_by_symbol = dict(zip(unique.tolist(), counts.tolist(), strict=True))
    weight = np.asarray([1.0 / count_by_symbol[item] for item in values], dtype=np.float64)
    return weight * len(values) / np.sum(weight)


def _append_symbol_identity(
    matrix: np.ndarray,
    symbols: np.ndarray,
    symbol_levels: tuple[str, ...],
) -> np.ndarray:
    encoded = np.zeros((len(symbols), len(symbol_levels)), dtype=np.float64)
    index = {symbol: column for column, symbol in enumerate(symbol_levels)}
    for row, symbol in enumerate(symbols):
        column = index.get(str(symbol))
        if column is not None:
            encoded[row, column] = 1.0
    return np.column_stack((matrix, encoded))


def _estimator(config: ModelConfig, *, model_threads: int) -> Any:
    import lightgbm as lgb

    return lgb.LGBMRegressor(
        objective="regression",
        learning_rate=config.learning_rate,
        n_estimators=config.n_estimators,
        num_leaves=config.num_leaves,
        max_depth=config.max_depth,
        min_child_samples=config.min_child_samples,
        subsample=config.subsample,
        subsample_freq=1,
        colsample_bytree=config.colsample_bytree,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        random_state=config.seed,
        n_jobs=model_threads,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )


def _fit(
    train_x: np.ndarray,
    train_y: np.ndarray,
    validation_x: np.ndarray,
    validation_y: np.ndarray,
    *,
    config: ModelConfig,
    model_threads: int,
    sample_weight: np.ndarray | None,
) -> Any:
    import lightgbm as lgb

    if not len(train_y) or not len(validation_y):
        raise IneligibleFoldError("LightGBM requires non-empty train and validation rows")
    estimator = _estimator(config, model_threads=model_threads)
    estimator.fit(
        train_x,
        train_y,
        sample_weight=sample_weight,
        eval_X=validation_x,
        eval_y=validation_y,
        callbacks=[
            lgb.early_stopping(config.early_stopping_rounds, first_metric_only=True, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    return estimator


@dataclass(slots=True)
class Phase7ModelBundle:
    architecture: Architecture
    feature_columns: tuple[str, ...]
    target_column: str
    estimators: dict[str, Any]
    cluster_mapping: dict[str, int]
    symbol_levels: tuple[str, ...]
    explicit_symbol_id: bool
    symbol_balanced: bool
    symbol_corrections: dict[str, float]
    cluster_corrections: dict[int, float]
    metadata: dict[str, Any]

    def predict(self, table: pa.Table) -> tuple[np.ndarray, np.ndarray]:
        base = _matrix(table, self.feature_columns)
        symbols = _symbols(table)
        predicted = np.full(table.num_rows, np.nan)
        covered = np.zeros(table.num_rows, dtype=bool)
        if self.architecture in {"G0", "H0"}:
            matrix = (
                _append_symbol_identity(base, symbols, self.symbol_levels)
                if self.explicit_symbol_id
                else base
            )
            estimator = self.estimators["global"]
            predicted = np.asarray(estimator.predict(matrix), dtype=np.float64)
            covered[:] = True
            if self.architecture == "H0":
                for index, symbol in enumerate(symbols):
                    if str(symbol) in self.symbol_corrections:
                        predicted[index] += self.symbol_corrections[str(symbol)]
                    else:
                        cluster = self.cluster_mapping.get(str(symbol))
                        if cluster in self.cluster_corrections:
                            predicted[index] += self.cluster_corrections[cluster]
        elif self.architecture == "C0":
            for symbol in np.unique(symbols):
                cluster = self.cluster_mapping.get(str(symbol))
                key = f"cluster:{cluster}" if cluster is not None else ""
                rows = np.flatnonzero(symbols == symbol)
                if key in self.estimators:
                    predicted[rows] = self.estimators[key].predict(base[rows])
                    covered[rows] = True
        elif self.architecture == "P0":
            for symbol in np.unique(symbols):
                key = f"symbol:{symbol}"
                rows = np.flatnonzero(symbols == symbol)
                if key in self.estimators:
                    predicted[rows] = self.estimators[key].predict(base[rows])
                    covered[rows] = True
        if np.any(covered & ~np.isfinite(predicted)):
            raise ValueError("Phase 7 model produced non-finite covered predictions")
        return predicted, covered


def _subset(table: pa.Table, mask: np.ndarray) -> pa.Table:
    return table.filter(pa.array(mask))


def fit_architecture(
    architecture: Architecture,
    train: pa.Table,
    validation: pa.Table,
    *,
    feature_columns: tuple[str, ...],
    target_column: str,
    config: ModelConfig,
    model_threads: int,
    cluster_mapping: dict[str, int] | None = None,
    explicit_symbol_id: bool = False,
    symbol_balanced: bool = False,
    hybrid_calibration: pa.Table | None = None,
    eligibility_calibration_a: pa.Table | None = None,
) -> Phase7ModelBundle:
    if architecture not in {"G0", "C0", "P0", "H0"}:
        raise ValueError(f"unknown Phase 7 architecture: {architecture}")
    cluster_mapping = dict(cluster_mapping or {})
    train_symbols = _symbols(train)
    validation_symbols = _symbols(validation)
    calibration_symbols = (
        _symbols(eligibility_calibration_a)
        if eligibility_calibration_a is not None
        else np.asarray([], dtype=object)
    )
    train_x = _matrix(train, feature_columns)
    validation_x = _matrix(validation, feature_columns)
    train_y = _floats(train, target_column)
    validation_y = _floats(validation, target_column)
    if not np.all(np.isfinite(train_y)) or not np.all(np.isfinite(validation_y)):
        raise ValueError("Phase 7 model targets must be finite")
    weights = symbol_balanced_weights(train_symbols) if symbol_balanced else None
    estimators: dict[str, Any] = {}
    per_symbol_eligibility: dict[str, dict[str, Any]] = {}
    symbol_levels: tuple[str, ...] = ()
    if architecture in {"G0", "H0"}:
        symbol_levels = tuple(sorted(str(value) for value in np.unique(train_symbols)))
        if explicit_symbol_id:
            train_x = _append_symbol_identity(train_x, train_symbols, symbol_levels)
            validation_x = _append_symbol_identity(validation_x, validation_symbols, symbol_levels)
        estimators["global"] = _fit(
            train_x,
            train_y,
            validation_x,
            validation_y,
            config=config,
            model_threads=model_threads,
            sample_weight=weights,
        )
        for symbol in sorted(str(value) for value in np.unique(train_symbols)):
            per_symbol_eligibility[symbol] = {"status": "GLOBAL_COVERED"}
    elif architecture == "C0":
        if not cluster_mapping:
            raise ValueError("C0 requires a frozen TRAIN-only cluster mapping")
        for cluster in sorted(set(cluster_mapping.values())):
            train_mask = np.asarray(
                [cluster_mapping.get(str(symbol)) == cluster for symbol in train_symbols]
            )
            validation_mask = np.asarray(
                [cluster_mapping.get(str(symbol)) == cluster for symbol in validation_symbols]
            )
            train_count = int(np.count_nonzero(train_mask))
            validation_count = int(np.count_nonzero(validation_mask))
            if train_count < 100 or validation_count < 20:
                for symbol, assigned_cluster in cluster_mapping.items():
                    if assigned_cluster == cluster:
                        per_symbol_eligibility[symbol] = {
                            "status": "CLUSTER_INELIGIBLE",
                            "reason": "insufficient_cluster_train_or_validation_rows",
                            "train_rows": train_count,
                            "validation_rows": validation_count,
                        }
                continue
            cluster_weights = (
                symbol_balanced_weights(train_symbols[train_mask]) if symbol_balanced else None
            )
            estimators[f"cluster:{cluster}"] = _fit(
                _matrix(_subset(train, train_mask), feature_columns),
                train_y[train_mask],
                _matrix(_subset(validation, validation_mask), feature_columns),
                validation_y[validation_mask],
                config=config,
                model_threads=model_threads,
                sample_weight=cluster_weights,
            )
            for symbol, assigned_cluster in cluster_mapping.items():
                if assigned_cluster == cluster:
                    per_symbol_eligibility[symbol] = {"status": "CLUSTER_COVERED"}
    else:
        for symbol in sorted(str(value) for value in np.unique(train_symbols)):
            train_mask = train_symbols == symbol
            validation_mask = validation_symbols == symbol
            calibration_mask = calibration_symbols == symbol
            train_count = int(np.count_nonzero(train_mask))
            validation_count = int(np.count_nonzero(validation_mask))
            calibration_a_count = int(np.count_nonzero(calibration_mask))
            reasons: list[str] = []
            if train_count < config.minimum_train_rows_per_coin:
                reasons.append("insufficient_train_rows")
            if validation_count < config.minimum_validation_rows_per_coin:
                reasons.append("insufficient_validation_rows")
            if calibration_a_count < config.minimum_calibration_rows_per_coin:
                reasons.append("insufficient_calibration_a_rows")
            if reasons:
                per_symbol_eligibility[symbol] = {
                    "status": "PER_COIN_INELIGIBLE",
                    "reasons": reasons,
                    "train_rows": train_count,
                    "validation_rows": validation_count,
                    "calibration_a_rows": calibration_a_count,
                }
                continue
            estimators[f"symbol:{symbol}"] = _fit(
                _matrix(_subset(train, train_mask), feature_columns),
                train_y[train_mask],
                _matrix(_subset(validation, validation_mask), feature_columns),
                validation_y[validation_mask],
                config=config,
                model_threads=model_threads,
                sample_weight=None,
            )
            per_symbol_eligibility[symbol] = {
                "status": "PER_COIN_ELIGIBLE",
                "train_rows": train_count,
                "validation_rows": validation_count,
                "calibration_a_rows": calibration_a_count,
            }
    if not estimators:
        raise IneligibleFoldError(f"{architecture} produced no eligible estimators")
    symbol_corrections: dict[str, float] = {}
    cluster_corrections: dict[int, float] = {}
    hybrid_symbol_eligibility: dict[str, dict[str, Any]] = {}
    if architecture == "H0" and hybrid_calibration is not None:
        calibration_x = _matrix(hybrid_calibration, feature_columns)
        calibration_symbols = _symbols(hybrid_calibration)
        if explicit_symbol_id:
            calibration_x = _append_symbol_identity(
                calibration_x, calibration_symbols, symbol_levels
            )
        raw = np.asarray(estimators["global"].predict(calibration_x), dtype=np.float64)
        residual = _floats(hybrid_calibration, target_column) - raw
        for symbol in sorted(str(value) for value in np.unique(calibration_symbols)):
            mask = calibration_symbols == symbol
            train_count = int(np.count_nonzero(train_symbols == symbol))
            residual_count = int(np.count_nonzero(mask))
            correction_supported = (
                train_count >= config.minimum_train_rows_per_coin
                and residual_count >= config.minimum_validation_rows_per_coin
                and residual_count >= config.minimum_calibration_rows_per_coin
            )
            hybrid_symbol_eligibility[symbol] = {
                "status": (
                    "SYMBOL_CORRECTION_ELIGIBLE"
                    if correction_supported
                    else "SYMBOL_CORRECTION_INELIGIBLE"
                ),
                "train_rows": train_count,
                "residual_rows": residual_count,
                "fallback": None if correction_supported else "cluster_then_global",
            }
            if correction_supported:
                symbol_corrections[symbol] = float(np.mean(residual[mask]))
        for cluster in sorted(set(cluster_mapping.values())):
            mask = np.asarray(
                [cluster_mapping.get(str(symbol)) == cluster for symbol in calibration_symbols]
            )
            if np.count_nonzero(mask) >= config.minimum_calibration_rows_per_coin:
                cluster_corrections[cluster] = float(np.mean(residual[mask]))
    metadata = {
        "architecture": architecture,
        "algorithm": "LightGBM",
        "feature_columns": list(feature_columns),
        "target_column": target_column,
        "explicit_symbol_id": explicit_symbol_id,
        "unknown_symbol_id_policy": (
            "ALL_ZERO_KNOWN_SYMBOL_LEVELS" if explicit_symbol_id else "NOT_APPLICABLE"
        ),
        "global_unseen_symbol_supported": architecture in {"G0", "H0"},
        "symbol_balanced": symbol_balanced,
        "estimators": sorted(estimators),
        "cluster_mapping": cluster_mapping,
        "symbol_correction_count": len(symbol_corrections),
        "cluster_correction_count": len(cluster_corrections),
        "hybrid_fallback_order": (
            ["symbol_correction", "cluster_correction", "global_prediction"]
            if architecture == "H0"
            else None
        ),
        "hybrid_symbol_corrections": sorted(symbol_corrections),
        "hybrid_cluster_corrections": sorted(cluster_corrections),
        "hybrid_symbol_correction_eligibility": hybrid_symbol_eligibility,
        "per_symbol_eligibility": per_symbol_eligibility,
        "test_used_for_fit": False,
        "seed": config.seed,
    }
    metadata["model_identity"] = stable_hash(metadata)
    return Phase7ModelBundle(
        architecture=architecture,
        feature_columns=feature_columns,
        target_column=target_column,
        estimators=estimators,
        cluster_mapping=cluster_mapping,
        symbol_levels=symbol_levels,
        explicit_symbol_id=explicit_symbol_id,
        symbol_balanced=symbol_balanced,
        symbol_corrections=symbol_corrections,
        cluster_corrections=cluster_corrections,
        metadata=metadata,
    )


def save_model(bundle: Phase7ModelBundle, path: Path) -> Path:
    path = path.resolve()
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite Phase 7 model: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        joblib.dump(bundle, temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def load_model(path: Path) -> Phase7ModelBundle:
    payload = joblib.load(path)
    if not isinstance(payload, Phase7ModelBundle):
        raise ValueError(f"Unsupported Phase 7 model artifact: {path}")
    return payload
