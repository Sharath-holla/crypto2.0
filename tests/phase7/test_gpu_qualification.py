"""GPU qualification ladder: execution success never implies equivalence or approval."""

from __future__ import annotations

import pytest

from crypto_ai.phase7.gpu_qualification import LADDER, evidence_hash, qualify_gpu

ATTESTED = {"status": "PASS", "actual_backend": "cuda"}
NUMERIC = {"status": "PASS", "scope": "PREDICTION_EQUIVALENCE_ONLY", "missing_limits": []}
POLICY = {"status": "PASS"}


def _approval(computed=True, attestation=ATTESTED, numerical=NUMERIC, policy=POLICY):
    return {
        "reviewer": "owner",
        "evidence_sha256": evidence_hash(computed, attestation, numerical, policy),
    }


def test_ladder_order_is_fixed() -> None:
    assert LADDER == (
        "COMPUTED",
        "DEVICE_ATTESTED",
        "NUMERICALLY_EQUIVALENT",
        "POLICY_EQUIVALENT",
        "APPROVED",
    )


def test_nothing_computed() -> None:
    result = qualify_gpu(computed=False)
    assert result["state"] == "NOT_COMPUTED" and not result["gpu_training_authorized"]
    assert result["baseline"] == "CPU_LIGHTGBM"


def test_computed_alone_is_not_device_attested() -> None:
    result = qualify_gpu(computed=True)
    assert result["state"] == "COMPUTED" and "DEVICE_ATTESTED" in result["blockers"]


def test_attested_but_not_equivalent() -> None:
    result = qualify_gpu(computed=True, attestation=ATTESTED)
    assert result["state"] == "DEVICE_ATTESTED"


def test_cpu_device_attestation_does_not_count() -> None:
    result = qualify_gpu(computed=True, attestation={"status": "PASS", "actual_backend": "cpu"})
    assert result["state"] == "COMPUTED"


@pytest.mark.parametrize(
    "numerical",
    [
        {"status": "REVIEW_REQUIRED", "scope": "PREDICTION_EQUIVALENCE_ONLY"},
        {"status": "FAIL", "scope": "PREDICTION_EQUIVALENCE_ONLY"},
        {"status": "PASS", "scope": "PREDICTION_EQUIVALENCE_ONLY", "missing_limits": ["x_max"]},
        {"status": "PASS", "scope": "SOMETHING_ELSE", "missing_limits": []},
    ],
)
def test_partial_or_failed_numerical_comparison_does_not_advance(numerical) -> None:
    result = qualify_gpu(computed=True, attestation=ATTESTED, numerical=numerical)
    assert result["state"] == "DEVICE_ATTESTED"


def test_numerical_without_policy_stops_at_numerical() -> None:
    result = qualify_gpu(computed=True, attestation=ATTESTED, numerical=NUMERIC)
    assert result["state"] == "NUMERICALLY_EQUIVALENT"
    assert "POLICY_EQUIVALENT" in result["blockers"]


def test_rungs_cannot_be_skipped() -> None:
    result = qualify_gpu(computed=True, numerical=NUMERIC, policy=POLICY)
    assert result["state"] == "COMPUTED"


def test_policy_equivalent_still_needs_bound_approval() -> None:
    result = qualify_gpu(computed=True, attestation=ATTESTED, numerical=NUMERIC, policy=POLICY)
    assert result["state"] == "POLICY_EQUIVALENT" and not result["gpu_training_authorized"]
    anonymous = qualify_gpu(
        computed=True,
        attestation=ATTESTED,
        numerical=NUMERIC,
        policy=POLICY,
        approval={"reviewer": " ", "evidence_sha256": result["evidence_sha256"]},
    )
    assert anonymous["state"] == "POLICY_EQUIVALENT"
    stale = qualify_gpu(
        computed=True,
        attestation=ATTESTED,
        numerical=NUMERIC,
        policy=POLICY,
        approval={"reviewer": "owner", "evidence_sha256": "0" * 64},
    )
    assert stale["state"] == "POLICY_EQUIVALENT"


def test_bound_approval_authorizes_and_changes_with_evidence() -> None:
    result = qualify_gpu(
        computed=True,
        attestation=ATTESTED,
        numerical=NUMERIC,
        policy=POLICY,
        approval=_approval(),
    )
    assert result["state"] == "APPROVED" and result["gpu_training_authorized"]
    changed = dict(NUMERIC, mean_abs_prediction_difference=1.0)
    rerun = qualify_gpu(
        computed=True,
        attestation=ATTESTED,
        numerical=changed,
        policy=POLICY,
        approval=_approval(),
    )
    assert rerun["state"] == "POLICY_EQUIVALENT"
