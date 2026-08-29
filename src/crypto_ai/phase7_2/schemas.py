from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

CANONICAL_MARKET_1M_VERSION = "canonical_market_1m_v1"
CANONICAL_MARKET_5M_VERSION = "canonical_market_5m_from_1m_v1"
OI_OBSERVATION_VERSION = "open_interest_observation_v1"
BBO_OBSERVATION_VERSION = "bbo_observation_v1"
DEPTH_SUMMARY_VERSION = "depth_summary_v1"
LIQUIDATION_EVENT_VERSION = "liquidation_event_v1"
EXCHANGE_METADATA_VERSION = "exchange_symbol_metadata_v1"
EVENT_CONTEXT_VERSION = "event_context_v1"


class DataQualityStatus(StrEnum):
    MISSING = "MISSING"
    STALE = "STALE"
    VALID = "VALID"
    INVALID = "INVALID"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class SymbolEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class LiquidationSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC")


def _require_nonnegative(value: Decimal | int, field: str) -> None:
    if value < 0:
        raise ValueError(f"{field} cannot be negative")


def _require_positive(value: Decimal, field: str) -> None:
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or normalized != value:
        raise ValueError("symbol must be non-empty normalized uppercase")
    return normalized


class _FrozenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_json(self) -> str:
        return self.model_dump_json()


class CanonicalMarket1m(_FrozenRecord):
    symbol: str
    interval_start: datetime
    interval_end: datetime
    availability_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_base: Decimal
    taker_buy_quote: Decimal
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    funding_state: Decimal | None = None
    missing_fields: tuple[str, ...] = ()
    quality_status: DataQualityStatus = DataQualityStatus.VALID
    symbol_eligibility_status: SymbolEligibilityStatus = SymbolEligibilityStatus.ELIGIBLE
    listing_age_days: int
    source_identity: str
    schema_version: Literal["canonical_market_1m_v1"] = CANONICAL_MARKET_1M_VERSION

    @field_validator("symbol")
    @classmethod
    def normalized_symbol(cls, value: str) -> str:
        return _require_symbol(value)

    @field_validator("missing_fields")
    @classmethod
    def normalized_missing_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({item.strip() for item in value if item.strip()}))
        if len(normalized) != len(value):
            raise ValueError("missing_fields must be unique non-empty names")
        return normalized

    @model_validator(mode="after")
    def validate_bar(self) -> Self:
        for field in ("interval_start", "interval_end", "availability_time"):
            _require_utc(getattr(self, field), field)
        if self.interval_end != self.interval_start + timedelta(minutes=1):
            raise ValueError("canonical 1m intervals must be half-open one-minute windows")
        if self.availability_time < self.interval_end:
            raise ValueError("a 1m row cannot be available before the interval is complete")
        for field in ("open", "high", "low", "close"):
            _require_positive(getattr(self, field), field)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC ordering is invalid")
        if self.high < self.low:
            raise ValueError("high cannot be below low")
        for field in (
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_base",
            "taker_buy_quote",
            "listing_age_days",
        ):
            _require_nonnegative(getattr(self, field), field)
        if self.taker_buy_base > self.volume or self.taker_buy_quote > self.quote_volume:
            raise ValueError("taker-buy volume cannot exceed total volume")
        for field in ("mark_price", "index_price"):
            value = getattr(self, field)
            if value is not None:
                _require_positive(value, field)
        if not self.source_identity.strip():
            raise ValueError("source_identity is required")
        return self

    @property
    def taker_sell_base(self) -> Decimal:
        return self.volume - self.taker_buy_base

    @property
    def taker_sell_quote(self) -> Decimal:
        return self.quote_volume - self.taker_buy_quote

    @property
    def identity(self) -> tuple[str, datetime]:
        return self.symbol, self.interval_start


