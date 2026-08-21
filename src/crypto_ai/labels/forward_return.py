from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.research.config import LabelConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LabelGenerationResult:
    valid_mask: np.ndarray
    feature_time_us: np.ndarray
    entry_time_us: np.ndarray
    label_end_time_us: np.ndarray
    entry_indices: np.ndarray
    target_indices: np.ndarray
    returns: np.ndarray
    reason_counts: dict[str, int]
    label_hash: str

    @property
    def valid_count(self) -> int:
        return int(np.count_nonzero(self.valid_mask))


def generate_forward_return_labels(
    candles: pa.Table,
    *,
    interval: str,
    config: LabelConfig,
) -> LabelGenerationResult:
    started = time.perf_counter()
    logger.info(
        "Label generation started",
        extra={
            "event": "label_generation_started",
            "label_version": config.version,
            "rows": candles.num_rows,
        },
    )
    n_rows = candles.num_rows
    interval_us = interval_milliseconds(interval) * 1_000
    horizon_steps = config.horizon_steps(interval)
    target_offset = horizon_steps + 1
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    opens = candles.column("open").combine_chunks().to_pylist()

    valid = np.zeros(n_rows, dtype=bool)
    feature_time = open_times + interval_us
    entry_time = np.full(n_rows, -1, dtype=np.int64)
    label_end = np.full(n_rows, -1, dtype=np.int64)
    entry_indices = np.full(n_rows, -1, dtype=np.int64)
    target_indices = np.full(n_rows, -1, dtype=np.int64)
    returns = np.full(n_rows, np.nan, dtype=np.float64)
    reasons = {"insufficient_future": 0, "gap_in_horizon": 0}

    consecutive_forward = np.zeros(n_rows, dtype=np.int64)
    for index in range(n_rows - 2, -1, -1):
        if open_times[index + 1] - open_times[index] == interval_us:
            consecutive_forward[index] = consecutive_forward[index + 1] + 1

    last_time = int(open_times[-1]) if n_rows else -1
    for index in range(n_rows):
        expected_target = int(open_times[index]) + target_offset * interval_us
        if expected_target > last_time:
            reasons["insufficient_future"] += 1
            continue
        if consecutive_forward[index] < target_offset:
            reasons["gap_in_horizon"] += 1
            continue
        entry_index = index + 1
        target_index = index + target_offset
        entry_price = opens[entry_index]
        future_price = opens[target_index]
        if entry_price <= 0 or future_price <= 0:
            reasons["gap_in_horizon"] += 1
            continue
        entry_indices[index] = entry_index
        target_indices[index] = target_index
        entry_time[index] = int(open_times[entry_index])
        label_end[index] = int(open_times[target_index])
        returns[index] = float(future_price / entry_price - Decimal(1))
        valid[index] = True

    logger.info(
        "Label generation completed",
        extra={
            "event": "label_generation_complete",
            "label_version": config.version,
            "rows": n_rows,
            "valid_rows": int(np.count_nonzero(valid)),
            "invalid_rows": int(n_rows - np.count_nonzero(valid)),
            "duration_seconds": time.perf_counter() - started,
        },
    )
    return LabelGenerationResult(
        valid_mask=valid,
        feature_time_us=feature_time,
        entry_time_us=entry_time,
        label_end_time_us=label_end,
        entry_indices=entry_indices,
        target_indices=target_indices,
        returns=returns,
        reason_counts=reasons,
        label_hash=config.config_hash,
    )
