from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.schema import DECIMAL_TYPE
from crypto_ai.data.storage import file_sha256
from crypto_ai.domain import interval_milliseconds

MARKET_DATA_SCHEMA_VERSION = "2.0.0"


class MarketDataKind(StrEnum):
    FUNDING = "funding"
    MARK_KLINE = "mark_kline"
    INDEX_KLINE = "index_kline"
    PREMIUM_KLINE = "premium_kline"
    OPEN_INTEREST = "open_interest"


_KLINE_PATHS = {
    MarketDataKind.MARK_KLINE: "/fapi/v1/markPriceKlines",
    MarketDataKind.INDEX_KLINE: "/fapi/v1/indexPriceKlines",
    MarketDataKind.PREMIUM_KLINE: "/fapi/v1/premiumIndexKlines",
}


def _epoch_ms(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return int(value.astimezone(UTC).timestamp() * 1_000)


def _utc(value: object) -> datetime:
    return datetime.fromtimestamp(int(value) / 1_000, tz=UTC)


def _identity_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def market_data_schema(kind: MarketDataKind) -> pa.Schema:
    common = [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("event_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("availability_time", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
    if kind is MarketDataKind.FUNDING:
        values = [
            pa.field("funding_rate", DECIMAL_TYPE, nullable=False),
            pa.field("mark_price", DECIMAL_TYPE, nullable=True),
            pa.field("rate_type", pa.string(), nullable=True),
        ]
    elif kind in _KLINE_PATHS:
        values = [
            pa.field("open", DECIMAL_TYPE, nullable=False),
            pa.field("high", DECIMAL_TYPE, nullable=False),
            pa.field("low", DECIMAL_TYPE, nullable=False),
            pa.field("close", DECIMAL_TYPE, nullable=False),
        ]
    elif kind is MarketDataKind.OPEN_INTEREST:
        values = [
            pa.field("sum_open_interest", DECIMAL_TYPE, nullable=False),
            pa.field("sum_open_interest_value", DECIMAL_TYPE, nullable=False),
        ]
    else:  # pragma: no cover - exhaustive enum guard
        raise ValueError(f"Unsupported market-data kind: {kind}")
    return pa.schema(
        common
        + values
        + [
            pa.field("source", pa.string(), nullable=False),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        ],
        metadata={
            b"schema_version": MARKET_DATA_SCHEMA_VERSION.encode(),
            b"dataset_kind": kind.value.encode(),
        },
    )


class DerivativesMarketDataClient:
    """Public-only USD-M market-data adapter.

    The injected request function makes the boundary testable and deliberately
    exposes no authenticated, account, leverage, position, or order methods.
    """

    def __init__(self, request_json: Callable[[str, dict[str, object] | None], Any]) -> None:
        self._request_json = request_json

    def fetch(
        self,
        kind: MarketDataKind,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "5m",
        ingested_at: datetime | None = None,
    ) -> pa.Table:
        start_ms, end_ms = _epoch_ms(start), _epoch_ms(end)
        if start_ms >= end_ms:
            raise ValueError("market-data range must be half-open with start < end")
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        if kind is MarketDataKind.FUNDING:
            rows = self._funding(symbol, start_ms, end_ms, captured)
        elif kind in _KLINE_PATHS:
            rows = self._price_klines(kind, symbol, interval, start_ms, end_ms, captured)
        elif kind is MarketDataKind.OPEN_INTEREST:
            rows = self._open_interest(symbol, interval, start_ms, end_ms, captured)
        else:  # pragma: no cover
            raise ValueError(f"Unsupported market-data kind: {kind}")
        return pa.Table.from_pylist(rows, schema=market_data_schema(kind))

    def _funding(
        self, symbol: str, start_ms: int, end_ms: int, captured: datetime
    ) -> list[dict[str, Any]]:
        by_time: dict[int, dict[str, Any]] = {}
        cursor = start_ms
        while cursor < end_ms:
            payload = self._request_json(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor, "endTime": end_ms - 1, "limit": 1_000},
            )
            if not isinstance(payload, list):
                raise ValueError("Funding response must be a JSON array")
            page_times: list[int] = []
            for raw in payload:
                if not isinstance(raw, dict):
                    raise ValueError("Funding rows must be JSON objects")
                timestamp = int(raw["fundingTime"])
                if timestamp < start_ms or timestamp >= end_ms:
                    continue
                try:
                    row = {
                        "symbol": symbol,
                        "event_time": _utc(timestamp),
                        "availability_time": _utc(timestamp),
                        "funding_rate": Decimal(str(raw["fundingRate"])),
                        "mark_price": (
                            Decimal(str(raw["markPrice"]))
                            if raw.get("markPrice") not in {None, ""}
                            else None
                        ),
                        "rate_type": raw.get("rateType"),
                        "source": "binance_usdm_funding_rest",
                        "ingested_at": captured,
                    }
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid funding row: {raw!r}") from exc
                previous = by_time.get(timestamp)
                if previous is not None and previous != row:
                    raise ValueError(f"Conflicting funding record at {timestamp}")
                by_time[timestamp] = row
                page_times.append(timestamp)
            if not page_times or len(payload) < 1_000:
                break
            next_cursor = max(page_times) + 1
            if next_cursor <= cursor:
                raise ValueError("Funding pagination did not advance")
            cursor = next_cursor
        return [by_time[key] for key in sorted(by_time)]

    def _price_klines(
        self,
        kind: MarketDataKind,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        captured: datetime,
    ) -> list[dict[str, Any]]:
        step = interval_milliseconds(interval)
        by_time: dict[int, dict[str, Any]] = {}
        cursor = start_ms
        while cursor < end_ms:
            page_end = min(end_ms, cursor + 1_500 * step)
            instrument_parameter = (
                {"pair": symbol} if kind is MarketDataKind.INDEX_KLINE else {"symbol": symbol}
            )
            payload = self._request_json(
                _KLINE_PATHS[kind],
                {
                    **instrument_parameter,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": page_end - 1,
                    "limit": 1_500,
                },
            )
            if not isinstance(payload, list):
                raise ValueError("Price-kline response must be a JSON array")
            for raw in payload:
                if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 5:
                    raise ValueError("Price-kline rows require at least five fields")
                timestamp = int(raw[0])
                if timestamp < start_ms or timestamp >= end_ms:
                    continue
                try:
                    row = {
                        "symbol": symbol,
                        "event_time": _utc(timestamp),
                        "availability_time": _utc(timestamp + step),
                        "open": Decimal(str(raw[1])),
                        "high": Decimal(str(raw[2])),
                        "low": Decimal(str(raw[3])),
                        "close": Decimal(str(raw[4])),
                        "source": f"binance_usdm_{kind.value}_rest",
                        "ingested_at": captured,
                    }
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid price-kline row: {raw!r}") from exc
                previous = by_time.get(timestamp)
                if previous is not None and previous != row:
                    raise ValueError(f"Conflicting {kind.value} at {timestamp}")
                by_time[timestamp] = row
            cursor = page_end
        return [by_time[key] for key in sorted(by_time)]

    def _open_interest(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        captured: datetime,
    ) -> list[dict[str, Any]]:
        step = interval_milliseconds(interval)
        by_time: dict[int, dict[str, Any]] = {}
        cursor = start_ms
        while cursor < end_ms:
            page_end = min(end_ms, cursor + 500 * step)
            payload = self._request_json(
                "/futures/data/openInterestHist",
                {
                    "symbol": symbol,
                    "period": interval,
                    "startTime": cursor,
                    "endTime": page_end - 1,
                    "limit": 500,
                },
            )
            if not isinstance(payload, list):
                raise ValueError("Open-interest response must be a JSON array")
            for raw in payload:
                if not isinstance(raw, dict):
                    raise ValueError("Open-interest rows must be JSON objects")
                timestamp = int(raw["timestamp"])
                if timestamp < start_ms or timestamp >= end_ms:
                    continue
                row = {
                    "symbol": symbol,
                    "event_time": _utc(timestamp),
                    "availability_time": _utc(timestamp),
                    "sum_open_interest": Decimal(str(raw["sumOpenInterest"])),
                    "sum_open_interest_value": Decimal(str(raw["sumOpenInterestValue"])),
                    "source": "binance_usdm_open_interest_rest",
                    "ingested_at": captured,
                }
                previous = by_time.get(timestamp)
                if previous is not None and previous != row:
                    raise ValueError(f"Conflicting open-interest record at {timestamp}")
                by_time[timestamp] = row
            cursor = page_end
        return [by_time[key] for key in sorted(by_time)]


def validate_market_table(table: pa.Table, kind: MarketDataKind) -> dict[str, Any]:
    expected = market_data_schema(kind)
    if table.schema.remove_metadata() != expected.remove_metadata():
        raise ValueError(f"Invalid {kind.value} schema")
    if table.num_rows == 0:
        raise ValueError(f"{kind.value} dataset is empty")
    event = table.column("event_time").combine_chunks().cast(pa.int64()).to_numpy()
    available = table.column("availability_time").combine_chunks().cast(pa.int64()).to_numpy()
    if np.any(np.diff(event) <= 0):
        raise ValueError(f"{kind.value} event times must be unique and strictly increasing")
    if np.any(available < event):
        raise ValueError(f"{kind.value} availability precedes event time")
    if kind in _KLINE_PATHS:
        prices = {
            name: np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)
            for name in ("open", "high", "low", "close")
        }
        if any(np.any(~np.isfinite(values) | (values <= 0)) for values in prices.values()):
            raise ValueError(f"{kind.value} contains non-positive/non-finite prices")
        maximum_components = np.maximum.reduce([prices["open"], prices["close"], prices["low"]])
        if np.any(prices["high"] < maximum_components):
            raise ValueError(f"{kind.value} contains invalid highs")
        if np.any(prices["low"] > np.minimum(prices["open"], prices["close"])):
            raise ValueError(f"{kind.value} contains invalid lows")
    return {
        "status": "PASS",
        "row_count": table.num_rows,
        "first_event_time": table.column("event_time")[0].as_py().isoformat(),
        "last_event_time": table.column("event_time")[-1].as_py().isoformat(),
    }


def _write_table(path: Path, table: pa.Table) -> str:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable market dataset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary, compression="zstd", write_statistics=True)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return file_sha256(path)


