from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from crypto_ai.contracts.versioning import SemanticVersion, canonical_sha256

_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


def _require_sha256(value: str, field: str) -> None:
    if not _HEX_64_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


class ModelArchitecture(StrEnum):
    G0 = "G0"
    C0 = "C0"
    P0 = "P0"
    H0 = "H0"


class RuntimeMode(StrEnum):
    DISABLED = "DISABLED"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class ModelLifecycle(StrEnum):
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    QUARANTINED = "QUARANTINED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class ModelContract:
    contract_version: SemanticVersion
    model_id: str
    model_version: str
    architecture: ModelArchitecture
    feature_contract: str
    target_contract: str
    configuration_hash: str
    code_revision: str
    artifact_sha256: str
    input_schema_sha256: str
    output_schema_sha256: str
    trained_through_exclusive: datetime
    research_cutoff_exclusive: datetime

    def __post_init__(self) -> None:
        for name in (
            "model_id",
            "model_version",
            "feature_contract",
            "target_contract",
            "configuration_hash",
            "code_revision",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("artifact_sha256", "input_schema_sha256", "output_schema_sha256"):
            _require_sha256(getattr(self, name), name)
        _require_utc(self.trained_through_exclusive, "trained_through_exclusive")
        _require_utc(self.research_cutoff_exclusive, "research_cutoff_exclusive")
        if self.trained_through_exclusive > self.research_cutoff_exclusive:
            raise ValueError("model training boundary cannot exceed the research cutoff")

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True, slots=True)
class PredictionEnvelope:
    prediction_id: str
    contract_version: SemanticVersion
    model_id: str
    model_version: str
    symbol: str
    feature_time: datetime
    emitted_at: datetime
    earliest_action_time: datetime
    horizon_minutes: int
    decision_latency_bars: int
    bar_interval_minutes: int
    target_version: str
    input_lineage_sha256: str
    expected_return: Decimal | None
    no_trade_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("prediction_id", "model_id", "model_version", "symbol", "target_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        _require_sha256(self.input_lineage_sha256, "input_lineage_sha256")
        for field, value in (
            ("feature_time", self.feature_time),
            ("emitted_at", self.emitted_at),
            ("earliest_action_time", self.earliest_action_time),
        ):
            _require_utc(value, field)
        if self.emitted_at < self.feature_time:
            raise ValueError("prediction cannot be emitted before its features are available")
        if self.decision_latency_bars <= 0 or self.bar_interval_minutes <= 0:
            raise ValueError("decision latency and bar interval must be positive")
        expected_action_time = self.feature_time + timedelta(
            minutes=self.decision_latency_bars * self.bar_interval_minutes
        )
        if self.earliest_action_time != expected_action_time:
            raise ValueError("earliest action time does not match the declared decision latency")
        if self.horizon_minutes <= 0:
            raise ValueError("prediction horizon must be positive")
        if self.expected_return is None and not self.no_trade_reason:
            raise ValueError("a missing forecast requires an explicit no-trade reason")
        if self.expected_return is not None and self.no_trade_reason:
            raise ValueError("a forecast and no-trade reason are mutually exclusive")

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True, slots=True)
class ModelDeploymentMetadata:
    model_identity_sha256: str
    lifecycle: ModelLifecycle
    requested_runtime_mode: RuntimeMode
    activation_authorized: bool
    validation_report_sha256: str
    rollback_model_identity_sha256: str | None = None
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.model_identity_sha256, "model_identity_sha256")
        _require_sha256(self.validation_report_sha256, "validation_report_sha256")
        if self.rollback_model_identity_sha256 is not None:
            _require_sha256(self.rollback_model_identity_sha256, "rollback_model_identity_sha256")
        if self.activation_authorized and not self.approval_reference:
            raise ValueError("runtime activation requires an explicit approval reference")


@runtime_checkable
class PredictionProvider(Protocol):
    """Structural interface for a future model-serving boundary."""

    def predict(self, *, symbol: str, feature_time: datetime) -> PredictionEnvelope: ...
