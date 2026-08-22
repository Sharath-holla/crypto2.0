from __future__ import annotations

import hashlib
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTEXT_CONFIG_VERSION = "context_config_v1"
CONTEXT_NETWORK_GUARD = "CRYPTO_AI_ALLOW_CONTEXT_NETWORK"
PHASE7_RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
PROSPECTIVE_HOLDOUT_START = datetime(2026, 8, 1, tzinfo=UTC)


def stable_hash(payload: Any, *, length: int = 24) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AlternativeMeConfig(_Frozen):
    enabled: bool = True
    training_enabled: Literal[False] = False
    historical_fetch_enabled: bool = True
    base_url: str = "https://api.alternative.me"
    endpoint: Literal["/fng/"] = "/fng/"
    cache_max_age_hours: float = Field(default=20.0, gt=0)
    feature_max_staleness_hours: float = Field(default=48.0, gt=0)


class OpenInterestConfig(_Frozen):
    enabled: bool = True
    training_enabled: Literal[False] = False
    recent_history_enabled: bool = True
    current_snapshot_enabled: bool = True
    base_url: str = "https://fapi.binance.com"
    current_endpoint: Literal["/fapi/v1/openInterest"] = "/fapi/v1/openInterest"
    history_endpoint: Literal["/futures/data/openInterestHist"] = "/futures/data/openInterestHist"
    period: Literal["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"] = "5m"
    history_limit: int = Field(default=500, ge=1, le=500)
    recent_history_days: int = Field(default=30, ge=1, le=31)
    symbols: tuple[str, ...] = ("BTCUSDT",)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip().upper() for item in value)
        if not normalized or any(not item for item in normalized):
            raise ValueError("open-interest symbols must be non-empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("open-interest symbols must be unique")
        return normalized


class DisabledProviderConfig(_Frozen):
    enabled: Literal[False] = False


class HttpConfig(_Frozen):
    timeout_seconds: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: float = Field(default=0.5, ge=0)


class ContextConfig(_Frozen):
    enabled: bool = True
    data_root: Path = Path("data/context")
    research_cutoff: datetime = PHASE7_RESEARCH_CUTOFF
    prospective_holdout_start: datetime = PROSPECTIVE_HOLDOUT_START
    july_2026_used: Literal[False] = False
    prospective_holdout_used: Literal[False] = False
    alternative_me: AlternativeMeConfig = AlternativeMeConfig()
    open_interest: OpenInterestConfig = OpenInterestConfig()
    cryptopanic: DisabledProviderConfig = DisabledProviderConfig()
    arkham: DisabledProviderConfig = DisabledProviderConfig()
    reddit: DisabledProviderConfig = DisabledProviderConfig()
    http: HttpConfig = HttpConfig()

    @field_validator("research_cutoff", "prospective_holdout_start")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("context safety boundaries must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def lock_phase7_non_interference(self) -> Self:
        if self.research_cutoff != PHASE7_RESEARCH_CUTOFF:
            raise ValueError("context research cutoff must preserve the Phase 7 cutoff")
        if self.prospective_holdout_start != PROSPECTIVE_HOLDOUT_START:
            raise ValueError("context holdout start must preserve the Phase 7 holdout")
        return self

    @property
    def configuration_hash(self) -> str:
        return stable_hash(self.model_dump(mode="json"))

    def assert_network_allowed(self) -> None:
        if os.environ.get(CONTEXT_NETWORK_GUARD) != "1":
            raise RuntimeError(
                "Context network access is locked; set CRYPTO_AI_ALLOW_CONTEXT_NETWORK=1 "
                "only for an explicit one-shot public-data collection"
            )


def load_context_config(path: Path) -> ContextConfig:
    path = path.resolve()
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    root = raw.get("context")
    if not isinstance(root, dict):
        raise ValueError(f"{path} must contain a [context] table")
    merged = dict(root)
    for section in ("alternative_me", "open_interest", "cryptopanic", "arkham", "reddit", "http"):
        payload = raw.get(f"context.{section}")
        if payload is None:
            payload = raw.get(section)
        if payload is not None:
            merged[section] = payload
    return ContextConfig.model_validate(merged)
