"""Opt-in Phase 7.2 research capabilities with no baseline or runtime side effects."""

from crypto_ai.phase7_2.challengers import ModelComparisonKey, TreeChallengerSpec
from crypto_ai.phase7_2.competing_risks import (
    COMPETING_RISK_TARGET_VERSION,
    CompetingRiskTarget,
    IntrabarOrderStatus,
)
from crypto_ai.phase7_2.config import Phase72Config, load_phase7_2_config
from crypto_ai.phase7_2.micro import Micro1mContext, aggregate_1m_to_5m, build_micro_1m_context
from crypto_ai.phase7_2.ood import OODAssessment, RobustOODModel
from crypto_ai.phase7_2.ranking import CROSS_ASSET_RANKING_VERSION, build_ranking_groups
from crypto_ai.phase7_2.schemas import CanonicalMarket1m

__all__ = [
    "COMPETING_RISK_TARGET_VERSION",
    "CROSS_ASSET_RANKING_VERSION",
    "CanonicalMarket1m",
    "CompetingRiskTarget",
    "IntrabarOrderStatus",
    "Micro1mContext",
    "ModelComparisonKey",
    "OODAssessment",
    "Phase72Config",
    "RobustOODModel",
    "TreeChallengerSpec",
    "aggregate_1m_to_5m",
    "build_micro_1m_context",
    "build_ranking_groups",
    "load_phase7_2_config",
]
