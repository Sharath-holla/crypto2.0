from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaptureDataset(StrEnum):
    OPEN_INTEREST = "OPEN_INTEREST"
    BBO = "BBO"
    DEPTH_SUMMARY = "DEPTH_SUMMARY"
    LIQUIDATION_EVENT = "LIQUIDATION_EVENT"
    EXCHANGE_METADATA = "EXCHANGE_METADATA"


@dataclass(frozen=True, slots=True)
class ProspectiveSymbolPolicy:
    max_symbols: int = 30
    include_core: bool = True
    include_expansion: bool = True
    enabled: bool = False

    def __post_init__(self) -> None:
        if self.max_symbols <= 0:
            raise ValueError("max_symbols must be positive")

    def select(
        self,
        *,
        fold_active_core: tuple[str, ...],
        fold_active_expansion: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Build a deterministic future collector list from already-frozen membership."""

        ordered: list[str] = []
        sources = []
        if self.include_core:
            sources.append(fold_active_core)
        if self.include_expansion:
            sources.append(fold_active_expansion)
        for source in sources:
            for symbol in source:
                normalized = symbol.strip().upper()
                if not normalized:
                    raise ValueError("capture symbols must be non-empty")
                if normalized not in ordered:
                    ordered.append(normalized)
        return tuple(ordered[: self.max_symbols])


@dataclass(frozen=True, slots=True)
class CaptureSpecification:
    dataset: CaptureDataset
    schema_version: str
    cadence: str
    enabled: bool = False
    network_enabled: bool = False
    collector_started: bool = False
    storage_format: str = "PARQUET"
    full_raw_l2: bool = False

    def __post_init__(self) -> None:
        if not self.schema_version.strip() or not self.cadence.strip():
            raise ValueError("capture schema and cadence are required")
        if self.enabled or self.network_enabled or self.collector_started:
            raise ValueError("Phase 7.2 capture specifications are design-only and disabled")
        if self.full_raw_l2:
            raise ValueError("raw L2 capture is not authorized in Phase 7.2")


def default_capture_plan() -> tuple[CaptureSpecification, ...]:
    return (
        CaptureSpecification(
            CaptureDataset.OPEN_INTEREST,
            "open_interest_observation_v1",
            "5m forward-only",
        ),
        CaptureSpecification(CaptureDataset.BBO, "bbo_observation_v1", "bounded snapshot"),
        CaptureSpecification(
            CaptureDataset.DEPTH_SUMMARY,
            "depth_summary_v1",
            "bounded summary snapshot",
        ),
        CaptureSpecification(
            CaptureDataset.LIQUIDATION_EVENT,
            "liquidation_event_v1",
            "event stream",
        ),
        CaptureSpecification(
            CaptureDataset.EXCHANGE_METADATA,
            "exchange_symbol_metadata_v1",
            "change event and periodic snapshot",
        ),
    )
