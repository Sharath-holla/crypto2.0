from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_missing_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    allowed_duplicate_count: int = Field(default=0, ge=0)
    maximum_consecutive_missing_intervals: int = Field(default=0, ge=0)
    zero_volume_warning_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    zero_volume_failure_percentage: float = Field(default=5.0, ge=0.0, le=100.0)
    outlier_window: int = Field(default=21, ge=5, le=10_000)
    outlier_min_observations: int = Field(default=7, ge=3)
    outlier_mad_threshold: float = Field(default=12.0, gt=0.0)
    stale_flat_run_warning: int = Field(default=3, ge=2)
    stale_flat_run_failure: int = Field(default=12, ge=2)
    ingestion_future_tolerance_seconds: int = Field(default=300, ge=0)
    allow_warnings_for_silver: bool = True
    sample_limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if self.zero_volume_warning_percentage > self.zero_volume_failure_percentage:
            raise ValueError("zero_volume_warning_percentage cannot exceed the failure percentage")
        if self.outlier_min_observations > self.outlier_window:
            raise ValueError("outlier_min_observations cannot exceed outlier_window")
        if self.stale_flat_run_warning > self.stale_flat_run_failure:
            raise ValueError("stale warning run cannot exceed stale failure run")
        return self


def load_quality_policy(path: Path | None = None) -> QualityPolicy:
    if path is None:
        return QualityPolicy()
    with path.open("rb") as stream:
        payload = tomllib.load(stream)
    section = payload.get("quality")
    if not isinstance(section, dict):
        raise ValueError(f"{path} must contain a [quality] table")
    return QualityPolicy.model_validate(section)
