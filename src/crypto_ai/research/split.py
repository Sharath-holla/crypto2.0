from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pyarrow as pa

from crypto_ai.research.config import SplitConfig

logger = logging.getLogger(__name__)


def _to_us(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value.astimezone(UTC) - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _iso_from_us(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    train: pa.Table
    validation: pa.Table
    test: pa.Table
    validation_start_us: int
    test_start_us: int
    purged_train_rows: int
    purged_validation_rows: int

    def metadata(self) -> dict[str, object]:
        return {
            "validation_start": _iso_from_us(self.validation_start_us),
            "test_start": _iso_from_us(self.test_start_us),
            "train_rows": self.train.num_rows,
            "validation_rows": self.validation.num_rows,
            "test_rows": self.test.num_rows,
            "purged_train_rows": self.purged_train_rows,
            "purged_validation_rows": self.purged_validation_rows,
            "train_period": _period(self.train),
            "validation_period": _period(self.validation),
            "test_period": _period(self.test),
        }


def _period(table: pa.Table) -> dict[str, str | None]:
    if table.num_rows == 0:
        return {"start": None, "end": None}
    values = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    return {"start": _iso_from_us(int(values[0])), "end": _iso_from_us(int(values[-1]))}


def chronological_purged_split(table: pa.Table, config: SplitConfig) -> TemporalSplit:
    if table.num_rows < config.minimum_rows_per_split * 3:
        raise ValueError(
            f"Gold dataset has {table.num_rows} rows; at least "
            f"{config.minimum_rows_per_split * 3} are required"
        )
    feature_time = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    entry_time = table.column("entry_time").combine_chunks().cast(pa.int64()).to_numpy()
    label_end = table.column("label_end_time").combine_chunks().cast(pa.int64()).to_numpy()
    if np.any(np.diff(feature_time) <= 0):
        raise ValueError("Gold rows must be strictly chronological")
    if np.any(feature_time > entry_time) or np.any(entry_time >= label_end):
        raise ValueError("Sample timestamp semantics are invalid")

    if config.validation_start is not None:
        validation_start = _to_us(config.validation_start)
        test_start = _to_us(config.test_start)
    else:
        validation_index = int(table.num_rows * config.train_fraction)
        test_index = int(table.num_rows * (config.train_fraction + config.validation_fraction))
        if validation_index <= 0 or test_index <= validation_index or test_index >= table.num_rows:
            raise ValueError("Split fractions produce an empty raw split")
        validation_start = int(feature_time[validation_index])
        test_start = int(feature_time[test_index])

    raw_train = feature_time < validation_start
    raw_validation = (feature_time >= validation_start) & (feature_time < test_start)
    test_mask = feature_time >= test_start
    train_mask = raw_train & (label_end < validation_start)
    validation_mask = raw_validation & (label_end < test_start)
    purged_train = int(np.count_nonzero(raw_train & ~train_mask))
    purged_validation = int(np.count_nonzero(raw_validation & ~validation_mask))

    def select(mask: np.ndarray) -> pa.Table:
        return table.filter(pa.array(mask))

    split = TemporalSplit(
        train=select(train_mask),
        validation=select(validation_mask),
        test=select(test_mask),
        validation_start_us=validation_start,
        test_start_us=test_start,
        purged_train_rows=purged_train,
        purged_validation_rows=purged_validation,
    )
    for name, subset in (
        ("train", split.train),
        ("validation", split.validation),
        ("test", split.test),
    ):
        if subset.num_rows < config.minimum_rows_per_split:
            raise ValueError(
                f"{name} contains {subset.num_rows} rows after boundary purge; "
                f"minimum is {config.minimum_rows_per_split}"
            )
    logger.info(
        "Chronological split created",
        extra={"event": "split_created", **split.metadata()},
    )
    return split
