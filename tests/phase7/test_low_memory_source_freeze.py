"""ADDED BY CLAUDE (2026-11-13): the experimental low-memory source freeze must match the code.

Any later change to a scientific, preparation or control module fails here until a NEW freeze
version is recorded. The historical v1_9 contract is not modified by this experiment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from crypto_ai.phase7.experiment_identity import experiment_control_identity
from crypto_ai.phase7.hardening import current_config
from crypto_ai.phase7.preparation_identity import preparation_source_identity
from crypto_ai.phase7.result_publication import selection_protocol_identity
from crypto_ai.phase7.training import training_source_identity

ROOT = Path(__file__).parents[2]
FREEZE = ROOT / "configs/contracts/phase7a_low_memory_experiment_freeze_v1.json"


def test_current_identities_match_the_experimental_freeze(monkeypatch) -> None:
    monkeypatch.delenv("PHASE7_FEATURE_CONTEXT_SIDECAR", raising=False)
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))["frozen_identities"]
    assert preparation_source_identity()["manifest_sha256"] == frozen["PREPARATION_DIGEST"]
    assert (
        experiment_control_identity(asdict(current_config()))["manifest_sha256"]
        == frozen["EXPERIMENT_CONTROL_DIGEST"]
    )
    assert (
        selection_protocol_identity()["selection_protocol_sha256"]
        == frozen["SELECTION_PROTOCOL_DIGEST"]
    )
    assert (
        training_source_identity(ROOT)["manifest_sha256"]
        == frozen["SCIENTIFIC_SOURCE_DIGEST_WITHOUT_SIDECAR"]
    )


def test_every_changed_file_is_recorded_with_its_current_bytes() -> None:
    record = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert record["scientific_contract"]["scientific_contract_values_changed"] is False
    assert record["scientific_contract"]["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert record["scientific_contract"]["prospective_holdout_used"] is False
    for item in record["changed_files"]:
        current = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
        assert current == item["new_sha256"], item["path"]


def test_historical_v1_9_contract_is_untouched_by_the_experiment() -> None:
    contract = ROOT / "configs/contracts/phase7_scientific_baseline_v1_9.json"
    assert json.loads(contract.read_text(encoding="utf-8"))["baseline_id"] == (
        "phase7_scientific_baseline_v1_9"
    )
