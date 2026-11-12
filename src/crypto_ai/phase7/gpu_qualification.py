"""Ordered GPU qualification ladder. CPU LightGBM is the scientific baseline.

A GPU result climbs one rung at a time and never skips one:

COMPUTED -> DEVICE_ATTESTED -> NUMERICALLY_EQUIVALENT -> POLICY_EQUIVALENT -> APPROVED

* COMPUTED: the fit finished on the requested backend (execution success only).
* DEVICE_ATTESTED: native fitted booster *and* live PID/GPU evidence agree.
* NUMERICALLY_EQUIVALENT: prediction comparison against the CPU baseline PASSED with the
  complete operator-approved limit set (a partial set is REVIEW_REQUIRED, not PASS).
* POLICY_EQUIVALENT: thresholds / no-trade decisions were separately shown equivalent.
* APPROVED: an explicit named-reviewer approval bound to the exact evidence hash.

Nothing here changes training behaviour; it only states what has been proven.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crypto_ai.phase7.config import stable_hash

LADDER = (
    "COMPUTED",
    "DEVICE_ATTESTED",
    "NUMERICALLY_EQUIVALENT",
    "POLICY_EQUIVALENT",
    "APPROVED",
)
BASELINE = "CPU_LIGHTGBM"


def _passed(evidence: Mapping[str, Any] | None) -> bool:
    return isinstance(evidence, Mapping) and evidence.get("status") == "PASS"


def evidence_hash(
    computed: bool,
    attestation: Mapping[str, Any] | None,
    numerical: Mapping[str, Any] | None,
    policy: Mapping[str, Any] | None,
) -> str:
    return stable_hash(
        {
            "computed": bool(computed),
            "attestation": attestation,
            "numerical": numerical,
            "policy": policy,
        },
        length=64,
    )


def qualify_gpu(
    *,
    computed: bool,
    attestation: Mapping[str, Any] | None = None,
    numerical: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the highest contiguous rung reached and why the next one is not."""

    reached: list[str] = []
    blockers: dict[str, str] = {}
    checks = (
        ("COMPUTED", bool(computed), "fit did not complete on the requested backend"),
        (
            "DEVICE_ATTESTED",
            _passed(attestation)
            and isinstance(attestation, Mapping)
            and attestation.get("actual_backend") in {"gpu", "cuda"},
            "no native-booster plus live PID/GPU attestation",
        ),
        (
            "NUMERICALLY_EQUIVALENT",
            _passed(numerical)
            and isinstance(numerical, Mapping)
            and numerical.get("scope") == "PREDICTION_EQUIVALENCE_ONLY"
            and not numerical.get("missing_limits"),
            "CPU-baseline prediction comparison is not PASS with the complete limit set",
        ),
        (
            "POLICY_EQUIVALENT",
            _passed(policy),
            "threshold/no-trade policy equivalence has not been shown",
        ),
    )
    for name, satisfied, reason in checks:
        if not satisfied:
            blockers[name] = reason
            break
        reached.append(name)
    bound = evidence_hash(computed, attestation, numerical, policy)
    if len(reached) == 4:
        approved = (
            isinstance(approval, Mapping)
            and bool(str(approval.get("reviewer", "")).strip())
            and approval.get("evidence_sha256") == bound
        )
        if approved:
            reached.append("APPROVED")
        else:
            blockers["APPROVED"] = (
                "explicit reviewer approval bound to this evidence hash is required"
            )
    return {
        "baseline": BASELINE,
        "ladder": list(LADDER),
        "state": reached[-1] if reached else "NOT_COMPUTED",
        "reached": reached,
        "blockers": blockers,
        "evidence_sha256": bound,
        "gpu_training_authorized": bool(reached) and reached[-1] == "APPROVED",
    }
