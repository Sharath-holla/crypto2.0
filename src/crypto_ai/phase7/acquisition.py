from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.config import BinanceSettings, load_binance_settings
from crypto_ai.data.binance import BinanceArchiveClient, BinanceRestClient
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.policy import load_quality_policy
from crypto_ai.data.quality.promotion import SilverPromoter
from crypto_ai.data.storage import file_sha256, read_candle_parquet
from crypto_ai.domain import interval_milliseconds
from crypto_ai.phase4.asof import causal_asof_join
from crypto_ai.phase4.market_data import (
    DerivativesMarketDataClient,
    MarketDataKind,
    ingest_public_market_data,
    read_market_dataset,
)
from crypto_ai.phase4_1.archive_market import ingest_archive_market_data
from crypto_ai.phase7.config import Phase7Config
from crypto_ai.phase7.registry import SymbolRegistry

_DATE_PARTITION = re.compile(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)")


@dataclass(frozen=True, slots=True)
class AcquisitionPaths:
    bronze: Path
    raw_archive: Path
    quality: Path
    silver: Path
    quarantine: Path
    market: Path

    @classmethod
    def from_config(cls, config: Phase7Config) -> AcquisitionPaths:
        root = config.paths.data_root.resolve() / "phase7"
        return cls(
            bronze=root / "bronze" / "binance",
            raw_archive=root / "bronze" / "binance-public-data",
            quality=root / "quality",
            silver=root / "silver" / "binance",
            quarantine=root / "quarantine",
            market=root / "market",
        )


class _RegistryMetadata:
    def __init__(self, registry: SymbolRegistry) -> None:
        self._records = registry.by_symbol()

    def fetch_exchange_info(self, symbol: str) -> dict[str, Any]:
        record = self._records[symbol.upper()]
        return {
            "symbol": record.symbol,
            "pair": record.symbol,
            "contractType": record.contract_type,
            "status": record.current_status,
            "baseAsset": record.base_asset,
            "quoteAsset": record.quote_asset,
            "onboardDate": (
                int(record.onboard_date.timestamp() * 1_000) if record.onboard_date else None
            ),
            "source": "phase7_historical_symbol_registry",
        }


def _candle_settings(
    config: Phase7Config,
    paths: AcquisitionPaths,
    *,
    symbol: str,
    interval: str,
) -> BinanceSettings:
    return load_binance_settings(
        config.binance_config,
        {
            "market": "usdm",
            "symbol": symbol,
            "interval": interval,
            "output_root": paths.bronze,
        },
    )


def _promote_candles(
    config: Phase7Config,
    paths: AcquisitionPaths,
    manifest: Path,
) -> Path:
    policy = load_quality_policy(config.quality_config)
    engine = QualityEngine(policy)
    report = engine.validate_manifest(manifest)
    engine.write_report(report, paths.quality)
    result = SilverPromoter(policy).promote(
        manifest,
        report,
        silver_root=paths.silver,
        quarantine_root=paths.quarantine,
    )
    if not result.promoted or result.promotion_manifest is None:
        raise ValueError(f"Phase 7 quality gate rejected {manifest}: {report.overall_status}")
    return result.promotion_manifest


def acquire_candle_family(
    config: Phase7Config,
    registry: SymbolRegistry,
    *,
    symbols: tuple[str, ...],
    interval: str,
    start: datetime,
    end: datetime,
) -> dict[str, str]:
    """Acquire checksum-verified official archives and promote through the quality gate."""

    config.assert_cloud_execution_allowed()
    paths = AcquisitionPaths.from_config(config)
    metadata = _RegistryMetadata(registry)
    records = registry.by_symbol()
    manifests: dict[str, str] = {}
    for position, symbol in enumerate(symbols, start=1):
        record = records[symbol]
        symbol_start = max(start.astimezone(UTC), record.available_from)
        symbol_end = min(end.astimezone(UTC), record.available_until or end.astimezone(UTC))
        if symbol_start >= symbol_end:
            continue
        settings = _candle_settings(
            config,
            paths,
            symbol=symbol,
            interval=interval,
        )
        print(f"[phase7:data] {interval} symbol {position}/{len(symbols)} {symbol}", flush=True)
        with BinanceArchiveClient(
            raw_root=paths.raw_archive,
            metadata_client=metadata,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            retry_base_seconds=settings.retry_base_seconds,
        ) as client:
            bronze_manifest = HistoricalDownloader(settings, client).download(
                DownloadRequest(start=symbol_start, end=symbol_end)
            )
        manifests[symbol] = str(_promote_candles(config, paths, bronze_manifest).resolve())
    return manifests


