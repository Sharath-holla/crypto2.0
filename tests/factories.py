from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_ai.domain import Candle


def make_candle(
    index: int = 0,
    *,
    start: datetime = datetime(2026, 8, 1, tzinfo=UTC),
    interval_minutes: int = 5,
    symbol: str = "BTCUSDT",
    source: str = "binance_usdm_futures_rest",
) -> Candle:
    open_time = start + timedelta(minutes=index * interval_minutes)
    close_time = open_time + timedelta(minutes=interval_minutes) - timedelta(milliseconds=1)
    price = Decimal("65000.123456789012345678") + Decimal(index)
    return Candle(
        symbol=symbol,
        open_time=open_time,
        close_time=close_time,
        open=price,
        high=price + Decimal("10.000000000000000001"),
        low=price - Decimal("10.000000000000000001"),
        close=price + Decimal("1.000000000000000001"),
        base_volume=Decimal("12.345678901234567890"),
        quote_volume=Decimal("802345.678901234567890123"),
        trade_count=1234,
        taker_buy_base_volume=Decimal("6.123456789012345678"),
        taker_buy_quote_volume=Decimal("401234.567890123456789012"),
        source=source,
        ingested_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def raw_kline(open_ms: int, *, interval_ms: int = 300_000, close: str = "65001.0") -> list:
    return [
        open_ms,
        "65000.00000000",
        "65010.00000000",
        "64990.00000000",
        close,
        "12.34567890",
        open_ms + interval_ms - 1,
        "802345.67890123",
        1234,
        "6.12345678",
        "401234.56789012",
        "0",
    ]
