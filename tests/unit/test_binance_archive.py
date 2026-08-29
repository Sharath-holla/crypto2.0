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


def _monthly_archive(
    *,
    symbol: str,
    interval: str,
    period: str,
    opens: list[datetime],
) -> bytes:
    interval_ms = {
        "5m": 5 * 60_000,
        "12h": 12 * 60 * 60_000,
        "1d": 24 * 60 * 60_000,
    }[interval]
    rows = []
    for opened in opens:
        open_ms = int(opened.timestamp() * 1_000)
        rows.append(f"{open_ms},100,102,99,101,10,{open_ms + interval_ms - 1},1010,20,6,606,0")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{symbol}-{interval}-{period}.csv", "\n".join(rows) + "\n")
    return buffer.getvalue()


def _boundary_transport(
    objects: dict[str, bytes],
    content_reads: list[str],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for filename, content in objects.items():
            if path.endswith(f"{filename}.CHECKSUM"):
                digest = hashlib.sha256(content).hexdigest()
                return httpx.Response(200, content=f"{digest}  {filename}\n".encode())
            if path.endswith(filename):
                content_reads.append(filename)
                return httpx.Response(200, content=content)
        return httpx.Response(404)

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


def test_exact_interval_bounds_inspect_only_outer_objects_and_reuse_cache(
    tmp_path: Path,
) -> None:
    symbol = "1000BTTCUSDT"
    january_opens = [datetime(2022, 1, day, tzinfo=UTC) for day in range(26, 32)]
    april_opens = [datetime(2022, 4, day, tzinfo=UTC) for day in range(1, 12)]
    objects = {
        f"{symbol}-1d-2022-01.zip": _monthly_archive(
            symbol=symbol,
            interval="1d",
            period="2022-01",
            opens=january_opens,
        ),
        f"{symbol}-1d-2022-04.zip": _monthly_archive(
            symbol=symbol,
            interval="1d",
            period="2022-04",
            opens=april_opens,
        ),
    }
    content_reads: list[str] = []
    transport = _boundary_transport(objects, content_reads)
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=transport,
        sleeper=lambda _: None,
    )

    bounds = client.inspect_interval_bounds(
        symbol=symbol,
        interval="1d",
        archive_start=datetime(2022, 1, 1, tzinfo=UTC),
        archive_end=datetime(2022, 5, 1, tzinfo=UTC),
    )
    first = client.fetch_klines(
        symbol=symbol,
        interval="1d",
        start=datetime(2022, 1, 26, tzinfo=UTC),
        end=datetime(2022, 1, 27, tzinfo=UTC),
    )
    last = client.fetch_klines(
        symbol=symbol,
        interval="1d",
        start=datetime(2022, 4, 11, tzinfo=UTC),
        end=datetime(2022, 4, 12, tzinfo=UTC),
    )
    metadata = client.source_metadata(
        datetime(2022, 4, 11, tzinfo=UTC),
        datetime(2022, 4, 12, tzinfo=UTC),
    )
    client.close()

    assert bounds.first_open_time == datetime(2022, 1, 26, tzinfo=UTC)
    assert bounds.last_open_time == datetime(2022, 4, 11, tzinfo=UTC)
    assert bounds.end_exclusive == datetime(2022, 4, 12, tzinfo=UTC)
    assert bounds.inspected_objects == (
        f"{symbol}-1d-2022-01.zip",
        f"{symbol}-1d-2022-04.zip",
    )
    assert len(first) == len(last) == 1
    assert content_reads == list(bounds.inspected_objects)
    assert metadata is not None
    assert metadata["exact_first_open_time"] == "2022-04-01T00:00:00+00:00"
    assert metadata["exact_last_open_time"] == "2022-04-11T00:00:00+00:00"

    second = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=transport,
        sleeper=lambda _: None,
    )
    assert (
        second.inspect_interval_bounds(
            symbol=symbol,
            interval="1d",
            archive_start=datetime(2022, 1, 1, tzinfo=UTC),
            archive_end=datetime(2022, 5, 1, tzinfo=UTC),
        )
        == bounds
    )
    second.close()
    assert content_reads == list(bounds.inspected_objects)


def test_legacy_coarse_range_probes_inward_to_interval_first_month(tmp_path: Path) -> None:
    symbol = "LEGACYUSDT"
    objects = {
        f"{symbol}-1d-2022-03.zip": _monthly_archive(
            symbol=symbol,
            interval="1d",
            period="2022-03",
            opens=[datetime(2022, 3, 10, tzinfo=UTC)],
        ),
        f"{symbol}-1d-2022-04.zip": _monthly_archive(
            symbol=symbol,
            interval="1d",
            period="2022-04",
            opens=[datetime(2022, 4, 11, tzinfo=UTC)],
        ),
    }
    content_reads: list[str] = []
    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=_boundary_transport(objects, content_reads),
        sleeper=lambda _: None,
    )

    bounds = client.inspect_interval_bounds(
        symbol=symbol,
        interval="1d",
        archive_start=datetime(2022, 1, 1, tzinfo=UTC),
        archive_end=datetime(2022, 5, 1, tzinfo=UTC),
    )
    client.close()

    assert bounds.first_open_time == datetime(2022, 3, 10, tzinfo=UTC)
    assert bounds.end_exclusive == datetime(2022, 4, 12, tzinfo=UTC)
    assert bounds.inspected_objects == (
        f"{symbol}-1d-2022-01.zip",
        f"{symbol}-1d-2022-02.zip",
        f"{symbol}-1d-2022-03.zip",
        f"{symbol}-1d-2022-04.zip",
    )
    assert content_reads == [
        f"{symbol}-1d-2022-03.zip",
        f"{symbol}-1d-2022-04.zip",
    ]
