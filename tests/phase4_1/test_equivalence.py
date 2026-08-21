from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import write_immutable
from crypto_ai.phase4_1.equivalence import compare_candle_transports
from tests.factories import make_candle


def _transport_manifest(
    root: Path, name: str, source: str, *, different_close: bool = False
) -> Path:
    candle = make_candle(source=source)
    if different_close:
        candle = replace(candle, close=candle.close + Decimal("1"))
    file_path = root / f"{name}.parquet"
    checksum = write_immutable(file_path, candles_to_table([candle]), metadata={"interval": "5m"})
    manifest = root / "manifests" / f"{name}.json"
    write_manifest(
        manifest,
        {
            "source": "binance_public_archive" if "archive" in name else "binance",
            "market": "usdm",
            "symbol": "BTCUSDT",
            "interval": "5m",
            "partitions": [{"file": file_path.name, "sha256": checksum}],
        },
    )
    return manifest


def test_archive_rest_equivalence_is_field_by_field(tmp_path: Path) -> None:
    archive = _transport_manifest(tmp_path, "archive", "binance_usdm_futures_archive")
    rest = _transport_manifest(tmp_path, "rest", "binance_usdm_futures_rest")

    equivalent = compare_candle_transports(archive, rest)

    assert equivalent["equivalent"] is True
    assert equivalent["timestamps_equal"] is True
    assert all(item["mismatch_count"] == 0 for item in equivalent["fields"].values())


def test_archive_rest_equivalence_reports_exact_discrepancy(tmp_path: Path) -> None:
    archive = _transport_manifest(tmp_path, "archive", "binance_usdm_futures_archive")
    rest = _transport_manifest(tmp_path, "rest", "binance_usdm_futures_rest", different_close=True)

    report = compare_candle_transports(archive, rest)

    assert report["equivalent"] is False
    assert report["fields"]["close"]["mismatch_count"] == 1
    assert report["fields"]["open"]["mismatch_count"] == 0
