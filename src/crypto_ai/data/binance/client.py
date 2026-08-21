from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from crypto_ai.config import BinanceSettings
from crypto_ai.domain import Candle, Market, interval_milliseconds

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URLS = {
    Market.SPOT: "https://data-api.binance.vision",
    Market.USD_M: "https://fapi.binance.com",
}
_KLINE_PATHS = {
    Market.SPOT: "/api/v3/klines",
    Market.USD_M: "/fapi/v1/klines",
}
_EXCHANGE_INFO_PATHS = {
    Market.SPOT: "/api/v3/exchangeInfo",
    Market.USD_M: "/fapi/v1/exchangeInfo",
}
_SOURCES = {
    Market.SPOT: "binance_spot_rest",
    Market.USD_M: "binance_usdm_futures_rest",
}


class BinanceAPIError(RuntimeError):
    """Raised when Binance returns an unusable response."""


def _utc_from_exchange_timestamp(value: object) -> datetime:
    timestamp = int(value)
    # REST JSON defaults to milliseconds. The public Spot archive changed to
    # microseconds in 2025, so accepting both here keeps normalization explicit.
    divisor = 1_000_000 if abs(timestamp) >= 100_000_000_000_000 else 1_000
    seconds, remainder = divmod(timestamp, divisor)
    microseconds = remainder if divisor == 1_000_000 else remainder * 1_000
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds, microseconds=microseconds)


def _epoch_milliseconds(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    normalized = value.astimezone(UTC)
    delta = normalized - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


class BinanceRestClient:
    def __init__(
        self,
        settings: BinanceSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._sleep = sleeper
        self._client = httpx.Client(
            base_url=settings.base_url or _DEFAULT_BASE_URLS[settings.market],
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={"User-Agent": "crypto-trading-ai/0.1.0"},
        )

    def __enter__(self) -> BinanceRestClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request_json(self, path: str, params: dict[str, object] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._client.get(path, params=params)
                if response.status_code in {418, 429} or response.status_code >= 500:
                    if attempt >= self.settings.max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        server_wait = float(retry_after) if retry_after is not None else 0.0
                    except ValueError:
                        server_wait = 0.0
                    delay = max(
                        server_wait,
                        self.settings.retry_base_seconds * (2**attempt),
                    )
                    logger.warning(
                        "Retrying safe Binance GET",
                        extra={
                            "event": "binance_retry",
                            "attempt": attempt + 1,
                            "delay_seconds": delay,
                            "path": path,
                            "status_code": response.status_code,
                        },
                    )
                    self._sleep(delay)
                    continue
                response.raise_for_status()
                used_weight = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower().startswith("x-mbx-used-weight")
                }
                if used_weight:
                    logger.debug(
                        "Binance request weight observed",
                        extra={"event": "binance_weight", "headers": used_weight},
                    )
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                delay = self.settings.retry_base_seconds * (2**attempt)
                logger.warning(
                    "Retrying Binance GET after transport failure",
                    extra={
                        "event": "binance_transport_retry",
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                        "path": path,
                        "error": str(exc),
                    },
                )
                self._sleep(delay)
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise BinanceAPIError(f"Binance request failed for {path}: {exc}") from exc
        raise BinanceAPIError(f"Binance request failed for {path}: {last_error}") from last_error

    def fetch_exchange_info(self, symbol: str) -> dict[str, Any]:
        params = {"symbol": symbol} if self.settings.market is Market.SPOT else None
        payload = self._request_json(_EXCHANGE_INFO_PATHS[self.settings.market], params)
        if not isinstance(payload, dict):
            raise BinanceAPIError("exchangeInfo response must be a JSON object")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list):
            raise BinanceAPIError("exchangeInfo response is missing symbols")
        instrument = next(
            (item for item in symbols if isinstance(item, dict) and item.get("symbol") == symbol),
            None,
        )
        if instrument is None:
            raise BinanceAPIError(f"Symbol {symbol} was not present in exchangeInfo")
        return {
            "source": _SOURCES[self.settings.market],
            "market": self.settings.market.value,
            "symbol": symbol,
            "endpoint": _EXCHANGE_INFO_PATHS[self.settings.market],
            "fetched_at": datetime.now(UTC).isoformat(),
            "timezone": payload.get("timezone"),
            "server_time": payload.get("serverTime"),
            "rate_limits": payload.get("rateLimits", []),
            "instrument": instrument,
        }

    def get_public_json(
        self,
        path: str,
        params: dict[str, object] | None = None,
    ) -> Any:
        """Issue a retry-aware public GET for a market-data adapter.

        This intentionally exposes only the existing unauthenticated GET path;
        it does not accept credentials, signatures, or mutating HTTP methods.
        """

        return self._request_json(path, params)

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        ingested_at: datetime | None = None,
    ) -> list[Candle]:
        """Fetch a half-open UTC range using deterministic forward pagination."""

        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        start_ms = _epoch_milliseconds(start)
        end_ms = _epoch_milliseconds(end)
        if start_ms >= end_ms:
            raise ValueError("start must be earlier than end")

        interval_ms = interval_milliseconds(interval)
        cursor_ms = start_ms
        captured_at = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        by_open_time: dict[datetime, Candle] = {}

        while cursor_ms < end_ms:
            page_end_exclusive = min(
                end_ms,
                cursor_ms + self.settings.request_limit * interval_ms,
            )
            payload = self._request_json(
                _KLINE_PATHS[self.settings.market],
                {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": cursor_ms,
                    "endTime": page_end_exclusive - 1,
                    "limit": self.settings.request_limit,
                },
            )
            if not isinstance(payload, list):
                raise BinanceAPIError("Kline response must be a JSON array")
            for raw in payload:
                candle = self._parse_kline(raw, symbol=symbol, ingested_at=captured_at)
                candle_ms = _epoch_milliseconds(candle.open_time)
                if candle_ms < start_ms or candle_ms >= end_ms:
                    continue
                existing = by_open_time.get(candle.open_time)
                if existing is not None and existing.market_values != candle.market_values:
                    raise BinanceAPIError(
                        "Conflicting duplicate kline for "
                        f"{symbol} at {candle.open_time.isoformat()}"
                    )
                by_open_time[candle.open_time] = candle
            cursor_ms = page_end_exclusive

        return [by_open_time[key] for key in sorted(by_open_time)]

    def _parse_kline(
        self,
        raw: object,
        *,
        symbol: str,
        ingested_at: datetime,
    ) -> Candle:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 12:
            raise BinanceAPIError("Each kline must contain at least 12 ordered fields")
        try:
            return Candle(
                symbol=symbol,
                open_time=_utc_from_exchange_timestamp(raw[0]),
                open=Decimal(str(raw[1])),
                high=Decimal(str(raw[2])),
                low=Decimal(str(raw[3])),
                close=Decimal(str(raw[4])),
                base_volume=Decimal(str(raw[5])),
                close_time=_utc_from_exchange_timestamp(raw[6]),
                quote_volume=Decimal(str(raw[7])),
                trade_count=int(raw[8]),
                taker_buy_base_volume=Decimal(str(raw[9])),
                taker_buy_quote_volume=Decimal(str(raw[10])),
                source=_SOURCES[self.settings.market],
                ingested_at=ingested_at,
            )
        except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
            raise BinanceAPIError(f"Invalid kline payload: {raw!r}") from exc
