"""Fold calendar, overlap matrix and the frozen selection protocol (IA-03).

CHANGED BY CLAUDE (2026-11-06, final architecture repair) - new file, standard library only.

Rolling folds reuse calendar time under different roles: fold 0's TEST months are fold 2's
VALIDATION months. A helper that ranks specs on ALL folds' validation scores and then reports the
winner's historical TEST path therefore consumes earlier TEST outcomes as later development
information. This module (a) maps every reuse, and (b) defines an immutable protocol:
development folds choose; evaluation folds only evaluate and must lie strictly after all
development data. The protocol is hashed; changing roles after seeing results changes the hash.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

# CHANGED BY CLAUDE (2026-11-06, closure): Cal-A and Cal-B are explicit roles. OLD CODE (kept):
# SEGMENTS = ("train", "validation", "calibration", "test")
SEGMENTS = ("train", "validation", "calibration_a", "calibration_b", "test")
_COARSE_SEGMENT = "calibration"  # legacy calendars that only carry the undivided window
DESCRIPTIVE_REPORT = "DESCRIPTIVE_REPORT"
DEVELOPMENT_SELECTION = "DEVELOPMENT_SELECTION"
INDEPENDENT_EVALUATION = "INDEPENDENT_EVALUATION"
PURPOSES = (DESCRIPTIVE_REPORT, DEVELOPMENT_SELECTION, INDEPENDENT_EVALUATION)
SELECTION_ELIGIBLE_RANKING = "SELECTION_ELIGIBLE_RANKING"
DESCRIPTIVE_RANKING = "DESCRIPTIVE_RANKING"
PROTOCOL_SCHEMA = "phase7_selection_chronology_v1"


class ChronologyError(ValueError):
    """The selection protocol or a selection request violates chronological roles."""


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def fold_calendar(plans: Iterable[Any]) -> dict[str, dict[str, tuple[str, str]]]:
    """fold_id -> segment -> (start, end) ISO strings, from FoldPlan-like objects.

    Cal-A / Cal-B use the SAME midpoint rule as ``phase5.folds.calibration_split_time``.
    """

    calendar: dict[str, dict[str, tuple[str, str]]] = {}
    for plan in plans:
        midpoint = plan.calibration_start + (plan.calibration_end - plan.calibration_start) / 2
        calendar[str(plan.fold_id)] = {
            "train": (_iso(plan.train_start), _iso(plan.train_end)),
            "validation": (_iso(plan.validation_start), _iso(plan.validation_end)),
            "calibration_a": (_iso(plan.calibration_start), _iso(midpoint)),
            "calibration_b": (_iso(midpoint), _iso(plan.calibration_end)),
            "test": (_iso(plan.test_start), _iso(plan.test_end)),
        }
    return calendar


def _roles(segments: Mapping[str, Any]) -> list[str]:
    """Roles present in one fold entry; the coarse window is skipped when A/B are given."""

    roles = [name for name in SEGMENTS if name in segments]
    if _COARSE_SEGMENT in segments and "calibration_a" not in segments:
        roles.append(_COARSE_SEGMENT)
    return roles


def _overlap(left: tuple[str, str], right: tuple[str, str]) -> bool:
    return datetime.fromisoformat(left[0]) < datetime.fromisoformat(right[1]) and (
        datetime.fromisoformat(right[0]) < datetime.fromisoformat(left[1])
    )


def overlap_matrix(calendar: Mapping[str, Mapping[str, tuple[str, str]]]) -> list[dict[str, Any]]:
    """Every case where fold A's TEST window is reused by fold B in any role."""

    rows: list[dict[str, Any]] = []
    for a, segments_a in calendar.items():
        for b, segments_b in calendar.items():
            if a == b:
                continue
            for segment in _roles(segments_b):
                if _overlap(segments_a["test"], segments_b[segment]):
                    rows.append(
                        {
                            "test_of_fold": a,
                            "reused_by_fold": b,
                            "reused_as": segment.upper(),
                            "test_window": list(segments_a["test"]),
                            "reuse_window": list(segments_b[segment]),
                        }
                    )
    return rows


