from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from crypto_ai.contracts.versioning import canonical_sha256


class TreeEstimatorFamily(StrEnum):
    LIGHTGBM = "LIGHTGBM"
    CATBOOST = "CATBOOST"
    XGBOOST = "XGBOOST"


class CalibrationMethod(StrEnum):
    ISOTONIC = "ISOTONIC"
    PLATT_LOGISTIC = "PLATT_LOGISTIC"
    TEMPERATURE = "TEMPERATURE"


class DecisionDisposition(StrEnum):
    OPPORTUNITY = "OPPORTUNITY"
    NO_OPPORTUNITY = "NO_OPPORTUNITY"
    NO_TRADE = "NO_TRADE"


class EvaluationSlice(StrEnum):
    CHRONOLOGICAL_OOS = "CHRONOLOGICAL_OOS"
    CORE_KNOWN = "CORE_KNOWN"
    EXPANSION = "EXPANSION"
    UNSEEN_SYMBOL = "UNSEEN_SYMBOL"
    LISTING_0_7D = "LISTING_0_7D"
    LISTING_8_30D = "LISTING_8_30D"
    LISTING_31_90D = "LISTING_31_90D"
    LISTING_OVER_90D = "LISTING_OVER_90D"
    LATER_DELISTED = "LATER_DELISTED"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    TRENDING = "TRENDING"
    SIDEWAYS = "SIDEWAYS"
    CRASH_STRESS = "CRASH_STRESS"
    RECOVERY = "RECOVERY"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    CLEAN_COMPLETE_DATA = "CLEAN_COMPLETE_DATA"
    MINOR_GAPS = "MINOR_GAPS"
    MISSING_FUNDING = "MISSING_FUNDING"
    MISSING_MARK_INDEX = "MISSING_MARK_INDEX"
    YOUNG_HIGHER_TIMEFRAME_HISTORY = "YOUNG_HIGHER_TIMEFRAME_HISTORY"
    STALE_CONTEXT = "STALE_CONTEXT"
    PARTIAL_PROVIDER_COVERAGE = "PARTIAL_PROVIDER_COVERAGE"
    DATA_DEGRADATION = "DATA_DEGRADATION"


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC")


@dataclass(frozen=True, slots=True)
class TreeChallengerSpec:
    family: TreeEstimatorFamily
    feature_schema: str
    target_schema: str
    fold_schema: str
    universe_schema: str
    calibration_schema: str
    cost_schema: str
    enabled: bool = False
    training_enabled: bool = False

    def __post_init__(self) -> None:
        for field in (
            "feature_schema",
            "target_schema",
            "fold_schema",
            "universe_schema",
            "calibration_schema",
            "cost_schema",
        ):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        if self.training_enabled:
            raise ValueError("tree challenger training is not authorized in Phase 7.2")

    @property
    def dependency_available(self) -> bool:
        module = {
            TreeEstimatorFamily.LIGHTGBM: "lightgbm",
            TreeEstimatorFamily.CATBOOST: "catboost",
            TreeEstimatorFamily.XGBOOST: "xgboost",
        }[self.family]
        return importlib.util.find_spec(module) is not None


@runtime_checkable
class EstimatorAdapter(Protocol):
    @property
    def spec(self) -> TreeChallengerSpec: ...


@dataclass(frozen=True, slots=True)
class ModelComparisonKey:
    symbol: str
    feature_time: datetime
    target: str
    horizon_minutes: int
    universe_version: str
    fold_id: str
    cost_model: str
    feature_schema: str

    def __post_init__(self) -> None:
        _require_utc(self.feature_time, "feature_time")
        if self.symbol != self.symbol.upper() or not self.symbol:
            raise ValueError("symbol must be normalized uppercase")
        for field in (
            "target",
            "universe_version",
            "fold_id",
            "cost_model",
            "feature_schema",
        ):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        if self.horizon_minutes <= 0:
            raise ValueError("horizon_minutes must be positive")

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True, slots=True)
class MatchedCoverage:
    native_rows: int
    matched_rows: int

    def __post_init__(self) -> None:
        if self.native_rows < 0 or not 0 <= self.matched_rows <= self.native_rows:
            raise ValueError("matched coverage counts are incoherent")

    @property
    def matched_fraction(self) -> float | None:
        return self.matched_rows / self.native_rows if self.native_rows else None


@dataclass(frozen=True, slots=True)
class CalibrationPlan:
    method: CalibrationMethod
    prediction_calibration_owner: str = "CAL_A"
    policy_threshold_owner: str = "CAL_B"
    enabled: bool = False

    def __post_init__(self) -> None:
        if self.prediction_calibration_owner == self.policy_threshold_owner:
            raise ValueError("prediction calibration and policy selection must remain separate")


@dataclass(frozen=True, slots=True)
class ConformalResearchPlan:
    empirical_coverage: bool = True
    interval_width: bool = True
    regime_stability: bool = True
    drift_coverage: bool = True
    enabled: bool = False
    phase7_baseline_active: bool = False


@dataclass(frozen=True, slots=True)
class ExperimentTrial:
    trial_family: str
    hypothesis: str
    exact_feature_change: str
    exact_target_change: str
    exact_model_change: str
    primary_metric: str
    promotion_rule: str
    random_seed: int
    data_manifest: str
    universe: str
    cost_assumptions: str

    def __post_init__(self) -> None:
        for field in (
            "trial_family",
            "hypothesis",
            "exact_feature_change",
            "exact_target_change",
            "exact_model_change",
            "primary_metric",
            "promotion_rule",
            "data_manifest",
            "universe",
            "cost_assumptions",
        ):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        if self.random_seed < 0:
            raise ValueError("random_seed cannot be negative")


TRIAL_FAMILIES: dict[str, tuple[str, ...]] = {
    "P7_BASELINE_TREE": ("RIDGE", "G0_LIGHTGBM", "C0_LIGHTGBM", "P0_LIGHTGBM", "H0_LIGHTGBM"),
    "P7_TREE_CHALLENGERS": ("CATBOOST", "XGBOOST"),
    "P7_MICRO_1M": ("5M_BASELINE", "5M_PLUS_MICRO_1M_CONTEXT_V1"),
    "P7_TARGET_CHALLENGERS": ("MULTIASSET_TARGETS_V2", "COMPETING_RISK_TARGETS_V1"),
    "P7_RANKING": ("RETURN_SCORE_RANKING", "DIRECT_LAMBDAMART_RANKING"),
    "P8_TEMPORAL": ("RESERVED_NOT_AUTHORIZED",),
}


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    predicted_move_available: bool
    probability_available: bool
    cost_inputs_available: bool
    uncertainty_available: bool
    liquidity_available: bool
    score: float | None = None
    formula_version: str = "UNDEFINED_RESEARCH_ONLY"

    def __post_init__(self) -> None:
        if self.score is not None:
            raise ValueError("Phase 7.2 does not authorize a finalized opportunity formula")


@dataclass(frozen=True, slots=True)
class NeuralInputContract:
    asset_axis: str = "fold_active_symbols"
    time_axis: str = "causal_completed_observations"
    feature_family_axis: str = "versioned_feature_families"
    missingness_mask: bool = True
    eligibility_mask: bool = True
    fine_context_version: str = "canonical_market_1m_v1"
    pooled_context_interval: str = "5m"
    higher_timeframe_context: bool = True
    cross_asset_context: bool = True
    model_implemented: bool = False
