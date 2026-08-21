from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.domain import interval_milliseconds


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


class GoldV2_1Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    silver_manifests: tuple[Path, ...]
    funding_manifest: Path | None = None
    mark_manifest: Path | None = None
    index_manifest: Path | None = None
    open_interest_manifest: Path | None = None
    dataset_family: Literal["core_long_history", "derivatives_overlap"]
    symbol: str = "BTCUSDT"
    interval: str = "5m"
    output_root: Path = Path("data/gold/market_intelligence_v2_1")
    start_time: datetime
    end_time: datetime

    @field_validator("silver_manifests")
    @classmethod
    def check_silver_manifests(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if not value:
            raise ValueError("At least one Silver manifest is required")
        if len(value) != len(set(value)):
            raise ValueError("Silver manifests must be unique")
        return value

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        result = value.strip().upper()
        if not result:
            raise ValueError("symbol cannot be empty")
        return result

    @field_validator("interval")
    @classmethod
    def check_interval(cls, value: str) -> str:
        interval_milliseconds(value)
        return value

    @model_validator(mode="after")
    def check_range_and_family(self) -> Self:
        for field in ("start_time", "end_time"):
            value = getattr(self, field)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
            object.__setattr__(self, field, value.astimezone(UTC))
        if self.start_time >= self.end_time:
            raise ValueError("Gold V2.1 range must be half-open with start_time < end_time")
        required_external = (self.funding_manifest, self.mark_manifest, self.index_manifest)
        all_external = (*required_external, self.open_interest_manifest)
        if self.dataset_family == "core_long_history" and any(
            item is not None for item in all_external
        ):
            raise ValueError("Core long-history Gold must not depend on shorter external history")
        if self.dataset_family == "derivatives_overlap" and any(
            item is None for item in required_external
        ):
            raise ValueError("Derivatives-overlap Gold requires funding, mark, and index manifests")
        if (self.mark_manifest is None) != (self.index_manifest is None):
            raise ValueError("Mark and index manifests must be supplied together")
        return self

    @property
    def config_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


def load_gold_v2_1_config(path: Path) -> GoldV2_1Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    section = raw.get("dataset")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain a [dataset] table")
    return GoldV2_1Config.model_validate(section)


class BacktestV2_1Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_minutes: int = Field(default=60, gt=0)
    maker_fee_bps_per_side: float = Field(default=2.0, ge=0)
    taker_fee_bps_per_side: float = Field(default=4.0, ge=0)
    fee_source: str = "explicit conservative research assumption"
    assumption_or_account_specific: Literal["assumption", "account_specific"] = "assumption"
    spread_bps_round_trip: float = Field(default=1.0, ge=0)
    slippage_bps_per_side: float = Field(default=1.0, ge=0)
    minimum_prediction_bps: float = Field(default=2.0, ge=0)
    minimum_expected_net_edge_bps: float = Field(default=0.0, ge=0)
    base_latency_minutes: int = Field(default=1, ge=0)
    minimum_reliable_trade_count: int = Field(default=30, ge=1)

    @property
    def non_funding_round_trip_bps(self) -> float:
        return (
            2 * self.taker_fee_bps_per_side
            + self.spread_bps_round_trip
            + 2 * self.slippage_bps_per_side
        )

    @property
    def config_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


def load_backtest_v2_1_config(path: Path) -> BacktestV2_1Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    section = raw.get("backtest_v2_1")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain a [backtest_v2_1] table")
    return BacktestV2_1Config.model_validate(section)
