from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.domain import interval_milliseconds


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def config_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


class GoldV2Config(_Frozen):
    silver_manifest: Path
    funding_manifest: Path | None = None
    mark_manifest: Path | None = None
    index_manifest: Path | None = None
    open_interest_manifest: Path | None = None
    symbol: str = "BTCUSDT"
    interval: str = "5m"
    output_root: Path = Path("data/gold/market_intelligence")
    start_time: datetime | None = None
    end_time: datetime | None = None

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
    def validate_range_and_basis(self) -> Self:
        for name in ("start_time", "end_time"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                object.__setattr__(self, name, value.astimezone(UTC))
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError("Gold V2 range must be half-open with start < end")
        if (self.mark_manifest is None) != (self.index_manifest is None):
            raise ValueError("mark_manifest and index_manifest must be supplied together")
        return self


class BacktestConfig(_Frozen):
    horizon_minutes: int = Field(default=60, gt=0)
    taker_fee_bps_per_side: float = Field(default=4.0, ge=0)
    spread_bps_round_trip: float = Field(default=1.0, ge=0)
    slippage_bps_per_side: float = Field(default=1.0, ge=0)
    minimum_prediction_bps: float = Field(default=2.0, ge=0)
    minimum_expected_net_edge_bps: float = Field(default=0.0, ge=0)
    annualization_periods: int = Field(default=8_760, gt=0)

    @property
    def non_funding_round_trip_bps(self) -> float:
        return (
            2 * self.taker_fee_bps_per_side
            + self.spread_bps_round_trip
            + 2 * self.slippage_bps_per_side
        )


def _section(path: Path, name: str) -> dict[str, Any]:
    with path.open("rb") as stream:
        payload = tomllib.load(stream)
    section = payload.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain a [{name}] table")
    return section


def load_gold_v2_config(path: Path) -> GoldV2Config:
    return GoldV2Config.model_validate(_section(path, "dataset_v2"))


def load_backtest_config(path: Path) -> BacktestConfig:
    return BacktestConfig.model_validate(_section(path, "backtest"))
