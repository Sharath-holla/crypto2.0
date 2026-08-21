from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.domain import interval_milliseconds

BASELINE_FEATURE_COLUMNS = (
    "return_5m",
    "return_15m",
    "return_30m",
    "return_1h",
    "log_return_5m",
    "candle_range_pct",
    "candle_body_pct",
    "relative_volume",
    "rolling_volatility_1h",
    "rolling_volatility_4h",
    "ema20_distance",
    "ema50_distance",
    "rsi14",
)

SUPPORTED_MODELS = (
    "zero",
    "historical_mean",
    "momentum",
    "mean_reversion",
    "ridge",
    "lightgbm",
)


def _stable_hash(payload: Any, *, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def config_hash(self) -> str:
        return _stable_hash(self.model_dump(mode="json"))


class LabelConfig(_FrozenModel):
    name: Literal["forward_return_60m"] = "forward_return_60m"
    version: str = "1.0.0"
    horizon_minutes: int = Field(default=60, gt=0)
    return_type: Literal["simple"] = "simple"
    entry_reference: Literal["next_candle_open"] = "next_candle_open"
    future_reference: Literal["horizon_open"] = "horizon_open"
    gap_behavior: Literal["invalidate"] = "invalidate"
    near_zero_threshold_bps: float = Field(default=1.0, ge=0)

    def horizon_steps(self, interval: str) -> int:
        interval_ms = interval_milliseconds(interval)
        horizon_ms = self.horizon_minutes * 60_000
        if horizon_ms % interval_ms:
            raise ValueError(
                f"Label horizon {self.horizon_minutes}m is not divisible by interval {interval}"
            )
        return horizon_ms // interval_ms


class FeatureConfig(_FrozenModel):
    version: str = "1.0.0"
    columns: tuple[str, ...] = BASELINE_FEATURE_COLUMNS
    relative_volume_window: int = Field(default=12, ge=2)
    volatility_1h_window: int = Field(default=12, ge=2)
    volatility_4h_window: int = Field(default=48, ge=2)
    ema_fast_span: int = Field(default=20, ge=2)
    ema_slow_span: int = Field(default=50, ge=2)
    rsi_period: int = Field(default=14, ge=2)

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, columns: tuple[str, ...]) -> tuple[str, ...]:
        if not columns:
            raise ValueError("Feature list cannot be empty")
        if len(columns) != len(set(columns)):
            raise ValueError("Feature names must be unique")
        unknown = sorted(set(columns) - set(BASELINE_FEATURE_COLUMNS))
        if unknown:
            raise ValueError(
                "Only the approved leakage-reviewed baseline features are allowed: "
                + ", ".join(unknown)
            )
        forbidden = ("future", "target", "label", "entry_reference", "label_end")
        suspicious = [name for name in columns if any(token in name for token in forbidden)]
        if suspicious:
            raise ValueError(f"Target-derived/future feature names are forbidden: {suspicious}")
        return columns

    @property
    def minimum_history_rows(self) -> int:
        return max(
            13,
            self.relative_volume_window,
            self.volatility_1h_window + 1,
            self.volatility_4h_window + 1,
            self.ema_fast_span,
            self.ema_slow_span,
            self.rsi_period + 1,
        )


def _normalize_utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a UTC offset")
    return value.astimezone(UTC)


class DatasetBuildConfig(_FrozenModel):
    silver_manifest: Path
    symbol: str = "BTCUSDT"
    interval: str = "5m"
    output_root: Path = Path("data/gold/training_sets")
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be empty")
        return normalized

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        interval_milliseconds(value)
        return value

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        start = _normalize_utc(self.start_time, "start_time")
        end = _normalize_utc(self.end_time, "end_time")
        object.__setattr__(self, "start_time", start)
        object.__setattr__(self, "end_time", end)
        if start is not None and end is not None and start >= end:
            raise ValueError("Dataset range must be half-open with start_time < end_time")
        return self

    @property
    def content_hash(self) -> str:
        return _stable_hash(
            {
                "symbol": self.symbol,
                "interval": self.interval,
                "start_time": self.start_time,
                "end_time": self.end_time,
            }
        )


