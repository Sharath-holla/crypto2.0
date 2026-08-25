from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_ai.contracts.baseline import PHASE7_APPROVED_BASELINE
from crypto_ai.phase7 import (
    load_phase7_config,
    phase7_dry_run,
    phase7_plan,
    validate_phase7_configuration,
)
from crypto_ai.phase7 import (
    test_phase7_universe as run_universe_test,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "contracts" / "phase7_scientific_baseline_v1.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_machine_readable_baseline_matches_typed_contract() -> None:
    manifest = _manifest()
    scientific = manifest["scientific_contract"]
    assert isinstance(scientific, dict)
    assert manifest["baseline_id"] == PHASE7_APPROVED_BASELINE.baseline_id
    assert scientific["configuration_hash"] == PHASE7_APPROVED_BASELINE.configuration_hash
    assert scientific["target_version"] == PHASE7_APPROVED_BASELINE.target_version
    assert scientific["decision_latency_bars"] == PHASE7_APPROVED_BASELINE.decision_latency_bars
    assert tuple(scientific["architectures"]) == PHASE7_APPROVED_BASELINE.architectures


def test_phase7_scientific_source_and_config_are_byte_frozen() -> None:
    manifest = _manifest()
    source_freeze = manifest["source_freeze"]
    assert isinstance(source_freeze, dict)
    expected_paths = {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "src/crypto_ai/phase7").glob("*.py")
    }
    expected_paths.add("configs/phase7/research_v1.toml")
    assert set(source_freeze) == expected_paths
    for relative_path, expected_sha256 in source_freeze.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert actual == expected_sha256, f"scientific baseline drift: {relative_path}"


def test_phase7_scientific_modules_do_not_depend_on_future_contract_package() -> None:
    for path in (ROOT / "src/crypto_ai/phase7").glob("*.py"):
        assert "crypto_ai.contracts" not in path.read_text(encoding="utf-8")


def test_safe_phase7_outputs_match_frozen_contract() -> None:
    config = load_phase7_config(ROOT / "configs/phase7/research_v1.toml")
    PHASE7_APPROVED_BASELINE.assert_validation(validate_phase7_configuration(config))
    PHASE7_APPROVED_BASELINE.assert_plan(phase7_plan(config))
    PHASE7_APPROVED_BASELINE.assert_dry_run(phase7_dry_run(config))
    PHASE7_APPROVED_BASELINE.assert_universe(run_universe_test(config))


def test_fingerprint_manifest_records_reviewer_accepted_canonical_v1() -> None:
    fingerprint = _manifest()["artifact_fingerprint"]
    assert isinstance(fingerprint, dict)
    assert fingerprint["algorithm"] == "artifact_fingerprint_v1"
    combined = fingerprint["combined"]
    assert isinstance(combined, dict)
    assert combined == {
        "byte_count": 2_875_078_792,
        "file_count": 18_885,
        "sha256": "ad44fe62a5bae2df4c9b21f3d39f02b2141fe4dd6db7db022bb3fe6ee62103f1",
    }
