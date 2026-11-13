"""Explicit environment names and an owner-supplied, identity-bound smoke contract."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APPROVAL_ENV = "PHASE7_OWNER_APPROVAL_FILE"
SMOKE_SPEC = "architecture-G0-A6-60m-raw"
KNOWN_ENVIRONMENT = frozenset(
    [
        "PHASE7_ALLOW_CLOUD_RESEARCH",
        "PHASE7_ACTUAL_BILLING_INR",
        "PHASE7_APPROVED_BASELINE",
        "PHASE7_ARTIFACT_ROOT",
        "PHASE7_BUDGET_BASELINE_AT_UTC",
        "PHASE7_BUDGET_BASELINE_INR",
        "PHASE7_BUDGET_HARD_INR",
        "PHASE7_BUDGET_HOURLY_INR",
        "PHASE7_BUDGET_PROJECTED_INR",
        "PHASE7_BUDGET_SOFT_INR",
        "PHASE7_CACHE_MAX_GB",
        "PHASE7_CACHE_MODE",
        "PHASE7_CACHE_ROOT",
        "PHASE7_CHECKPOINT_ROOT",
        "PHASE7_CLOUD_RESEARCH_COMPLETE",
        "PHASE7_CLOUD_STORAGE_ROOT",
        "PHASE7_CONFIGURATION_HASH",
        "PHASE7_DATA_ROOT",
        "PHASE7_FEATURE_CONTEXT_SIDECAR",
        "PHASE7_FEATURE_VERSION",
        "PHASE7_GNU_TIME_BIN",
        "PHASE7_GOLD_ROOT",
        "PHASE7_GOLD_VALIDATION_REPORT",
        "PHASE7_GPU_APPROVAL_FILE",
        "PHASE7_HARDENING_CONFIG",
        "PHASE7_LGBM_DEVICE",
        "PHASE7_LIGHTGBM_THREADS_PER_MODEL",
        "PHASE7_LOG_ROOT",
        "PHASE7_LOG_ROTATE_KEEP",
        "PHASE7_LOG_ROTATE_MB",
        "PHASE7_LOW_MEMORY_VALIDATION_FILE",
        "PHASE7_MEMORY_PROFILE",
        "PHASE7_METRICS_EVERY",
        "PHASE7_MIN_AVAILABLE_RAM_GB",
        "PHASE7_MIN_FREE_DISK_GB",
        "PHASE7_MIN_FREE_DISK_GIB",
        "PHASE7_MIN_FREE_RAM_GIB",
        "PHASE7_MODEL_HASH_REGISTRY",
        "PHASE7_MODEL_PARALLELISM",
        "PHASE7_MODEL_ROOT",
        "PHASE7_REPORT_ROOT",
        "PHASE7_REPOSITORY_ROOT",
        "PHASE7_REQUIRE_MODEL_REGISTRY",
        "PHASE7_RESEARCH_CUTOFF",
        "PHASE7_STAGING_DAYS",
        "PHASE7_TARGET_VERSION",
        "PHASE7_TEMP_ROOT",
        "PHASE7_TOTAL_CPU_THREADS",
        "PHASE7_UNCACHED_DIGEST_FILE",
        "PHASE7_UV_BIN",
        "PHASE7_OWNER_APPROVAL_FILE",
    ]
) | frozenset(
    f"PHASE7_LEGACY_{family}_ROOT" for family in ("DATA", "GOLD", "ARTIFACT", "MODEL", "REPORT")
)


def validate_environment(environ: Mapping[str, str]) -> list[str]:
    unknown = sorted(
        name for name in environ if name.startswith("PHASE7_") and name not in KNOWN_ENVIRONMENT
    )
    if unknown:
        raise ValueError("UNKNOWN_PHASE7_ENVIRONMENT: " + ", ".join(unknown))
    # Record names only: an arbitrary environment value must never be dumped into logs.
    return sorted(set(environ) & KNOWN_ENVIRONMENT)


def smoke_resource_errors(snapshot: Mapping[str, Any]) -> list[str]:
    """Conservative owner-specified first-smoke hardware floor, independent of fit estimates."""
    errors = []
    for key, minimum, label in (
        ("ram_total_bytes", 64 * 1024**3, "effective RAM >=64 GiB"),
        ("cpu_count", 8, "effective CPUs >=8"),
        ("disk_total_bytes", 150_000_000_000, "local filesystem capacity >=150 GB"),
    ):
        if int(snapshot[key]) < minimum:
            errors.append(label)
    return errors


# ADDED BY CLAUDE (2026-11-13): explicit, opt-in low-memory profile floors. They apply ONLY when
# PHASE7_MEMORY_PROFILE=low_memory; the standard profile keeps the 64 GiB / 8 CPU / 150 GB floor
# above unchanged. Basis (experiments/phase7_low_memory/REPORT.md, synthetic Fold-0 shape):
# measured preparation peak anonymous memory 11.15 GiB (10.56 GiB for the all-20-symbols worst
# case), training from the read-only cache <= 2.0 GiB. RAM is the container-effective total
# (cgroup-aware); disk is FREE space on the cache filesystem, not device size, because a device
# can be much larger than the writable allowance.
LOW_MEMORY_MIN_RAM_BYTES = 13 * 1024**3
LOW_MEMORY_MIN_CPUS = 4
LOW_MEMORY_MIN_FREE_DISK_BYTES = {"prepare": 14 * 1024**3, "train": 2 * 1024**3}


def low_memory_resource_errors(snapshot: Mapping[str, Any], mode: str) -> list[str]:
    if mode not in LOW_MEMORY_MIN_FREE_DISK_BYTES:
        raise ValueError(f"BAD_ADMISSION_MODE: {mode!r}")
    errors = []
    if int(snapshot["ram_total_bytes"]) < LOW_MEMORY_MIN_RAM_BYTES:
        errors.append("low-memory profile: effective RAM >=13 GiB")
    if int(snapshot["cpu_count"]) < LOW_MEMORY_MIN_CPUS:
        errors.append("low-memory profile: effective CPUs >=4")
    if int(snapshot["disk_free_bytes"]) < LOW_MEMORY_MIN_FREE_DISK_BYTES[mode]:
        gib = LOW_MEMORY_MIN_FREE_DISK_BYTES[mode] // 1024**3
        errors.append(f"low-memory profile: free cache-filesystem space >={gib} GiB for {mode}")
    return errors


def validate_owner_approval(
    path: Path, *, expected: Mapping[str, Any], mode: str, now: datetime | None = None
) -> dict[str, Any]:
    approval = json.loads(path.read_text())
    if (
        approval.get("schema") != "phase7_owner_smoke_approval_v1"
        or approval.get("status") != "APPROVED"
        or not approval.get("owner")
    ):
        raise ValueError("OWNER_APPROVAL_REQUIRED: explicit APPROVED owner contract required")
    if approval.get("binding") != dict(expected) or approval.get("mode") != mode:
        raise ValueError("OWNER_APPROVAL_IDENTITY_MISMATCH")
    try:
        deadline = datetime.fromisoformat(approval["stop_deadline_utc"].replace("Z", "+00:00"))
        ceiling = float(approval["cost_ceiling"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("OWNER_COST_DEADLINE_CONTRACT_REQUIRED") from exc
    if deadline.utcoffset() is None or deadline.utcoffset().total_seconds() != 0:
        raise ValueError("OWNER_DEADLINE_MUST_BE_UTC")
    if deadline <= (now or datetime.now(UTC)):
        raise ValueError("OWNER_APPROVAL_EXPIRED")
    if not math.isfinite(ceiling) or ceiling <= 0 or not approval.get("cost_currency"):
        raise ValueError("OWNER_COST_DEADLINE_CONTRACT_REQUIRED")
    from crypto_ai.data.storage import file_sha256

    return {
        "approval_sha256": file_sha256(path),
        "binding": dict(expected),
        "mode": mode,
        "stop_deadline_utc": deadline.isoformat(),
        "cost_ceiling": ceiling,
        "cost_currency": approval["cost_currency"],
    }


def approval_binding(
    config: Any, spec_id: str, fold_id: str, *, mode: str | None = None
) -> dict[str, Any]:
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.context_sidecar import SIDECAR_ENV
    from crypto_ai.phase7.gold_validation import locate_gold_manifest
    from crypto_ai.phase7.identity_summary import identity_summary
    from crypto_ai.phase7.runtime import RuntimePaths

    first = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    if spec_id != SMOKE_SPEC or fold_id != first.fold_id:
        raise ValueError("OWNER_SCOPE_REFUSED: only CORE/A6/60m/raw/Fold 0 is eligible")
    value = os.environ.get(SIDECAR_ENV, "").strip()
    if not value:
        raise ValueError("M01_FEATURE_CONTEXT_SIDECAR_REQUIRED")
    gold = locate_gold_manifest(RuntimePaths.resolve(config.paths).gold_root)
    manifest = json.loads(gold.read_text())
    binding = {
        **identity_summary(gold, Path(value)),
        "configuration_hash": config.configuration_hash,
        "dataset_id": manifest["dataset_id"],
        "spec_id": spec_id,
        "fold_id": fold_id,
        "research_view": "CORE",
        "backend": "cpu",
        "workers": 1,
        "minimum_effective_ram_bytes": 64 * 1024**3,
        "minimum_effective_cpus": 8,
        "minimum_local_disk_bytes": 150_000_000_000,
    }
    # ADDED BY CLAUDE (2026-11-13): the low-memory profile needs its OWN explicit owner approval
    # (a standard-profile approval never matches it), and training additionally binds the exact
    # VALIDATED cached-versus-uncached record for the current source.
    from crypto_ai.phase7 import low_memory

    if low_memory.enabled():
        binding.pop("minimum_local_disk_bytes")
        binding.update(
            {
                "memory_profile": low_memory.LOW_MEMORY,
                "minimum_effective_ram_bytes": LOW_MEMORY_MIN_RAM_BYTES,
                "minimum_effective_cpus": LOW_MEMORY_MIN_CPUS,
                "minimum_free_disk_bytes": LOW_MEMORY_MIN_FREE_DISK_BYTES[mode or "train"],
            }
        )
        if mode == "train":
            from crypto_ai.phase7.low_memory_validation import require_validation

            binding["low_memory_validation_sha256"] = require_validation()["sha256"]
    return binding


def require_owner_contract(config: Any, mode: str, spec_id: str, fold_id: str) -> dict[str, Any]:
    value = os.environ.get(APPROVAL_ENV, "").strip()
    if not value:
        raise ValueError(
            "OWNER_APPROVAL_REQUIRED: cost/deadline and exact smoke identity must be approved"
        )
    from crypto_ai.phase7 import low_memory

    expected = (
        approval_binding(config, spec_id, fold_id, mode=mode)
        if low_memory.enabled()
        else approval_binding(config, spec_id, fold_id)
    )
    return validate_owner_approval(Path(value), expected=expected, mode=mode)