class CanonicalMarket5m(_FrozenRecord):
    symbol: str
    interval_start: datetime
    interval_end: datetime
    availability_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_base: Decimal
    taker_buy_quote: Decimal
    source_row_count: Literal[5] = 5
    source_schema_version: Literal["canonical_market_1m_v1"] = CANONICAL_MARKET_1M_VERSION
    schema_version: Literal["canonical_market_5m_from_1m_v1"] = CANONICAL_MARKET_5M_VERSION

    @field_validator("symbol")
    @classmethod
    def normalized_symbol(cls, value: str) -> str:
        return _require_symbol(value)

    @model_validator(mode="after")
    def validate_bar(self) -> Self:
        for field in ("interval_start", "interval_end", "availability_time"):
            _require_utc(getattr(self, field), field)
        if self.interval_end != self.interval_start + timedelta(minutes=5):
            raise ValueError("derived 5m intervals must be half-open five-minute windows")
        if self.availability_time < self.interval_end:
            raise ValueError("a derived 5m row cannot predate final 1m availability")
        for field in ("open", "high", "low", "close"):
            _require_positive(getattr(self, field), field)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("derived OHLC ordering is invalid")
        if self.high < self.low:
            raise ValueError("derived high cannot be below low")
        for field in (
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_base",
            "taker_buy_quote",
        ):
            _require_nonnegative(getattr(self, field), field)
        if self.taker_buy_base > self.volume or self.taker_buy_quote > self.quote_volume:
            raise ValueError("derived taker-buy volume cannot exceed total volume")
        return self


class _TimedProspectiveRecord(_FrozenRecord):
    symbol: str
    event_time: datetime
    received_time: datetime
    availability_time: datetime
    source: str
    quality_status: DataQualityStatus

    @field_validator("symbol")
    @classmethod
    def normalized_symbol(cls, value: str) -> str:
        return _require_symbol(value)

    @model_validator(mode="after")
    def validate_timing(self) -> Self:
        for field in ("event_time", "received_time", "availability_time"):
            _require_utc(getattr(self, field), field)
        if not self.event_time <= self.received_time <= self.availability_time:
            raise ValueError("prospective timestamps must follow event <= received <= availability")
        if not self.source.strip():
            raise ValueError("source is required")
        return self


class OpenInterestObservation(_TimedProspectiveRecord):
    open_interest: Decimal
    open_interest_value: Decimal | None = None
    training_eligibility: Literal["FORWARD_ONLY"] = "FORWARD_ONLY"
    schema_version: Literal["open_interest_observation_v1"] = OI_OBSERVATION_VERSION

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        _require_nonnegative(self.open_interest, "open_interest")
        if self.open_interest_value is not None:
            _require_nonnegative(self.open_interest_value, "open_interest_value")
        return self


class BBOObservation(_TimedProspectiveRecord):
    bid: Decimal
    ask: Decimal
    bid_quantity: Decimal
    ask_quantity: Decimal
    mid: Decimal
    spread: Decimal
    spread_bps: Decimal
    sequence: int | None = None
    schema_version: Literal["bbo_observation_v1"] = BBO_OBSERVATION_VERSION

    @model_validator(mode="after")
    def validate_book(self) -> Self:
        for field in ("bid", "ask", "mid"):
            _require_positive(getattr(self, field), field)
        for field in ("bid_quantity", "ask_quantity", "spread", "spread_bps"):
            _require_nonnegative(getattr(self, field), field)
        if self.bid >= self.ask:
            raise ValueError("BBO requires bid < ask")
        expected_mid = (self.bid + self.ask) / Decimal(2)
        expected_spread = self.ask - self.bid
        expected_bps = expected_spread / expected_mid * Decimal(10_000)
        if self.mid != expected_mid or self.spread != expected_spread:
            raise ValueError("BBO mid/spread must exactly match bid and ask")
        if self.spread_bps != expected_bps:
            raise ValueError("spread_bps must exactly match bid and ask")
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        return self


