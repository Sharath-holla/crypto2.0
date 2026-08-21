from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from crypto_ai.data.binance.archive import (
    ArchiveDataset,
    ArchiveFrequency,
    ArchiveNotFoundError,
    ArchiveObject,
    BinanceArchiveClient,
    expected_rows_for_object,
    monthly_objects,
)


class _MetadataClient:
    def fetch_exchange_info(self, symbol: str) -> dict[str, object]:
        return {"instrument": {"symbol": symbol}}


def _archive_bytes(*, header: bool = True, row_count: int = 12) -> bytes:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    rows: list[str] = []
    if header:
        rows.append(
            "open_time,open,high,low,close,volume,close_time,quote_volume,"
            "count,taker_buy_volume,taker_buy_quote_volume,ignore"
        )
    for index in range(row_count):
        opened = start + timedelta(minutes=5 * index)
        open_ms = int(opened.timestamp() * 1_000)
        close_ms = open_ms + 299_999
        rows.append(f"{open_ms},100.100000000000000001,102,99,101,10,{close_ms},1010,20,6,606,0")
    payload = ("\n".join(rows) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-5m-2026-07.csv", payload)
    return buffer.getvalue()


def _transport(content: bytes, *, checksum: str | None = None) -> httpx.MockTransport:
    digest = checksum or hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            body = f"{digest}  BTCUSDT-5m-2026-07.zip\n".encode()
            return httpx.Response(200, content=body)
        return httpx.Response(200, content=content)

    return httpx.MockTransport(handler)


def test_archive_object_urls_and_month_coverage() -> None:
    item = ArchiveObject(
        dataset=ArchiveDataset.KLINES,
        frequency=ArchiveFrequency.MONTHLY,
        symbol="BTCUSDT",
        interval="5m",
        period=date(2026, 7, 1),
    )

    assert item.relative_url == "/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2026-07.zip"
    assert item.checksum_url == f"{item.relative_url}.CHECKSUM"
    assert expected_rows_for_object(item) == 31 * 24 * 12
    objects = monthly_objects(
        ArchiveDataset.KLINES,
        symbol="btcusdt",
        interval="5m",
        start=datetime(2026, 6, 15, tzinfo=UTC),
        end=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert [entry.period_token for entry in objects] == ["2026-06", "2026-07"]


@pytest.mark.parametrize("header", [True, False])
def test_archive_checksum_zip_and_exact_decimal_parsing(tmp_path: Path, header: bool) -> None:
    content = _archive_bytes(header=header)
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=_transport(content),
        sleeper=lambda _: None,
    )
    start = datetime(2026, 7, 1, tzinfo=UTC)

    candles = client.fetch_klines(
        symbol="BTCUSDT",
        interval="5m",
        start=start,
        end=start + timedelta(hours=1),
        ingested_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    metadata = client.source_metadata(start, start + timedelta(hours=1))
    client.close()

    assert len(candles) == 12
    assert candles[0].open == Decimal("100.100000000000000001")
    assert candles[0].source == "binance_usdm_futures_archive"
    assert metadata is not None
    assert metadata["upstream_sha256"] == hashlib.sha256(content).hexdigest()
    assert Path(str(metadata["raw_file"])).read_bytes() == content


def test_archive_detects_checksum_mismatch(tmp_path: Path) -> None:
    content = _archive_bytes()
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=_transport(content, checksum="0" * 64),
        sleeper=lambda _: None,
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=datetime(2026, 7, 1, tzinfo=UTC),
            end=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_archive_detects_corrupt_zip(tmp_path: Path) -> None:
    content = b"not a zip"
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=_transport(content),
        sleeper=lambda _: None,
    )

    with pytest.raises(ValueError, match="Corrupt ZIP"):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=datetime(2026, 7, 1, tzinfo=UTC),
            end=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_archive_reports_missing_official_object(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=transport,
        sleeper=lambda _: None,
    )

    with pytest.raises(ArchiveNotFoundError):
        client.fetch_klines(
            symbol="BTCUSDT",
            interval="5m",
            start=datetime(2026, 7, 1, tzinfo=UTC),
            end=datetime(2026, 7, 2, tzinfo=UTC),
        )
