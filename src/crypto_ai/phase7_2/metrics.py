from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def brier_score(actual: Sequence[float], probability: Sequence[float]) -> float:
    observed = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(probability, dtype=np.float64)
    if observed.shape != predicted.shape or observed.ndim != 1 or not observed.size:
        raise ValueError("Brier inputs must be matching non-empty vectors")
    if not np.all(np.isin(observed, (0.0, 1.0))):
        raise ValueError("Brier outcomes must be binary")
    if not np.all(np.isfinite(predicted)) or np.any((predicted < 0) | (predicted > 1)):
        raise ValueError("Brier probabilities must be finite and within [0, 1]")
    return float(np.mean((predicted - observed) ** 2))


def pinball_loss(actual: Sequence[float], prediction: Sequence[float], *, quantile: float) -> float:
    if not 0 < quantile < 1:
        raise ValueError("quantile must be inside (0, 1)")
    observed = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(prediction, dtype=np.float64)
    if observed.shape != predicted.shape or observed.ndim != 1 or not observed.size:
        raise ValueError("pinball inputs must be matching non-empty vectors")
    if not np.all(np.isfinite(observed)) or not np.all(np.isfinite(predicted)):
        raise ValueError("pinball inputs must be finite")
    error = observed - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


def ndcg_at_k(relevance: Sequence[float], scores: Sequence[float], *, k: int) -> float:
    truth = np.asarray(relevance, dtype=np.float64)
    predicted = np.asarray(scores, dtype=np.float64)
    if truth.shape != predicted.shape or truth.ndim != 1 or not truth.size:
        raise ValueError("NDCG inputs must be matching non-empty vectors")
    if not np.all(np.isfinite(truth)) or not np.all(np.isfinite(predicted)):
        raise ValueError("NDCG inputs must be finite")
    if np.any(truth < 0) or k <= 0:
        raise ValueError("NDCG relevance must be nonnegative and k positive")
    limit = min(k, truth.size)

    def dcg(values: np.ndarray) -> float:
        discounts = np.log2(np.arange(2, values.size + 2, dtype=np.float64))
        return float(np.sum((np.exp2(values) - 1.0) / discounts))

    predicted_order = np.lexsort((np.arange(truth.size), -predicted))[:limit]
    ideal_order = np.lexsort((np.arange(truth.size), -truth))[:limit]
    ideal = dcg(truth[ideal_order])
    result = dcg(truth[predicted_order]) / ideal if ideal else 0.0
    if not math.isfinite(result):
        raise ValueError("NDCG calculation was non-finite")
    return result
