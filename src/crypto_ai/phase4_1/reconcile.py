from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def reconcile_archive_with_rest(
    archive_manifest_path: Path,
    rest_overlay_manifests: tuple[Path, ...],
    *,
    equivalence_reports: tuple[Path, ...],
) -> Path:
    """Create auditable lineage that replaces discrepant archive partitions with REST.

    Both source transports remain immutable. The result is only a manifest-level
    composition and records every official-data replacement explicitly.
    """

    archive_manifest_path = archive_manifest_path.resolve()
    archive = read_manifest(archive_manifest_path)
    if archive is None:
        raise FileNotFoundError(archive_manifest_path)
    if archive.get("source") != "binance_public_archive":
        raise ValueError("Reconciliation requires a Binance public-archive base manifest")
    if not rest_overlay_manifests:
        raise ValueError("At least one REST overlay manifest is required")
    if len(rest_overlay_manifests) != len(equivalence_reports):
        raise ValueError("Every REST overlay requires an equivalence report")

    overlays: dict[str, dict[str, Any]] = {}
    overlay_lineage: list[dict[str, Any]] = []
    for manifest_path, report_path in zip(rest_overlay_manifests, equivalence_reports, strict=True):
        manifest_path, report_path = manifest_path.resolve(), report_path.resolve()
        manifest = read_manifest(manifest_path)
        report = read_manifest(report_path)
        if manifest is None or report is None:
            raise FileNotFoundError(manifest_path if manifest is None else report_path)
        if manifest.get("source") != "binance":
            raise ValueError("Overlay manifest must come from Binance REST")
        if report.get("equivalent") is not False:
            raise ValueError("REST overlay is allowed only for a documented discrepancy")
        for record in manifest.get("partitions", []):
            if not isinstance(record, dict) or record.get("status") != "complete":
                raise ValueError("REST overlay contains an incomplete partition")
            overlays[str(record["partition_key"])] = deepcopy(record)
        overlay_lineage.append(
            {
                "manifest": str(manifest_path),
                "run_id": manifest["run_id"],
                "equivalence_report": str(report_path),
            }
        )

    partitions: list[dict[str, Any]] = []
    used: set[str] = set()
    for raw_record in archive.get("partitions", []):
        record = deepcopy(raw_record)
        key = str(record["partition_key"])
        if key in overlays:
            record = overlays[key]
            record["row_source"] = "binance_usdm_futures_rest"
            record["reconciliation"] = {
                "action": "replace_archive_partition_with_current_official_rest",
                "reason": "archive/REST market-value discrepancy",
            }
            used.add(key)
        else:
            record["row_source"] = "binance_usdm_futures_archive"
        partitions.append(record)
    unused = sorted(set(overlays) - used)
    if unused:
        raise ValueError(f"REST overlays fall outside archive manifest: {unused}")

    identity = {
        "archive_run_id": archive["run_id"],
        "overlays": overlay_lineage,
        "reconciler_version": "1.0.0",
    }
    market = str(archive.get("market", "usdm")).lower()
    symbol = str(archive.get("symbol", "BTCUSDT")).lower()
    interval = str(archive.get("interval", "unknown")).lower()
    run_id = f"reconciled-{market}-{symbol}-{interval}-{_hash(identity)}"
    manifest_path = archive_manifest_path.parent / f"{run_id}.json"
    existing = read_manifest(manifest_path)
    if existing is not None:
        if existing.get("reconciliation_identity") != identity:
            raise ValueError(f"Existing reconciliation identity mismatch: {manifest_path}")
        return manifest_path
    manifest = deepcopy(archive)
    manifest.update(
        {
            "run_id": run_id,
            "source": "binance_official_public_reconciled",
            "source_transport": "archive_primary_rest_corrections",
            "created_at": datetime.now(UTC).isoformat(),
            "last_updated_at": datetime.now(UTC).isoformat(),
            "partitions": partitions,
            "file_locations": [record["file"] for record in partitions if record.get("file")],
            "row_count": sum(int(record.get("row_count", 0)) for record in partitions),
            "reconciliation_identity": identity,
            "reconciliation": {
                "archive_manifest": str(archive_manifest_path),
                "rest_overlays": overlay_lineage,
                "replaced_partition_count": len(used),
                "raw_sources_mutated": False,
                "policy": "archive primary; current official REST replaces proven discrepancies",
            },
        }
    )
    manifest.pop("row_source", None)
    write_manifest(manifest_path, manifest)
    return manifest_path


