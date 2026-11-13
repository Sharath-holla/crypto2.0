"""Chronological batch-staged fold slicing for the opt-in low-memory profile.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-cloud-training-prep).

Enabled only when ``PHASE7_MEMORY_PROFILE=low_memory`` AND ``PHASE7_STAGING_DAYS=<n>`` are both
set. It produces the same ``MultiAssetFoldData`` as ``folds.slice_multiasset_fold`` followed by
``low_memory.spill_fold`` (identical rows, order, values, purge/embargo report, eligibility and
TRAIN-only metadata), but never materializes the whole fold table:

* Gold is physically ``symbol=<S>/year=<Y>`` with one row group per file, so the I/O unit is one
  calendar year of the fold window (all symbols, one horizon), read in column groups and sorted
  by ``(feature_time, symbol)`` exactly like the full read;
* inside that year, rows are processed in half-open ``[t, t + n days)`` windows aligned to
  ``plan.train_start`` (and split at year boundaries). Windows partition the timeline, so no row
  is duplicated or lost at a boundary;
* every fold-level operation applied per window is row-local or timestamp-local: symbol
  eligibility is frozen once per fold (point in time, at ``train_end``); cross-sectional context
  groups strictly by ``feature_time`` (verified in ``cross_section``), so binding a window with the
  context-source rows of the SAME window is exact; segment assignment, actual-``label_end_time``
  purge and embargo are per-row predicates against fixed fold boundaries;
* rolling features, warm-ups, lags, HTF as-of joins and labels were computed during the Gold build
  over the full history and are stored as columns; staging never recomputes them, so no lookback
  carry-over is needed and none is lost;
* each kept window is appended to a per-segment Arrow IPC file in the process spill directory;
  the files are re-opened memory-mapped at the end. Fold-level checks (minimum segment size,
  holdout, Cal-A/Cal-B separation) run on the completed segments, and the report uses the same
  structure and counts as the Phase 5 slicer.

Data identity is untouched: the full Gold manifest (every partition's SHA-256) is still verified
by ``training._load_gold_manifest`` before any staged read.
"""

from __future__ import annotations

import math
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.ipc as ipc

from crypto_ai.phase7 import low_memory

STAGING_ENV = "PHASE7_STAGING_DAYS"
SUPPORTED_STAGING_DAYS = (1, 3, 7, 14, 30)
_US = 1_000_000
_US_PER_MINUTE = 60 * _US
_SEGMENTS = ("train", "validation", "calibration_a", "calibration_b", "test")


def staging_days(environ: dict[str, str] | None = None) -> int | None:
    """Configured window in days, or None. Requires the low-memory profile."""

    env = os.environ if environ is None else environ
    value = env.get(STAGING_ENV, "").strip()
    if not value:
        return None
    if not low_memory.enabled(env):
        raise ValueError(f"{STAGING_ENV} requires PHASE7_MEMORY_PROFILE=low_memory")
    try:
        days = int(value)
    except ValueError as exc:
        raise ValueError(f"{STAGING_ENV} must be an integer number of days") from exc
    if days not in SUPPORTED_STAGING_DAYS:
        raise ValueError(f"{STAGING_ENV} must be one of {SUPPORTED_STAGING_DAYS}")
    return days


def _us(value: datetime) -> int:
    return int(value.timestamp() * _US)


def _times(table: pa.Table, column: str) -> np.ndarray:
    return table.column(column).combine_chunks().cast(pa.int64()).to_numpy()


def windows(plan: Any, window: timedelta) -> list[tuple[datetime, datetime]]:
    """Half-open windows covering [train_start, test_end), aligned to train_start, cut at years."""

    if window <= timedelta(0):
        raise ValueError("staging window must be positive")
    result: list[tuple[datetime, datetime]] = []
    start = plan.train_start
    while start < plan.test_end:
        end = min(start + window, plan.test_end)
        boundary = datetime(start.year + 1, 1, 1, tzinfo=UTC)
        if end > boundary:
            end = boundary
        result.append((start, end))
        start = end
    return result


