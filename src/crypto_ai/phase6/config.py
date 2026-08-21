from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.domain import interval_milliseconds

PHASE6_VERSION = "1.1.0"
FEATURE_RESEARCH_VERSION = "market_v3_research-1.0.0"
LABEL_RESEARCH_VERSION = "label_v2_research-1.0.0"


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


class Phase6Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = "BTCUSDT"
    decision_interval: str = "5m"
    silver_5m_manifests: tuple[Path, ...]
    silver_12h_manifests: tuple[Path, ...]
    silver_1d_manifests: tuple[Path, ...]
    silver_1m_manifest: Path | None = None
    funding_manifest: Path | None = None
    mark_manifest: Path | None = None
    index_manifest: Path | None = None
    phase6_research_cutoff: datetime
    prospective_holdout_start: datetime
    output_root: Path = Path("local_artifacts/phase6/research_v1")
    gold_root: Path = Path("data/gold/phase6_research")
    sample_every_n_rows: int = Field(default=12, ge=1)
    seed: int = 42
    redundancy_threshold: float = Field(default=0.98, gt=0, le=1)
    ridge_alpha: float = Field(default=10.0, gt=0)
    lightgbm_estimators: int = Field(default=120, ge=20, le=1000)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be empty")
        return normalized

    @field_validator("decision_interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        interval_milliseconds(value)
        if value != "5m":
            raise ValueError("Phase 6 decision infrastructure is leakage-reviewed for 5m")
        return value

    @field_validator("silver_5m_manifests", "silver_12h_manifests", "silver_1d_manifests")
    @classmethod
    def validate_manifests(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("Each Silver family needs unique non-empty manifests")
        return value

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        for name in ("phase6_research_cutoff", "prospective_holdout_start"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.phase6_research_cutoff >= self.prospective_holdout_start:
            raise ValueError("Phase 6 research cutoff must precede the prospective holdout")
        safe_latest = datetime(2026, 7, 9, tzinfo=UTC)
        if self.phase6_research_cutoff > safe_latest:
            raise ValueError("Phase 6 cannot consume the preserved July buffer")
        if self.prospective_holdout_start != datetime(2026, 8, 1, tzinfo=UTC):
            raise ValueError("Prospective holdout boundary is permanently locked")
        if (self.mark_manifest is None) != (self.index_manifest is None):
            raise ValueError("mark and index manifests must be configured together")
        return self

    @property
    def config_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


def load_phase6_config(path: Path) -> Phase6Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    section = raw.get("phase6")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain a [phase6] table")
    return Phase6Config.model_validate(section)
