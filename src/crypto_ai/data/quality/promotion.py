from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.models import (
    DatasetQualityReport,
    ValidationStatus,
)
from crypto_ai.data.quality.policy import QualityPolicy
from crypto_ai.data.storage import file_sha256, read_candle_parquet, write_immutable

logger = logging.getLogger(__name__)
SILVER_TRANSFORMATION_VERSION = "sort-and-exact-deduplicate-v2-versioned-paths"


@dataclass(frozen=True, slots=True)
class PromotionResult:
    promoted: bool
    status: str
    validation_report_id: str
    silver_dataset_version: str | None = None
    promotion_manifest: Path | None = None
    quarantine_record: Path | None = None
    output_files: tuple[Path, ...] = ()
    exact_duplicates_removed: int = 0


def _silver_version(report: DatasetQualityReport) -> str:
    identity = {
        "dataset_version": report.dataset_version,
        "validation_report_id": report.report_id,
        "validator_version": report.validator_version,
        "transformation": SILVER_TRANSFORMATION_VERSION,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return f"silver-{digest}"


def _deduplicate_exact(table: pa.Table) -> tuple[pa.Table, int]:
    ordered = table.sort_by([("symbol", "ascending"), ("open_time", "ascending")])
    rows = ordered.to_pylist()
    names = ordered.column_names
    seen: set[tuple[Any, ...]] = set()
    keep: list[int] = []
    for index, row in enumerate(rows):
        identity = tuple(row[name] for name in names)
        if identity in seen:
            continue
        seen.add(identity)
        keep.append(index)
    if len(keep) == ordered.num_rows:
        return ordered, 0
    return ordered.take(pa.array(keep, type=pa.int64())), ordered.num_rows - len(keep)


class SilverPromoter:
    def __init__(self, policy: QualityPolicy | None = None) -> None:
        self.policy = policy or QualityPolicy()

    def promote(
        self,
        manifest_path: Path,
        report: DatasetQualityReport,
        *,
        silver_root: Path,
        quarantine_root: Path,
    ) -> PromotionResult:
        manifest_path = manifest_path.resolve()
        if report.source_manifest != str(manifest_path):
            raise ValueError("Quality report does not belong to the requested source manifest")

        gate_allows = report.overall_status is ValidationStatus.PASS or (
            report.overall_status is ValidationStatus.WARN and self.policy.allow_warnings_for_silver
        )
        if not gate_allows:
            quarantine = self._write_quarantine(report, manifest_path, quarantine_root)
            logger.warning(
                "Silver promotion rejected by quality gate",
                extra={
                    "event": "silver_promotion_rejected",
                    "status": report.overall_status.value,
                    "validation_report_id": report.report_id,
                    "quarantine": str(quarantine),
                },
            )
            return PromotionResult(
                promoted=False,
                status="rejected",
                validation_report_id=report.report_id,
                quarantine_record=quarantine,
            )

        logger.info(
            "Silver promotion started",
            extra={
                "event": "silver_promotion_started",
                "validation_report_id": report.report_id,
                "source_manifest": str(manifest_path),
            },
        )
        manifest = read_manifest(manifest_path)
        if manifest is None:
            raise FileNotFoundError(manifest_path)
        bronze_root = manifest_path.parent.parent
        silver_root = silver_root.resolve()
        silver_version = _silver_version(report)
        version_root = silver_root / "versions" / f"silver_dataset_version={silver_version}"
        output_files: list[Path] = []
        output_records: list[dict[str, Any]] = []
        duplicates_removed = 0

        source_hashes_before: dict[Path, str] = {}
        for entry in report.source_files:
            relative_value = entry.get("relative_path")
            if not relative_value or entry.get("status") != "readable":
                continue
            relative = Path(str(relative_value))
            source_path = bronze_root / relative
            source_checksum = file_sha256(source_path)
            if source_checksum != entry.get("sha256"):
                raise ValueError(f"Bronze checksum changed after validation: {source_path}")
            source_hashes_before[source_path] = source_checksum

            table = read_candle_parquet(source_path)
            silver_table, removed = _deduplicate_exact(table)
            duplicates_removed += removed
            destination = version_root / relative
            metadata = {
                "layer": "silver",
                "source_layer": "bronze",
                "source_file": str(source_path),
                "source_sha256": source_checksum,
                "source_manifest": str(manifest_path),
                "source_dataset_version": report.dataset_version,
                "validation_report_id": report.report_id,
                "validation_version": report.validator_version,
                "silver_dataset_version": silver_version,
                "exact_duplicates_removed": str(removed),
            }
            if destination.exists():
                existing = pq.ParquetFile(destination)
                existing_metadata = {
                    key.decode("utf-8"): value.decode("utf-8")
                    for key, value in (existing.schema_arrow.metadata or {}).items()
                }
                required = {
                    "source_sha256": source_checksum,
                    "validation_report_id": report.report_id,
                    "silver_dataset_version": silver_version,
                }
                mismatches = [
                    key for key, value in required.items() if existing_metadata.get(key) != value
                ]
                if mismatches:
                    raise ValueError(
                        f"Existing Silver file lineage mismatch for {destination}: "
                        f"{', '.join(mismatches)}"
                    )
                read_candle_parquet(destination)
            else:
                write_immutable(destination, silver_table, metadata=metadata)
            output_checksum = file_sha256(destination)
            output_files.append(destination)
            output_records.append(
                {
                    "file": destination.relative_to(silver_root).as_posix(),
                    "sha256": output_checksum,
                    "row_count": silver_table.num_rows,
                    "source_file": relative.as_posix(),
                    "source_sha256": source_checksum,
                    "exact_duplicates_removed": removed,
                }
            )

        for source_path, before in source_hashes_before.items():
            if file_sha256(source_path) != before:
                raise RuntimeError(f"Bronze source changed during promotion: {source_path}")

        promotion_manifest = silver_root / "manifests" / f"{silver_version}.json"
        existing_manifest = read_manifest(promotion_manifest)
        if existing_manifest is not None:
            if (
                existing_manifest.get("source_dataset_version") != report.dataset_version
                or existing_manifest.get("validation_report_id") != report.report_id
            ):
                raise ValueError(
                    f"Existing Silver manifest identity mismatch: {promotion_manifest}"
                )
        else:
            write_manifest(
                promotion_manifest,
                {
                    "silver_dataset_version": silver_version,
                    "schema_version": "1.0.0",
                    "created_at": datetime.now(UTC).isoformat(),
                    "source_manifest": str(manifest_path),
                    "source_dataset_version": report.dataset_version,
                    "validation_report_id": report.report_id,
                    "validation_version": report.validator_version,
                    "quality_status": report.overall_status.value,
                    "transformation": SILVER_TRANSFORMATION_VERSION,
                    "exact_duplicates_removed": duplicates_removed,
                    "source_files": [str(path) for path in source_hashes_before],
                    "output_files": output_records,
                },
            )

        logger.info(
            "Silver promotion completed",
            extra={
                "event": "silver_promotion_completed",
                "status": "promoted",
                "validation_report_id": report.report_id,
                "silver_dataset_version": silver_version,
                "output_file_count": len(output_files),
            },
        )
        return PromotionResult(
            promoted=True,
            status="promoted",
            validation_report_id=report.report_id,
            silver_dataset_version=silver_version,
            promotion_manifest=promotion_manifest,
            output_files=tuple(output_files),
            exact_duplicates_removed=duplicates_removed,
        )

    def _write_quarantine(
        self,
        report: DatasetQualityReport,
        manifest_path: Path,
        quarantine_root: Path,
    ) -> Path:
        path = quarantine_root.resolve() / f"{report.report_id}.json"
        failures = [
            check.to_dict() for check in report.checks if check.status is ValidationStatus.FAIL
        ]
        write_manifest(
            path,
            {
                "quarantine_id": report.report_id,
                "created_at": datetime.now(UTC).isoformat(),
                "reason": "quality_gate_failed",
                "overall_status": report.overall_status.value,
                "source_manifest": str(manifest_path),
                "source_dataset_version": report.dataset_version,
                "validation_report_id": report.report_id,
                "validation_version": report.validator_version,
                "source_files": report.source_files,
                "failed_checks": failures,
            },
        )
        return path