class SplitConfig(_FrozenModel):
    train_fraction: float = Field(default=0.70, gt=0, lt=1)
    validation_fraction: float = Field(default=0.15, gt=0, lt=1)
    test_fraction: float = Field(default=0.15, gt=0, lt=1)
    validation_start: datetime | None = None
    test_start: datetime | None = None
    minimum_rows_per_split: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-9:
            raise ValueError("Split fractions must sum to 1.0")
        validation_start = _normalize_utc(self.validation_start, "validation_start")
        test_start = _normalize_utc(self.test_start, "test_start")
        object.__setattr__(self, "validation_start", validation_start)
        object.__setattr__(self, "test_start", test_start)
        if (validation_start is None) != (test_start is None):
            raise ValueError("validation_start and test_start must be provided together")
        if validation_start is not None and validation_start >= test_start:
            raise ValueError("validation_start must be before test_start")
        return self


class RidgeConfig(_FrozenModel):
    alpha: float = Field(default=1.0, gt=0)


class LightGBMConfig(_FrozenModel):
    n_estimators: int = Field(default=500, ge=10, le=10_000)
    learning_rate: float = Field(default=0.03, gt=0, le=1)
    num_leaves: int = Field(default=15, ge=2)
    max_depth: int = Field(default=5, ge=-1)
    min_child_samples: int = Field(default=50, ge=1)
    subsample: float = Field(default=0.8, gt=0, le=1)
    colsample_bytree: float = Field(default=0.8, gt=0, le=1)
    reg_alpha: float = Field(default=0.1, ge=0)
    reg_lambda: float = Field(default=1.0, ge=0)
    early_stopping_rounds: int = Field(default=50, ge=1)


class ExperimentConfig(_FrozenModel):
    models: tuple[str, ...] = SUPPORTED_MODELS
    seed: int = 42
    artifact_root: Path = Path("local_artifacts")
    split: SplitConfig = SplitConfig()
    ridge: RidgeConfig = RidgeConfig()
    lightgbm: LightGBMConfig = LightGBMConfig()

    @field_validator("models")
    @classmethod
    def validate_models(cls, models: tuple[str, ...]) -> tuple[str, ...]:
        if not models:
            raise ValueError("At least one model must be configured")
        if len(models) != len(set(models)):
            raise ValueError("Model names must be unique")
        unknown = sorted(set(models) - set(SUPPORTED_MODELS))
        if unknown:
            raise ValueError(f"Unsupported models: {', '.join(unknown)}")
        return models

    @property
    def research_hash(self) -> str:
        return _stable_hash(
            {
                "models": self.models,
                "seed": self.seed,
                "split": self.split.model_dump(mode="json"),
                "ridge": self.ridge.model_dump(mode="json"),
                "lightgbm": self.lightgbm.model_dump(mode="json"),
            }
        )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _section(path: Path, name: str) -> dict[str, Any]:
    raw = _read_toml(path)
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a [{name}] table")
    return value


def load_label_config(path: Path) -> LabelConfig:
    return LabelConfig.model_validate(_section(path, "label"))


def load_feature_config(path: Path) -> FeatureConfig:
    return FeatureConfig.model_validate(_section(path, "features"))


def load_dataset_config(path: Path) -> DatasetBuildConfig:
    return DatasetBuildConfig.model_validate(_section(path, "dataset"))


def load_experiment_config(path: Path) -> ExperimentConfig:
    raw = _read_toml(path)
    experiment = raw.get("experiment")
    if not isinstance(experiment, dict):
        raise ValueError(f"{path} must contain an [experiment] table")
    values = dict(experiment)
    for name in ("split", "ridge", "lightgbm"):
        section = raw.get(name, {})
        if not isinstance(section, dict):
            raise ValueError(f"[{name}] must be a TOML table")
        values[name] = section
    return ExperimentConfig.model_validate(values)
