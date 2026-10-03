from __future__ import annotations

import hashlib
import json
import subprocess
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
from crypto_ai.phase7.training import training_source_identity

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "contracts" / f"{PHASE7_APPROVED_BASELINE.baseline_id}.json"
FROZEN_SOURCE_COMMIT = "28d3098a82952a3d09073e4d81b5281f856c072e"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_machine_readable_baseline_matches_typed_contract() -> None:
    manifest = _manifest()
    scientific = manifest["scientific_contract"]
    assert isinstance(scientific, dict)
    assert manifest["baseline_id"] == PHASE7_APPROVED_BASELINE.baseline_id
    assert manifest["contract_version"] == PHASE7_APPROVED_BASELINE.contract_version
    assert scientific["configuration_hash"] == PHASE7_APPROVED_BASELINE.configuration_hash
    assert scientific["target_version"] == PHASE7_APPROVED_BASELINE.target_version
    assert scientific["decision_latency_bars"] == PHASE7_APPROVED_BASELINE.decision_latency_bars
    assert tuple(scientific["architectures"]) == PHASE7_APPROVED_BASELINE.architectures


def test_phase7_scientific_source_and_config_are_byte_frozen() -> None:
    """The v1.9 byte contract is historical evidence for the frozen Git baseline."""

    manifest = _manifest()
    source_freeze = manifest["source_freeze"]
    assert isinstance(source_freeze, dict)
    phase7_paths = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            FROZEN_SOURCE_COMMIT,
            "--",
            "src/crypto_ai/phase7",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    expected_paths = {path for path in phase7_paths if path.endswith(".py")}
    expected_paths.update(
        {
            "configs/data_quality/default.toml",
            "configs/phase7/research_v1.toml",
            "src/crypto_ai/data/binance/__init__.py",
            "src/crypto_ai/data/binance/archive.py",
            "src/crypto_ai/data/binance/client.py",
            "src/crypto_ai/data/ingestion/downloader.py",
            "src/crypto_ai/data/quality/checks.py",
            "src/crypto_ai/data/quality/engine.py",
            "src/crypto_ai/data/quality/models.py",
            "src/crypto_ai/data/quality/policy.py",
            "src/crypto_ai/data/quality/promotion.py",
            "src/crypto_ai/phase4_1/equivalence.py",
            "src/crypto_ai/phase4_1/reconcile.py",
        }
    )
    assert set(source_freeze) == expected_paths
    for relative_path, expected_sha256 in source_freeze.items():
        source = subprocess.run(
            ["git", "show", f"{FROZEN_SOURCE_COMMIT}:{relative_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        actual = hashlib.sha256(source).hexdigest()
        assert actual == expected_sha256, f"scientific baseline drift: {relative_path}"


def test_active_scientific_identity_covers_remediation_modules() -> None:
    identity = training_source_identity(ROOT)
    paths = {item["path"] for item in identity["files"]}
    assert {
        "src/crypto_ai/phase7/backend.py",
        "src/crypto_ai/phase7/gold_validation.py",
        "src/crypto_ai/phase7/models.py",
        "src/crypto_ai/phase7/prepared_cache.py",
        "src/crypto_ai/phase7/training.py",
        "src/crypto_ai/phase7/acquisition.py",
        "src/crypto_ai/phase7/quality.py",
        "src/crypto_ai/data/schema.py",
    }.issubset(paths)


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
