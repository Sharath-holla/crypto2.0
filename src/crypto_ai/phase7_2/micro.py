from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_ai.phase7_2.config import MicroContextToggle
from crypto_ai.phase7_2.schemas import (
    CANONICAL_MARKET_1M_VERSION,
    CanonicalMarket1m,
    CanonicalMarket5m,
    DataQualityStatus,
    SymbolEligibilityStatus,
)

MICRO_1M_CONTEXT_VERSION = "micro_1m_context_v1"


class CausalAggregationError(ValueError):
    """Raised when one-minute rows cannot safely form a completed five-minute bar."""


@dataclass(frozen=True, slots=True)
class Micro1mContext:
    symbol: str
    feature_time: datetime
    enabled: bool
    values: tuple[tuple[str, float], ...]
    schema_version: str = MICRO_1M_CONTEXT_VERSION

    def __post_init__(self) -> None:
        if self.feature_time.tzinfo is None or self.feature_time.utcoffset() is None:
            raise ValueError("feature_time must be timezone-aware UTC")
        if self.feature_time.utcoffset() != UTC.utcoffset(self.feature_time):
            raise ValueError("feature_time must be UTC")
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        names = [name for name, _ in self.values]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("micro feature names must be unique and sorted")
        if any(not math.isfinite(value) for _, value in self.values):
            raise ValueError("micro features must be finite")
        if not self.enabled and self.values:
            raise ValueError("disabled micro context cannot carry feature values")

    @property
    def features(self) -> dict[str, float]:
        return dict(self.values)


def _validate_window(rows: Iterable[CanonicalMarket1m]) -> tuple[CanonicalMarket1m, ...]:
    window = tuple(rows)
    if not window:
        raise CausalAggregationError("one-minute window is empty")
    starts = [row.interval_start for row in window]
    if len(starts) != len(set(starts)):
        raise CausalAggregationError("duplicate 1m candle")
    if starts != sorted(starts):
        raise CausalAggregationError("out-of-order 1m input")
    if len(window) != 5:
        raise CausalAggregationError("a completed 5m window requires exactly five 1m candles")
    if len({row.symbol for row in window}) != 1:
        raise CausalAggregationError("a 5m window cannot mix symbols")
    if any(row.schema_version != CANONICAL_MARKET_1M_VERSION for row in window):
        raise CausalAggregationError("unexpected 1m schema version")
    start = window[0].interval_start
    if start.second or start.microsecond or start.minute % 5:
        raise CausalAggregationError("the first 1m candle is not aligned to a 5m boundary")
    expected = [start + timedelta(minutes=offset) for offset in range(5)]
    if starts != expected:
        raise CausalAggregationError("gap inside 1m window")
    if any(row.quality_status is not DataQualityStatus.VALID for row in window):
        raise CausalAggregationError("invalid or incomplete 1m quality status")
    if any(row.symbol_eligibility_status is not SymbolEligibilityStatus.ELIGIBLE for row in window):
        raise CausalAggregationError("ineligible 1m row cannot enter a model-facing 5m bar")
    return window


def aggregate_1m_to_5m(
    rows: Iterable[CanonicalMarket1m],
    *,
    as_of: datetime | None = None,
) -> CanonicalMarket5m:
    window = _validate_window(rows)
    availability_time = max(row.availability_time for row in window)
    if as_of is not None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise CausalAggregationError("as_of must be timezone-aware UTC")
        if as_of.utcoffset() != UTC.utcoffset(as_of):
            raise CausalAggregationError("as_of must be UTC")
        if as_of < availability_time:
            raise CausalAggregationError("final 1m observation is not yet available")
    return CanonicalMarket5m(
        symbol=window[0].symbol,
        interval_start=window[0].interval_start,
        interval_end=window[-1].interval_end,
        availability_time=availability_time,
        open=window[0].open,
        high=max(row.high for row in window),
        low=min(row.low for row in window),
        close=window[-1].close,
        volume=sum((row.volume for row in window), start=Decimal(0)),
        quote_volume=sum((row.quote_volume for row in window), start=Decimal(0)),
        trade_count=sum(row.trade_count for row in window),
        taker_buy_base=sum((row.taker_buy_base for row in window), start=Decimal(0)),
        taker_buy_quote=sum((row.taker_buy_quote for row in window), start=Decimal(0)),
    )


