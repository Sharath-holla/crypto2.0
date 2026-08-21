from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from crypto_ai.data.binance import ArchiveDataset, BinanceArchiveClient
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase4_1.archive_market import ingest_archive_market_data


class _MetadataClient:
    def fetch_exchange_info(self, symbol: str) -> dict[str, object]:
        return {"instrument": {"symbol": symbol}}


def _zip(row_count: int) -> bytes:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    rows = []
    for index in range(row_count):
        opened = start + timedelta(minutes=5 * index)
        open_ms = int(opened.timestamp() * 1_000)
        rows.append(f"{open_ms},100.1,102,99,101.2,{open_ms + 299999},0,0,0,0,0,0")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-5m-2026-07.csv", "\n".join(rows) + "\n")
    return buffer.getvalue()


def _client(tmp_path: Path, content: bytes) -> BinanceArchiveClient:
    digest = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-5m-2026-07.zip\n")
        return httpx.Response(200, content=content)

    return BinanceArchiveClient(
        raw_root=tmp_path / "raw",
        metadata_client=_MetadataClient(),
        dataset=ArchiveDataset.MARK_PRICE_KLINES,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )


def test_archive_market_builds_bronze_lineage_and_causal_silver(tmp_path: Path) -> None:
    client = _client(tmp_path, _zip(12))
    start = datetime(2026, 7, 1, tzinfo=UTC)
    manifest_path = ingest_archive_market_data(
        client,
        kind=MarketDataKind.MARK_KLINE,
        symbol="BTCUSDT",
        interval="5m",
        start=start,
        end=start + timedelta(hours=1),
        output_root=tmp_path / "market",
    )
    table, manifest = read_market_dataset(manifest_path, MarketDataKind.MARK_KLINE)
    bronze = json.loads(Path(manifest["source_manifest"]).read_text(encoding="utf-8"))
    client.close()

    assert table.num_rows == 12
    assert table.column("open")[0].as_py() == Decimal("100.100000000000000000")
    assert table.column("availability_time")[0].as_py() == start + timedelta(minutes=5)
    assert table.column("source")[0].as_py() == "binance_usdm_mark_kline_archive"
    assert manifest["coverage"]["status"] == "PASS"
    assert bronze["representation"] == "immutable-upstream-zip"
    assert bronze["archive_count"] == 1


def test_archive_market_rejects_a_gap(tmp_path: Path) -> None:
    client = _client(tmp_path, _zip(11))
    start = datetime(2026, 7, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="coverage is incomplete"):
        ingest_archive_market_data(
            client,
            kind=MarketDataKind.MARK_KLINE,
            symbol="BTCUSDT",
            interval="5m",
            start=start,
            end=start + timedelta(hours=1),
            output_root=tmp_path / "market",
        )


def test_archive_market_fills_only_missing_ranges_from_public_rest(tmp_path: Path) -> None:
    client = _client(tmp_path, _zip(11))
    start = datetime(2026, 7, 1, tzinfo=UTC)
    missing_ms = int((start + timedelta(minutes=55)).timestamp() * 1_000)
    calls: list[tuple[str, dict[str, object] | None]] = []

    def request(path: str, params: dict[str, object] | None) -> object:
        calls.append((path, params))
        return [[missing_ms, "100", "102", "99", "101", "0", missing_ms + 299_999]]

    manifest_path = ingest_archive_market_data(
        client,
        kind=MarketDataKind.MARK_KLINE,
        symbol="BTCUSDT",
        interval="5m",
        start=start,
        end=start + timedelta(hours=1),
        output_root=tmp_path / "market",
        gap_fill_request_json=request,
    )
    _, manifest = read_market_dataset(manifest_path, MarketDataKind.MARK_KLINE)
    bronze = json.loads(Path(manifest["source_manifest"]).read_text(encoding="utf-8"))

    assert calls[0][0] == "/fapi/v1/markPriceKlines"
    assert manifest["coverage"]["status"] == "PASS"
    assert bronze["archive_coverage"]["missing_rows"] == 1
    assert bronze["rest_gap_fill"]["row_count"] == 1