def ingest_public_market_data(
    table: pa.Table,
    *,
    kind: MarketDataKind,
    symbol: str,
    interval: str | None,
    output_root: Path,
    request_start: datetime,
    request_end: datetime,
) -> Path:
    """Validate and persist content-addressed Bronze plus canonical Silver."""

    validation = validate_market_table(table, kind)
    raw_identity = {
        "kind": kind.value,
        "symbol": symbol,
        "interval": interval,
        "request_start": request_start.astimezone(UTC).isoformat(),
        "request_end": request_end.astimezone(UTC).isoformat(),
        "rows": table.num_rows,
        # Retrieval time is provenance, not market content. Excluding it keeps
        # an identical completed request restartable across process restarts.
        "content": table.drop(["ingested_at"]).to_pylist(),
    }
    bronze_version = f"market-bronze-{_identity_hash(raw_identity)}"
    bronze_dir = output_root.resolve() / "bronze" / kind.value / bronze_version
    bronze_path = bronze_dir / "dataset.parquet"
    bronze_manifest = bronze_dir / "manifest.json"
    if not bronze_manifest.exists():
        checksum = _write_table(bronze_path, table)
        write_manifest(
            bronze_manifest,
            {
                "dataset_version": bronze_version,
                "layer": "bronze",
                "kind": kind.value,
                "symbol": symbol,
                "interval": interval,
                "request_range": {
                    "start": raw_identity["request_start"],
                    "end": raw_identity["request_end"],
                },
                "row_count": table.num_rows,
                "file": "dataset.parquet",
                "sha256": checksum,
                "schema_version": MARKET_DATA_SCHEMA_VERSION,
            },
        )
    else:
        existing = read_manifest(bronze_manifest)
        if (
            existing is None
            or not bronze_path.exists()
            or file_sha256(bronze_path) != existing.get("sha256")
        ):
            raise ValueError(f"Existing Bronze market dataset is incomplete: {bronze_dir}")

    silver_identity = {
        "source_version": bronze_version,
        "source_sha256": file_sha256(bronze_path),
        "validation": validation,
        "transformation": "strict-sort-deduplicate-v1",
    }
    silver_version = f"market-silver-{_identity_hash(silver_identity)}"
    silver_dir = output_root.resolve() / "silver" / kind.value / silver_version
    silver_path = silver_dir / "dataset.parquet"
    silver_manifest = silver_dir / "manifest.json"
    if not silver_manifest.exists():
        canonical = table.sort_by([("event_time", "ascending")])
        metadata = dict(canonical.schema.metadata or {})
        metadata.update(
            {
                b"layer": b"silver",
                b"dataset_version": silver_version.encode(),
                b"source_dataset_version": bronze_version.encode(),
            }
        )
        checksum = _write_table(silver_path, canonical.replace_schema_metadata(metadata))
        write_manifest(
            silver_manifest,
            {
                "dataset_version": silver_version,
                "layer": "silver",
                "kind": kind.value,
                "symbol": symbol,
                "interval": interval,
                "source_manifest": str(bronze_manifest),
                "source_dataset_version": bronze_version,
                "source_sha256": file_sha256(bronze_path),
                "validation": validation,
                "row_count": canonical.num_rows,
                "file": "dataset.parquet",
                "sha256": checksum,
                "schema_version": MARKET_DATA_SCHEMA_VERSION,
            },
        )
    return silver_manifest


def read_market_dataset(
    manifest_path: Path,
    expected_kind: MarketDataKind | None = None,
) -> tuple[pa.Table, dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)
    kind = MarketDataKind(str(manifest.get("kind")))
    if expected_kind is not None and kind is not expected_kind:
        raise ValueError(f"Expected {expected_kind.value}, found {kind.value}")
    path = manifest_path.parent / str(manifest.get("file", "dataset.parquet"))
    if not path.exists() or file_sha256(path) != manifest.get("sha256"):
        raise ValueError(f"Market dataset checksum mismatch: {path}")
    table = pq.ParquetFile(path).read()
    validate_market_table(table.replace_schema_metadata(market_data_schema(kind).metadata), kind)
    return table, manifest
