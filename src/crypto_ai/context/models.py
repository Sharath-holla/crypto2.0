from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class TrainingEligibility(StrEnum):
    HISTORICAL_RESEARCH_CANDIDATE = "HISTORICAL_RESEARCH_CANDIDATE"
    FORWARD_ONLY = "FORWARD_ONLY"
    NOT_TRAINING_ELIGIBLE = "NOT_TRAINING_ELIGIBLE"
    DISABLED = "DISABLED"

    @property
    def training_eligible(self) -> bool:
        return self is self.HISTORICAL_RESEARCH_CANDIDATE


class ObservationClass(StrEnum):
    HISTORICAL_RESEARCH_DATA = "HISTORICAL_RESEARCH_DATA"
    FORWARD_OBSERVATION_DATA = "FORWARD_OBSERVATION_DATA"


class ProviderCapability(StrEnum):
    HISTORICAL_FETCH = "HISTORICAL_FETCH"
    RECENT_HISTORY = "RECENT_HISTORY"
    CURRENT_SNAPSHOT = "CURRENT_SNAPSHOT"
    RESEARCH_FEATURES = "RESEARCH_FEATURES"


class ProviderStatus(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    DISABLED = "DISABLED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True, slots=True)
class CollectionResult:
    dataset_version: str
    dataset_path: Path
    manifest_path: Path
    raw_path: Path
    row_count: int
    duplicate_count: int
    reused: bool
