"""Provider-neutral Phase 7A environment preflight; never starts training."""

from __future__ import annotations

import argparse
import json
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
from crypto_ai.phase7.resources import configured_floor
from crypto_ai.phase7.runtime import (
    ComputeBudget,
    RuntimePaths,
    cache_mode_from_environment,
    git_commit,
    system_snapshot,
)
from crypto_ai.phase7.telemetry import telemetry
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
        not isinstance(payload, dict)
        or payload.get("status") != "PASS"
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
    verification_only: bool = False,
) -> dict[str, Any]:
    config = load_phase7_config(config_path)
    paths = RuntimePaths.resolve(config.paths)
    errors = paths.validate(require_gold=not verification_only, create_outputs=create_outputs)
    manifest_report: dict[str, Any] | None = None
    byte_validation: dict[str, Any] | None = None
    # Cheap contract/capacity checks precede any Gold inspection or backend fit.
    # Invalid environment values become an actionable FAIL report, not a traceback.
    try:
        backend = resolve_lightgbm_backend()
    except ValueError as exc:
        backend = None
        errors.append(str(exc))
    smoke: dict[str, Any] | None = None
    if not run_backend_smoke and not verification_only:
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

    def floor(primary: str, legacy: str, *, default: float = 0) -> float | None:
        try:
            return configured_floor(primary, legacy, default=default)
        except ValueError as exc:
            errors.append(f"{primary}: {exc}")
            return None

    minimum_disk_gb = floor("PHASE7_MIN_FREE_DISK_GIB", "PHASE7_MIN_FREE_DISK_GB", default=25)
    minimum_ram_gb = floor("PHASE7_MIN_FREE_RAM_GIB", "PHASE7_MIN_AVAILABLE_RAM_GB")
    if not verification_only and minimum_ram_gb == 0:
        errors.append("explicit positive PHASE7_MIN_FREE_RAM_GIB workload floor is required")
    try:
        cache_mode = cache_mode_from_environment()
    except ValueError as exc:
        cache_mode = "INVALID"
        errors.append(str(exc))
    if not verification_only and cache_mode != "read_only":
        errors.append(
            "training preflight requires PHASE7_CACHE_MODE=read_only; do not rebuild data"
        )
    filesystem_capacity = {}
    for name in (
        "artifact_root",
        "cache_root",
        "model_root",
        "report_root",
        "checkpoint_root",
        "log_root",
        "temporary_root",
    ):
        target = (
            Path(os.environ.get("PHASE7_TEMP_ROOT", str(paths.cache_root)))
            if name == "temporary_root"
            else getattr(paths, name)
        )
        try:
            location = _existing_ancestor(target)
            capacity = system_snapshot(location)
        except OSError as exc:
            errors.append(f"unable to inspect {name} filesystem capacity: {exc}")
            filesystem_capacity[name] = {"path": str(target), "disk_free_bytes": None}
            continue
        filesystem_capacity[name] = {
            "path": str(location),
            "disk_free_bytes": capacity["disk_free_bytes"],
        }
        if minimum_disk_gb is not None and capacity["disk_free_bytes"] < minimum_disk_gb * 1024**3:
            errors.append(f"{name} filesystem is below the configured free disk floor")
    if minimum_disk_gb is not None and int(system["disk_free_bytes"]) < minimum_disk_gb * 1024**3:
        errors.append(f"available disk is below PHASE7_MIN_FREE_DISK_GB={minimum_disk_gb}")
    if minimum_ram_gb is not None and int(system["ram_available_bytes"]) < minimum_ram_gb * 1024**3:
        errors.append(f"available RAM is below PHASE7_MIN_AVAILABLE_RAM_GB={minimum_ram_gb}")
    if not verification_only and not errors:
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
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(str(exc))
    cache: dict[str, Any] = {"status": "NOT_INSPECTED_BLOCKING_ERRORS"}
    if not errors:
        try:
            cache = cache_size_report(paths.cache_root)
        except (OSError, ValueError) as exc:
            errors.append(f"unable to inspect prepared cache: {exc}")
    if not verification_only and not errors and backend is not None:
        try:
            smoke = smoke_test_backend(backend.name)
            if smoke.get("status") != "PASS" or smoke.get("fit_success") is False:
                errors.append("backend smoke did not report PASS")
        except Exception as exc:
            errors.append(str(exc))
    # Do not probe a GPU device when an earlier prerequisite already failed.
    backend_report = (
        {"status": "INVALID"}
        if backend is None
        else {**asdict(backend), "runtime_probe": "NOT_RUN_BLOCKING_ERRORS"}
    )
    if not errors and backend is not None:
        try:
            backend_report = backend_metadata(backend)
        except (OSError, ValueError) as exc:
            errors.append(f"unable to inspect backend metadata: {exc}")
    report = {
        "status": "PASS" if not errors else "FAIL",
        "training_readiness": "READY"
        if not errors and not verification_only and create_outputs
        else "NOT_READY",
        "output_write_probe": (
            "NOT_RUN_READ_ONLY_INSPECTION"
            if not create_outputs
            else "REQUESTED_NOT_FULLY_VERIFIED"
            if errors
            else "PERFORMED"
        ),
        "qualification_mode": "SOFTWARE_ENVIRONMENT_ONLY"
        if verification_only
        else "TRAINING_PREFLIGHT",
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
        "cache_mode": cache_mode,
        "cache": cache,
        "compute_budget": budget,
        "backend": backend_report,
        "backend_smoke": smoke,
        "gold_manifest": manifest_report,
        "gold_byte_validation": byte_validation,
        "holdout": config.holdout_status_payload(),
    }
    if not errors:
        telemetry("PREFLIGHT", "END", qualification_mode=report["qualification_mode"])
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
