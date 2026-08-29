from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_ai.phase7_2.ranking import RankingCandidate, build_ranking_groups


def _candidate(
    symbol: str,
    feature_time: datetime,
    relevance: str | None,
    *,
    later_delisted: bool = False,
) -> RankingCandidate:
    return RankingCandidate(
        symbol=symbol,
        feature_time=feature_time,
        fold_id="fold-001",
        relevance=Decimal(relevance) if relevance is not None else None,
        historically_eligible=True,
        later_delisted=later_delisted,
    )


def test_groups_use_only_fold_active_symbols() -> None:
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    group = build_ranking_groups(
        (
            _candidate("BTCUSDT", timestamp, "0.1"),
            _candidate("ETHUSDT", timestamp, "0.2"),
            _candidate("FUTUREUSDT", timestamp, "0.9"),
        ),
        fold_active_symbols={timestamp: frozenset({"BTCUSDT", "ETHUSDT"})},
    )[0]
    assert [row.symbol for row in group.rows] == ["BTCUSDT", "ETHUSDT"]
    assert group.membership_source == "fold_active_symbols"


def test_future_symbol_addition_cannot_change_earlier_group() -> None:
    earlier = datetime(2025, 1, 1, tzinfo=UTC)
    later = earlier + timedelta(days=90)
    base = (
        _candidate("BTCUSDT", earlier, "0.1"),
        _candidate("ETHUSDT", earlier, "0.2"),
    )
    before = build_ranking_groups(
        base,
        fold_active_symbols={earlier: frozenset({"BTCUSDT", "ETHUSDT"})},
    )[0]
    after = build_ranking_groups(
        (*base, _candidate("NEWUSDT", later, "0.3")),
        fold_active_symbols={
            earlier: frozenset({"BTCUSDT", "ETHUSDT"}),
            later: frozenset({"BTCUSDT", "ETHUSDT", "NEWUSDT"}),
        },
    )[0]
    assert after == before


def test_rank_group_order_and_identity_are_deterministic() -> None:
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    rows = (
        _candidate("ETHUSDT", timestamp, "0.2"),
        _candidate("BTCUSDT", timestamp, "0.1"),
    )
    active = {timestamp: frozenset({"BTCUSDT", "ETHUSDT"})}
    forward = build_ranking_groups(rows, fold_active_symbols=active)[0]
    reverse = build_ranking_groups(tuple(reversed(rows)), fold_active_symbols=active)[0]
    assert forward == reverse
    assert [row.symbol for row in forward.rows] == ["BTCUSDT", "ETHUSDT"]


def test_missing_target_is_preserved_but_not_marked_available() -> None:
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    group = build_ranking_groups(
        (_candidate("BTCUSDT", timestamp, None),),
        fold_active_symbols={timestamp: frozenset({"BTCUSDT"})},
    )[0]
    assert group.target_available_count == 0
    assert group.rows[0].relevance is None
    assert group.rows[0].target_available is False


def test_later_delisted_symbol_remains_when_historically_active() -> None:
    timestamp = datetime(2023, 1, 1, tzinfo=UTC)
    group = build_ranking_groups(
        (_candidate("OLDUSDT", timestamp, "0.4", later_delisted=True),),
        fold_active_symbols={timestamp: frozenset({"OLDUSDT"})},
    )[0]
    assert group.rows[0].later_delisted is True


def test_duplicate_candidate_is_rejected() -> None:
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    row = _candidate("BTCUSDT", timestamp, "0.1")
    with pytest.raises(ValueError, match="duplicate"):
        build_ranking_groups(
            (row, row),
            fold_active_symbols={timestamp: frozenset({"BTCUSDT"})},
        )
