from __future__ import annotations

import csv
import hashlib
import io
import os
import time
import uuid
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from crypto_ai.data.binance.client import _utc_from_exchange_timestamp
from crypto_ai.domain import Candle, interval_milliseconds

ARCHIVE_BASE_URL = "https://data.binance.vision/data/futures/um"


class ArchiveDataset(StrEnum):
    KLINES = "klines"
    MARK_PRICE_KLINES = "markPriceKlines"
    INDEX_PRICE_KLINES = "indexPriceKlines"
    PREMIUM_PRICE_KLINES = "premiumPriceKlines"


class ArchiveFrequency(StrEnum):
    MONTHLY = "monthly"
    DAILY = "daily"


class ArchiveNotFoundError(FileNotFoundError):
    """Raised when an expected official archive object is unavailable."""


@dataclass(frozen=True, slots=True)
class ArchiveObject:
    dataset: ArchiveDataset
    frequency: ArchiveFrequency
    symbol: str
    interval: str
    period: date

    @property
    def period_token(self) -> str:
        if self.frequency is ArchiveFrequency.MONTHLY:
            return self.period.strftime("%Y-%m")
        return self.period.isoformat()

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.interval}-{self.period_token}.zip"

    @property
    def relative_url(self) -> str:
        return (
            f"/{self.frequency.value}/{self.dataset.value}/{self.symbol}/"
            f"{self.interval}/{self.filename}"
        )

    @property
    def checksum_url(self) -> str:
        return f"{self.relative_url}.CHECKSUM"


