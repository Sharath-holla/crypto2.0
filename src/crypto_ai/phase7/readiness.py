"""Pre-training readiness: which fold segments are unusable because of post-TRAIN data gaps.

``slice_multiasset_fold`` stops a fold (a data defect, never INELIGIBLE) when an active
symbol has an unusable data gap after TRAIN.  This report lists those blocked segments
*before* any paid training so an operator learns about them up front.  It is purely
informational: it never changes TRAIN membership, clusters, tiers or context, and it
never restores membership look-ahead (membership still depends on history up to the
TRAIN end only).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class _Gap(Protocol):
    symbol: str
    interval: str
    start: datetime
    end: datetime
    partition: str


class _Plan(Protocol):
    fold_id: str
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    calibration_start: datetime
    calibration_end: datetime
    test_start: datetime
    test_end: datetime


def _overlaps(gap: _Gap, start: datetime, end: datetime) -> bool:
    return (
        start < end
        and gap.start.astimezone(UTC) < end.astimezone(UTC)
        and gap.end.astimezone(UTC) > start.astimezone(UTC)
    )


def post_train_gap_readiness(
    plans: Iterable[_Plan],
    gaps: Iterable[_Gap],
    *,
    active_symbols_by_fold: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Per-fold list of non-TRAIN segments made unusable by data gaps of active symbols.

    ``active_symbols_by_fold=None`` is the conservative mode: every symbol with a gap is
    treated as active, which can only over-report blocked folds, never under-report.
    """

    gap_list = sorted(gaps, key=lambda gap: (gap.symbol, gap.start, gap.interval, gap.partition))
    folds: list[dict[str, Any]] = []
    for plan in plans:
        split = plan.calibration_start + (plan.calibration_end - plan.calibration_start) / 2
        segments = (
            ("VALIDATION", plan.validation_start, plan.validation_end),
            ("CAL_A", plan.calibration_start, split),
            ("CAL_B", split, plan.calibration_end),
            ("TEST", plan.test_start, plan.test_end),
        )
        active = (
            None
            if active_symbols_by_fold is None
            else {str(item).upper() for item in active_symbols_by_fold.get(plan.fold_id, ())}
        )
        blocked: list[dict[str, Any]] = []
        for gap in gap_list:
            if active is not None and gap.symbol.upper() not in active:
                continue
            if not _overlaps(gap, plan.train_end, plan.test_end):
                continue
            for name, start, end in segments:
                if _overlaps(gap, start, end):
                    blocked.append(
                        {
                            "segment": name,
                            "symbol": gap.symbol,
                            "interval": gap.interval,
                            "partition": gap.partition,
                            "gap_start": gap.start.astimezone(UTC).isoformat(),
                            "gap_end": gap.end.astimezone(UTC).isoformat(),
                        }
                    )
        folds.append(
            {
                "fold_id": plan.fold_id,
                "status": "BLOCKED_POST_TRAIN_GAP" if blocked else "READY",
                "blocked_segments": blocked,
                "blocked_segment_names": sorted({item["segment"] for item in blocked}),
            }
        )
    return {
        "schema": "phase7_post_train_gap_readiness_v1",
        "membership_filter": (
            "NOT_APPLIED_CONSERVATIVE" if active_symbols_by_fold is None else "FOLD_ACTIVE_SYMBOLS"
        ),
        "train_membership_effect": "NONE_REPORT_ONLY",
        "folds": folds,
        "blocked_fold_count": sum(item["status"] != "READY" for item in folds),
        "all_folds_ready": all(item["status"] == "READY" for item in folds),
    }


# CHANGED BY CLAUDE (2026-11-02, finding M-06): read-only "gap census" for every fold. It wraps
# post_train_gap_readiness, labels where the gaps came from, and adds a per-fold ``can_run``.
# When Silver stage state is unavailable it falls back to gaps OBSERVED in Gold timestamps
# and says so in the output. It never changes membership, features or any data.
@dataclass(frozen=True)
class ObservedGap:
    """A hole in a symbol's Gold timeline (an observation, not Silver quality evidence)."""

    symbol: str
    interval: str
    start: datetime
    end: datetime
    partition: str = "GOLD_OBSERVED"


