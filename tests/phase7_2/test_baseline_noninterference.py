from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_ai.contracts.baseline import PHASE7_APPROVED_BASELINE
from crypto_ai.phase7 import (
    load_phase7_config,
    phase7_dry_run,
)
from crypto_ai.phase7 import (
    test_phase7_universe as run_universe_test,
)
from crypto_ai.phase7_2 import Phase72Config
from crypto_ai.phase7_2.config import load_phase7_2_config

ROOT = Path(__file__).resolve().parents[2]
BASELINE_MANIFEST = ROOT / "configs/contracts/phase7_scientific_baseline_v1.json"
PHASE7_2_CONFIG = ROOT / "configs/phase7_2/research_capabilities_v1.toml"


def _normalized_dry_run(payload: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(payload, default=str))
    source_contract = normalized.get("source_contract")
    if isinstance(source_contract, dict):
        source_contract.pop("verified_at", None)
    return normalized


def test_phase7_2_config_is_additive_and_disabled_by_default() -> None:
    config = load_phase7_2_config(PHASE7_2_CONFIG)
    assert config == Phase72Config()
    assert config.baseline_configuration_hash == PHASE7_APPROVED_BASELINE.configuration_hash
    assert config.baseline_feature_version == PHASE7_APPROVED_BASELINE.feature_version
    assert config.baseline_feature_count == 54
    assert config.baseline_target_version == "multiasset_targets_v2"
    assert config.baseline_decision_latency_bars == 1
    assert config.baseline_architectures == ("G0", "C0", "P0", "H0")
    assert config.baseline_fold_count == 16
    assert config.all_experiments_disabled is True
    assert config.fear_greed_training_enabled is False
    assert config.open_interest_historical_training_enabled is False
    assert config.prospective_holdout_status == "LOCKED_UNUSED"


def test_phase7_scientific_files_remain_byte_frozen_and_do_not_import_phase7_2() -> None:
    manifest = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    source_freeze = manifest["source_freeze"]
    for relative_path, expected_sha256 in source_freeze.items():
        source = (ROOT / relative_path).read_bytes()
        assert hashlib.sha256(source).hexdigest() == expected_sha256
        if relative_path.startswith("src/crypto_ai/phase7/"):
            assert b"crypto_ai.phase7_2" not in source


def test_importing_phase7_2_cannot_change_deterministic_phase7_outputs() -> None:
    config = load_phase7_config(ROOT / "configs/phase7/research_v1.toml")
    before_dry_run = _normalized_dry_run(phase7_dry_run(config))
    before_universe = run_universe_test(config)

    import crypto_ai.phase7_2 as capabilities

    assert capabilities.Phase72Config().all_experiments_disabled is True
    after_dry_run = _normalized_dry_run(phase7_dry_run(config))
    after_universe = run_universe_test(config)
    assert after_dry_run == before_dry_run
    assert after_universe == before_universe
    PHASE7_APPROVED_BASELINE.assert_dry_run(after_dry_run)
    PHASE7_APPROVED_BASELINE.assert_universe(after_universe)
