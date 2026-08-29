from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class BaselineViolation(AssertionError):
    """Raised when a safe Phase 7 result differs from the approved baseline."""


@dataclass(frozen=True, slots=True)
class ArtifactRootBaseline:
    root: str
    file_count: int
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Phase7ScientificBaseline:
    baseline_id: str
    contract_version: str
    phase7_version: str
    configuration_hash: str
    feature_version: str
    market_context_version: str
    target_version: str
    decision_latency_bars: int
    architectures: tuple[str, ...]
    core_universe_version: str
    expansion_universe_version: str
    research_cutoff_exclusive: datetime
    prospective_holdout_start: datetime
    prospective_holdout_status: str
    artifact_roots: tuple[ArtifactRootBaseline, ...]
    combined_artifact_sha256: str

    def _common(self, payload: dict[str, Any]) -> None:
        expected = {
            "configuration_hash": self.configuration_hash,
            "target_version": self.target_version,
            "target_decision_latency_bars": self.decision_latency_bars,
            "research_cutoff_exclusive": self.research_cutoff_exclusive.isoformat(),
            "prospective_holdout_start": self.prospective_holdout_start.isoformat(),
            "prospective_holdout_status": self.prospective_holdout_status,
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
            "july_2026_used": False,
            "private_api_used": False,
        }
        differences = {
            key: (payload.get(key), value)
            for key, value in expected.items()
            if payload.get(key) != value
        }
        if differences:
            raise BaselineViolation(f"Phase 7 common baseline mismatch: {differences}")

    def assert_validation(self, payload: dict[str, Any]) -> None:
        self._common(payload)
        if payload.get("status") != "VALID" or payload.get("qualified_model") != "NONE":
            raise BaselineViolation("Phase 7 validation status or qualification changed")

    def assert_plan(self, payload: dict[str, Any]) -> None:
        self._common(payload)
        expected = {
            "architectures": list(self.architectures),
            "calendar_fold_count": 16,
            "core_universe_version": self.core_universe_version,
            "expansion_universe_version": self.expansion_universe_version,
            "target_horizons_minutes": [15, 30, 60, 120],
            "research_views": ["CORE", "EXPANDING"],
            "network_used": False,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise BaselineViolation("Phase 7 plan differs from the approved scientific baseline")

    def assert_dry_run(self, payload: dict[str, Any]) -> None:
        self._common(payload)
        expected = {
            "status": "PASS",
            "feature_count": 54,
            "feature_rows": 2880,
            "target_rows": 11308,
            "files_written": 0,
            "network_used": False,
            "heavy_training_executed": False,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise BaselineViolation("Phase 7 dry run differs from the approved scientific baseline")

    def assert_universe(self, payload: dict[str, Any]) -> None:
        expected = {
            "status": "PASS",
            "core_universe_version": self.core_universe_version,
            "expansion_universe_version": self.expansion_universe_version,
            "future_descriptor_perturbation_invariant": True,
            "prospective_holdout_status": self.prospective_holdout_status,
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
            "universe_hash": "771b0b4fe3c304bfad72b6e6",
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise BaselineViolation(
                "Phase 7 universe differs from the approved scientific baseline"
            )


PHASE7_APPROVED_BASELINE = Phase7ScientificBaseline(
    baseline_id="phase7_scientific_baseline_v1_2",
    contract_version="1.0.3",
    phase7_version="1.3.0",
    configuration_hash="cc550337f1f4ee4654124bf6",
    feature_version="multiasset_features_v2",
    market_context_version="market_context_v2",
    target_version="multiasset_targets_v2",
    decision_latency_bars=1,
    architectures=("G0", "C0", "P0", "H0"),
    core_universe_version="core_universe_v1",
    expansion_universe_version="expansion_universe_v1",
    research_cutoff_exclusive=datetime(2026, 7, 1, tzinfo=UTC),
    prospective_holdout_start=datetime(2026, 8, 1, tzinfo=UTC),
    prospective_holdout_status="LOCKED_UNUSED",
    artifact_roots=(
        ArtifactRootBaseline(
            root="data",
            file_count=16_754,
            byte_count=1_955_207_062,
            sha256="c2060c9ec37917df8cbc31eab0dd437523eaebbef01ba0e74fb5b911d6e510d2",
        ),
        ArtifactRootBaseline(
            root="local_artifacts",
            file_count=2_131,
            byte_count=919_871_730,
            sha256="c6121785ca4d07bd6278199d706df4b9e582b4f064b299f7478c87a3d1d50af8",
        ),
    ),
    combined_artifact_sha256="ad44fe62a5bae2df4c9b21f3d39f02b2141fe4dd6db7db022bb3fe6ee62103f1",
)