def reconcile_archive_missing_with_rest(
    archive_manifest_path: Path,
    rest_overlay_manifests: tuple[Path, ...],
    *,
    comparison_report: Path,
) -> Path:
    """Fill proven empty archive partitions with exact official REST partitions.

    This is intentionally distinct from discrepancy replacement. Existing
    archive rows can never be selected by this reconciler, and both transports
    remain immutable.
    """

    archive_manifest_path = archive_manifest_path.resolve()
    comparison_report = comparison_report.resolve()
    archive = read_manifest(archive_manifest_path)
    comparison = read_manifest(comparison_report)
    if archive is None or comparison is None:
        raise FileNotFoundError(archive_manifest_path if archive is None else comparison_report)
    if archive.get("source") != "binance_public_archive":
        raise ValueError("Gap reconciliation requires a Binance archive base manifest")
    if comparison.get("status") != "PROVEN_EXACT_MISSING_ROWS":
        raise ValueError("Gap reconciliation requires proven exact missing-row evidence")
    if not rest_overlay_manifests:
        raise ValueError("At least one REST gap overlay manifest is required")

    archive_records = {
        str(record.get("partition_key")): record
        for record in archive.get("partitions", [])
        if isinstance(record, dict)
    }
    expected = tuple(str(value) for value in comparison.get("missing_partition_keys", []))
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Missing partition evidence must be non-empty and unique")

    overlays: dict[str, dict[str, Any]] = {}
    overlay_lineage: list[dict[str, Any]] = []
    for raw_path in rest_overlay_manifests:
        manifest_path = raw_path.resolve()
        manifest = read_manifest(manifest_path)
        if manifest is None:
            raise FileNotFoundError(manifest_path)
        if (
            manifest.get("source") != "binance"
            or manifest.get("source_transport") != "rest"
            or manifest.get("symbol") != archive.get("symbol")
            or manifest.get("interval") != archive.get("interval")
        ):
            raise ValueError("REST gap overlay identity differs from the archive")
        keys: list[str] = []
        for raw_record in manifest.get("partitions", []):
            if not isinstance(raw_record, dict) or raw_record.get("status") != "complete":
                raise ValueError("REST gap overlay contains an incomplete partition")
            key = str(raw_record.get("partition_key"))
            if key in overlays:
                raise ValueError(f"Duplicate REST gap overlay partition: {key}")
            overlays[key] = deepcopy(raw_record)
            keys.append(key)
        overlay_lineage.append(
            {
                "manifest": str(manifest_path),
                "run_id": manifest["run_id"],
                "downloaded_at": manifest.get("downloaded_at"),
                "partition_keys": keys,
                "partition_sha256s": [
                    str(record.get("sha256"))
                    for record in manifest.get("partitions", [])
                    if isinstance(record, dict)
                ],
            }
        )

    if set(overlays) != set(expected):
        raise ValueError("REST overlays do not exactly match proven missing partitions")
    for key in expected:
        archive_record = archive_records.get(key)
        if archive_record is None or not (
            archive_record.get("status") == "empty"
            and int(archive_record.get("row_count", 0)) == 0
            and not archive_record.get("file")
        ):
            raise ValueError(f"Archive partition is not proven empty: {key}")

    partitions: list[dict[str, Any]] = []
    used: set[str] = set()
    for raw_record in archive.get("partitions", []):
        record = deepcopy(raw_record)
        key = str(record.get("partition_key"))
        if key in overlays:
            archive_evidence = {
                "partition_key": key,
                "status": record.get("status"),
                "row_count": record.get("row_count"),
                "file": record.get("file"),
                "sha256": record.get("sha256"),
            }
            record = overlays[key]
            record["row_source"] = "binance_usdm_futures_rest"
            record["reconciliation"] = {
                "action": "fill_proven_empty_archive_partition_with_official_rest",
                "reason": "official archive omitted expected historical candles",
                "archive_evidence": archive_evidence,
                "comparison_report": str(comparison_report),
            }
            used.add(key)
        else:
            record["row_source"] = "binance_usdm_futures_archive"
        partitions.append(record)
    if used != set(expected):
        raise ValueError("Not every proven archive omission was composed")

    identity = {
        "archive_run_id": archive["run_id"],
        "archive_manifest": str(archive_manifest_path),
        "archive_manifest_sha256": comparison.get("archive_manifest_sha256"),
        "overlays": overlay_lineage,
        "comparison_report": str(comparison_report),
        "comparison_report_sha256": file_sha256(comparison_report),
        "missing_partition_keys": list(expected),
        "reconciler_version": "archive_missing_rest_v1",
    }
    market = str(archive.get("market", "usdm")).lower()
    symbol = str(archive.get("symbol", "BTCUSDT")).lower()
    interval = str(archive.get("interval", "unknown")).lower()
    run_id = f"reconciled-gap-{market}-{symbol}-{interval}-{_hash(identity)}"
    manifest_path = archive_manifest_path.parent / f"{run_id}.json"
    existing = read_manifest(manifest_path)
    if existing is not None:
        if existing.get("reconciliation_identity") != identity:
            raise ValueError(f"Existing gap reconciliation identity mismatch: {manifest_path}")
        return manifest_path

    now = datetime.now(UTC).isoformat()
    manifest = deepcopy(archive)
    manifest.update(
        {
            "run_id": run_id,
            "source": "binance_official_public_reconciled",
            "source_transport": "archive_primary_rest_missing_rows",
            "created_at": now,
            "last_updated_at": now,
            "partitions": partitions,
            "file_locations": [record["file"] for record in partitions if record.get("file")],
            "row_count": sum(int(record.get("row_count", 0)) for record in partitions),
            "reconciliation_identity": identity,
            "reconciliation": {
                "archive_manifest": str(archive_manifest_path),
                "archive_manifest_sha256": comparison.get("archive_manifest_sha256"),
                "original_quality_report": comparison.get("quality_report"),
                "original_quality_report_sha256": comparison.get("quality_report_sha256"),
                "original_quarantine": comparison.get("quarantine"),
                "original_quarantine_sha256": comparison.get("quarantine_sha256"),
                "comparison_report": str(comparison_report),
                "comparison_report_sha256": file_sha256(comparison_report),
                "rest_overlays": overlay_lineage,
                "filled_partition_count": len(used),
                "missing_partition_keys": list(expected),
                "missing_open_times": comparison.get("missing_open_times", []),
                "raw_sources_mutated": False,
                "policy": (
                    "archive primary; bounded official REST supplies only validator-proven "
                    "missing historical rows"
                ),
            },
        }
    )
    manifest.pop("row_source", None)
    write_manifest(manifest_path, manifest)
    return manifest_path
