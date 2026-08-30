from __future__ import annotations

import logging
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.config import BinanceSettings, load_binance_settings
from crypto_ai.data.binance import ArchiveCandleBounds, BinanceArchiveClient, BinanceRestClient
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.models import DatasetQualityReport, ValidationStatus
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
from crypto_ai.phase4_1.equivalence import compare_candle_transports
from crypto_ai.phase4_1.reconcile import reconcile_archive_with_rest
from crypto_ai.phase7.config import Phase7Config, stable_hash
from crypto_ai.phase7.registry import SymbolRecord, SymbolRegistry
from crypto_ai.phase7.segments import (
    AcquisitionOutcome,
    AcquisitionStatus,
    CandleFamilyAcquisition,
    CausalDataGap,
    ReconciliationStatus,
)

_DATE_PARTITION = re.compile(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)")
logger = logging.getLogger(__name__)
AcquisitionProgress = Callable[[int, int, str, str, str], None]

_RECONCILABLE_MARKET_VALUE_CHECKS = frozenset(
    {
        "high_below_open",
        "high_below_close",
        "high_below_low",
        "low_above_open",
        "low_above_close",
        "non_positive_price",
        "invalid_ohlc",
        "negative_base_volume",
        "negative_quote_volume",
        "negative_taker_buy_base_volume",
        "negative_taker_buy_quote_volume",
        "negative_trade_count",
        "taker_buy_base_exceeds_volume",
        "taker_buy_quote_exceeds_volume",
        "positive_volume_without_trades",
        "zero_base_volume_with_activity",
    }
)


@dataclass(frozen=True, slots=True)
class AcquisitionPaths:
    bronze: Path
    raw_archive: Path
    quality: Path
    silver: Path
    quarantine: Path
    reconciliation: Path
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
            reconciliation=root / "reconciliation",
            market=root / "market",
        )


class QualityGateRejected(ValueError):
    """Structured Phase 7 rejection retaining the immutable quality report."""

    def __init__(self, manifest: Path, report: DatasetQualityReport) -> None:
        self.manifest = manifest.resolve()
        self.report = report
        super().__init__(f"Phase 7 quality gate rejected {manifest}: {report.overall_status}")


@dataclass(frozen=True, slots=True)
class ReconciliationAttempt:
    corrected_manifest: Path | None = None
    segment_source_manifest: Path | None = None
    gaps: tuple[CausalDataGap, ...] = ()

    @property
    def identical_invalid(self) -> bool:
        return self.segment_source_manifest is not None and bool(self.gaps)


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


class _RestReconciliationClient:
    """Public REST candle transport with historical registry metadata."""

    source_identity = "binance"
    row_source = "binance_usdm_futures_rest"
    source_transport = "rest"

    def __init__(self, client: BinanceRestClient, metadata: _RegistryMetadata) -> None:
        self._client = client
        self._metadata = metadata

    def fetch_exchange_info(self, symbol: str) -> dict[str, Any]:
        return self._metadata.fetch_exchange_info(symbol)

    def fetch_klines(self, **kwargs: Any):
        return self._client.fetch_klines(**kwargs)


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
        raise QualityGateRejected(manifest, report)
    return result.promotion_manifest


def _failed_market_value_partitions(report: DatasetQualityReport) -> tuple[str, ...]:
    failures = [check for check in report.checks if check.status is ValidationStatus.FAIL]
    if not failures or any(
        check.check_name not in _RECONCILABLE_MARKET_VALUE_CHECKS or check.partition is None
        for check in failures
    ):
        return ()
    return tuple(sorted({str(check.partition) for check in failures}))


