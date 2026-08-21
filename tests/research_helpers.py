from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import write_immutable
from crypto_ai.domain import Candle


def make_research_candles(
    count: int,
    *,
    gap_index: int | None = None,
    start: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        if index == gap_index:
            continue
        open_time = start + timedelta(minutes=5 * index)
        base = Decimal("50000") + Decimal(index * 3) + Decimal((index % 11) ** 2)
        change = Decimal((index % 7) - 3) / Decimal("2")
        close = base + change
        high = max(base, close) + Decimal("8") + Decimal(index % 3)
        low = min(base, close) - Decimal("7") - Decimal(index % 2)
        volume = Decimal("10") + Decimal(index % 13) + Decimal(index // 17) / Decimal("10")
        quote_volume = volume * close
        candles.append(
            Candle(
                symbol="BTCUSDT",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5) - timedelta(milliseconds=1),
                open=base,
                high=high,
                low=low,
                close=close,
                base_volume=volume,
                quote_volume=quote_volume,
                trade_count=100 + index % 37,
                taker_buy_base_volume=volume / Decimal("2"),
                taker_buy_quote_volume=quote_volume / Decimal("2"),
                source="binance_usdm_futures_rest",
                ingested_at=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
    return candles


def write_silver_dataset(tmp_path: Path, candles: list[Candle]) -> tuple[Path, Path]:
    root = tmp_path / "silver" / "binance"
    relative = Path(
        "klines",
        "market=usdm",
        "symbol=BTCUSDT",
        "interval=5m",
        f"date={candles[0].open_time.date().isoformat()}",
        "part-test.parquet",
    )
    path = root / relative
    silver_version = "silver-test-v1"
    checksum = write_immutable(
        path,
        candles_to_table(candles),
        metadata={
            "source": "binance",
            "market": "usdm",
            "symbol": "BTCUSDT",
            "interval": "5m",
            "requested_start": candles[0].open_time.isoformat(),
            "requested_end": (candles[-1].open_time + timedelta(minutes=5)).isoformat(),
            "ingestion_version": "0.1.0",
            "layer": "silver",
            "source_layer": "bronze",
            "source_file": "synthetic-bronze.parquet",
            "source_sha256": "synthetic-bronze-sha256",
            "source_manifest": "synthetic-bronze-manifest.json",
            "source_dataset_version": "dataset-test-v1",
            "validation_report_id": "quality-test-v1",
            "validation_version": "1.0.0",
            "silver_dataset_version": silver_version,
            "exact_duplicates_removed": "0",
        },
    )
    manifest_path = root / "manifests" / f"{silver_version}.json"
    write_manifest(
        manifest_path,
        {
            "silver_dataset_version": silver_version,
            "quality_status": "PASS",
            "source_manifest": "synthetic-bronze-manifest.json",
            "source_dataset_version": "dataset-test-v1",
            "validation_report_id": "quality-test-v1",
            "output_files": [
                {
                    "file": relative.as_posix(),
                    "sha256": checksum,
                    "row_count": len(candles),
                    "source_file": "synthetic-bronze.parquet",
                    "source_sha256": "synthetic-bronze-sha256",
                    "exact_duplicates_removed": 0,
                }
            ],
        },
    )
    return manifest_path, path