def build_selection_protocol(
    calendar: Mapping[str, Mapping[str, tuple[str, str]]],
    *,
    development_fold_ids: Sequence[str],
    evaluation_fold_ids: Sequence[str],
    selection_policy_version: str,
    registered_trial_ids: Sequence[str] = (),
    precommitted_specs: Sequence[str] = (),
    modes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and freeze the roles. Evaluation TEST must start at/after every development end."""

    dev, ev = [str(x) for x in development_fold_ids], [str(x) for x in evaluation_fold_ids]
    unknown = sorted((set(dev) | set(ev)) - set(calendar))
    if unknown or not dev or not ev:
        raise ChronologyError(f"UNKNOWN_OR_EMPTY_ROLES: {unknown}")
    if set(dev) & set(ev):
        raise ChronologyError(f"ROLE_CONFLICT: folds in both roles: {sorted(set(dev) & set(ev))}")
    dev_end = max(datetime.fromisoformat(calendar[f]["test"][1]) for f in dev)
    for fold in ev:
        if datetime.fromisoformat(calendar[fold]["test"][0]) < dev_end:
            raise ChronologyError(
                f"EVALUATION_NOT_AFTER_DEVELOPMENT: {fold} TEST starts before development data end"
            )
    body = {
        "schema": PROTOCOL_SCHEMA,
        "selection_policy_version": selection_policy_version,
        "development_folds": sorted(dev),
        "evaluation_folds": sorted(ev),
        "development_data_end": dev_end.isoformat(),
        "allowed": {
            "development_folds": "fit, early stopping, comparison and predeclared selection",
            "evaluation_folds": "evaluate the ALREADY CHOSEN spec once; never used to choose",
        },
        "forbidden": [
            "reinterpreting fold roles after seeing results",
            "ranking specs with evaluation-fold metrics",
            "using any fold whose TEST overlaps another fold's validation as independent evidence",
            "August 2026 holdout (LOCKED_UNUSED) and July 2026 (unused)",
        ],
        "registered_trial_ids": sorted(registered_trial_ids),
        # CHANGED BY CLAUDE (2026-11-06, closure): the real calendar, every reuse, and the specs
        # that may be INDEPENDENTLY evaluated (declared before any result exists).
        "calendar": {fold: {k: list(v) for k, v in seg.items()} for fold, seg in calendar.items()},
        "overlap_matrix": overlap_matrix(calendar),
        "precommitted_specs": sorted(precommitted_specs),
        "modes": dict(modes or {}),
        "purposes": {
            DESCRIPTIVE_REPORT: "any completed fold; never independent evidence",
            DEVELOPMENT_SELECTION: "development folds only",
            INDEPENDENT_EVALUATION: "evaluation folds only, precommitted specs only, and the "
            "TEST window must not overlap any segment of any development fold",
        },
        "holdout": {"status": "LOCKED_UNUSED", "used": False, "evaluation_authorized": False},
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {**body, "protocol_sha256": digest}


def write_protocol(path: Path, protocol: Mapping[str, Any]) -> Path:
    """Write once. A second write with different content is refused (roles are immutable)."""

    if path.exists():
        existing = json.loads(path.read_text())
        if existing.get("protocol_sha256") != protocol.get("protocol_sha256"):
            raise ChronologyError("PROTOCOL_IMMUTABLE: refusing to overwrite different roles")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(protocol, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return path


def load_protocol(path: Path) -> dict[str, Any]:
    protocol = json.loads(path.read_text())
    body = {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != protocol.get(
        "protocol_sha256"
    ):
        raise ChronologyError("PROTOCOL_TAMPERED: stored hash does not match content")
    return protocol


def assert_rows_selection_eligible(
    rows: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]
) -> None:
    """A selector may only see development folds, and only registered ones."""

    allowed = set(protocol["development_folds"])
    evaluation = set(protocol["evaluation_folds"])
    for row in rows:
        fold = str(row.get("fold_id"))
        if fold in evaluation:
            raise ChronologyError(f"EVALUATION_FOLD_IN_SELECTION: {fold}")
        if fold not in allowed:
            raise ChronologyError(f"FOLD_NOT_IN_PROTOCOL: {fold}")


def authorize_use(
    protocol: Mapping[str, Any],
    purpose: str,
    fold_ids: Sequence[str],
    *,
    spec: str | None = None,
) -> dict[str, Any]:
    """Decide whether a set of fold results may be used for ``purpose``; raise otherwise.

    DESCRIPTIVE_REPORT   any folds in the protocol; the label is never independent evidence.
    DEVELOPMENT_SELECTION  development folds only.
    INDEPENDENT_EVALUATION evaluation folds only, for a spec precommitted in the protocol, and
        each evaluation TEST window must not overlap ANY segment (train/validation/cal-A/cal-B/
        test) of ANY development fold - otherwise a model chosen with that information cannot be
        confirmed by it, even if rolling retraining legitimately reuses the months.
    """

    if purpose not in PURPOSES:
        raise ChronologyError(f"UNKNOWN_PURPOSE: {purpose}")
    folds = [str(item) for item in fold_ids]
    calendar = protocol["calendar"]
    unknown = sorted(set(folds) - set(calendar))
    if not folds or unknown:
        raise ChronologyError(f"UNKNOWN_OR_EMPTY_FOLDS: {unknown}")
    development, evaluation = set(protocol["development_folds"]), set(protocol["evaluation_folds"])
    if purpose == DESCRIPTIVE_REPORT:
        return {"purpose": purpose, "independent": False, "folds": sorted(folds)}
    if purpose == DEVELOPMENT_SELECTION:
        bad = sorted(set(folds) - development)
        if bad:
            raise ChronologyError(f"NOT_DEVELOPMENT_FOLDS: {bad}")
        return {"purpose": purpose, "independent": False, "folds": sorted(folds)}
    bad = sorted(set(folds) - evaluation)
    if bad:
        raise ChronologyError(f"NOT_EVALUATION_FOLDS: {bad}")
    if spec is None or spec not in set(protocol.get("precommitted_specs", [])):
        raise ChronologyError(f"SPEC_NOT_PRECOMMITTED: {spec!r}")
    for fold in folds:
        test_window = tuple(calendar[fold]["test"])
        for dev_fold in sorted(development):
            for role in _roles(calendar[dev_fold]):
                if _overlap(test_window, tuple(calendar[dev_fold][role])):
                    raise ChronologyError(
                        f"EVALUATION_TEST_OVERLAPS_DEVELOPMENT: {fold} TEST overlaps "
                        f"{dev_fold} {role.upper()}"
                    )
    return {"purpose": purpose, "independent": True, "folds": sorted(folds), "spec": spec}
