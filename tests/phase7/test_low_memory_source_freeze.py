"""ADDED BY CLAUDE (2026-11-13): experimental low-memory source freezes.

* v1 (commit 2da4a74) is historical: its record is never edited, and every recorded file hash
  must equal that file's bytes AT that commit (like the v1_9 historical anchor).
* v2 is current: identities and changed-file hashes must match the working tree, so any later
  change to a scientific, preparation or control module fails here until a v3 is recorded.
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
from tests.historical_source import historical_blob

ROOT = Path(__file__).parents[2]
CONTRACTS = ROOT / "configs/contracts"
V1 = CONTRACTS / "phase7a_low_memory_experiment_freeze_v1.json"
V2 = CONTRACTS / "phase7a_low_memory_experiment_freeze_v2.json"
V3 = CONTRACTS / "phase7a_low_memory_experiment_freeze_v3.json"
V2_COMMIT = "57f702e"
V1_COMMIT = "2da4a749b9b7c0299d90166264d8f289c57dec3a"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_record_is_unchanged_since_its_commit() -> None:
    historical = historical_blob(ROOT, V1_COMMIT, str(V1.relative_to(ROOT)))
    assert V1.read_bytes() == historical


def test_v1_file_hashes_match_the_v1_commit() -> None:
    for item in _load(V1)["changed_files"]:
        source = historical_blob(ROOT, V1_COMMIT, item["path"])
        assert hashlib.sha256(source).hexdigest() == item["new_sha256"], item["path"]


def test_v2_record_and_files_are_anchored_to_their_commit() -> None:
    assert V2.read_bytes() == historical_blob(ROOT, V2_COMMIT, str(V2.relative_to(ROOT)))
    for item in _load(V2)["changed_files"]:
        source = historical_blob(ROOT, V2_COMMIT, item["path"])
        assert hashlib.sha256(source).hexdigest() == item["new_sha256"], item["path"]


def test_current_identities_match_the_v3_freeze(monkeypatch) -> None:
    monkeypatch.delenv("PHASE7_FEATURE_CONTEXT_SIDECAR", raising=False)
    frozen = _load(V3)["frozen_identities"]
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


def test_v2_predecessor_is_v1() -> None:
    record = _load(V2)
    assert record["predecessor"]["commit"] == V1_COMMIT
    assert record["predecessor"]["frozen_identities"] == _load(V1)["frozen_identities"]


def test_v3_changed_files_record_current_bytes_and_scope() -> None:
    from crypto_ai.phase7.run_contract import LOW_MEMORY_FOLD0_SCOPE_V3

    record = _load(V3)
    assert record["predecessor"]["frozen_identities"] == _load(V2)["frozen_identities"]
    assert record["unchanged_by_v3"]["PREPARATION_DIGEST"] is True
    assert record["unchanged_by_v3"]["SCIENTIFIC_SOURCE_DIGEST_WITHOUT_SIDECAR"] is True
    assert set(record["approved_scope_v3"]["specs"]) == set(LOW_MEMORY_FOLD0_SCOPE_V3)
    assert record["scientific_contract"]["scientific_contract_values_changed"] is False
    assert record["scientific_contract"]["prospective_holdout_status"] == "LOCKED_UNUSED"
    for item in record["changed_files"]:
        current = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
        assert current == item["new_sha256"], item["path"]
        assert item["change"]


def test_historical_v1_9_contract_is_untouched() -> None:
    contract = _load(CONTRACTS / "phase7_scientific_baseline_v1_9.json")
    assert contract["baseline_id"] == "phase7_scientific_baseline_v1_9"
