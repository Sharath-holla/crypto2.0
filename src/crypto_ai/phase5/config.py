from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _hash(payload: Any, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScheduleConfig(_Frozen):
    train_months: int = Field(default=24, ge=1)
    validation_months: int = Field(default=3, ge=1)
    calibration_months: int = Field(default=3, ge=1)
    test_months: int = Field(default=3, ge=1)
    step_months: int = Field(default=3, ge=1)
    embargo_minutes: int = Field(default=60, ge=0)
    window: Literal["rolling"] = "rolling"
    minimum_rows_per_segment: int = Field(default=500, ge=1)

    @model_validator(mode="after")
    def validate_nonoverlapping_tests(self) -> Self:
        if self.step_months < self.test_months:
            raise ValueError("step_months must be at least test_months to prevent overlapping OOS")
        return self


class CalibrationConfig(_Frozen):
    methods: tuple[Literal["identity", "linear"], ...] = ("identity", "linear")
    reliability_buckets: int = Field(default=10, ge=2, le=50)
    minimum_samples: int = Field(default=100, ge=2)

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("calibration methods must be non-empty and unique")
        return value


class ThresholdConfig(_Frozen):
    grid_bps: tuple[float, ...] = (2.0, 4.0, 6.0, 8.0, 10.0)
    minimum_calibration_trades: int = Field(default=30, ge=1)
    drawdown_penalty: float = Field(default=0.25, ge=0)
    low_trade_penalty: float = Field(default=0.0005, ge=0)

    @field_validator("grid_bps")
    @classmethod
    def validate_grid(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value or any(item < 0 for item in value):
            raise ValueError("threshold grid must contain non-negative values")
        if tuple(sorted(set(value))) != value:
            raise ValueError("threshold grid must be unique and strictly increasing")
        return value


class BootstrapConfig(_Frozen):
    samples: int = Field(default=500, ge=100)
    block_rows: int = Field(default=288, ge=2)
    confidence: float = Field(default=0.95, gt=0.5, lt=1)


class QualificationConfig(_Frozen):
    minimum_test_folds: int = Field(default=5, ge=1)
    minimum_total_trades: int = Field(default=100, ge=1)
    minimum_reliable_folds: int = Field(default=3, ge=1)
    minimum_reliable_trades_per_fold: int = Field(default=30, ge=1)
    maximum_drawdown: float = Field(default=0.25, gt=0, lt=1)
    maximum_top_fold_pnl_share: float = Field(default=0.50, gt=0, le=1)
    maximum_top_year_pnl_share: float = Field(default=0.65, gt=0, le=1)
    maximum_top_regime_pnl_share: float = Field(default=0.75, gt=0, le=1)
    required_cost_multiplier: float = Field(default=1.5, ge=1)


class WalkForwardConfig(_Frozen):
    name: str = Field(min_length=1)
    family: Literal["primary", "derivatives"]
    dataset_manifest: Path
    experiment_config: Path = Path("configs/models/main_model_v2_1.toml")
    backtest_config: Path = Path("configs/backtests/foundation_v2_1.toml")
    funding_manifest: Path | None = None
    execution_1m_silver_manifest: Path | None = None
    artifact_root: Path = Path("local_artifacts/phase5/walkforward")
    candidates: tuple[str, ...]
    prospective_holdout_start: datetime
    seed: int = 42
    schedule: ScheduleConfig = ScheduleConfig()
    calibration: CalibrationConfig = CalibrationConfig()
    threshold: ThresholdConfig = ThresholdConfig()
    bootstrap: BootstrapConfig = BootstrapConfig()
    qualification: QualificationConfig = QualificationConfig()
    cost_multipliers: tuple[float, ...] = (0.0, 1.0, 1.25, 1.5, 2.0)

    @field_validator("prospective_holdout_start")
    @classmethod
    def normalize_holdout(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("prospective_holdout_start must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("cost_multipliers")
    @classmethod
    def validate_costs(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if tuple(sorted(set(value))) != value or 0.0 not in value or 1.0 not in value:
            raise ValueError("cost multipliers must be sorted, unique, and include 0x and 1x")
        return value

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        expected = {"primary": ("L0", "L5"), "derivatives": ("D0", "D2")}[self.family]
        if self.candidates != expected:
            raise ValueError(f"{self.family} candidates are frozen as {expected}")
        return self

    @property
    def configuration_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


class HardeningConfig(_Frozen):
    walkforward: WalkForwardConfig
    source_summary: Path
    artifact_root: Path = Path("local_artifacts/phase5_hardening/walkforward_v1_1")
    protocol_version: Literal["1.1.0"] = "1.1.0"

    @property
    def configuration_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


def _walk_forward_payload(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    section = payload.get("walkforward")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain [walkforward]")
    merged = dict(section)
    for name in ("schedule", "calibration", "threshold", "bootstrap", "qualification"):
        if name in payload:
            merged[name] = payload[name]
    return merged


def load_walk_forward_config(path: Path) -> WalkForwardConfig:
    path = path.resolve()
    with path.open("rb") as stream:
        payload = tomllib.load(stream)
    return WalkForwardConfig.model_validate(_walk_forward_payload(payload, path))


def load_hardening_config(path: Path) -> HardeningConfig:
    path = path.resolve()
    with path.open("rb") as stream:
        payload = tomllib.load(stream)
    section = payload.get("hardening")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain [hardening]")
    return HardeningConfig.model_validate(
        {**section, "walkforward": _walk_forward_payload(payload, path)}
    )