def acquire_discovery_daily(
    config: Phase7Config,
    registry: SymbolRegistry,
) -> dict[str, str]:
    """Acquire bounded 1d evidence for core selection and causal fold admissions.

    The wider discovery catalog is not model membership. Each expansion fold
    still applies its policy using only rows strictly before that fold's TRAIN
    end, then caps the active universe before full-resolution acquisition.
    """

    core_cutoff = config.universe.core_selection_cutoff
    end = config.research_cutoff if config.universe.enable_expansion else core_cutoff
    start = core_cutoff - timedelta(days=config.universe.selection_lookback_days)
    symbols = tuple(
        record.symbol
        for record in registry.records
        if record.quote_asset == config.universe.quote_asset
        and record.contract_type == config.universe.contract_type
        and set(config.universe.required_intervals).issubset(record.available_intervals)
        and record.available_from < end - timedelta(days=config.universe.minimum_history_days)
    )
    return acquire_candle_family(
        config,
        registry,
        symbols=symbols,
        interval="1d",
        start=start,
        end=end,
    )


def load_candle_family(
    manifests: dict[str, str],
    *,
    interval: str,
    start: datetime,
    end: datetime,
) -> pa.Table:
    tables: list[pa.Table] = []
    for symbol, manifest in sorted(manifests.items()):
        manifest_path = Path(manifest).resolve()
        payload = read_manifest(manifest_path)
        if payload is None or payload.get("quality_status") not in {"PASS", "WARN"}:
            raise ValueError(f"Ineligible Silver manifest: {manifest_path}")
        root = manifest_path.parent.parent
        selected: list[pa.Table] = []
        for record in payload.get("output_files", []):
            relative = str(record["file"])
            match = _DATE_PARTITION.search(relative.replace("\\", "/"))
            if match:
                partition_date = datetime.fromisoformat(match.group(1)).date()
                if partition_date < start.date() or partition_date > end.date():
                    continue
            path = root / relative
            if not path.exists() or file_sha256(path) != record.get("sha256"):
                raise ValueError(f"Silver checksum mismatch: {path}")
            table = read_candle_parquet(path)
            times = table.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
            start_us = int(start.astimezone(UTC).timestamp() * 1_000_000)
            end_us = int(end.astimezone(UTC).timestamp() * 1_000_000)
            mask = (times >= start_us) & (times < end_us)
            if np.any(mask):
                selected.append(table.filter(pa.array(mask)))
        if not selected:
            raise ValueError(f"No {symbol} {interval} rows exist in requested window")
        symbol_table = pa.concat_tables(selected).sort_by([("open_time", "ascending")])
        if set(symbol_table.column("symbol").to_pylist()) != {symbol}:
            raise ValueError(f"Silver family symbol mismatch for {symbol}")
        tables.append(symbol_table)
    if not tables:
        raise ValueError(f"No {interval} candle tables were available")
    return pa.concat_tables(tables).sort_by([("symbol", "ascending"), ("open_time", "ascending")])