def _simple_return(end: Decimal, start: Decimal) -> float:
    return float(end / start - Decimal(1))


def _acceleration(current: Decimal | int, previous: list[Decimal | int]) -> float:
    baseline = sum((Decimal(value) for value in previous), start=Decimal(0)) / Decimal(
        len(previous)
    )
    if baseline == 0:
        return 0.0 if Decimal(current) == 0 else 1.0
    return float(Decimal(current) / baseline - Decimal(1))


def build_micro_1m_context(
    rows: Iterable[CanonicalMarket1m],
    *,
    feature_time: datetime,
    config: MicroContextToggle | None = None,
) -> Micro1mContext:
    settings = config or MicroContextToggle()
    supplied = tuple(rows)
    symbol = supplied[0].symbol if supplied else "DISABLED"
    if not settings.enabled:
        return Micro1mContext(
            symbol=symbol,
            feature_time=feature_time,
            enabled=False,
            values=(),
        )

    window = _validate_window(supplied)
    aggregate_1m_to_5m(window, as_of=feature_time)
    if any(row.interval_end > feature_time for row in window):
        raise CausalAggregationError("future 1m interval entered micro feature construction")
    minute_returns = [_simple_return(row.close, row.open) for row in window]
    close_returns = [
        _simple_return(window[index].close, window[index - 1].close)
        for index in range(1, len(window))
    ]
    range_high = max(row.high for row in window)
    range_low = min(row.low for row in window)
    range_width = range_high - range_low
    taker_sells = [row.taker_sell_base for row in window]
    total_volume = sum((row.volume for row in window), start=Decimal(0))
    signed_consistency = sum(1 if value > 0 else -1 if value < 0 else 0 for value in minute_returns)
    features = {
        "close_location_in_5m_range": (
            float((window[-1].close - range_low) / range_width) if range_width else 0.5
        ),
        "directional_consistency_5m": signed_consistency / len(minute_returns),
        "intrabar_range_5m": _simple_return(range_high, range_low),
        "largest_1m_shock": max(abs(value) for value in minute_returns),
        "max_abs_1m_return_5m": max(abs(value) for value in close_returns),
        "momentum_score_5m": _simple_return(window[-1].close, window[0].open),
        "realized_volatility_1m_5m": statistics.pstdev(minute_returns),
        "return_1m": close_returns[-1],
        "return_2m": _simple_return(window[-1].close, window[-3].close),
        "return_3m": _simple_return(window[-1].close, window[-4].close),
        "return_5m": _simple_return(window[-1].close, window[0].open),
        "short_term_reversal_score": -close_returns[-1],
        "taker_buy_acceleration_1m": _acceleration(
            window[-1].taker_buy_base,
            [row.taker_buy_base for row in window[:-1]],
        ),
        "taker_sell_acceleration_1m": _acceleration(taker_sells[-1], taker_sells[:-1]),
        "trade_count_acceleration_1m": _acceleration(
            window[-1].trade_count,
            [row.trade_count for row in window[:-1]],
        ),
        "volume_acceleration_1m": _acceleration(
            window[-1].volume,
            [row.volume for row in window[:-1]],
        ),
        "volume_concentration_5m": (
            float(max(row.volume for row in window) / total_volume) if total_volume else 0.0
        ),
    }
    return Micro1mContext(
        symbol=window[0].symbol,
        feature_time=feature_time,
        enabled=True,
        values=tuple(sorted(features.items())),
    )
