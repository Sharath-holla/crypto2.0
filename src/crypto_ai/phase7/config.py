from __future__ import annotations

import hashlib
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.phase5.config import CalibrationConfig, ScheduleConfig
from crypto_ai.phase5.folds import add_calendar_months

PHASE7_VERSION = "1.6.0"
SYMBOL_REGISTRY_VERSION = "symbol_registry_v1"
UNIVERSE_VERSION = "dual_universe_v3"
CORE_UNIVERSE_VERSION = "core_universe_v1"
EXPANSION_UNIVERSE_VERSION = "expansion_universe_v2"
FEATURE_VERSION = "multiasset_features_v2"
MARKET_CONTEXT_VERSION = "market_context_v2"
TARGET_VERSION = "multiasset_targets_v2"
RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
PROSPECTIVE_HOLDOUT = datetime(2026, 8, 1, tzinfo=UTC)
PROSPECTIVE_HOLDOUT_STATUS = "LOCKED_UNUSED"


def stable_hash(payload: Any, *, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def _canonical_logical_path(value: Path) -> str:
    """Serialize a path-typed logical value independently of the host OS."""

    return PurePosixPath(str(value).replace("\\", "/")).as_posix()


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathConfig(_Frozen):
    data_root: Path = Path("data")
    artifact_root: Path = Path("local_artifacts/phase7")
    gold_root: Path = Path("data/gold/phase7")
    checkpoint_root: Path = Path("local_artifacts/phase7/checkpoints")
    cloud_storage_root: str | None = None

    def resolved_cloud_storage_root(self) -> str | None:
        value = os.environ.get("PHASE7_CLOUD_STORAGE_ROOT", self.cloud_storage_root or "").strip()
        return value.rstrip("/") or None


class UniverseConfig(_Frozen):
    core_target_size: int = Field(default=20, ge=2, le=30)
    fixture_mode: bool = False
    core_selection_cutoff: datetime = datetime(2022, 1, 1, tzinfo=UTC)
    enable_expansion: bool = True
    expansion_as_of: Literal["fold_train_end"] = "fold_train_end"
    expansion_max_symbols_per_fold: int = Field(default=10, ge=0, le=30)
    total_max_symbols_per_fold: int = Field(default=30, ge=2, le=30)
    minimum_history_days: int = Field(default=365, ge=90)
    age_bucket_edges_days: tuple[int, int, int] = (365, 730, 1460)
    minimum_coverage_ratio: float = Field(default=0.995, gt=0, le=1)
    warning_coverage_ratio: float = Field(default=0.999, gt=0, le=1)
    minimum_trailing_quote_volume: float = Field(default=0.0, ge=0)
    selection_lookback_days: int = Field(default=90, ge=30)
    required_anchor_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    required_intervals: tuple[str, ...] = ("5m", "12h", "1d")
    quote_asset: Literal["USDT"] = "USDT"
    contract_type: Literal["PERPETUAL"] = "PERPETUAL"

    @field_validator("core_selection_cutoff")
    @classmethod
    def normalize_core_selection_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("core universe selection cutoff must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("age_bucket_edges_days")
    @classmethod
    def validate_age_buckets(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("cold-start age bucket edges must be unique and increasing")
        return value

    @field_validator("required_anchor_symbols")
    @classmethod
    def normalize_anchors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip().upper() for item in value)
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("required anchor symbols must be non-empty and unique")
        if not {"BTCUSDT", "ETHUSDT"}.issubset(normalized):
            raise ValueError("Phase 7 requires BTCUSDT and ETHUSDT anchors")
        return normalized

    @field_validator("required_intervals")
    @classmethod
    def validate_universe_intervals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("5m", "12h", "1d"):
            raise ValueError("Phase 7 universe requires 5m, 12h, and 1d coverage")
        return value

    @model_validator(mode="after")
    def enforce_research_pilot_range(self) -> Self:
        if not self.fixture_mode and self.core_target_size < 15:
            raise ValueError("Phase 7 core target size must be between 15 and 30")
        if not self.fixture_mode and self.total_max_symbols_per_fold < 15:
            raise ValueError("Phase 7 total fold universe must remain between 15 and 30")
        if self.core_target_size < len(self.required_anchor_symbols):
            raise ValueError("core target size cannot be smaller than mandatory anchors")
        if self.total_max_symbols_per_fold < self.core_target_size:
            raise ValueError("total fold cap cannot be smaller than the core target size")
        if self.expansion_max_symbols_per_fold > self.total_max_symbols_per_fold:
            raise ValueError("expansion fold cap cannot exceed the total fold cap")
        if self.enable_expansion and self.expansion_max_symbols_per_fold < 1:
            raise ValueError("enabled expansion requires a positive per-fold expansion cap")
        if self.minimum_history_days != self.age_bucket_edges_days[0]:
            raise ValueError("first cold-start age bucket edge must equal minimum history days")
        if self.warning_coverage_ratio < self.minimum_coverage_ratio:
            raise ValueError("warning coverage cannot be below the eligibility minimum")
        return self

    @property
    def selection_cutoff(self) -> datetime:
        """Compatibility accessor; this is specifically the core benchmark cutoff."""

        return self.core_selection_cutoff

    @property
    def pilot_size(self) -> int:
        """Compatibility accessor; the historical pilot is now the core target size."""

        return self.core_target_size


class FeatureConfig(_Frozen):
    correlation_window_rows: int = Field(default=2_016, ge=12)
    liquidity_window_rows: int = Field(default=2_016, ge=12)
    volatility_window_rows: int = Field(default=2_016, ge=12)
    daily_volatility_rows: int = Field(default=288, ge=12)
    seven_day_volatility_rows: int = Field(default=2_016, ge=24)
    include_12h: bool = True
    include_1d: bool = True
    include_derivatives: bool = True
    include_rejected_negative_controls: bool = False


class TargetConfig(_Frozen):
    horizons_minutes: tuple[int, ...] = (15, 30, 60, 120)
    decision_latency_bars: Literal[1] = 1
    target_types: tuple[Literal["raw", "volatility_normalized"], ...] = (
        "raw",
        "volatility_normalized",
    )
    normalization_floor: float = Field(default=1e-8, gt=0)

    @field_validator("horizons_minutes")
    @classmethod
    def validate_horizons(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if tuple(sorted(set(value))) != value or any(item <= 0 or item % 5 for item in value):
            raise ValueError("target horizons must be unique increasing positive 5m multiples")
        for required in (15, 30, 60, 120):
            if required not in value:
                raise ValueError("Phase 7 requires 15m, 30m, 1h, and 2h targets")
        return value

    @field_validator("target_types")
    @classmethod
    def validate_target_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("raw", "volatility_normalized"):
            raise ValueError("Phase 7 requires raw and volatility-normalized targets")
        return value


class ModelConfig(_Frozen):
    architectures: tuple[Literal["G0", "C0", "P0", "H0"], ...] = (
        "G0",
        "C0",
        "P0",
        "H0",
    )
    cluster_count: int = Field(default=4, ge=3, le=5)
    include_symbol_id_ablation: bool = True
    compare_symbol_balanced_weights: bool = True
    minimum_train_rows_per_coin: int = Field(default=20_000, ge=100)
    minimum_validation_rows_per_coin: int = Field(default=2_000, ge=20)
    minimum_calibration_rows_per_coin: int = Field(default=2_000, ge=20)
    learning_rate: float = Field(default=0.02, gt=0, le=0.2)
    n_estimators: int = Field(default=500, ge=20, le=2_000)
    num_leaves: int = Field(default=31, ge=4, le=255)
    max_depth: int = Field(default=-1, ge=-1, le=32)
    min_child_samples: int = Field(default=100, ge=5)
    subsample: float = Field(default=0.9, gt=0, le=1)
    colsample_bytree: float = Field(default=0.9, gt=0, le=1)
    reg_alpha: float = Field(default=0.1, ge=0)
    reg_lambda: float = Field(default=1.0, ge=0)
    early_stopping_rounds: int = Field(default=50, ge=5)
    seed: int = 42

    @field_validator("architectures")
    @classmethod
    def validate_architectures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("G0", "C0", "P0", "H0"):
            raise ValueError("Phase 7 architecture comparison is frozen as G0/C0/P0/H0")
        return value


class ResourceConfig(_Frozen):
    max_workers: int = Field(default=4, ge=1, le=32)
    model_threads: int = Field(default=4, ge=1, le=32)
    batch_size: int = Field(default=250_000, ge=1_000)
    memory_guard_gb: float = Field(default=8.0, gt=0)
    require_gpu: Literal[False] = False


class CostTier(_Frozen):
    taker_fee_bps_per_side: float = Field(ge=0)
    spread_bps_round_trip: float = Field(ge=0)
    slippage_bps_per_side: float = Field(ge=0)

    @property
    def round_trip_bps(self) -> float:
        return (
            2.0 * self.taker_fee_bps_per_side
            + self.spread_bps_round_trip
            + 2.0 * self.slippage_bps_per_side
        )


class CostConfig(_Frozen):
    assumption_classification: Literal["RESEARCH COST ASSUMPTIONS"] = "RESEARCH COST ASSUMPTIONS"
    high_liquidity: CostTier = CostTier(
        taker_fee_bps_per_side=4.0,
        spread_bps_round_trip=1.0,
        slippage_bps_per_side=1.0,
    )
    medium_liquidity: CostTier = CostTier(
        taker_fee_bps_per_side=4.0,
        spread_bps_round_trip=2.0,
        slippage_bps_per_side=2.0,
    )
    lower_liquidity: CostTier = CostTier(
        taker_fee_bps_per_side=4.0,
        spread_bps_round_trip=4.0,
        slippage_bps_per_side=4.0,
    )
    fixed_policy_multipliers: tuple[float, ...] = (1.0, 1.25, 1.5, 2.0)
    threshold_grid_bps: tuple[float, ...] = (2.0, 4.0, 6.0, 8.0, 10.0)
    minimum_calibration_trades: int = Field(default=30, ge=1)

    @field_validator("fixed_policy_multipliers", "threshold_grid_bps")
    @classmethod
    def sorted_unique(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value or any(item < 0 for item in value) or tuple(sorted(set(value))) != value:
            raise ValueError("cost/threshold values must be sorted and unique")
        return value


class Phase7Config(_Frozen):
    name: str = "phase7-multiasset-research-v1"
    mode: Literal["local", "cloud"] = "cloud"
    data_start: datetime = datetime(2020, 1, 1, tzinfo=UTC)
    research_cutoff: datetime = RESEARCH_CUTOFF
    prospective_holdout_start: datetime = PROSPECTIVE_HOLDOUT
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = PROSPECTIVE_HOLDOUT_STATUS
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False
    decision_interval: Literal["5m"] = "5m"
    required_intervals: tuple[str, ...] = ("5m", "12h", "1d")
    derivative_datasets: tuple[str, ...] = ("funding", "mark", "index")
    binance_config: Path = Path("configs/data/binance.toml")
    quality_config: Path = Path("configs/data_quality/default.toml")
    paths: PathConfig = PathConfig()
    universe: UniverseConfig = UniverseConfig()
    features: FeatureConfig = FeatureConfig()
    targets: TargetConfig = TargetConfig()
    models: ModelConfig = ModelConfig()
    resources: ResourceConfig = ResourceConfig()
    costs: CostConfig = CostConfig()
    schedule: ScheduleConfig = ScheduleConfig(embargo_minutes=120)
    calibration: CalibrationConfig = CalibrationConfig()

    @field_validator("data_start", "research_cutoff", "prospective_holdout_start")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Phase 7 boundaries must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("required_intervals")
    @classmethod
    def validate_intervals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("5m", "12h", "1d"):
            raise ValueError("Phase 7 requires 5m, 12h, and 1d data")
        return value

    @field_validator("derivative_datasets")
    @classmethod
    def validate_derivatives(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("funding", "mark", "index"):
            raise ValueError("Phase 7 derivatives are frozen as funding/mark/index")
        return value

    @model_validator(mode="after")
    def lock_boundaries(self) -> Self:
        if self.research_cutoff != RESEARCH_CUTOFF:
            raise ValueError("Phase 7 research cutoff is locked to 2026-07-01T00:00:00Z")
        if self.prospective_holdout_start != PROSPECTIVE_HOLDOUT:
            raise ValueError("Prospective holdout is locked to 2026-08-01T00:00:00Z")
        if self.research_cutoff >= self.prospective_holdout_start:
            raise ValueError("Research cutoff must precede the holdout")
        if add_calendar_months(self.research_cutoff, 1) != self.prospective_holdout_start:
            raise ValueError("Phase 7 requires the complete July 2026 unused buffer")
        if self.data_start != datetime(2020, 1, 1, tzinfo=UTC):
            raise ValueError("Phase 7 data start is locked to 2020-01-01T00:00:00Z")
        if self.data_start >= self.universe.core_selection_cutoff:
            raise ValueError("Data start must precede the core universe selection cutoff")
        expected_selection_cutoff = add_calendar_months(self.data_start, self.schedule.train_months)
        if self.universe.core_selection_cutoff != expected_selection_cutoff:
            raise ValueError(
                "Core universe selection cutoff must equal the first walk-forward TRAIN end "
                f"({expected_selection_cutoff.isoformat()})"
            )
        if self.universe.core_selection_cutoff >= self.research_cutoff:
            raise ValueError("Core universe selection cutoff must precede the research cutoff")
        if self.universe.fixture_mode:
            raise ValueError("fixture_mode is not valid in the Phase 7 research configuration")
        if self.schedule.embargo_minutes < max(self.targets.horizons_minutes):
            raise ValueError("Phase 7 embargo must cover the longest configured target horizon")
        return self

    @property
    def configuration_hash(self) -> str:
        return stable_hash(self.configuration_identity_payload())

    def configuration_identity_payload(self) -> dict[str, Any]:
        """Return the semantic configuration using canonical logical paths."""

        payload = self.model_dump(mode="json")
        payload["binance_config"] = _canonical_logical_path(self.binance_config)
        payload["quality_config"] = _canonical_logical_path(self.quality_config)
        path_payload = dict(payload["paths"])
        for field in ("data_root", "artifact_root", "gold_root", "checkpoint_root"):
            path_payload[field] = _canonical_logical_path(getattr(self.paths, field))
        payload["paths"] = path_payload
        return payload

    def holdout_status_payload(self) -> dict[str, Any]:
        return {
            "prospective_holdout_status": self.prospective_holdout_status,
            "prospective_holdout_start": self.prospective_holdout_start.isoformat(),
            "prospective_holdout_used": self.prospective_holdout_used,
            "prospective_holdout_evaluation_authorized": (
                self.prospective_holdout_evaluation_authorized
            ),
        }

    def assert_cloud_execution_allowed(self) -> None:
        if self.mode != "cloud":
            raise RuntimeError("Heavy Phase 7 stages require mode='cloud'")
        if os.environ.get("PHASE7_ALLOW_CLOUD_RESEARCH") != "1":
            raise RuntimeError(
                "Heavy Phase 7 stages are locked; set PHASE7_ALLOW_CLOUD_RESEARCH=1 "
                "only on the training VM"
            )


def load_phase7_config(path: Path) -> Phase7Config:
    path = path.resolve()
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    root = raw.get("phase7")
    if not isinstance(root, dict):
        raise ValueError(f"{path} must contain a [phase7] table")
    merged = dict(root)
    for section in (
        "paths",
        "universe",
        "features",
        "targets",
        "models",
        "resources",
        "costs",
        "schedule",
        "calibration",
    ):
        payload = raw.get(section)
        if payload is not None:
            merged[section] = payload
    tier_payload = raw.get("cost_tiers")
    if tier_payload is not None:
        costs = dict(merged.get("costs", {}))
        costs.update(tier_payload)
        merged["costs"] = costs
    return Phase7Config.model_validate(merged)
