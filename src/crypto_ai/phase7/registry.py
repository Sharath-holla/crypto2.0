from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.phase7.config import SYMBOL_REGISTRY_VERSION, stable_hash

OFFICIAL_EXCHANGE_INFO_URL = (
    "https://developers.binance.com/en/docs/catalog/"
    "core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data"
    "#exchange-information"
)
OFFICIAL_ARCHIVE_URL = "https://github.com/binance/binance-public-data/blob/master/README.md"


def _utc(value: datetime | str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1_000, tz=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("symbol registry timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageSummary(_Frozen):
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    expected_rows: int = Field(default=0, ge=0)
    actual_rows: int = Field(default=0, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    gap_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    zero_volume_count: int = Field(default=0, ge=0)
    warnings: tuple[str, ...] = ()

    @field_validator("first_timestamp", "last_timestamp", mode="before")
    @classmethod
    def normalize_time(cls, value: object) -> datetime | None:
        return _utc(value)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if (
            self.first_timestamp
            and self.last_timestamp
            and self.last_timestamp < self.first_timestamp
        ):
            raise ValueError("coverage last timestamp precedes first timestamp")
        return self


class SymbolRecord(_Frozen):
    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str
    first_market_data_time: datetime
    last_market_data_time: datetime
    current_status: str
    onboard_date: datetime | None = None
    availability_evidence: Literal[
        "VERIFIED_MARKET_DATA_TIMESTAMPS", "OFFICIAL_ARCHIVE_PERIOD_EVIDENCE"
    ] = "VERIFIED_MARKET_DATA_TIMESTAMPS"
    available_from: datetime
    available_until: datetime | None = None
    history_days: float = Field(ge=0)
    available_intervals: tuple[str, ...]
    coverage_5m: CoverageSummary = CoverageSummary()
    coverage_12h: CoverageSummary = CoverageSummary()
    coverage_1d: CoverageSummary = CoverageSummary()
    funding_coverage: CoverageSummary = CoverageSummary()
    mark_coverage: CoverageSummary = CoverageSummary()
    index_coverage: CoverageSummary = CoverageSummary()
    metadata_sources: tuple[str, ...]

    @field_validator("symbol", "base_asset", "quote_asset", "contract_type", "current_status")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol registry text fields cannot be empty")
        return normalized

    @field_validator(
        "first_market_data_time",
        "last_market_data_time",
        "onboard_date",
        "available_from",
        "available_until",
        mode="before",
    )
    @classmethod
    def normalize_times(cls, value: object) -> datetime | None:
        return _utc(value)  # type: ignore[arg-type]

    @field_validator("available_intervals", "metadata_sources")
    @classmethod
    def unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("registry interval/source lists must be non-empty and unique")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.last_market_data_time < self.first_market_data_time:
            raise ValueError("last market data precedes first market data")
        if self.available_from > self.first_market_data_time:
            raise ValueError("available_from cannot follow first verified market data")
        if self.available_until and self.available_until <= self.available_from:
            raise ValueError("available_until must follow available_from")
        return self

    def exists_at(self, timestamp: datetime) -> bool:
        value = _utc(timestamp)
        assert value is not None
        return self.available_from <= value and (
            self.available_until is None or value < self.available_until
        )


class SymbolRegistry(_Frozen):
    version: str = SYMBOL_REGISTRY_VERSION
    observed_at: datetime
    research_cutoff: datetime
    records: tuple[SymbolRecord, ...]
    source_urls: tuple[str, ...] = (OFFICIAL_EXCHANGE_INFO_URL, OFFICIAL_ARCHIVE_URL)
    registry_hash: str
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = "LOCKED_UNUSED"
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False

    @field_validator("observed_at", "research_cutoff", mode="before")
    @classmethod
    def normalize_time(cls, value: object) -> datetime:
        result = _utc(value)  # type: ignore[arg-type]
        if result is None:
            raise ValueError("registry time is required")
        return result

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        symbols = [record.symbol for record in self.records]
        if symbols != sorted(symbols) or len(symbols) != len(set(symbols)):
            raise ValueError("registry records must be unique and symbol-sorted")
        expected = registry_identity(self.records, self.research_cutoff)
        if self.registry_hash != expected:
            raise ValueError("symbol registry hash does not match its records")
        return self

    def by_symbol(self) -> dict[str, SymbolRecord]:
        return {record.symbol: record for record in self.records}


def registry_identity(records: tuple[SymbolRecord, ...], research_cutoff: datetime) -> str:
    return stable_hash(
        {
            "version": SYMBOL_REGISTRY_VERSION,
            "research_cutoff": _utc(research_cutoff),
            "records": [record.model_dump(mode="json") for record in records],
        }
    )


def _coverage(payload: Any) -> CoverageSummary:
    return CoverageSummary.model_validate(payload or {})


def build_symbol_registry(
    exchange_info: dict[str, Any],
    historical_evidence: list[dict[str, Any]],
    *,
    observed_at: datetime,
    research_cutoff: datetime,
) -> SymbolRegistry:
    """Union current metadata with official historical archive evidence.

    `historical_evidence` is deliberately the universe driver. A contract that
    disappeared from current exchangeInfo remains represented when official
    archive keys or validated manifests establish its historical existence.
    """

    current = {
        str(item.get("symbol", "")).upper(): item
        for item in exchange_info.get("symbols", [])
        if isinstance(item, dict) and item.get("symbol")
    }
    historical = {
        str(item.get("symbol", "")).upper(): item
        for item in historical_evidence
        if isinstance(item, dict) and item.get("symbol")
    }
    records: list[SymbolRecord] = []
    cutoff = _utc(research_cutoff)
    captured = _utc(observed_at)
    if cutoff is None or captured is None:
        raise ValueError("registry timestamps are required")
    for symbol in sorted(set(current) | set(historical)):
        metadata = current.get(symbol, {})
        evidence = historical.get(symbol, {})
        first = _utc(evidence.get("first_market_data_time") or evidence.get("first_timestamp"))
        last = _utc(evidence.get("last_market_data_time") or evidence.get("last_timestamp"))
        onboard = _utc(metadata.get("onboardDate") or evidence.get("onboard_date"))
        if first is None or last is None:
            continue
        effective_last = min(last, cutoff - timedelta(microseconds=1))
        if effective_last < first or first >= cutoff:
            continue
        status = str(metadata.get("status") or evidence.get("current_status") or "INACTIVE")
        is_current = status.upper() == "TRADING" and symbol in current
        evidence_until = _utc(evidence.get("available_until"))
        if is_current:
            available_until = cutoff
        elif evidence_until is not None:
            available_until = min(evidence_until, cutoff)
        else:
            available_until = min(effective_last + timedelta(minutes=5), cutoff)
        # Onboard time is descriptive metadata, not proof that canonical rows
        # exist. Never make the point-in-time data boundary precede the first
        # official market-data evidence.
        available_from = first
        interval_values = tuple(
            sorted({str(value) for value in evidence.get("available_intervals", ())})
        )
        if not interval_values:
            interval_values = tuple(
                name
                for name, key in (
                    ("5m", "coverage_5m"),
                    ("12h", "coverage_12h"),
                    ("1d", "coverage_1d"),
                )
                if evidence.get(key)
            )
        if not interval_values:
            interval_values = ("5m",)
        sources = tuple(
            sorted(
                set(evidence.get("metadata_sources", ()))
                | ({"exchangeInfo"} if metadata else set())
                | {"official_archive"}
            )
        )
        record = SymbolRecord(
            symbol=symbol,
            base_asset=str(metadata.get("baseAsset") or evidence.get("base_asset") or symbol),
            quote_asset=str(metadata.get("quoteAsset") or evidence.get("quote_asset") or "USDT"),
            contract_type=str(
                metadata.get("contractType") or evidence.get("contract_type") or "PERPETUAL"
            ),
            first_market_data_time=first,
            last_market_data_time=effective_last,
            current_status=status,
            onboard_date=onboard,
            availability_evidence=str(
                evidence.get("availability_evidence") or "VERIFIED_MARKET_DATA_TIMESTAMPS"
            ),
            available_from=available_from,
            available_until=available_until,
            history_days=max(0.0, (effective_last - first).total_seconds() / 86_400),
            available_intervals=interval_values,
            coverage_5m=_coverage(evidence.get("coverage_5m")),
            coverage_12h=_coverage(evidence.get("coverage_12h")),
            coverage_1d=_coverage(evidence.get("coverage_1d")),
            funding_coverage=_coverage(evidence.get("funding_coverage")),
            mark_coverage=_coverage(evidence.get("mark_coverage")),
            index_coverage=_coverage(evidence.get("index_coverage")),
            metadata_sources=sources,
        )
        records.append(record)
    ordered = tuple(records)
    return SymbolRegistry(
        observed_at=captured,
        research_cutoff=cutoff,
        records=ordered,
        registry_hash=registry_identity(ordered, cutoff),
    )


def write_registry(path: Path, registry: SymbolRegistry) -> Path:
    path = path.resolve()
    payload = json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"Refusing to overwrite different symbol registry: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def read_registry(path: Path) -> SymbolRegistry:
    return SymbolRegistry.model_validate(json.loads(path.read_text(encoding="utf-8")))
