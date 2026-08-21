from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from crypto_ai.phase5.config import ThresholdConfig


@dataclass(frozen=True)
class ThresholdPolicy:
    threshold_bps: float | None
    decision: str
    calibration_trade_count: int
    calibration_score: float | None

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_bps": self.threshold_bps,
            "decision": self.decision,
            "calibration_trade_count": self.calibration_trade_count,
            "calibration_score": self.calibration_score,
        }


def _candidate_result(
    predictions: np.ndarray,
    actual: np.ndarray,
    feature_times_us: np.ndarray,
    threshold_bps: float,
    cost_bps: float,
    horizon_minutes: int,
    config: ThresholdConfig,
) -> dict[str, Any]:
    required_bps = cost_bps + threshold_bps
    eligible = np.abs(predictions) * 10_000 >= required_bps
    selected: list[int] = []
    active_until = -1
    horizon_us = horizon_minutes * 60_000_000
    for index in np.flatnonzero(eligible):
        if feature_times_us[index] < active_until:
            continue
        selected.append(int(index))
        active_until = int(feature_times_us[index]) + horizon_us
    if selected:
        positions = np.asarray(selected, dtype=np.int64)
        gross = np.sign(predictions[positions]) * actual[positions]
        net = gross - cost_bps / 10_000
        equity = np.cumprod(1.0 + net)
        with_start = np.concatenate(([1.0], equity))
        drawdown = with_start / np.maximum.accumulate(with_start) - 1.0
        expectancy = float(np.mean(net))
        maximum_drawdown = float(np.min(drawdown))
    else:
        net = np.asarray([], dtype=np.float64)
        expectancy = None
        maximum_drawdown = 0.0
    count = len(selected)
    shortage = max(0, config.minimum_calibration_trades - count)
    score = (
        None
        if expectancy is None
        else expectancy
        - config.drawdown_penalty * abs(maximum_drawdown)
        - config.low_trade_penalty * shortage / config.minimum_calibration_trades
    )
    return {
        "threshold_bps": threshold_bps,
        "required_prediction_bps": required_bps,
        "trade_count": count,
        "expectancy": expectancy,
        "maximum_drawdown": maximum_drawdown,
        "net_return": float(np.sum(net)),
        "score": score,
        "eligible": count >= config.minimum_calibration_trades,
    }


def select_threshold(
    calibrated_predictions: np.ndarray,
    actual: np.ndarray,
    feature_times_us: np.ndarray,
    config: ThresholdConfig,
    *,
    cost_bps: float,
    horizon_minutes: int,
) -> tuple[ThresholdPolicy, dict[str, Any]]:
    predicted = np.asarray(calibrated_predictions, dtype=np.float64)
    target = np.asarray(actual, dtype=np.float64)
    times = np.asarray(feature_times_us, dtype=np.int64)
    if predicted.shape != target.shape or target.shape != times.shape or predicted.ndim != 1:
        raise ValueError("threshold inputs must be matching vectors")
    if not np.all(np.isfinite(predicted)) or not np.all(np.isfinite(target)):
        raise ValueError("threshold inputs must be finite")
    results = [
        _candidate_result(
            predicted,
            target,
            times,
            value,
            cost_bps,
            horizon_minutes,
            config,
        )
        for value in config.grid_bps
    ]
    eligible = [item for item in results if item["eligible"]]
    if not eligible:
        policy = ThresholdPolicy(None, "NO_TRADE", 0, None)
    else:
        selected = max(eligible, key=lambda item: (item["score"], item["threshold_bps"]))
        policy = ThresholdPolicy(
            float(selected["threshold_bps"]),
            "TRADE",
            int(selected["trade_count"]),
            float(selected["score"]),
        )
    diagnostics = {
        "selection_source": "calibration_only",
        "cost_bps": cost_bps,
        "minimum_calibration_trades": config.minimum_calibration_trades,
        "grid": results,
        "selected": policy.to_dict(),
    }
    return policy, diagnostics