def acquire_derivative_family(
    config: Phase7Config,
    registry: SymbolRegistry,
    *,
    symbols: tuple[str, ...],
    start: datetime,
    end: datetime,
) -> dict[str, dict[str, str]]:
    config.assert_cloud_execution_allowed()
    paths = AcquisitionPaths.from_config(config)
    records = registry.by_symbol()
    result: dict[str, dict[str, str]] = {}
    for position, symbol in enumerate(symbols, start=1):
        record = records[symbol]
        symbol_start = max(start, record.available_from)
        symbol_end = min(end, record.available_until or end)
        settings = _candle_settings(config, paths, symbol=symbol, interval="5m")
        print(
            f"[phase7:data] derivatives symbol {position}/{len(symbols)} {symbol}",
            flush=True,
        )
        with BinanceRestClient(settings) as rest_client:
            funding = DerivativesMarketDataClient(rest_client.get_public_json).fetch(
                MarketDataKind.FUNDING,
                symbol=symbol,
                start=symbol_start,
                end=symbol_end,
            )
            funding_manifest = ingest_public_market_data(
                funding,
                kind=MarketDataKind.FUNDING,
                symbol=symbol,
                interval=None,
                output_root=paths.market,
                request_start=symbol_start,
                request_end=symbol_end,
            )
            with BinanceArchiveClient(
                raw_root=paths.raw_archive,
                metadata_client=rest_client,
                timeout_seconds=settings.timeout_seconds,
                max_retries=settings.max_retries,
                retry_base_seconds=settings.retry_base_seconds,
            ) as archive:
                mark_manifest = ingest_archive_market_data(
                    archive,
                    kind=MarketDataKind.MARK_KLINE,
                    symbol=symbol,
                    interval="5m",
                    start=symbol_start,
                    end=symbol_end,
                    output_root=paths.market,
                    gap_fill_request_json=rest_client.get_public_json,
                )
                index_manifest = ingest_archive_market_data(
                    archive,
                    kind=MarketDataKind.INDEX_KLINE,
                    symbol=symbol,
                    interval="5m",
                    start=symbol_start,
                    end=symbol_end,
                    output_root=paths.market,
                    gap_fill_request_json=rest_client.get_public_json,
                )
        result[symbol] = {
            "funding": str(funding_manifest.resolve()),
            "mark": str(mark_manifest.resolve()),
            "index": str(index_manifest.resolve()),
        }
    return result


def align_derivatives(
    candles: pa.Table,
    manifests: dict[str, dict[str, str]],
) -> pa.Table:
    """Attach only already-available funding, mark, and index observations."""

    candle_symbols = np.asarray(candles.column("symbol").combine_chunks().to_pylist(), dtype=object)
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    feature_times = open_times + interval_milliseconds("5m") * 1_000
    outputs = {
        "funding_rate": np.full(candles.num_rows, np.nan),
        "mark_price": np.full(candles.num_rows, np.nan),
        "index_price": np.full(candles.num_rows, np.nan),
    }
    specifications = (
        ("funding", MarketDataKind.FUNDING, "funding_rate", 24 * 60 * 60_000_000),
        ("mark", MarketDataKind.MARK_KLINE, "close", 5 * 60_000_000),
        ("index", MarketDataKind.INDEX_KLINE, "close", 5 * 60_000_000),
    )
    for symbol, family in sorted(manifests.items()):
        target = np.flatnonzero(candle_symbols == symbol)
        for key, kind, source_column, maximum_age in specifications:
            table, _ = read_market_dataset(Path(family[key]), kind)
            available = (
                table.column("availability_time").combine_chunks().cast(pa.int64()).to_numpy()
            )
            values = np.asarray(
                table.column(source_column).combine_chunks().to_pylist(), dtype=np.float64
            )
            aligned = causal_asof_join(
                feature_times[target],
                available,
                {source_column: values},
                maximum_age_us=maximum_age,
            )
            destination = {
                "funding": "funding_rate",
                "mark": "mark_price",
                "index": "index_price",
            }[key]
            outputs[destination][target] = aligned.values[source_column]
    result = candles
    for name, values in outputs.items():
        result = result.append_column(name, pa.array(values))
    return result
