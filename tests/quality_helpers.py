from __future__ import annotations

from datetime import datetime
from pathlib import Path

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION, candles_to_table
from crypto_ai.data.storage import write_immutable
from crypto_ai.domain import Candle


def write_bronze_dataset(
    tmp_path: Path,
    partitions: list[tuple[datetime, datetime, list[Candle]]],
    *,
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    market: str = "usdm",
) -> tuple[Path, list[Path]]:
    root = tmp_path / "bronze"
    records = []
    files: list[Path] = []
    for start, end, candles in partitions:
        start_ms = int(start.timestamp() * 1_000)
        end_ms = int(end.timestamp() * 1_000)
        relative = Path(
            "klines",
            f"market={market}",
            f"symbol={symbol}",
            f"interval={interval}",
            f"date={start.date().isoformat()}",
            f"part-{start_ms}-{end_ms}.parquet",
        )
        path = root / relative
        checksum = write_immutable(
            path,
            candles_to_table(candles),
            metadata={
                "source": "binance",
                "market": market,
                "symbol": symbol,
                "interval": interval,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "ingestion_version": "0.1.0",
            },
        )
        files.append(path)
        records.append(
            {
                "partition_key": f"{start_ms}-{end_ms}",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": "complete",
                "row_count": len(candles),
                "file": relative.as_posix(),
                "sha256": checksum,
                "quality": {"is_valid": True},
            }
        )
    manifest_path = root / "manifests" / "test-dataset.json"
    write_manifest(
        manifest_path,
        {
            "run_id": "test-dataset",
            "source": "binance",
            "market": market,
            "symbol": symbol,
            "interval": interval,
            "start": partitions[0][0].isoformat(),
            "end": partitions[-1][1].isoformat(),
            "row_count": sum(len(candles) for _, _, candles in partitions),
            "file_locations": [record["file"] for record in records],
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": "0.1.0",
            "status": "completed",
            "partitions": records,
        },
    )
    return manifest_path, files
