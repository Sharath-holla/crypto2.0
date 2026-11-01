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
from collections.abc import Iterable, Mapping
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


def main() -> int:
    from pathlib import Path

    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.pipeline import _load_stage_state
    from crypto_ai.phase7.segments import CausalDataGap

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    config = load_phase7_config(args.config)
    _registry, _universe, _policy, data = _load_stage_state(args.run_root)
    gaps = tuple(CausalDataGap.model_validate(item) for item in data.get("unusable_segments", []))
    plans = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    print(json.dumps(post_train_gap_readiness(plans, gaps), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