def _attempt_archive_reconciliation(
    config: Phase7Config,
    paths: AcquisitionPaths,
    registry: SymbolRegistry,
    rejection: QualityGateRejected,
) -> ReconciliationAttempt:
    """Compose proven REST corrections for archive-only market-value failures.

    This is deliberately one-shot and narrow. The original archive manifest,
    quality report, quarantine reference, raw archive, and REST overlay all
    remain immutable. Any non-market-value failure, timestamp disagreement, or
    persistent REST inconsistency remains a hard stop.
    """

    manifest = read_manifest(rejection.manifest)
    if manifest is None or manifest.get("source") != "binance_public_archive":
        return ReconciliationAttempt()
    partition_keys = _failed_market_value_partitions(rejection.report)
    if not partition_keys:
        return ReconciliationAttempt()
    records = {
        str(record.get("partition_key")): record
        for record in manifest.get("partitions", [])
        if isinstance(record, dict)
    }
    selected = [records.get(key) for key in partition_keys]
    if any(
        record is None or record.get("status") != "complete" or not record.get("file")
        for record in selected
    ):
        return ReconciliationAttempt()

    symbol = str(manifest["symbol"])
    interval = str(manifest["interval"])
    metadata = _RegistryMetadata(registry)
    settings = _candle_settings(config, paths, symbol=symbol, interval=interval)
    rest_manifests: list[Path] = []
    comparison_reports: list[Path] = []
    gaps: list[CausalDataGap] = []
    with BinanceRestClient(settings) as rest:
        client = _RestReconciliationClient(rest, metadata)
        for key, record in zip(partition_keys, selected, strict=True):
            assert record is not None
            start = datetime.fromisoformat(str(record["start"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(record["end"]).replace("Z", "+00:00"))
            rest_manifest = HistoricalDownloader(settings, client).download(
                DownloadRequest(start=start, end=end)
            )
            comparison_id = stable_hash(
                {
                    "archive_manifest": str(rejection.manifest),
                    "archive_partition": key,
                    "rest_manifest": str(rest_manifest.resolve()),
                    "comparison": "field_exact_archive_rest_v1",
                }
            )
            comparison_path = paths.reconciliation / f"archive-rest-{comparison_id}.json"
            comparison = compare_candle_transports(
                rejection.manifest,
                rest_manifest,
                output_path=comparison_path,
            )
            expected_rows = int(record.get("row_count", 0))
            exact_identity = (
                comparison.get("equivalent") is True
                and comparison.get("timestamps_equal") is True
                and comparison.get("left_rows") == expected_rows
                and comparison.get("right_rows") == expected_rows
            )
            exact_correction = (
                comparison.get("equivalent") is False
                and comparison.get("timestamps_equal") is True
                and comparison.get("left_rows") == expected_rows
                and comparison.get("right_rows") == expected_rows
            )
            if exact_identity:
                quality_report = paths.quality / f"{rejection.report.report_id}.json"
                quarantine = paths.quarantine / f"{rejection.report.report_id}.json"
                if not quality_report.is_file() or not quarantine.is_file():
                    raise FileNotFoundError(
                        "Identical invalid reconciliation is missing quality/quarantine lineage"
                    )
                failed_checks = tuple(
                    sorted(
                        {
                            check.check_name
                            for check in rejection.report.checks
                            if check.status is ValidationStatus.FAIL and str(check.partition) == key
                        }
                    )
                )
                gaps.append(
                    CausalDataGap(
                        symbol=symbol,
                        interval=interval,
                        start=start,
                        end=end,
                        partition=key,
                        failed_checks=failed_checks,
                        source_manifest=str(rejection.manifest),
                        source_manifest_sha256=file_sha256(rejection.manifest),
                        quality_report=str(quality_report.resolve()),
                        quality_report_sha256=file_sha256(quality_report),
                        quarantine=str(quarantine.resolve()),
                        quarantine_sha256=file_sha256(quarantine),
                        rest_manifest=str(rest_manifest.resolve()),
                        rest_manifest_sha256=file_sha256(rest_manifest),
                        comparison_report=str(comparison_path.resolve()),
                        comparison_report_sha256=file_sha256(comparison_path),
                        reconciliation_status=ReconciliationStatus.IDENTICAL_INVALID,
                    )
                )
                continue
            if not exact_correction:
                logger.error(
                    "Archive/REST reconciliation did not prove an exact-row correction",
                    extra={
                        "event": "phase7_archive_rest_reconciliation_rejected",
                        "symbol": symbol,
                        "interval": interval,
                        "partition": key,
                        "comparison_report": str(comparison_path),
                    },
                )
                return ReconciliationAttempt()
            rest_manifests.append(rest_manifest)
            comparison_reports.append(comparison_path)

    base_manifest = rejection.manifest
    if rest_manifests:
        base_manifest = reconcile_archive_with_rest(
            rejection.manifest,
            tuple(rest_manifests),
            equivalence_reports=tuple(comparison_reports),
        )
        logger.warning(
            "Retrying Phase 7 quality gate with proven official REST corrections",
            extra={
                "event": "phase7_archive_rest_reconciliation_created",
                "symbol": symbol,
                "interval": interval,
                "archive_manifest": str(rejection.manifest),
                "reconciled_manifest": str(base_manifest),
                "partition_count": len(rest_manifests),
            },
        )
    if gaps:
        logger.error(
            "Archive and REST contain identical structurally invalid rows",
            extra={
                "event": "phase7_identical_invalid_segments",
                "symbol": symbol,
                "interval": interval,
                "partition_count": len(gaps),
                "partitions": [gap.partition for gap in gaps],
            },
        )
        return ReconciliationAttempt(
            segment_source_manifest=base_manifest,
            gaps=tuple(gaps),
        )
    return ReconciliationAttempt(corrected_manifest=base_manifest if rest_manifests else None)


def _reconcile_failed_archive_partitions(
    config: Phase7Config,
    paths: AcquisitionPaths,
    registry: SymbolRegistry,
    rejection: QualityGateRejected,
) -> Path | None:
    """Compatibility wrapper returning only a proven corrected manifest."""

    return _attempt_archive_reconciliation(config, paths, registry, rejection).corrected_manifest


def _partition_time(record: dict[str, Any], name: str) -> datetime:
    value = record.get(name)
    if not isinstance(value, str):
        raise ValueError(f"Segment partition is missing {name}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Segment partition {name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _contiguous_partition_groups(
    partitions: list[dict[str, Any]],
    rejected: set[str],
) -> tuple[tuple[dict[str, Any], ...], ...]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    for raw_record in sorted(partitions, key=lambda item: _partition_time(item, "start")):
        record = deepcopy(raw_record)
        if str(record.get("partition_key")) in rejected:
            if current:
                groups.append(current)
                current = []
            previous_end = None
            continue
        if record.get("status") != "complete" or not record.get("file"):
            raise ValueError("Causal segmentation requires complete source partitions")
        start = _partition_time(record, "start")
        end = _partition_time(record, "end")
        if previous_end is not None and start != previous_end:
            if current:
                groups.append(current)
            current = []
        current.append(record)
        previous_end = end
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups)


def _segment_manifest(
    source_manifest: Path,
    source: dict[str, Any],
    records: tuple[dict[str, Any], ...],
    *,
    position: int,
    gaps: tuple[CausalDataGap, ...],
) -> Path:
    start = _partition_time(records[0], "start")
    end = _partition_time(records[-1], "end")
    identity = {
        "source_manifest": str(source_manifest.resolve()),
        "source_manifest_sha256": file_sha256(source_manifest),
        "position": position,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "partitions": [str(record["partition_key"]) for record in records],
        "gaps": [gap.model_dump(mode="json") for gap in gaps],
        "segmenter_version": "causal_segment_quarantine_v1",
    }
    market = str(source.get("market", "usdm")).lower()
    symbol = str(source["symbol"]).lower()
    interval = str(source["interval"]).lower()
    run_id = f"segmented-{market}-{symbol}-{interval}-{position:03d}-{stable_hash(identity)}"
    path = source_manifest.parent / f"{run_id}.json"
    payload = deepcopy(source)
    payload.update(
        {
            "run_id": run_id,
            "source": "binance_official_public_causal_segment",
            "source_transport": "validated_source_segment",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "partitions": list(records),
            "file_locations": [str(record["file"]) for record in records],
            "row_count": sum(int(record.get("row_count", 0)) for record in records),
            "segment_identity": identity,
            "causal_segment": {
                "position": position,
                "half_open_range": [start.isoformat(), end.isoformat()],
                "source_manifest": str(source_manifest.resolve()),
                "unusable_segments": [gap.model_dump(mode="json") for gap in gaps],
                "raw_sources_mutated": False,
            },
        }
    )
    payload.pop("created_at", None)
    payload.pop("last_updated_at", None)
    existing = read_manifest(path)
    if existing is not None:
        if existing.get("segment_identity") != identity:
            raise ValueError(f"Existing causal segment identity mismatch: {path}")
        return path
    write_manifest(path, payload)
    return path


def _promote_causal_segments(
    config: Phase7Config,
    paths: AcquisitionPaths,
    attempt: ReconciliationAttempt,
) -> Path:
    if attempt.segment_source_manifest is None or not attempt.gaps:
        raise ValueError("Causal segment promotion requires identical-invalid gap evidence")
    source_manifest = attempt.segment_source_manifest.resolve()
    source = read_manifest(source_manifest)
    if source is None:
        raise FileNotFoundError(source_manifest)
    rejected = {gap.partition for gap in attempt.gaps}
    groups = _contiguous_partition_groups(list(source.get("partitions", [])), rejected)
    if not groups:
        raise ValueError("Every source partition was rejected; no valid causal segment remains")

    segments: list[dict[str, Any]] = []
    for position, records in enumerate(groups, start=1):
        bronze_segment = _segment_manifest(
            source_manifest,
            source,
            records,
            position=position,
            gaps=attempt.gaps,
        )
        silver_segment = _promote_candles(config, paths, bronze_segment)
        silver = read_manifest(silver_segment)
        if silver is None or silver.get("quality_status") not in {"PASS", "WARN"}:
            raise ValueError("Causal segment did not pass the unchanged quality gate")
        segments.append(
            {
                "position": position,
                "start": _partition_time(records[0], "start").isoformat(),
                "end": _partition_time(records[-1], "end").isoformat(),
                "bronze_manifest": str(bronze_segment.resolve()),
                "bronze_manifest_sha256": file_sha256(bronze_segment),
                "silver_manifest": str(silver_segment.resolve()),
                "silver_manifest_sha256": file_sha256(silver_segment),
                "validation_report_id": silver["validation_report_id"],
                "quality_status": silver["quality_status"],
            }
        )

    identity = {
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": file_sha256(source_manifest),
        "segments": segments,
        "unusable_segments": [gap.model_dump(mode="json") for gap in attempt.gaps],
        "segmenter_version": "causal_segment_quarantine_v1",
    }
    group_id = f"segment-group-{stable_hash(identity)}"
    group_path = paths.silver / "manifests" / f"{group_id}.json"
    payload = {
        "manifest_kind": "phase7_causal_segment_group",
        "schema_version": "1.0.0",
        "group_id": group_id,
        "symbol": source["symbol"],
        "interval": source["interval"],
        "quality_status": "SEGMENTED_VALID",
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": file_sha256(source_manifest),
        "segments": segments,
        "unusable_segments": [gap.model_dump(mode="json") for gap in attempt.gaps],
        "raw_sources_mutated": False,
        "corrupt_rows_promoted": False,
        "segment_identity": identity,
    }
    existing = read_manifest(group_path)
    if existing is not None:
        if existing.get("segment_identity") != identity:
            raise ValueError(f"Existing Silver segment group identity mismatch: {group_path}")
        return group_path
    write_manifest(group_path, payload)
    return group_path


def plan_candle_download_request(
    record: SymbolRecord,
    *,
    interval: str,
    start: datetime,
    end: datetime,
    exact_bounds: ArchiveCandleBounds | None = None,
) -> DownloadRequest | None:
    """Plan a bounded request while retaining the candle containing onboard time."""

    requested_start = start.astimezone(UTC)
    requested_end = end.astimezone(UTC)
    symbol_start = max(requested_start, record.candle_available_from(interval))
    symbol_end = min(requested_end, record.available_until or requested_end)
    if exact_bounds is not None:
        symbol_start = max(symbol_start, exact_bounds.first_open_time)
        symbol_end = min(symbol_end, exact_bounds.end_exclusive)
    if symbol_start >= symbol_end:
        return None
    return DownloadRequest(start=symbol_start, end=symbol_end)


def _interval_archive_range(
    record: SymbolRecord,
    *,
    interval: str,
    requested_end: datetime,
) -> tuple[datetime, datetime]:
    period = record.archive_period_for(interval)
    if period is not None:
        return period.first_month, period.last_month_exclusive
    return record.available_from, record.available_until or requested_end.astimezone(UTC)


def acquire_candle_family(
    config: Phase7Config,
    registry: SymbolRegistry,
    *,
    symbols: tuple[str, ...],
    interval: str,
    start: datetime,
    end: datetime,
    strict_symbols: frozenset[str] = frozenset(),
    progress: AcquisitionProgress | None = None,
) -> CandleFamilyAcquisition:
    """Acquire checksum-verified official archives and promote through the quality gate."""

    config.assert_cloud_execution_allowed()
    paths = AcquisitionPaths.from_config(config)
    metadata = _RegistryMetadata(registry)
    records = registry.by_symbol()
    outcomes: list[AcquisitionOutcome] = []
    for position, symbol in enumerate(symbols, start=1):
        record = records[symbol]
        coarse_request = plan_candle_download_request(
            record,
            interval=interval,
            start=start,
            end=end,
        )
        if coarse_request is None:
            outcomes.append(
                AcquisitionOutcome(
                    symbol=symbol,
                    interval=interval,
                    status=AcquisitionStatus.LIFECYCLE_ABSENCE,
                    reason="no causal source overlap with requested range",
                )
            )
            if progress is not None:
                progress(
                    position,
                    len(symbols),
                    symbol,
                    interval,
                    AcquisitionStatus.LIFECYCLE_ABSENCE.value,
                )
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
            archive_start, archive_end = _interval_archive_range(
                record,
                interval=interval,
                requested_end=end,
            )
            exact_bounds = client.inspect_interval_bounds(
                symbol=symbol,
                interval=interval,
                archive_start=archive_start,
                archive_end=archive_end,
            )
            request = plan_candle_download_request(
                record,
                interval=interval,
                start=start,
                end=end,
                exact_bounds=exact_bounds,
            )
            if request is None:
                outcomes.append(
                    AcquisitionOutcome(
                        symbol=symbol,
                        interval=interval,
                        status=AcquisitionStatus.LIFECYCLE_ABSENCE,
                        reason="official archive has no exact rows in requested range",
                    )
                )
                if progress is not None:
                    progress(
                        position,
                        len(symbols),
                        symbol,
                        interval,
                        AcquisitionStatus.LIFECYCLE_ABSENCE.value,
                    )
                continue
            bronze_manifest = HistoricalDownloader(settings, client).download(request)
        try:
            silver_manifest = _promote_candles(config, paths, bronze_manifest)
        except QualityGateRejected as rejection:
            attempt = _attempt_archive_reconciliation(
                config,
                paths,
                registry,
                rejection,
            )
            if attempt.corrected_manifest is not None:
                silver_manifest = _promote_candles(
                    config,
                    paths,
                    attempt.corrected_manifest,
                )
            elif attempt.identical_invalid:
                if symbol in strict_symbols:
                    logger.error(
                        "Required core/context symbol contains an unrecoverable causal gap",
                        extra={
                            "event": "phase7_core_segment_hard_stop",
                            "symbol": symbol,
                            "interval": interval,
                            "partitions": [gap.partition for gap in attempt.gaps],
                        },
                    )
                    raise
                silver_manifest = _promote_causal_segments(config, paths, attempt)
                outcomes.append(
                    AcquisitionOutcome(
                        symbol=symbol,
                        interval=interval,
                        status=AcquisitionStatus.QUALITY_REJECTED_SEGMENT,
                        silver_manifest=str(silver_manifest.resolve()),
                        reason="identical structurally invalid archive and REST row",
                        gaps=attempt.gaps,
                    )
                )
                if progress is not None:
                    progress(
                        position,
                        len(symbols),
                        symbol,
                        interval,
                        AcquisitionStatus.QUALITY_REJECTED_SEGMENT.value,
                    )
                continue
            else:
                raise
        outcomes.append(
            AcquisitionOutcome(
                symbol=symbol,
                interval=interval,
                status=AcquisitionStatus.VALID,
                silver_manifest=str(silver_manifest.resolve()),
            )
        )
        if progress is not None:
            progress(
                position,
                len(symbols),
                symbol,
                interval,
                AcquisitionStatus.VALID.value,
            )
    return CandleFamilyAcquisition(tuple(outcomes))


def acquire_discovery_daily(
    config: Phase7Config,
    registry: SymbolRegistry,
    *,
    progress: AcquisitionProgress | None = None,
) -> CandleFamilyAcquisition:
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
        and record.causal_available_from
        < end - timedelta(days=config.universe.minimum_history_days)
    )
    return acquire_candle_family(
        config,
        registry,
        symbols=symbols,
        interval="1d",
        start=start,
        end=end,
        progress=progress,
    )


