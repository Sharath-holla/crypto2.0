from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from crypto_ai.config import BinanceSettings
from crypto_ai.data.binance import BinanceArchiveClient
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.quality.engine import QualityEngine


class _MetadataClient:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_exchange_info(self, symbol: str) -> dict[str, object]:
        self.calls += 1
        return {"instrument": {"symbol": symbol}, "market": "usdm"}


def _zip() -> bytes:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    rows = []
    for index in range(12):
        open_ms = int((start + timedelta(minutes=5 * index)).timestamp() * 1_000)
        rows.append(f"{open_ms},100,102,99,101,10,{open_ms + 299999},1010,20,6,606,0")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-5m-2026-07.csv", "\n".join(rows) + "\n")
    return buffer.getvalue()


def test_archive_download_is_resumable_and_quality_uses_archive_source(tmp_path: Path) -> None:
    content = _zip()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith(".CHECKSUM"):
            digest = hashlib.sha256(content).hexdigest()
            return httpx.Response(200, text=f"{digest}  BTCUSDT-5m-2026-07.zip\n")
        return httpx.Response(200, content=content)

    metadata = _MetadataClient()
    archive = BinanceArchiveClient(
        raw_root=tmp_path / "raw",
        metadata_client=metadata,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    settings = BinanceSettings(output_root=tmp_path / "bronze")
    downloader = HistoricalDownloader(settings, archive)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    request = DownloadRequest(start=start, end=start + timedelta(hours=1))

    manifest_path = downloader.download(request)
    assert downloader.download(request) == manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = QualityEngine().validate_manifest(manifest_path)
    archive.close()

    assert metadata.calls == 1
    assert len(requests) == 2
    assert manifest["source"] == "binance_public_archive"
    assert manifest["row_source"] == "binance_usdm_futures_archive"
    assert manifest["source_transport"] == "archive"
    assert "transport=archive" in manifest["file_locations"][0]
    assert manifest["partitions"][0]["source_metadata"]["dataset"] == "klines"
    assert report.overall_status.value == "PASS"