class _SegmentWriter:
    """Append-only IPC file for one segment; empty segments still get a schema."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._sink: Any = None
        self._writer: Any = None
        self.schema: pa.Schema | None = None
        self.rows = 0

    def write(self, table: pa.Table) -> None:
        if self._writer is None:
            self.schema = table.schema
            self._sink = pa.OSFile(str(self.path), "wb")
            self._writer = ipc.new_file(self._sink, table.schema)
        elif table.schema != self.schema:
            raise RuntimeError(f"staged segment schema drifted in {self.path.name}")
        if table.num_rows:
            self._writer.write_table(table)
            self.rows += table.num_rows

    def close(self, schema: pa.Schema) -> pa.Table:
        if self._writer is None:
            self.write(schema.empty_table())
        self._writer.close()
        self._sink.close()
        with pa.memory_map(str(self.path), "r") as source, ipc.open_file(source) as reader:
            return reader.read_all()


class _Stats:
    def __init__(self) -> None:
        self.before = dict.fromkeys(_SEGMENTS, 0)
        self.purged = dict.fromkeys(_SEGMENTS, 0)
        self.embargoed = dict.fromkeys(_SEGMENTS, 0)
        self.holdout_rows = dict.fromkeys(_SEGMENTS, 0)
        self.cal_a_max_feature = -math.inf
        self.cal_a_max_label_end = -math.inf
        self.cal_b_min_feature = math.inf


def _segment_masks(
    feature: np.ndarray, label_end: np.ndarray, plan: Any, split: datetime, embargo_minutes: int
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Per segment: (raw range mask, purge keep mask, final keep mask), Phase 5 semantics."""

    embargo = embargo_minutes * _US_PER_MINUTE

    def in_range(start: datetime, end: datetime) -> np.ndarray:
        return (feature >= _us(start)) & (feature < _us(end))

    def purge(next_start: datetime) -> np.ndarray:
        return label_end < _us(next_start)

    def after_embargo(start: datetime) -> np.ndarray:
        if embargo_minutes == 0:
            return np.ones(len(feature), dtype=bool)
        return feature >= _us(start) + embargo

    raw = {
        "train": in_range(plan.train_start, plan.train_end),
        "validation": in_range(plan.validation_start, plan.validation_end),
        "calibration_a": in_range(plan.calibration_start, split),
        "calibration_b": in_range(split, plan.calibration_end),
        "test": in_range(plan.test_start, plan.test_end),
    }
    purged = {
        "train": raw["train"] & purge(plan.validation_start),
        "validation": raw["validation"] & purge(plan.calibration_start),
        "calibration_a": raw["calibration_a"] & purge(split),
        "calibration_b": raw["calibration_b"] & purge(plan.test_start),
        "test": raw["test"],
    }
    final = {
        "train": purged["train"],
        "validation": purged["validation"] & after_embargo(plan.validation_start),
        "calibration_a": purged["calibration_a"] & after_embargo(plan.calibration_start),
        "calibration_b": purged["calibration_b"] & after_embargo(split),
        "test": purged["test"] & after_embargo(plan.test_start),
    }
    return {name: (raw[name], purged[name], final[name]) for name in _SEGMENTS}


