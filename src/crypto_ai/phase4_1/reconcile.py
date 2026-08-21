from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest


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
