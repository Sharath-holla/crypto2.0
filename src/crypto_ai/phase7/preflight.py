"""Provider-neutral Phase 7A environment preflight; never starts training."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.backend import (
    backend_metadata,
    resolve_lightgbm_backend,
    smoke_test_backend,
)
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.gold_validation import (
    production_feature_columns,
    production_gold_schema,
    validate_gold_manifest,
)
from crypto_ai.phase7.prepared_cache import cache_size_report
from crypto_ai.phase7.runtime import (
    ComputeBudget,
    RuntimePaths,
    cache_mode_from_environment,
    git_commit,
    system_snapshot,
)
from crypto_ai.phase7.training import execution_source_identity, scientific_source_identity


def _existing_ancestor(path: Path) -> Path:
    """Return a safe existing location for read-only capacity inspection."""

    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.is_dir() else candidate.parent


def _validated_gold_report(
    report_path: Path,
    *,
    dataset_id: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        payload.get("status") != "PASS"
        or payload.get("partition_hashes_verified") is not True
        or payload.get("dataset_id") != dataset_id
        or payload.get("manifest_sha256") != manifest_sha256
        or payload.get("holdout_status") != "LOCKED_UNUSED"
        or payload.get("production_features") != list(production_feature_columns())
        or payload.get("production_schema")
        != {name: str(dtype) for name, dtype in production_gold_schema().items()}
    ):
        raise ValueError("Gold validation report is absent, stale, or incompatible")
    return payload


def build_preflight_report(
    config_path: Path,
    *,
    create_outputs: bool = True,
    gold_validation_report: Path | None = None,
    run_backend_smoke: bool = True,
) -> dict[str, Any]:
    config = load_phase7_config(config_path)
    paths = RuntimePaths.resolve(config.paths)
    errors = paths.validate(require_gold=True, create_outputs=create_outputs)
    manifest_report: dict[str, Any] | None = None
    byte_validation: dict[str, Any] | None = None
    try:
        manifest_path, manifest, partitions = validate_gold_manifest(paths.gold_root)
        manifest_sha = file_sha256(manifest_path)
        manifest_report = {
            "path": str(manifest_path),
            "sha256": manifest_sha,
            "dataset_id": manifest["dataset_id"],
            "parquet_partition_count": len(partitions),
            "row_count": manifest.get("rows", manifest.get("row_count")),
        }
        if gold_validation_report is None:
            errors.append("byte-level Gold validation report is required")
        else:
            byte_validation = _validated_gold_report(
                gold_validation_report.resolve(),
                dataset_id=str(manifest["dataset_id"]),
                manifest_sha256=manifest_sha,
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    backend = resolve_lightgbm_backend()
    smoke: dict[str, Any] | None = None
    if run_backend_smoke:
        try:
            smoke = smoke_test_backend(backend.name)
        except Exception as exc:
            errors.append(str(exc))
    else:
        errors.append("backend smoke was skipped; training readiness cannot be established")
    try:
        budget: dict[str, Any] | None = asdict(ComputeBudget.resolve(config.resources))
    except ValueError as exc:
        budget = None
        errors.append(str(exc))
    try:
        system = system_snapshot(_existing_ancestor(paths.artifact_root))
    except OSError as exc:
        errors.append(f"unable to inspect system capacity: {exc}")
        system = {
            "python": None,
            "os": None,
            "cpu_count": os.cpu_count(),
            "ram_total_bytes": 0,
            "ram_available_bytes": 0,
            "disk_total_bytes": 0,
            "disk_free_bytes": 0,
        }
    minimum_disk_gb = float(os.environ.get("PHASE7_MIN_FREE_DISK_GB", "25"))
    minimum_ram_gb = float(os.environ.get("PHASE7_MIN_AVAILABLE_RAM_GB", "32"))
    if any(not math.isfinite(value) or value <= 0 for value in (minimum_disk_gb, minimum_ram_gb)):
        raise ValueError("preflight RAM/disk minimums must be positive and finite")
    filesystem_capacity = {}
    for name in ("artifact_root", "cache_root", "model_root", "report_root", "checkpoint_root"):
        location = _existing_ancestor(getattr(paths, name))
        capacity = system_snapshot(location)
        filesystem_capacity[name] = {
            "path": str(location),
            "disk_free_bytes": capacity["disk_free_bytes"],
        }
        if capacity["disk_free_bytes"] < minimum_disk_gb * 1024**3:
            errors.append(f"{name} filesystem is below the configured free disk floor")
    if int(system["disk_free_bytes"]) < minimum_disk_gb * 1024**3:
        errors.append(f"available disk is below PHASE7_MIN_FREE_DISK_GB={minimum_disk_gb}")
    if int(system["ram_available_bytes"]) < minimum_ram_gb * 1024**3:
        errors.append(f"available RAM is below PHASE7_MIN_AVAILABLE_RAM_GB={minimum_ram_gb}")
    report = {
        "status": "PASS" if not errors else "FAIL",
        "training_readiness": "READY" if not errors else "NOT_READY",
        "blocking_errors": errors,
        "git_commit": git_commit(),
        "scientific_source_identity": scientific_source_identity(),
        "execution_source_identity": execution_source_identity(),
        "configuration_hash": config.configuration_hash,
        "paths": paths.payload(),
        "system": system,
        "filesystem_capacity": filesystem_capacity,
        "resource_requirements": {
            "minimum_free_disk_gb": minimum_disk_gb,
            "minimum_available_ram_gb": minimum_ram_gb,
        },
        "cache_mode": cache_mode_from_environment(),
        "cache": cache_size_report(paths.cache_root),
        "compute_budget": budget,
        "backend": backend_metadata(backend),
        "backend_smoke": smoke,
        "gold_manifest": manifest_report,
        "gold_byte_validation": byte_validation,
        "holdout": config.holdout_status_payload(),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/phase7/research_core20_primary_v1.toml"),
    )
    parser.add_argument("--no-create", action="store_true")
    parser.add_argument(
        "--gold-validation-report",
        type=Path,
        default=(
            Path(os.environ["PHASE7_GOLD_VALIDATION_REPORT"])
            if os.environ.get("PHASE7_GOLD_VALIDATION_REPORT")
            else None
        ),
    )
    parser.add_argument("--skip-backend-smoke", action="store_true")
    args = parser.parse_args()
    report = build_preflight_report(
        args.config,
        create_outputs=not args.no_create,
        gold_validation_report=args.gold_validation_report,
        run_backend_smoke=not args.skip_backend_smoke,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
