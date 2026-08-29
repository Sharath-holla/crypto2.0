from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

PHASE7_2_CONFIG_VERSION = "phase7_2_capabilities_v1"
PHASE7_CONFIGURATION_HASH = "68e4b39899f8c9f0542d227b"
PHASE7_FEATURE_VERSION = "multiasset_features_v2"
PHASE7_TARGET_VERSION = "multiasset_targets_v2"
PHASE7_RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
PROSPECTIVE_HOLDOUT_START = datetime(2026, 8, 1, tzinfo=UTC)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityToggle(_Frozen):
    enabled: bool = False
    research_only: Literal[True] = True


class MicroContextToggle(CapabilityToggle):
    schema_version: Literal["micro_1m_context_v1"] = "micro_1m_context_v1"
    training_row_interval: Literal["5m"] = "5m"
    pilot_symbols: tuple[Literal["BTCUSDT", "ETHUSDT"], ...] = ("BTCUSDT", "ETHUSDT")


class CompetingRiskToggle(CapabilityToggle):
    target_version: Literal["competing_risk_targets_v1"] = "competing_risk_targets_v1"


class RankingToggle(CapabilityToggle):
    dataset_version: Literal["cross_asset_ranking_v1"] = "cross_asset_ranking_v1"
    membership_source: Literal["fold_active_symbols"] = "fold_active_symbols"


class TreeChallengerToggle(_Frozen):
    catboost_enabled: bool = False
    xgboost_enabled: bool = False
    training_enabled: Literal[False] = False


class ProspectiveCaptureToggle(_Frozen):
    enabled: bool = False
    network_enabled: Literal[False] = False
    collector_started: Literal[False] = False


class Phase72Config(_Frozen):
    config_version: Literal["phase7_2_capabilities_v1"] = PHASE7_2_CONFIG_VERSION
    baseline_configuration_hash: Literal["68e4b39899f8c9f0542d227b"] = PHASE7_CONFIGURATION_HASH
    baseline_feature_version: Literal["multiasset_features_v2"] = PHASE7_FEATURE_VERSION
    baseline_feature_count: Literal[54] = 54
    baseline_target_version: Literal["multiasset_targets_v2"] = PHASE7_TARGET_VERSION
    baseline_decision_latency_bars: Literal[1] = 1
    baseline_architectures: tuple[Literal["G0", "C0", "P0", "H0"], ...] = (
        "G0",
        "C0",
        "P0",
        "H0",
    )
    baseline_fold_count: Literal[16] = 16
    baseline_training_interval: Literal["5m"] = "5m"
    research_cutoff: datetime = PHASE7_RESEARCH_CUTOFF
    july_2026_used: Literal[False] = False
    prospective_holdout_start: datetime = PROSPECTIVE_HOLDOUT_START
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = "LOCKED_UNUSED"
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False
    fear_greed_training_enabled: Literal[False] = False
    open_interest_historical_training_enabled: Literal[False] = False
    cloud_execution_enabled: Literal[False] = False
    private_binance_enabled: Literal[False] = False
    live_orders_enabled: Literal[False] = False
    leverage_enabled: Literal[False] = False
    phase8_enabled: Literal[False] = False
    micro_1m_context: MicroContextToggle = MicroContextToggle()
    competing_risk: CompetingRiskToggle = CompetingRiskToggle()
    ranking: RankingToggle = RankingToggle()
    tree_challengers: TreeChallengerToggle = TreeChallengerToggle()
    prospective_capture: ProspectiveCaptureToggle = ProspectiveCaptureToggle()

    @field_validator("research_cutoff", "prospective_holdout_start")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Phase 7.2 safety boundaries must be timezone-aware")
        if value.utcoffset().total_seconds() != 0:
            raise ValueError("Phase 7.2 safety boundaries must be UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def preserve_phase7_boundaries(self) -> Self:
        if self.research_cutoff != PHASE7_RESEARCH_CUTOFF:
            raise ValueError("Phase 7.2 cannot change the Phase 7 research cutoff")
        if self.prospective_holdout_start != PROSPECTIVE_HOLDOUT_START:
            raise ValueError("Phase 7.2 cannot change the prospective holdout start")
        if self.baseline_architectures != ("G0", "C0", "P0", "H0"):
            raise ValueError("Phase 7.2 cannot change Phase 7 architecture order or membership")
        return self

    @property
    def configuration_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:24]

    @property
    def all_experiments_disabled(self) -> bool:
        return not any(
            (
                self.micro_1m_context.enabled,
                self.competing_risk.enabled,
                self.ranking.enabled,
                self.tree_challengers.catboost_enabled,
                self.tree_challengers.xgboost_enabled,
                self.prospective_capture.enabled,
            )
        )


def load_phase7_2_config(path: Path) -> Phase72Config:
    with path.resolve().open("rb") as stream:
        payload = tomllib.load(stream)
    root = payload.get("phase7_2")
    if not isinstance(root, dict):
        raise ValueError(f"{path} must contain a [phase7_2] table")
    merged = dict(root)
    for section in (
        "micro_1m_context",
        "competing_risk",
        "ranking",
        "tree_challengers",
        "prospective_capture",
    ):
        value = payload.get(f"phase7_2.{section}")
        if value is None:
            value = payload.get(section)
        if value is not None:
            merged[section] = value
    return Phase72Config.model_validate(merged)
