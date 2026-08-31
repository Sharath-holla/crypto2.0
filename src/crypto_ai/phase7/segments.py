from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class AcquisitionStatus(StrEnum):
    VALID = "VALID"
    QUALITY_REJECTED_SEGMENT = "QUALITY_REJECTED_SEGMENT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    LIFECYCLE_ABSENCE = "LIFECYCLE_ABSENCE"


class ReconciliationStatus(StrEnum):
    CORRECTED = "CORRECTED"
    IDENTICAL_INVALID = "IDENTICAL_INVALID"
    NOT_PROVEN = "NOT_PROVEN"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CausalDataGap(_Frozen):
    symbol: str
    interval: str
    start: datetime
    end: datetime
    partition: str
    failed_checks: tuple[str, ...]
    source_manifest: str
    source_manifest_sha256: str
    quality_report: str
    quality_report_sha256: str
    quarantine: str
    quarantine_sha256: str
    rest_manifest: str
    rest_manifest_sha256: str
    comparison_report: str
    comparison_report_sha256: str
    reconciliation_status: ReconciliationStatus
    unusable_data_gap: bool = True
    causal_consequences: tuple[str, ...] = (
        "no_silver_row_for_rejected_interval",
        "no_feature_or_target_may_bridge_gap",
        "fold_requires_contiguous_history",
        "future_gap_cannot_disqualify_earlier_fold",
    )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("causal gap symbol cannot be empty")
        return normalized

    @field_validator("start", "end")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("causal gap timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.start >= self.end:
            raise ValueError("causal gap must be a non-empty half-open interval")
        if not self.failed_checks:
            raise ValueError("causal gap requires explicit failed checks")
        if self.reconciliation_status not in {
            ReconciliationStatus.IDENTICAL_INVALID,
            ReconciliationStatus.NOT_PROVEN,
        }:
            raise ValueError("causal gaps require inconclusive official-source reconciliation")
        return self

    def intersects(self, start: datetime, end: datetime) -> bool:
        return self.start < end.astimezone(UTC) and self.end > start.astimezone(UTC)


class AcquisitionOutcome(_Frozen):
    symbol: str
    interval: str
    status: AcquisitionStatus
    silver_manifest: str | None = None
    reason: str | None = None
    gaps: tuple[CausalDataGap, ...] = ()

    @field_validator("symbol")
    @classmethod
    def normalize_outcome_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("acquisition outcome symbol cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is AcquisitionStatus.VALID and self.silver_manifest is None:
            raise ValueError("valid acquisition requires a Silver manifest")
        if self.status is AcquisitionStatus.QUALITY_REJECTED_SEGMENT and (
            self.silver_manifest is None or not self.gaps
        ):
            raise ValueError("segmented acquisition requires Silver lineage and gaps")
        if self.status is AcquisitionStatus.LIFECYCLE_ABSENCE and self.silver_manifest is not None:
            raise ValueError("lifecycle absence cannot have a Silver manifest")
        return self


@dataclass(frozen=True, slots=True)
class CandleFamilyAcquisition:
    outcomes: tuple[AcquisitionOutcome, ...]

    @property
    def manifests(self) -> dict[str, str]:
        return {
            outcome.symbol: outcome.silver_manifest
            for outcome in self.outcomes
            if outcome.silver_manifest is not None
        }

    @property
    def gaps(self) -> tuple[CausalDataGap, ...]:
        return tuple(gap for outcome in self.outcomes for gap in outcome.gaps)

    def model_dump(self) -> dict[str, object]:
        return {
            "outcomes": [outcome.model_dump(mode="json") for outcome in self.outcomes],
            "unusable_segments": [gap.model_dump(mode="json") for gap in self.gaps],
        }