def observed_gaps_from_times(
    times_by_symbol: Mapping[str, Iterable[int]],
    *,
    step_microseconds: int,
    interval: str = "5m",
) -> list[ObservedGap]:
    """Gaps between consecutive bar times (epoch microseconds) larger than one step."""

    gaps: list[ObservedGap] = []
    for symbol in sorted(times_by_symbol):
        values = sorted({int(item) for item in times_by_symbol[symbol]})
        for earlier, later in zip(values, values[1:], strict=False):
            if later - earlier > step_microseconds:
                gaps.append(
                    ObservedGap(
                        symbol=str(symbol).upper(),
                        interval=interval,
                        start=datetime.fromtimestamp((earlier + step_microseconds) / 1e6, UTC),
                        end=datetime.fromtimestamp(later / 1e6, UTC),
                    )
                )
    return gaps


def gap_census(
    plans: Iterable[_Plan],
    gaps: Iterable[_Gap],
    *,
    source: str,
    active_symbols_by_fold: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Per-fold census: which gaps exist, whether the fold can run, and where the data came from."""

    report = post_train_gap_readiness(plans, gaps, active_symbols_by_fold=active_symbols_by_fold)
    for fold in report["folds"]:
        fold["can_run"] = fold["status"] == "READY"
        fold["gap_symbols"] = sorted({item["symbol"] for item in fold["blocked_segments"]})
    report["schema"] = "phase7_gap_census_v1"
    report["source"] = source
    report["runnable_fold_count"] = sum(fold["can_run"] for fold in report["folds"])
    return report


def _gold_symbol_times(gold_root: Any) -> dict[str, Any]:
    """Distinct (symbol -> feature_time microseconds) from Gold parquet files, file by file."""

    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    collected: dict[str, list[Any]] = {}
    for path in sorted(gold_root.rglob("*.parquet")):
        table = pq.read_table(path, columns=["symbol", "feature_time"])
        frame = table.to_pandas()
        frame["feature_time"] = (
            table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
        )
        for symbol, group in frame.groupby("symbol"):
            collected.setdefault(str(symbol), []).append(
                np.unique(group["feature_time"].to_numpy())
            )
    return {symbol: np.unique(np.concatenate(parts)) for symbol, parts in collected.items()}


def main() -> int:
    from pathlib import Path

    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.pipeline import _load_stage_state
    from crypto_ai.phase7.runtime import RuntimePaths
    from crypto_ai.phase7.segments import CausalDataGap

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    config = load_phase7_config(args.config)
    plans = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    # OLD CODE (kept for reference): Silver stage state was required, so a missing Silver
    # mirror crashed the census.
    # _registry, _universe, _policy, data = _load_stage_state(args.run_root)
    # gaps = tuple(CausalDataGap.model_validate(i) for i in data.get("unusable_segments", []))
    # print(json.dumps(post_train_gap_readiness(plans, gaps), indent=2, sort_keys=True))
    try:
        _registry, _universe, _policy, data = _load_stage_state(args.run_root)
        gaps: Iterable[_Gap] = tuple(
            CausalDataGap.model_validate(item) for item in data.get("unusable_segments", [])
        )
        source = "SILVER_STAGE_STATE"
    except (OSError, KeyError, ValueError) as exc:
        print(
            "WARNING: Silver stage state unavailable "
            f"({type(exc).__name__}); running the census on Gold timestamps instead.",
            file=sys.stderr,
        )
        gold_root = RuntimePaths.resolve(config.paths).gold_root
        gaps = observed_gaps_from_times(
            _gold_symbol_times(gold_root), step_microseconds=5 * 60 * 1_000_000
        )
        source = "GOLD_OBSERVED_TIMESTAMPS (Silver unavailable; not quality evidence)"
    print(json.dumps(gap_census(plans, gaps, source=source), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
