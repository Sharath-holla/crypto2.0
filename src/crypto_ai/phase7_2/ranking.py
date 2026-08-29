from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from crypto_ai.contracts.versioning import canonical_sha256

CROSS_ASSET_RANKING_VERSION = "cross_asset_ranking_v1"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC")


class RankingCandidate(_Frozen):
    symbol: str
    feature_time: datetime
    fold_id: str
    relevance: Decimal | None
    historically_eligible: bool
    later_delisted: bool = False

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        _require_utc(self.feature_time, "feature_time")
        if not self.symbol.strip() or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be normalized uppercase")
        if not self.fold_id.strip():
            raise ValueError("fold_id is required")
        if not self.historically_eligible:
            raise ValueError("ranking candidates must be historically eligible")
        return self


class RankingRow(_Frozen):
    symbol: str
    feature_time: datetime
    fold_id: str
    relevance: Decimal | None
    target_available: bool
    later_delisted: bool


class RankingGroup(_Frozen):
    group_id: str
    feature_time: datetime
    fold_id: str
    rows: tuple[RankingRow, ...]
    membership_source: Literal["fold_active_symbols"] = "fold_active_symbols"
    dataset_version: Literal["cross_asset_ranking_v1"] = CROSS_ASSET_RANKING_VERSION

    @model_validator(mode="after")
    def validate_group(self) -> Self:
        _require_utc(self.feature_time, "feature_time")
        symbols = [row.symbol for row in self.rows]
        if symbols != sorted(symbols) or len(symbols) != len(set(symbols)):
            raise ValueError("ranking group rows must be unique and sorted by symbol")
        if any(
            row.feature_time != self.feature_time or row.fold_id != self.fold_id
            for row in self.rows
        ):
            raise ValueError("ranking group row identity mismatch")
        expected = canonical_sha256(
            {
                "dataset_version": self.dataset_version,
                "feature_time": self.feature_time,
                "fold_id": self.fold_id,
                "symbols": symbols,
            }
        )
        if self.group_id != expected:
            raise ValueError("ranking group identity mismatch")
        return self

    @property
    def target_available_count(self) -> int:
        return sum(row.target_available for row in self.rows)


def build_ranking_groups(
    candidates: Iterable[RankingCandidate],
    *,
    fold_active_symbols: Mapping[datetime, frozenset[str]],
) -> tuple[RankingGroup, ...]:
    supplied = tuple(candidates)
    identities = [(row.fold_id, row.feature_time, row.symbol) for row in supplied]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate ranking candidate")

    grouped: dict[tuple[str, datetime], list[RankingCandidate]] = defaultdict(list)
    for candidate in supplied:
        active = fold_active_symbols.get(candidate.feature_time)
        if active is None:
            raise ValueError(
                f"missing fold_active_symbols for {candidate.feature_time.isoformat()}"
            )
        if candidate.symbol not in active:
            continue
        grouped[(candidate.fold_id, candidate.feature_time)].append(candidate)

    result: list[RankingGroup] = []
    for (fold_id, feature_time), rows in sorted(
        grouped.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        active = fold_active_symbols[feature_time]
        selected = sorted(rows, key=lambda row: row.symbol)
        if any(row.symbol not in active for row in selected):
            raise AssertionError("ranking membership escaped fold_active_symbols")
        ranking_rows = tuple(
            RankingRow(
                symbol=row.symbol,
                feature_time=row.feature_time,
                fold_id=row.fold_id,
                relevance=row.relevance,
                target_available=row.relevance is not None,
                later_delisted=row.later_delisted,
            )
            for row in selected
        )
        group_id = canonical_sha256(
            {
                "dataset_version": CROSS_ASSET_RANKING_VERSION,
                "feature_time": feature_time,
                "fold_id": fold_id,
                "symbols": [row.symbol for row in ranking_rows],
            }
        )
        result.append(
            RankingGroup(
                group_id=group_id,
                feature_time=feature_time,
                fold_id=fold_id,
                rows=ranking_rows,
            )
        )
    return tuple(result)
