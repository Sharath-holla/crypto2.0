"""Research-scope date guard for data acquisition.

The Phase 7A research window ends at 2026-07-01T00:00:00Z (exclusive).  July
2026 is outside the current experiment and August 2026 is the LOCKED_UNUSED
prospective holdout.  Acquisition commands refuse any request that reaches
either range; there is deliberately no override flag.  Historical evidence that
already exists on disk is never deleted by this guard.
"""

from __future__ import annotations

from datetime import UTC, datetime

RESEARCH_CUTOFF_EXCLUSIVE = datetime(2026, 7, 1, tzinfo=UTC)
GUARDED_ACQUISITION_COMMANDS = frozenset(
    {"download", "download-archive", "download-market-data", "download-market-archive"}
)


class ResearchScopeViolation(ValueError):
    """Raised when an acquisition request would enter a forbidden date range."""


def assert_acquisition_in_research_scope(
    start: datetime | None, end: datetime | None, *, command: str
) -> None:
    """Fail closed unless ``[start, end)`` lies entirely before the research cutoff."""

    if start is None or end is None:
        raise ResearchScopeViolation(
            f"{command}: acquisition requires explicit --start and --end inside the research "
            "window; an open-ended range could reach the locked holdout"
        )
    if any(value.tzinfo is None or value.utcoffset() is None for value in (start, end)):
        raise ResearchScopeViolation(f"{command}: acquisition timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise ResearchScopeViolation(f"{command}: --end must be after --start")
    if end > RESEARCH_CUTOFF_EXCLUSIVE:
        raise ResearchScopeViolation(
            f"{command}: requested range ends {end.isoformat()} which is after the research "
            f"cutoff {RESEARCH_CUTOFF_EXCLUSIVE.isoformat()} (exclusive); July 2026 is outside "
            "the current experiment and August 2026 is the LOCKED_UNUSED holdout"
        )
