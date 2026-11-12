"""CHANGED BY CLAUDE (2026-11-06, closure): the real frozen selection protocol and purposes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from crypto_ai.phase7.selection_chronology import (
    DESCRIPTIVE_REPORT,
    DEVELOPMENT_SELECTION,
    INDEPENDENT_EVALUATION,
    ChronologyError,
    authorize_use,
    load_protocol,
)

ROOT = Path(__file__).parents[2]
PROTOCOL_PATH = ROOT / "configs/research/phase7_selection_chronology_v1.json"
SPEC = "architecture-G0-A6-60m-raw"


@pytest.fixture(scope="module")
def protocol() -> dict:
    return load_protocol(PROTOCOL_PATH)


def test_real_protocol_is_tamper_evident_and_holdout_locked(protocol: dict) -> None:
    assert protocol["schema"] == "phase7_selection_chronology_v1"
    assert protocol["holdout"] == {
        "status": "LOCKED_UNUSED",
        "used": False,
        "evaluation_authorized": False,
    }
    forged = json.loads(PROTOCOL_PATH.read_text())
    forged["evaluation_folds"] = forged["development_folds"]
    forged_path = PROTOCOL_PATH.parent / "_forged_probe.json"
    try:
        forged_path.write_text(json.dumps(forged))
        with pytest.raises(ChronologyError, match="PROTOCOL_TAMPERED"):
            load_protocol(forged_path)
    finally:
        forged_path.unlink(missing_ok=True)


def test_real_protocol_encodes_all_five_roles_for_all_sixteen_folds(protocol: dict) -> None:
    calendar = protocol["calendar"]
    assert len(calendar) == 16
    for fold, segments in calendar.items():
        assert set(segments) == {"train", "validation", "calibration_a", "calibration_b", "test"}
        # roles tile chronologically: train -> validation -> cal-A -> cal-B -> test
        order = ["train", "validation", "calibration_a", "calibration_b", "test"]
        for left, right in zip(order, order[1:], strict=False):
            assert segments[left][1] == segments[right][0], (fold, left, right)


def test_real_protocol_records_every_kind_of_test_reuse(protocol: dict) -> None:
    reused_as = {row["reused_as"] for row in protocol["overlap_matrix"]}
    assert {"TRAIN", "VALIDATION", "CALIBRATION_A", "CALIBRATION_B"} <= reused_as
    first = protocol["development_folds"][0]
    assert any(
        r["test_of_fold"] == first and r["reused_as"] == "VALIDATION"
        for r in protocol["overlap_matrix"]
    )


def test_real_protocol_roles_and_modes(protocol: dict) -> None:
    dev, ev = protocol["development_folds"], protocol["evaluation_folds"]
    assert len(dev) == 10 and len(ev) == 6 and not set(dev) & set(ev)
    assert protocol["precommitted_specs"] == [SPEC]
    smoke = protocol["modes"]["smoke"]
    assert smoke["purpose"] == "REGRESSION_PLUMBING_AND_PIPELINE_SMOKE"
    assert smoke["scientific_claims_allowed"] == [] and smoke["backend"] == "cpu"
    assert smoke["folds"] == [sorted(protocol["calendar"])[0]]
    assert protocol["modes"]["pilot"]["default_use_of_all_16_folds"] == DESCRIPTIVE_REPORT


def test_committed_protocol_equals_the_one_generated_from_the_real_config(protocol: dict):
    cli = pytest.importorskip("crypto_ai.phase7.selection_protocol_cli")
    assert cli.build(ROOT / cli.DEFAULT_CONFIG)["protocol_sha256"] == protocol["protocol_sha256"]


def test_purposes_are_separated(protocol: dict) -> None:
    dev, ev = protocol["development_folds"], protocol["evaluation_folds"]
    everything = dev + ev
    assert authorize_use(protocol, DESCRIPTIVE_REPORT, everything)["independent"] is False
    assert authorize_use(protocol, DEVELOPMENT_SELECTION, dev)["independent"] is False
    with pytest.raises(ChronologyError, match="NOT_DEVELOPMENT_FOLDS"):
        authorize_use(protocol, DEVELOPMENT_SELECTION, everything)
    assert authorize_use(protocol, INDEPENDENT_EVALUATION, ev, spec=SPEC)["independent"] is True
    with pytest.raises(ChronologyError, match="NOT_EVALUATION_FOLDS"):
        authorize_use(protocol, INDEPENDENT_EVALUATION, everything, spec=SPEC)
    with pytest.raises(ChronologyError, match="SPEC_NOT_PRECOMMITTED"):
        authorize_use(protocol, INDEPENDENT_EVALUATION, ev, spec="architecture-G0-A6-15m-raw")
    with pytest.raises(ChronologyError, match="SPEC_NOT_PRECOMMITTED"):
        authorize_use(protocol, INDEPENDENT_EVALUATION, ev)
    with pytest.raises(ChronologyError, match="UNKNOWN_PURPOSE"):
        authorize_use(protocol, "CONFIRMED_WINNER", ev, spec=SPEC)


def test_later_validation_overlapping_earlier_test_is_not_independent_confirmation(protocol):
    """fold-000 TEST months are fold-002 VALIDATION months: a spec chosen with fold-002 cannot be
    'confirmed' by fold-000, even though rolling retraining legitimately reuses those months."""

    ids = sorted(protocol["calendar"])
    swapped = copy.deepcopy(protocol)
    swapped["development_folds"] = [ids[2]]
    swapped["evaluation_folds"] = [ids[0]]
    with pytest.raises(ChronologyError, match="EVALUATION_TEST_OVERLAPS_DEVELOPMENT"):
        authorize_use(swapped, INDEPENDENT_EVALUATION, [ids[0]], spec=SPEC)
    # the same months used DESCRIPTIVELY are allowed, labelled non-independent
    assert authorize_use(swapped, DESCRIPTIVE_REPORT, [ids[0]])["independent"] is False


@pytest.mark.parametrize("role", ["TRAIN", "CALIBRATION_A", "CALIBRATION_B"])
def test_reuse_as_train_or_calibration_also_blocks_independence(protocol, role):
    """Any development fold segment overlapping an evaluation TEST blocks independence."""

    ids = sorted(protocol["calendar"])
    rows = [r for r in protocol["overlap_matrix"] if r["reused_as"] == role]
    assert rows, f"no TEST reuse as {role} found in the real calendar"
    row = rows[0]
    swapped = copy.deepcopy(protocol)
    swapped["development_folds"] = [row["reused_by_fold"]]
    swapped["evaluation_folds"] = [row["test_of_fold"]]
    with pytest.raises(ChronologyError, match="EVALUATION_TEST_OVERLAPS_DEVELOPMENT"):
        authorize_use(swapped, INDEPENDENT_EVALUATION, [row["test_of_fold"]], spec=SPEC)
    assert ids  # calendar loaded


def test_no_generic_sort_all_folds_choose_winner_path() -> None:
    hardening = pytest.importorskip("crypto_ai.phase7.hardening")
    rows = [
        {"spec": "a", "fold_id": f"f{i}", "status": "COMPLETE", "lightgbm_skill_vs_zero": 0.1}
        for i in range(3)
    ]
    ranking = hardening.descriptive_ranking(rows)
    assert ranking["inference_status"] == "NOT_INDEPENDENT"
    assert "winner" not in ranking and "selected" not in ranking
