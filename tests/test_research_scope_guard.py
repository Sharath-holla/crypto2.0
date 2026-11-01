"""Holdout hygiene: acquisition cannot enter July/August 2026 (defect 17)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_ai import cli
from crypto_ai.research_scope import (
    GUARDED_ACQUISITION_COMMANDS,
    RESEARCH_CUTOFF_EXCLUSIVE,
    ResearchScopeViolation,
    assert_acquisition_in_research_scope,
)

ROOT = Path(__file__).resolve().parents[1]


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def test_cutoff_is_frozen_phase7a_value() -> None:
    assert RESEARCH_CUTOFF_EXCLUSIVE == _utc(2026, 7, 1)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (_utc(2020, 1, 1), _utc(2026, 7, 1)),
        (_utc(2026, 6, 30, 23), _utc(2026, 7, 1)),
        (_utc(2020, 1, 1), _utc(2021, 1, 1)),
    ],
)
def test_in_scope_ranges_are_allowed(start: datetime, end: datetime) -> None:
    assert_acquisition_in_research_scope(start, end, command="download-archive")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (_utc(2020, 1, 1), _utc(2026, 8, 1)),
        (_utc(2026, 7, 1), _utc(2026, 7, 2)),
        (_utc(2026, 8, 1), _utc(2026, 8, 1, 1)),
        (_utc(2026, 6, 30), _utc(2026, 7, 1, 0, 0, 1)),
        (_utc(2020, 1, 1), None),
        (None, _utc(2021, 1, 1)),
        (_utc(2021, 1, 2), _utc(2021, 1, 1)),
    ],
)
def test_forbidden_or_open_ended_ranges_are_rejected(start, end) -> None:
    with pytest.raises(ResearchScopeViolation):
        assert_acquisition_in_research_scope(start, end, command="download")


@pytest.mark.parametrize(
    "arguments",
    [
        ["download", "--start", "2026-07-01T00:00:00Z", "--end", "2026-07-01T01:00:00Z"],
        ["download-archive", "--start", "2020-01-01T00:00:00Z", "--end", "2026-08-01T00:00:00Z"],
        [
            "download-market-data",
            "--kind",
            "funding",
            "--start",
            "2026-07-01T00:00:00Z",
            "--end",
            "2026-08-01T00:00:00Z",
        ],
    ],
)
def test_cli_refuses_forbidden_ranges_before_any_network_or_config_access(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network/client must not be reached")

    monkeypatch.setattr(cli, "BinanceRestClient", forbidden)
    with pytest.raises(ResearchScopeViolation):
        cli.main(arguments)


def test_all_acquisition_commands_are_guarded() -> None:
    assert GUARDED_ACQUISITION_COMMANDS == {
        "download",
        "download-archive",
        "download-market-data",
        "download-market-archive",
    }


def test_documented_download_examples_stay_inside_the_research_window() -> None:
    pattern = re.compile(
        r"crypto-ai (?:download|download-archive|download-market-data|download-market-archive)"
        r".{0,160}?--end\s+(\S+)",
        re.DOTALL,
    )
    for name in ("README.md", "docs/RUNBOOK.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            end = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            assert end <= RESEARCH_CUTOFF_EXCLUSIVE, (name, match.group(0)[:120])
