from datetime import UTC, datetime, timedelta

import httpx
import pytest

from crypto_ai.config import BinanceSettings
from crypto_ai.data.binance import BinanceAPIError, BinanceRestClient
from crypto_ai.domain import Market
from tests.factories import raw_kline


def test_client_paginates_forward_and_keeps_decimal_strings_exact() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)
    rows = [raw_kline(start_ms + index * 300_000) for index in range(3)]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_start = int(request.url.params["startTime"])
        page_end = int(request.url.params["endTime"])
        page = [row for row in rows if page_start <= row[0] <= page_end]
        return httpx.Response(200, json=page, headers={"X-MBX-USED-WEIGHT-1M": "4"})

    settings = BinanceSettings(market=Market.SPOT, request_limit=2, max_retries=0)
    with BinanceRestClient(settings, transport=httpx.MockTransport(handler)) as client:
        candles = client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(minutes=15),
        )

    assert len(candles) == 3
    assert str(candles[0].open) == "65000.00000000"
    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/klines"
    assert int(requests[0].url.params["endTime"]) == start_ms + 600_000 - 1
    assert int(requests[1].url.params["startTime"]) == start_ms + 600_000


def test_client_honors_retry_after_for_safe_get() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)
    attempts = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"code": -1003}, headers={"Retry-After": "1.25"})
        return httpx.Response(200, json=[raw_kline(start_ms)])

    settings = BinanceSettings(
        market=Market.SPOT,
        max_retries=1,
        retry_base_seconds=0.1,
    )
    with BinanceRestClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    ) as client:
        candles = client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(minutes=5),
        )

    assert len(candles) == 1
    assert attempts == 2
    assert sleeps == [1.25]


def test_client_rejects_conflicting_duplicate_open_times() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[raw_kline(start_ms, close="65001"), raw_kline(start_ms, close="65002")],
        )

    with (
        BinanceRestClient(
            BinanceSettings(market=Market.SPOT, max_retries=0),
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(BinanceAPIError, match="Conflicting duplicate"),
    ):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(minutes=5),
        )


def test_client_normalizes_public_archive_microsecond_timestamps() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_us = int(start.timestamp() * 1_000_000)
    raw = raw_kline(start_us, interval_ms=300_000_000)
    raw[6] = start_us + 300_000_000 - 1

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[raw])

    with BinanceRestClient(
        BinanceSettings(market=Market.SPOT, max_retries=0),
        transport=httpx.MockTransport(handler),
    ) as client:
        candles = client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(minutes=5),
        )

    assert candles[0].open_time == start
    assert candles[0].close_time == start + timedelta(minutes=5) - timedelta(microseconds=1)


def test_usdm_client_uses_explicit_futures_routes_and_source() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/fapi/v1/exchangeInfo":
            return httpx.Response(
                200,
                json={
                    "timezone": "UTC",
                    "symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}],
                },
            )
        return httpx.Response(200, json=[raw_kline(start_ms)])

    settings = BinanceSettings(market=Market.USD_M, max_retries=0)
    with BinanceRestClient(settings, transport=httpx.MockTransport(handler)) as client:
        instrument = client.fetch_exchange_info("BTCUSDT")
        candles = client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(minutes=5),
        )

    assert [request.url.path for request in requests] == [
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/klines",
    ]
    assert all(request.url.host == "fapi.binance.com" for request in requests)
    assert instrument["source"] == "binance_usdm_futures_rest"
    assert candles[0].source == "binance_usdm_futures_rest"
