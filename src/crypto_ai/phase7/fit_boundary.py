"""Fail-closed invariants checked right at the LightGBM fit / evaluation boundary.

Added by Claude (2026-11-08, pre-RunPod hardening). Standard library + NumPy (+ PyArrow only for
the segment check). Every function here only READS its inputs: it never reorders, filters, casts or
repairs a matrix, so it cannot change a feature, a target, a prepared cache or a fitted model. A
violated invariant raises ``ValueError`` with a leading UPPER_CASE reason code before LightGBM sees
the data; a weak prediction is never treated as a software error (only a broken one is).

Why this exists: prepared matrices can come back from the on-disk prepared cache, so the checks
that ran when they were first built (``models._matrix``) are not a guarantee at fit time.
"""

from __future__ import annotations

from typing import Any

import numpy as np

FIT_BOUNDARY_VERSION = "phase7_fit_boundary_v1"
_BLOCK_ROWS = 131_072  # bounded temporary memory for finiteness checks on multi-GB matrices


def _all_finite_blocked(matrix: np.ndarray) -> bool:
    for start in range(0, matrix.shape[0], _BLOCK_ROWS):
        if not np.isfinite(matrix[start : start + _BLOCK_ROWS]).all():
            return False
    return True


def assert_fit_matrices(
    train_x: np.ndarray,
    train_y: np.ndarray,
    validation_x: np.ndarray,
    validation_y: np.ndarray,
    sample_weight: np.ndarray | None,
) -> None:
    """Shapes, dtypes, finiteness and weight sanity of the exact arrays handed to LightGBM."""

    for name, matrix in (("train_x", train_x), ("validation_x", validation_x)):
        if not isinstance(matrix, np.ndarray) or matrix.ndim != 2:
            raise ValueError(f"FIT_BOUNDARY_SHAPE: {name} must be a 2-D NumPy matrix")
        if matrix.dtype != np.float64:
            raise ValueError(f"FIT_BOUNDARY_DTYPE: {name} is {matrix.dtype}, expected float64")
    if train_x.shape[1] != validation_x.shape[1]:
        raise ValueError(
            f"FIT_BOUNDARY_FEATURE_COUNT: train {train_x.shape[1]} vs validation "
            f"{validation_x.shape[1]} columns"
        )
    for name, vector, rows in (
        ("train_y", train_y, train_x.shape[0]),
        ("validation_y", validation_y, validation_x.shape[0]),
    ):
        values = np.asarray(vector)
        if values.ndim != 1 or len(values) != rows:
            raise ValueError(f"FIT_BOUNDARY_ROWS: {name} {values.shape} vs {rows} matrix rows")
        if not np.isfinite(values).all():
            raise ValueError(f"FIT_BOUNDARY_NON_FINITE: {name}")
    if not _all_finite_blocked(train_x) or not _all_finite_blocked(validation_x):
        raise ValueError("FIT_BOUNDARY_NON_FINITE: feature matrix")
    if sample_weight is not None:
        weights = np.asarray(sample_weight, dtype=np.float64)
        if weights.ndim != 1 or len(weights) != train_x.shape[0]:
            raise ValueError("FIT_BOUNDARY_ROWS: sample_weight does not match the train rows")
        if not np.isfinite(weights).all() or not (weights > 0).all():
            raise ValueError("FIT_BOUNDARY_WEIGHTS: sample weights must be finite and positive")


