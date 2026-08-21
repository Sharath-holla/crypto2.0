from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.domain import Market, interval_milliseconds


class BinanceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market: Market = Market.USD_M
    symbol: str = "BTCUSDT"
    interval: str = "5m"
    output_root: Path = Path("data/bronze/binance")
    request_limit: int = Field(default=1_000, ge=1, le=1_500)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=5, ge=0, le=12)
    retry_base_seconds: float = Field(default=0.5, ge=0, le=60)
    base_url: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol or not symbol.isascii() or not symbol.replace("_", "").isalnum():
            raise ValueError("symbol must contain only ASCII letters, digits, or underscores")
        return symbol

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        interval_milliseconds(value)
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("base_url must start with https:// or http://")
        return normalized

    @model_validator(mode="after")
    def validate_market_request_limit(self) -> Self:
        if self.market is Market.SPOT and self.request_limit > 1_000:
            raise ValueError("Binance Spot request_limit cannot exceed 1000")
        return self


def load_binance_settings(
    path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> BinanceSettings:
    values: dict[str, Any] = {}
    if path is not None:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        section = raw.get("binance")
        if not isinstance(section, dict):
            raise ValueError(f"{path} must contain a [binance] table")
        values.update(section)
    if overrides:
        values.update({key: value for key, value in overrides.items() if value is not None})
    return BinanceSettings.model_validate(values)