def _silver_segment_manifests(manifest_path: Path, payload: dict[str, Any]) -> tuple[Path, ...]:
    if payload.get("manifest_kind") != "phase7_causal_segment_group":
        return (manifest_path,)
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError(f"Causal segment group has no segments: {manifest_path}")
    paths: list[Path] = []
    previous_end: datetime | None = None
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError(f"Invalid causal segment record: {manifest_path}")
        child = Path(str(segment.get("silver_manifest", ""))).resolve()
        if not child.is_file() or file_sha256(child) != segment.get("silver_manifest_sha256"):
            raise ValueError(f"Causal segment Silver lineage mismatch: {child}")
        start = datetime.fromisoformat(str(segment["start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(segment["end"]).replace("Z", "+00:00"))
        if previous_end is not None and start <= previous_end:
            raise ValueError("Causal Silver segments must be ordered and non-overlapping")
        previous_end = end
        paths.append(child)
    return tuple(paths)


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
        if payload is None or payload.get("quality_status") not in {
            "PASS",
            "WARN",
            "SEGMENTED_VALID",
        }:
            raise ValueError(f"Ineligible Silver manifest: {manifest_path}")
        selected: list[pa.Table] = []
        for child_manifest in _silver_segment_manifests(manifest_path, payload):
            child_payload = read_manifest(child_manifest)
            if child_payload is None or child_payload.get("quality_status") not in {"PASS", "WARN"}:
                raise ValueError(f"Ineligible Silver segment manifest: {child_manifest}")
            root = child_manifest.parent.parent
            for record in child_payload.get("output_files", []):
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
    progress: AcquisitionProgress | None = None,
) -> dict[str, dict[str, str]]:
    config.assert_cloud_execution_allowed()
    paths = AcquisitionPaths.from_config(config)
    records = registry.by_symbol()
    result: dict[str, dict[str, str]] = {}
    for position, symbol in enumerate(symbols, start=1):
        record = records[symbol]
        symbol_start = max(start, record.causal_available_from)
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
        if progress is not None:
            progress(position, len(symbols), symbol, "derivatives", AcquisitionStatus.VALID.value)
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
