from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class Market(StrEnum):
    SPOT = "spot"
    USD_M = "usdm"


_FIXED_INTERVAL_MILLISECONDS = {
    "1s": 1_000,
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def interval_milliseconds(interval: str) -> int:
    """Return the duration of a fixed Binance interval.

    Calendar-month candles are deliberately excluded because they do not have a
    fixed duration. Phase 1 uses 1m and 5m candles.
    """

    try:
        return _FIXED_INTERVAL_MILLISECONDS[interval]
    except KeyError as exc:
        supported = ", ".join(sorted(_FIXED_INTERVAL_MILLISECONDS))
        raise ValueError(
            f"Unsupported fixed interval {interval!r}; choose one of: {supported}"
        ) from exc


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    source: str
    ingested_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("open_time", "close_time", "ingested_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            if value.utcoffset() != UTC.utcoffset(value):
                raise ValueError(f"{field_name} must be normalized to UTC")

    @property
    def identity(self) -> tuple[str, datetime]:
        return self.symbol, self.open_time

    @property
    def market_values(self) -> tuple[object, ...]:
        """Values used to detect conflicting duplicate exchange rows."""

        return (
            self.close_time,
            self.open,
            self.high,
            self.low,
            self.close,
            self.base_volume,
            self.quote_volume,
            self.trade_count,
            self.taker_buy_base_volume,
            self.taker_buy_quote_volume,
            self.source,
        )
