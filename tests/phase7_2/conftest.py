from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_ai.phase7_2.schemas import CanonicalMarket1m


@pytest.fixture
def one_minute_rows() -> tuple[CanonicalMarket1m, ...]:
    start = datetime(2026, 6, 30, tzinfo=UTC)
    rows = []
    for offset in range(5):
        interval_start = start + timedelta(minutes=offset)
        price = Decimal(100 + offset)
        rows.append(
            CanonicalMarket1m(
                symbol="BTCUSDT",
                interval_start=interval_start,
                interval_end=interval_start + timedelta(minutes=1),
                availability_time=interval_start + timedelta(minutes=1, seconds=2),
                open=price,
                high=price + Decimal("1.5"),
                low=price - Decimal("0.5"),
                close=price + Decimal("1"),
                volume=Decimal(10 + offset),
                quote_volume=Decimal(1_000 + offset * 100),
                trade_count=100 + offset,
                taker_buy_base=Decimal(5 + offset),
                taker_buy_quote=Decimal(500 + offset * 50),
                mark_price=price + Decimal("1"),
                index_price=price + Decimal("0.9"),
                funding_state=Decimal("0.0001"),
                listing_age_days=1_000 + offset,
                source_identity="binance-usdm-public-archive",
            )
        )
    return tuple(rows)
