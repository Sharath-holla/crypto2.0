from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from crypto_ai.phase7.registry import OFFICIAL_ARCHIVE_URL, OFFICIAL_EXCHANGE_INFO_URL

_MONTH_PATTERN = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")


def _next_month(value: datetime) -> datetime:
    return value.replace(
        year=value.year + (value.month == 12),
        month=value.month % 12 + 1,
        day=1,
    )


class BinancePublicDiscoveryClient:
    """Unauthenticated official metadata/archive catalog discovery only."""

    def __init__(
        self,
        *,
        futures_base_url: str = "https://fapi.binance.com",
        archive_base_url: str = ("https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"),
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._futures = httpx.Client(
            base_url=futures_base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "crypto-trading-ai-phase7/1.0"},
        )
        self._archive = httpx.Client(
            base_url=archive_base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "crypto-trading-ai-phase7/1.0"},
        )

    def __enter__(self) -> BinancePublicDiscoveryClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._futures.close()
        self._archive.close()

    def fetch_exchange_info(self) -> dict[str, Any]:
        response = self._futures.get("/fapi/v1/exchangeInfo")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ValueError("unexpected Binance exchangeInfo response")
        return payload

    def _list(self, *, prefix: str, delimiter: str | None = None) -> tuple[list[str], list[str]]:
        keys: list[str] = []
        prefixes: list[str] = []
        continuation: str | None = None
        while True:
            params = {"list-type": "2", "prefix": prefix}
            if delimiter:
                params["delimiter"] = delimiter
            if continuation:
                params["continuation-token"] = continuation
            response = self._archive.get("", params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            keys.extend(item.text or "" for item in root.findall(".//{*}Contents/{*}Key"))
            prefixes.extend(
                item.text or "" for item in root.findall(".//{*}CommonPrefixes/{*}Prefix")
            )
            truncated = (root.findtext(".//{*}IsTruncated") or "false").lower() == "true"
            continuation = root.findtext(".//{*}NextContinuationToken")
            if not truncated:
                break
            if not continuation:
                raise ValueError("archive listing was truncated without continuation token")
        return keys, prefixes

    def archive_symbols(self) -> tuple[str, ...]:
        root = "data/futures/um/monthly/klines/"
        _, prefixes = self._list(prefix=root, delimiter="/")
        symbols = {
            prefix.removeprefix(root).strip("/").upper()
            for prefix in prefixes
            if prefix.removeprefix(root).strip("/")
        }
        return tuple(sorted(symbols))

    def monthly_keys(self, symbol: str, interval: str) -> tuple[str, ...]:
        prefix = f"data/futures/um/monthly/klines/{symbol.upper()}/{interval}/"
        keys, _ = self._list(prefix=prefix)
        return tuple(sorted(key for key in keys if key.endswith(".zip")))

    def historical_evidence(
        self,
        *,
        intervals: tuple[str, ...] = ("5m", "12h", "1d"),
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for symbol in self.archive_symbols():
            if not symbol.endswith("USDT"):
                continue
            months: list[datetime] = []
            available: list[str] = []
            for interval in intervals:
                keys = self.monthly_keys(symbol, interval)
                parsed: list[datetime] = []
                for key in keys:
                    match = _MONTH_PATTERN.search(key)
                    if match:
                        parsed.append(
                            datetime(
                                int(match.group("year")),
                                int(match.group("month")),
                                1,
                                tzinfo=UTC,
                            )
                        )
                if parsed:
                    months.extend(parsed)
                    available.append(interval)
            if not months:
                continue
            first = min(months)
            available_until = _next_month(max(months))
            last = available_until - timedelta(minutes=5)
            base = symbol[:-4] if symbol.endswith("USDT") else symbol
            evidence.append(
                {
                    "symbol": symbol,
                    "base_asset": base,
                    "quote_asset": "USDT" if symbol.endswith("USDT") else "UNKNOWN",
                    "contract_type": "PERPETUAL",
                    "first_market_data_time": first.isoformat(),
                    "last_market_data_time": last.isoformat(),
                    "available_until": available_until.isoformat(),
                    "availability_evidence": "OFFICIAL_ARCHIVE_PERIOD_EVIDENCE",
                    "available_intervals": sorted(set(available)),
                    "metadata_sources": [
                        "official_binance_public_archive_object_listing",
                        OFFICIAL_ARCHIVE_URL,
                    ],
                }
            )
        return evidence


def source_verification_manifest(*, verified_at: datetime | None = None) -> dict[str, Any]:
    return {
        "verified_at": (verified_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "private_api_used": False,
        "api_key_required": False,
        "exchange_info": {
            "endpoint": "/fapi/v1/exchangeInfo",
            "official_documentation": OFFICIAL_EXCHANGE_INFO_URL,
        },
        "klines": {
            "endpoint": "/fapi/v1/klines",
            "intervals": ["5m", "12h", "1d"],
        },
        "funding": {"endpoint": "/fapi/v1/fundingRate"},
        "mark": {"endpoint": "/fapi/v1/markPriceKlines"},
        "index": {"endpoint": "/fapi/v1/indexPriceKlines"},
        "archive": {
            "layout": "data/futures/um/<monthly|daily>/<dataset>/<symbol>/<interval>/",
            "catalog_endpoint": ("https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"),
            "checksums_required": True,
            "official_documentation": OFFICIAL_ARCHIVE_URL,
        },
    }
