"""Canonical result identity and fail-closed aggregation (IA-01, IA-02).

CHANGED BY CLAUDE (2026-11-06, final architecture repair) - new file, standard library only.

Why this exists: the earlier ranking/success helpers counted every CSV row, so ten copies of one
fold passed "10 folds", and they presented validation-set p-values (the same validation rows that
stop the estimator early) as statistical evidence. This module defines ONE canonical result
key, refuses duplicates / missing folds / mixed experiments, and names the evidence classes so a
development number can never be labelled independent confirmation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# ---- evidence terminology (use these strings in every report) -------------------------------
DEVELOPMENT_METRIC = "DEVELOPMENT_METRIC"  # validation: used for early stopping / debugging
SELECTION_METRIC = "SELECTION_METRIC"  # predeclared comparison on registered development folds
INDEPENDENT_EVALUATION_METRIC = "INDEPENDENT_EVALUATION_METRIC"  # chronologically after selection

# ---- inference status (never a p-value from development data) --------------------------------
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_INDEPENDENT = "NOT_INDEPENDENT"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"

CANONICAL_KEY_FIELDS = (
    "run_id",
    "spec",
    "fold_id",
    "seed",
    "architecture",
    "horizon_minutes",
    "target_type",
    "feature_set",
    "gold_dataset_id",
    "configuration_hash",
    "scientific_code_identity",
    "backend",
)
# Fields whose value must be identical across every row of one qualifying experiment.
UNIFORM_FIELDS = (
    "run_id",
    "seed",
    "gold_dataset_id",
    "configuration_hash",
    "scientific_code_identity",
    "hardening_identity",
    "baseline_contract_version",
    "backend",
)
MINIMAL_KEY_FIELDS = ("run_id", "spec", "fold_id")


class ResultIntegrityError(ValueError):
    """A result set cannot be aggregated: duplicate, missing, mixed or unidentified rows."""


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def canonical_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    """The full canonical identity of one fold/spec result; missing fields are an error."""

    missing = [name for name in CANONICAL_KEY_FIELDS if _blank(row.get(name))]
    if missing:
        raise ResultIntegrityError(f"MISSING_IDENTITY_FIELDS: {missing}")
    return tuple(str(row[name]) for name in CANONICAL_KEY_FIELDS)


def minimal_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Key available on legacy rows; duplicates under it are always rejected."""

    return tuple("" if _blank(row.get(name)) else str(row[name]) for name in MINIMAL_KEY_FIELDS)


def reject_duplicates(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return the rows unchanged, or raise if any (run, spec, fold) appears twice.

    Duplicates are never averaged or collapsed: an identical replay and a conflicting rerun are both
    reported, because either one means the aggregation input is not a clean ledger.
    """

    seen: dict[tuple[str, ...], int] = {}
    ordered = list(rows)
    for index, row in enumerate(ordered):
        key = minimal_key(row)
        if key in seen:
            raise ResultIntegrityError(
                f"DUPLICATE_RESULT: rows {seen[key]} and {index} share (run, spec, fold)={key}"
            )
        seen[key] = index
    return ordered


def validate_result_set(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_fold_ids: Sequence[str] | None = None,
    require_complete_status: bool = True,
    strict_identity: bool = True,
) -> list[Mapping[str, Any]]:
    """Fail-closed validation for any aggregation that can say a spec "qualifies".

    Rejects: duplicate canonical keys, missing identity fields (strict), mixed dataset / config /
    source / hardening / backend / seed identities, non-COMPLETE rows, and any spec whose fold set
    differs from ``expected_fold_ids`` (missing or extra folds).
    """

    ordered = reject_duplicates(rows)
    if not ordered:
        raise ResultIntegrityError("EMPTY_RESULT_SET")
    if require_complete_status:
        bad = [r.get("status") for r in ordered if str(r.get("status")) != "COMPLETE"]
        if bad:
            raise ResultIntegrityError(f"NON_COMPLETE_ROWS: statuses={sorted(set(map(str, bad)))}")
    if strict_identity:
        keys = [canonical_key(row) for row in ordered]
        if len(keys) != len(set(keys)):
            raise ResultIntegrityError("DUPLICATE_CANONICAL_KEY")
        for field in UNIFORM_FIELDS:
            values = {None if _blank(r.get(field)) else str(r[field]) for r in ordered}
            if None in values:
                raise ResultIntegrityError(f"MISSING_IDENTITY_FIELDS: ['{field}']")
            if len(values) > 1:
                raise ResultIntegrityError(f"MIXED_IDENTITY: {field} has {len(values)} values")
    if expected_fold_ids is not None:
        expected = {str(item) for item in expected_fold_ids}
        by_spec: dict[str, set[str]] = {}
        for row in ordered:
            by_spec.setdefault(str(row.get("spec")), set()).add(str(row.get("fold_id")))
        for spec, folds in sorted(by_spec.items()):
            if folds != expected:
                raise ResultIntegrityError(
                    f"FOLD_SET_MISMATCH: spec={spec} missing={sorted(expected - folds)} "
                    f"extra={sorted(folds - expected)}"
                )
    return ordered