def slice_fold_staged(
    dataset: ds.Dataset,
    plan: Any,
    horizon_minutes: int,
    *,
    context_source: pa.Table,
    registry: Any,
    universe: Any,
    expansion_policy: Any,
    research_view: str,
    descriptors: list[Any],
    universe_config: Any,
    schedule: Any,
    holdout_start: datetime,
    cluster_count: int,
    seed: int,
    unusable_segments: tuple[Any, ...] = (),
    window: timedelta,
    directory: Path,
    progress: Any = None,
) -> Any:
    """Staged equivalent of ``slice_multiasset_fold`` + ``low_memory.spill_fold``."""

    from crypto_ai.phase5.folds import _utc, calibration_split_time, check_calibration_separation
    from crypto_ai.phase7.features import bind_fold_cross_sectional_context
    from crypto_ai.phase7.folds import (
        IneligibleFoldError,
        MultiAssetFoldData,
        fold_membership,
        fold_metadata,
    )

    policy, membership, eligible_symbols = fold_membership(
        plan,
        registry=registry,
        universe=universe,
        expansion_policy=expansion_policy,
        research_view=research_view,  # type: ignore[arg-type]
        descriptors=descriptors,
        universe_config=universe_config,
        unusable_segments=unusable_segments,
    )
    if not eligible_symbols:  # pragma: no cover - fold_membership raises first
        raise IneligibleFoldError(f"{plan.fold_id} has no point-in-time eligible symbols")
    holdout_start = _utc(holdout_start)
    if plan.test_end > holdout_start:
        raise ValueError("fold test period crosses the prospective holdout")
    split = calibration_split_time(plan)
    # Binding de-duplicates and orders context internally by (symbol, feature_time), so sorting
    # the (small) feature-only source once does not change any bound value.
    context = low_memory.filter_symbols(context_source, eligible_symbols).sort_by(
        [("feature_time", "ascending"), ("symbol", "ascending")]
    )
    context_times = _times(context, "feature_time")
    target = directory / f"{plan.fold_id}-staged-{uuid.uuid4().hex[:12]}"
    target.mkdir(parents=True)
    names = {"test": "_test"}
    writers = {
        name: _SegmentWriter(target / f"{names.get(name, name)}.arrow") for name in _SEGMENTS
    }
    stats = _Stats()
    schema: pa.Schema | None = None
    holdout_us = _us(holdout_start)
    eligible_rows = 0
    base = (
        (ds.field("feature_time") >= pa.scalar(plan.train_start))
        & (ds.field("feature_time") < pa.scalar(plan.test_end))
        & (ds.field("horizon_minutes") == horizon_minutes)
    )
    end_year = (plan.test_end - timedelta(microseconds=1)).year
    plan_windows = windows(plan, window)
    for year in range(plan.train_start.year, end_year + 1):
        condition = base
        if "year" in dataset.schema.names:
            condition = (ds.field("year") == year) & condition
        else:
            condition = (
                (ds.field("feature_time") >= pa.scalar(datetime(year, 1, 1, tzinfo=UTC)))
                & (ds.field("feature_time") < pa.scalar(datetime(year + 1, 1, 1, tzinfo=UTC)))
                & condition
            )
        year_table = low_memory.read_sorted_fold_rows(dataset, condition, None)
        if year_table.num_rows == 0:
            continue
        year_times = _times(year_table, "feature_time")
        for window_start, window_end in plan_windows:
            if window_start.year != year:
                continue
            lo = int(np.searchsorted(year_times, _us(window_start), side="left"))
            hi = int(np.searchsorted(year_times, _us(window_end), side="left"))
            if hi <= lo:
                continue
            rows = low_memory.filter_symbols(year_table.slice(lo, hi - lo), eligible_symbols)
            if rows.num_rows == 0:
                continue
            eligible_rows += rows.num_rows
            c_lo = int(np.searchsorted(context_times, _us(window_start), side="left"))
            c_hi = int(np.searchsorted(context_times, _us(window_end), side="left"))
            bound = bind_fold_cross_sectional_context(
                rows, context_source=context.slice(c_lo, c_hi - c_lo)
            )
            schema = bound.schema if schema is None else schema
            feature = _times(bound, "feature_time")
            label_end = _times(bound, "label_end_time")
            masks = _segment_masks(feature, label_end, plan, split, schedule.embargo_minutes)
            for name, (raw, purged, final) in masks.items():
                stats.before[name] += int(raw.sum())
                stats.purged[name] += int(raw.sum() - purged.sum())
                stats.embargoed[name] += int(purged.sum() - final.sum())
                if not final.any():
                    continue
                kept = low_memory.filter_rows(bound, final)
                stats.holdout_rows[name] += int(np.count_nonzero(feature[final] >= holdout_us))
                if name == "calibration_a":
                    stats.cal_a_max_feature = max(stats.cal_a_max_feature, feature[final].max())
                    stats.cal_a_max_label_end = max(
                        stats.cal_a_max_label_end, label_end[final].max()
                    )
                if name == "calibration_b":
                    stats.cal_b_min_feature = min(stats.cal_b_min_feature, feature[final].min())
                writers[name].write(low_memory.compact_variable_width(kept))
            if progress is not None:
                progress(window_start, window_end, rows.num_rows)
            del rows, bound
        del year_table
        low_memory.release_unused_memory()
    if eligible_rows == 0 or schema is None:
        raise ValueError(
            f"{plan.fold_id} has point-in-time eligible symbols but zero rows "
            "in the fold table; Gold coverage defect, not an INELIGIBLE outcome"
        )
    segments = {name: writer.close(schema) for name, writer in writers.items()}
    too_small = {
        name: segment.num_rows
        for name, segment in segments.items()
        if segment.num_rows < schedule.minimum_rows_per_segment
    }
    if too_small:
        raise ValueError(f"{plan.fold_id} has undersized hardened segments: {too_small}")
    for name in _SEGMENTS:
        if stats.holdout_rows[name]:
            raise ValueError(f"{name} contains prospective holdout rows")
    check_calibration_separation(segments["calibration_a"], segments["calibration_b"])

    def entry(name: str, start: datetime, end: datetime, embargo: bool) -> dict[str, Any]:
        return {
            "range": [start.isoformat(), end.isoformat()],
            "before": stats.before[name],
            "purged": stats.purged[name] if name != "test" else 0,
            "embargoed": stats.embargoed[name] if embargo else 0,
            "remaining": segments[name].num_rows,
        }

    report = {
        "fold_id": plan.fold_id,
        "boundaries": plan.to_dict(),
        "calibration_split_time": split.isoformat(),
        "embargo_minutes": schedule.embargo_minutes,
        "segments": {
            "train": entry("train", plan.train_start, plan.train_end, False),
            "validation": entry("validation", plan.validation_start, plan.validation_end, True),
            "calibration_a": entry("calibration_a", plan.calibration_start, split, True),
            "calibration_b": entry("calibration_b", split, plan.calibration_end, True),
            "test": entry("test", plan.test_start, plan.test_end, True),
        },
    }
    metadata = fold_metadata(
        plan,
        policy=policy,
        membership=membership,
        eligible_symbols=eligible_symbols,
        universe=universe,
        research_view=research_view,  # type: ignore[arg-type]
        descriptors=descriptors,
        cluster_count=cluster_count,
        seed=seed,
        unusable_segments=unusable_segments,
    )
    return MultiAssetFoldData(
        plan=plan,
        train=segments["train"],
        validation=segments["validation"],
        calibration_a=segments["calibration_a"],
        calibration_b=segments["calibration_b"],
        _test=segments["test"],
        eligibility_manifest=metadata["eligibility_manifest"],
        cluster_mapping=metadata["clusters"],
        liquidity_tiers=metadata["liquidity"],
        age_buckets=metadata["age_buckets"],
        research_view=research_view,
        report=report,
    )
