from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_ai.config import BinanceSettings
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.storage import read_candle_parquet
from tests.factories import make_candle


class FakeBinanceClient:
    def __init__(self) -> None:
        self.instrument_calls = 0
        self.kline_calls = 0

    def fetch_exchange_info(self, symbol: str) -> dict:
        self.instrument_calls += 1
        return {
            "source": "binance_usdm_futures_rest",
            "market": "usdm",
            "symbol": symbol,
            "endpoint": "/fapi/v1/exchangeInfo",
            "fetched_at": datetime(2026, 8, 2, tzinfo=UTC).isoformat(),
            "instrument": {"symbol": symbol, "status": "TRADING"},
        }

    def fetch_klines(self, *, start: datetime, end: datetime, **_: object) -> list:
        self.kline_calls += 1
        base = datetime(2026, 8, 1, tzinfo=UTC)
        candles = [make_candle(index, start=base) for index in range(12)]
        return [candle for candle in candles if start <= candle.open_time < end]


def test_download_is_resumable_and_manifest_is_complete(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    settings = BinanceSettings(output_root=tmp_path / "bronze")
    client = FakeBinanceClient()
    downloader = HistoricalDownloader(settings, client)  # type: ignore[arg-type]
    request = DownloadRequest(start=start, end=start + timedelta(hours=1))

    first_manifest_path = downloader.download(request)
    second_manifest_path = downloader.download(request)

    assert first_manifest_path == second_manifest_path
    assert client.instrument_calls == 1
    assert client.kline_calls == 1
    manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["row_count"] == 12
    assert manifest["quality_summary"]["is_valid"] is True
    assert len(manifest["file_locations"]) == 1
    parquet_path = settings.output_root.resolve() / manifest["file_locations"][0]
    assert read_candle_parquet(parquet_path).num_rows == 12
    assert manifest["partitions"][0]["sha256"]


def test_checksum_mismatch_stops_instead_of_overwriting(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    settings = BinanceSettings(output_root=tmp_path / "bronze")
    client = FakeBinanceClient()
    downloader = HistoricalDownloader(settings, client)  # type: ignore[arg-type]
    request = DownloadRequest(start=start, end=start + timedelta(hours=1))
    manifest_path = downloader.download(request)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parquet_path = settings.output_root.resolve() / manifest["file_locations"][0]
    with parquet_path.open("ab") as stream:
        stream.write(b"tamper")

    with pytest.raises(ValueError, match="Checksum mismatch"):
        downloader.download(request)

    failed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert client.kline_calls == 1


def test_download_request_rejects_sub_millisecond_boundaries() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="whole milliseconds"):
        DownloadRequest(
            start=start + timedelta(microseconds=1),
            end=start + timedelta(minutes=5),
        )