class DepthSummary(_TimedProspectiveRecord):
    depth_10bps_bid: Decimal
    depth_10bps_ask: Decimal
    depth_25bps_bid: Decimal
    depth_25bps_ask: Decimal
    depth_50bps_bid: Decimal
    depth_50bps_ask: Decimal
    imbalance: Decimal
    microprice: Decimal | None
    spread: Decimal | None
    sequence_healthy: bool
    schema_version: Literal["depth_summary_v1"] = DEPTH_SUMMARY_VERSION

    @model_validator(mode="after")
    def validate_depth(self) -> Self:
        for field in (
            "depth_10bps_bid",
            "depth_10bps_ask",
            "depth_25bps_bid",
            "depth_25bps_ask",
            "depth_50bps_bid",
            "depth_50bps_ask",
        ):
            _require_nonnegative(getattr(self, field), field)
        if not Decimal(-1) <= self.imbalance <= Decimal(1):
            raise ValueError("depth imbalance must be between -1 and 1")
        if self.microprice is not None:
            _require_positive(self.microprice, "microprice")
        if self.spread is not None:
            _require_nonnegative(self.spread, "spread")
        return self


class LiquidationEvent(_TimedProspectiveRecord):
    side: LiquidationSide
    price: Decimal
    quantity: Decimal
    notional: Decimal
    schema_version: Literal["liquidation_event_v1"] = LIQUIDATION_EVENT_VERSION

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        for field in ("price", "quantity", "notional"):
            _require_positive(getattr(self, field), field)
        return self


class ExchangeSymbolMetadata(_FrozenRecord):
    symbol: str
    effective_from: datetime
    effective_to: datetime | None
    availability_time: datetime
    trading_status: str
    onboard_time: datetime | None
    delist_time: datetime | None
    tick_size: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    minimum_notional: Decimal
    funding_interval_minutes: int
    contract_type: str
    source_version: str
    schema_version: Literal["exchange_symbol_metadata_v1"] = EXCHANGE_METADATA_VERSION

    @field_validator("symbol")
    @classmethod
    def normalized_symbol(cls, value: str) -> str:
        return _require_symbol(value)

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        for field in (
            "effective_from",
            "availability_time",
            "effective_to",
            "onboard_time",
            "delist_time",
        ):
            value = getattr(self, field)
            if value is not None:
                _require_utc(value, field)
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from")
        for field in ("tick_size", "quantity_step", "min_quantity", "minimum_notional"):
            _require_positive(getattr(self, field), field)
        if self.funding_interval_minutes <= 0:
            raise ValueError("funding_interval_minutes must be positive")
        for field in ("trading_status", "contract_type", "source_version"):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        return self


class EventContext(_FrozenRecord):
    event_id: str
    entities: tuple[str, ...]
    event_type: str
    publisher_time: datetime
    first_seen_time: datetime
    ingestion_time: datetime
    revision_time: datetime | None
    novelty: Decimal | None
    severity: Decimal | None
    direction_hint: str | None
    horizon_hint: str | None
    source_quality: DataQualityStatus
    confidence: Decimal | None
    schema_version: Literal["event_context_v1"] = EVENT_CONTEXT_VERSION

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        for field in ("publisher_time", "first_seen_time", "ingestion_time", "revision_time"):
            value = getattr(self, field)
            if value is not None:
                _require_utc(value, field)
        if not self.publisher_time <= self.first_seen_time <= self.ingestion_time:
            raise ValueError("event timestamps must follow publisher <= first_seen <= ingestion")
        if self.revision_time is not None and self.revision_time < self.ingestion_time:
            raise ValueError("revision_time cannot predate ingestion_time")
        if not self.event_id.strip() or not self.event_type.strip() or not self.entities:
            raise ValueError("event identity, type, and entities are required")
        for field in ("novelty", "severity", "confidence"):
            value = getattr(self, field)
            if value is not None and not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{field} must be between 0 and 1")
        return self