def _keys(table: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(integer symbol codes, symbol per row, int64 feature_time) without string sorting."""

    import pyarrow as pa

    symbols = table.column("symbol").combine_chunks().dictionary_encode()
    codes = np.asarray(symbols.indices.to_numpy(zero_copy_only=False), dtype=np.int64)
    names = np.asarray(symbols.dictionary.to_pylist(), dtype=object)
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    return codes, names[codes], times


def _duplicate_key_count(codes: np.ndarray, times: np.ndarray) -> int:
    if len(times) < 2:
        return 0
    order = np.lexsort((times, codes))
    c, t = codes[order], times[order]
    return int(np.count_nonzero((c[1:] == c[:-1]) & (t[1:] == t[:-1])))


def assert_fit_segments(
    train: Any,
    validation: Any,
    *,
    model_inputs: Any,
    feature_columns: tuple[str, ...],
    target_column: str,
    validation_start_us: int | None = None,
) -> dict[str, Any]:
    """Row identity / ordering / purge invariants of the Train and Validation tables.

    Returns a small JSON-safe summary for the training report. Only Train and Validation are
    inspected (the rows the fit and early stopping see); Cal-A / Cal-B / TEST are not touched.
    """

    if tuple(model_inputs.feature_columns) != tuple(feature_columns):
        raise ValueError("FIT_BOUNDARY_FEATURE_ORDER: prepared feature order differs from spec")
    if model_inputs.target_column != target_column:
        raise ValueError("FIT_BOUNDARY_TARGET: prepared target column differs from spec")
    summary: dict[str, Any] = {"version": FIT_BOUNDARY_VERSION}
    for name, table, y, symbols in (
        ("train", train, model_inputs.train_y, model_inputs.train_symbols),
        ("validation", validation, model_inputs.validation_y, model_inputs.validation_symbols),
    ):
        if table.num_rows != len(y) or table.num_rows != len(symbols):
            raise ValueError(f"FIT_BOUNDARY_ROWS: {name} metadata rows differ from the matrix")
        codes, table_symbols, times = _keys(table)
        if not np.array_equal(table_symbols, np.asarray(symbols, dtype=object)):
            raise ValueError(f"FIT_BOUNDARY_SYMBOL_ORDER: {name} symbols differ from the matrix")
        duplicates = _duplicate_key_count(codes, times)
        if duplicates:
            raise ValueError(
                f"FIT_BOUNDARY_DUPLICATE_ROWS: {name} has {duplicates} repeated (symbol, time) keys"
            )
        summary[f"{name}_rows"] = int(table.num_rows)
        summary[f"{name}_symbols"] = int(len(np.unique(codes)))
    if (
        validation_start_us is not None
        and train.num_rows
        and "label_end_time" in train.column_names
    ):
        import pyarrow as pa

        ends = train.column("label_end_time").combine_chunks().cast(pa.int64()).to_numpy()
        if int(ends.max()) >= int(validation_start_us):
            # Same rule as phase5.folds._prepare_previous (purge by the ACTUAL label end).
            raise ValueError("FIT_BOUNDARY_PURGE: a TRAIN label ends at/after the VALIDATION start")
        summary["train_labels_end_before_validation_start"] = True
    return summary


def sample_weight_summary(weights: np.ndarray | None, symbols: np.ndarray) -> dict[str, Any]:
    """Effective TRAIN sample weights (they depend on symbol row counts only, never on targets)."""

    if weights is None:
        return {"status": "UNWEIGHTED", "source": "NONE"}
    w = np.asarray(weights, dtype=np.float64)
    names = np.asarray(symbols).astype(str)
    per_symbol: dict[str, dict[str, float | int]] = {}
    for symbol in np.unique(names):
        mask = names == symbol
        per_symbol[str(symbol)] = {
            "rows": int(np.count_nonzero(mask)),
            "weight": float(w[mask][0]),
            "total_weight_share": float(w[mask].sum() / w.sum()),
        }
    return {
        "status": "SYMBOL_BALANCED",
        "source": "TRAIN_SYMBOL_ROW_COUNTS_ONLY",
        "uses_target_information": False,
        "min": float(w.min()),
        "max": float(w.max()),
        "mean": float(w.mean()),
        "per_symbol": per_symbol,
    }


def prediction_health(predicted: np.ndarray, covered: np.ndarray, *, rows: int) -> dict[str, Any]:
    """Post-fit evaluation-boundary check of model predictions (Validation rows).

    Length mismatch and non-finite COVERED predictions raise. A constant prediction vector is not a
    software error (a tree ensemble with no useful split legitimately predicts a constant), so it is
    reported as a WARNING with the numbers.
    """

    p = np.asarray(predicted, dtype=np.float64)
    c = np.asarray(covered, dtype=bool)
    if p.ndim != 1 or len(p) != rows or c.shape != p.shape:
        raise ValueError(f"PREDICTION_BOUNDARY_ROWS: {p.shape} predictions for {rows} rows")
    scored = p[c]
    if not np.isfinite(scored).all():
        raise ValueError("PREDICTION_BOUNDARY_NON_FINITE: covered predictions must be finite")
    constant = bool(len(scored) and np.ptp(scored) == 0.0)
    return {
        "rows": int(rows),
        "covered_rows": int(len(scored)),
        "finite_fraction_covered": 1.0 if len(scored) else None,
        "std": float(scored.std()) if len(scored) and not constant else (0.0 if constant else None),
        "constant": constant,
        "status": "WARNING_CONSTANT_PREDICTIONS" if constant else "OK",
    }