def monthly_objects(
    dataset: ArchiveDataset,
    *,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> list[ArchiveObject]:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("archive range must be timezone-aware with start < end")
    cursor = date(start.year, start.month, 1)
    final = end.astimezone(UTC)
    result: list[ArchiveObject] = []
    while datetime(cursor.year, cursor.month, 1, tzinfo=UTC) < final:
        result.append(
            ArchiveObject(
                dataset=dataset,
                frequency=ArchiveFrequency.MONTHLY,
                symbol=symbol.upper(),
                interval=interval,
                period=cursor,
            )
        )
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return result


class BinanceArchiveClient:
    """Official USD-M archive transport implementing the candle-client protocol.

    Raw ZIP bytes and upstream checksum text are stored immutably by content
    hash. The existing HistoricalDownloader remains responsible for canonical
    daily Parquet partitions, validation, manifests, and restart behavior.
    """

    source_identity = "binance_public_archive"
    row_source = "binance_usdm_futures_archive"
    source_transport = "archive"

    def __init__(
        self,
        *,
        raw_root: Path,
        metadata_client: Any,
        dataset: ArchiveDataset = ArchiveDataset.KLINES,
        base_url: str = ARCHIVE_BASE_URL,
        timeout_seconds: float = 60.0,
        max_retries: int = 4,
        retry_base_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.raw_root = raw_root.resolve()
        self.metadata_client = metadata_client
        self.dataset = dataset
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self._sleep = sleeper
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "crypto-trading-ai/0.1.0"},
        )
        self._cached_object: ArchiveObject | None = None
        self._cached_candles: tuple[Candle, ...] = ()
        self._cached_metadata: dict[str, Any] | None = None

    def __enter__(self) -> BinanceArchiveClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_exchange_info(self, symbol: str) -> dict[str, Any]:
        return self.metadata_client.fetch_exchange_info(symbol)

    def fetch_object_bytes(self, archive_object: ArchiveObject) -> tuple[bytes, dict[str, Any]]:
        """Fetch, verify, and immutably cache one official archive object."""

        return self._load_object(archive_object)

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        ingested_at: datetime | None = None,
    ) -> list[Candle]:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("archive request must be timezone-aware with start < end")
        last_included = end - timedelta(microseconds=1)
        if (start.year, start.month) != (last_included.year, last_included.month):
            raise ValueError("archive client requests cannot cross a UTC month")
        archive_object = ArchiveObject(
            dataset=self.dataset,
            frequency=ArchiveFrequency.MONTHLY,
            symbol=symbol.upper(),
            interval=interval,
            period=date(start.year, start.month, 1),
        )
        if self._cached_object != archive_object:
            captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
            content, metadata = self._load_object(archive_object)
            self._cached_candles = tuple(self._parse_candle_rows(content, archive_object, captured))
            self._cached_object = archive_object
            self._cached_metadata = metadata
        return [row for row in self._cached_candles if start <= row.open_time < end]

    def source_metadata(self, start: datetime, _: datetime) -> dict[str, Any] | None:
        if self._cached_object is None or (
            self._cached_object.period.year,
            self._cached_object.period.month,
        ) != (start.year, start.month):
            return None
        return dict(self._cached_metadata or {})

    def _get(self, path: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(path)
                if response.status_code == 404:
                    raise ArchiveNotFoundError(path)
                if response.status_code in {418, 429} or response.status_code >= 500:
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    self._sleep(self.retry_base_seconds * (2**attempt))
                    continue
                response.raise_for_status()
                return response.content
            except ArchiveNotFoundError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self._sleep(self.retry_base_seconds * (2**attempt))
        raise RuntimeError(f"Official Binance archive request failed for {path}: {last_error}")

    def _load_object(self, archive_object: ArchiveObject) -> tuple[bytes, dict[str, Any]]:
        checksum_bytes = self._get(archive_object.checksum_url)
        expected_hash = self._parse_checksum(checksum_bytes, archive_object.filename)
        destination = self._raw_path(archive_object, expected_hash)
        if destination.exists():
            content = destination.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected_hash:
                raise ValueError(f"Cached archive checksum mismatch: {destination}")
        else:
            content = self._get(archive_object.relative_url)
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Official archive checksum mismatch for {archive_object.filename}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
            self._validate_zip(content, archive_object.filename)
            self._write_immutable(destination, content)
            self._write_immutable(destination.with_suffix(".zip.CHECKSUM"), checksum_bytes)
        self._validate_zip(content, archive_object.filename)
        return content, {
            "archive_url": f"{self._client.base_url}{archive_object.relative_url}",
            "checksum_url": f"{self._client.base_url}{archive_object.checksum_url}",
            "upstream_sha256": expected_hash,
            "raw_file": str(destination),
            "dataset": archive_object.dataset.value,
            "frequency": archive_object.frequency.value,
        }

    def _raw_path(self, archive_object: ArchiveObject, checksum: str) -> Path:
        return (
            self.raw_root
            / "archives"
            / "market=usdm"
            / f"dataset={archive_object.dataset.value}"
            / f"symbol={archive_object.symbol}"
            / f"interval={archive_object.interval}"
            / f"frequency={archive_object.frequency.value}"
            / f"year={archive_object.period.year:04d}"
            / f"month={archive_object.period.month:02d}"
            / f"sha256={checksum}"
            / archive_object.filename
        )

    @staticmethod
    def _parse_checksum(content: bytes, expected_filename: str) -> str:
        try:
            parts = content.decode("ascii").strip().split()
        except UnicodeDecodeError as exc:
            raise ValueError("Archive checksum file is not ASCII") from exc
        if len(parts) < 2 or parts[-1].lstrip("*") != expected_filename:
            raise ValueError("Archive checksum filename does not match requested object")
        value = parts[0].lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("Archive checksum is not a valid SHA-256 digest")
        return value

    @staticmethod
    def _validate_zip(content: bytes, expected_filename: str) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                bad = archive.testzip()
                if bad is not None:
                    raise ValueError(f"Corrupt member {bad} in {expected_filename}")
                files = [item for item in archive.infolist() if not item.is_dir()]
                if len(files) != 1:
                    raise ValueError(f"{expected_filename} must contain exactly one CSV")
                member = PurePosixPath(files[0].filename)
                if member.is_absolute() or ".." in member.parts or member.suffix.lower() != ".csv":
                    raise ValueError(f"Unsafe archive member: {files[0].filename}")
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Corrupt ZIP archive: {expected_filename}") from exc

    def _parse_candle_rows(
        self,
        content: bytes,
        archive_object: ArchiveObject,
        captured: datetime,
    ) -> list[Candle]:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            member = next(item for item in archive.infolist() if not item.is_dir())
            with archive.open(member) as raw_stream:
                text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8", newline="")
                rows = csv.reader(text_stream)
                result: list[Candle] = []
                for line_number, raw in enumerate(rows, start=1):
                    if line_number == 1 and raw and not raw[0].strip().lstrip("-").isdigit():
                        continue
                    result.append(self._parse_kline(raw, archive_object, captured, line_number))
        by_time: dict[datetime, Candle] = {}
        for candle in result:
            prior = by_time.get(candle.open_time)
            if prior is not None and prior.market_values != candle.market_values:
                raise ValueError(f"Conflicting archive candle at {candle.open_time.isoformat()}")
            by_time[candle.open_time] = candle
        return [by_time[key] for key in sorted(by_time)]

    def _parse_kline(
        self,
        raw: Sequence[str],
        archive_object: ArchiveObject,
        captured: datetime,
        line_number: int,
    ) -> Candle:
        if len(raw) < 12:
            raise ValueError(
                f"Archive {archive_object.filename} line {line_number} has {len(raw)} fields"
            )
        try:
            return Candle(
                symbol=archive_object.symbol,
                open_time=_utc_from_exchange_timestamp(raw[0]),
                open=Decimal(raw[1]),
                high=Decimal(raw[2]),
                low=Decimal(raw[3]),
                close=Decimal(raw[4]),
                base_volume=Decimal(raw[5]),
                close_time=_utc_from_exchange_timestamp(raw[6]),
                quote_volume=Decimal(raw[7]),
                trade_count=int(raw[8]),
                taker_buy_base_volume=Decimal(raw[9]),
                taker_buy_quote_volume=Decimal(raw[10]),
                source=self.row_source,
                ingested_at=captured,
            )
        except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Invalid archive kline in {archive_object.filename} line {line_number}"
            ) from exc

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> None:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite immutable archive object: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def expected_rows_for_object(archive_object: ArchiveObject) -> int:
    """Return the calendar maximum, used for coverage reporting only."""

    start = datetime(archive_object.period.year, archive_object.period.month, 1, tzinfo=UTC)
    if archive_object.period.month == 12:
        end = datetime(archive_object.period.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(archive_object.period.year, archive_object.period.month + 1, 1, tzinfo=UTC)
    return int((end - start).total_seconds() * 1_000) // interval_milliseconds(
        archive_object.interval
    )
