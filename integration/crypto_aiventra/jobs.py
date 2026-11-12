"""Closed job definitions, exact source/contract approval, no arbitrary commands."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .adapter import Crypto2Adapter, read_json
from .config import CONFIG_HASH, RUN_ID, SOURCE_HEAD, CryptoPaths, require_branch

JobType = Literal[
    "CRYPTO_RUNTIME_HEALTH",
    "CRYPTO_LINEAGE_VALIDATE",
    "CRYPTO_CACHE_PREPARE",
    "CRYPTO_CACHE_VALIDATE",
    "CRYPTO_FOLD_TRAIN",
    "CRYPTO_SPEC_TRAIN",
    "CRYPTO_MODEL_VALIDATE",
    "CRYPTO_REPORT_GENERATE",
    "CRYPTO_RECOVERY_INSPECT",
]
HEAVY = {
    "CRYPTO_CACHE_PREPARE",
    "CRYPTO_CACHE_VALIDATE",
    "CRYPTO_FOLD_TRAIN",
    "CRYPTO_SPEC_TRAIN",
    "CRYPTO_LINEAGE_VALIDATE",
    "CRYPTO_MODEL_VALIDATE",
}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_type: JobType
    spec_id: str = "architecture-G0-A6-60m-raw"
    maximum_runtime_seconds: int = Field(default=60, ge=5, le=86400)
    deadline_utc: int = Field(gt=0)
    cost_ceiling: str = Field(min_length=1, max_length=80)
    cost_currency: str = Field(default="UNKNOWN", pattern=r"^[A-Z]{3,12}$")
    cpu_threads: int = Field(default=1, ge=1, le=128)
    minimum_free_ram_gib: float = Field(default=1, gt=0, allow_inf_nan=False)
    minimum_free_disk_gib: float = Field(default=1, gt=0, allow_inf_nan=False)
    parent_job_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")


def preview(request: JobRequest, adapter: Crypto2Adapter):
    from crypto_ai.phase7.phase7a import select_one_spec

    require_branch(adapter.paths.repo)
    config, folds, _ = adapter._canonical()
    selected = select_one_spec(config, request.spec_id)
    if request.cpu_threads > (os.cpu_count() or 1):
        raise ValueError("Requested CPU threads exceed the host allocation")
    if request.deadline_utc <= time.time() or request.deadline_utc > time.time() + 86400:
        raise ValueError("Fresh deadline within one day is required")
    scope = {
        "request": request.model_dump(mode="json"),
        "identity": adapter.get_project_identity(),
        "fold_id": folds[0].fold_id,
        "spec": {
            "spec_id": selected.name,
            "architecture": selected.architecture,
            "horizon_minutes": selected.horizon_minutes,
            "target_type": selected.target_type,
        },
        "source_branch_head": SOURCE_HEAD,
        "run_identity": RUN_ID,
        "configuration_hash": CONFIG_HASH,
        "runtime_paths": {key: str(value) for key, value in asdict(adapter.paths).items()},
    }
    scope["command"] = command_for(scope, adapter.paths)
    scope["expected_models_hash"] = expected_models_hash(adapter.paths)
    scope["verification_gate_hash"] = verification_gate_hash()
    scope["approval_required"] = True
    scope["execution_blockers"] = execution_blockers(scope, adapter.paths)
    scope["scope_hash"] = digest(scope)
    return scope


def expected_models_hash(paths):
    path = paths.verification / "aiventra-expected-model-identities.json"
    if path.is_symlink():
        raise ValueError("Trusted expected identities must not be aliased")
    return digest(read_json(path)) if path.is_file() else None


def verification_gate_hash():
    configured = os.environ.get("CRYPTO_SCIENTIFIC_GATE_REPORT", "")
    if not configured:
        return None
    path = Path(configured)
    if path.is_symlink():
        raise ValueError("Reviewed scientific gate must not be aliased")
    return digest(read_json(path)) if path.is_file() else None


def command_for(scope, paths: CryptoPaths) -> list[str]:
    request = JobRequest.model_validate(scope["request"])
    python = Path(sys.executable).resolve()
    if request.job_type == "CRYPTO_FOLD_TRAIN":
        return [
            str(python),
            "-m",
            "crypto_ai.phase7.lightning",
            "--stage",
            "train",
            "--canary",
            "--resume",
        ]
    if request.job_type == "CRYPTO_SPEC_TRAIN":
        return [
            str(python),
            "-m",
            "crypto_ai.phase7.benchmark_one_spec",
            "--spec-id",
            request.spec_id,
            "--output-root",
            str(paths.runtime / "benchmarks"),
            "--execute",
        ]
    return [
        str(python),
        "-m",
        "integration.crypto_aiventra.operations",
        "--operation",
        request.job_type,
        "--spec-id",
        request.spec_id,
    ]


def execution_blockers(scope, paths: CryptoPaths) -> list[str]:
    kind = scope["request"]["job_type"]
    if kind not in HEAVY:
        return []
    blockers = []
    if scope["identity"].get("mode") == "DEMO_FIXTURE_STATE":
        blockers.append("Fixture state cannot authorize scientific execution")
    if os.name != "posix":
        blockers.append("Scientific workloads are prohibited on this Windows/laptop host")
    if os.environ.get("CRYPTO_ENABLE_SCIENTIFIC_JOBS") != "1":
        blockers.append(
            "Scientific execution is disabled; a fresh owner cost/deadline contract is required"
        )
    # Configuration cannot claim that absent target-host evidence passed.
    gate_path = os.environ.get("CRYPTO_SCIENTIFIC_GATE_REPORT", "")
    try:
        gate = read_json(Path(gate_path)) if gate_path else None
        if not gate or (
            gate.get("status") != "PASS"
            or gate.get("configuration_hash") != CONFIG_HASH
            or gate.get("scientific_source_identity")
            != scope["identity"]["scientific_source_identity"]
            or gate.get("prospective_holdout_status") != "LOCKED_UNUSED"
            or gate.get("prospective_holdout_used") is not False
            or gate.get("prospective_holdout_evaluation_authorized") is not False
            or gate.get("july_2026_used") is not False
            or gate.get("linux_verified") is not True
            or gate.get("gold_bytes_verified") is not True
            or gate.get("prepared_matrix_equivalence_verified") is not True
        ):
            blockers.append(
                "Reviewed Linux/Gold/scientific-equivalence gate evidence is absent or stale"
            )
    except (OSError, ValueError):
        blockers.append("Scientific gate evidence is unreadable")
    if kind == "CRYPTO_MODEL_VALIDATE":
        blockers.append(
            "Independent per-spec expected identity must be supplied through "
            "the canonical recovery utility"
        )
    if kind in {"CRYPTO_FOLD_TRAIN", "CRYPTO_SPEC_TRAIN"} and not expected_models_hash(paths):
        blockers.append(
            "Independently reviewed expected model identities are required for completion"
        )
    return blockers


def validate_scope(scope, adapter: Crypto2Adapter):
    require_branch(adapter.paths.repo)
    unsigned = dict(scope)
    claimed = unsigned.pop("scope_hash", None)
    if digest(unsigned) != claimed:
        raise ValueError("Approved scope checksum mismatch")
    request = JobRequest.model_validate(scope["request"])
    identity = adapter.get_project_identity()
    if scope["identity"] != identity or scope["command"] != command_for(scope, adapter.paths):
        raise ValueError("Approved scientific/source/command identity changed")
    if scope.get("expected_models_hash") != expected_models_hash(adapter.paths):
        raise ValueError("Approved expected model identities changed")
    if scope.get("runtime_paths") != {
        key: str(value) for key, value in asdict(adapter.paths).items()
    }:
        raise ValueError("Approved runtime input/output paths changed")
    if scope.get("verification_gate_hash") != verification_gate_hash():
        raise ValueError("Approved scientific verification gate changed")
    if request.deadline_utc <= time.time():
        raise ValueError("Approved deadline expired")
    blockers = execution_blockers(scope, adapter.paths)
    if blockers:
        raise PermissionError("; ".join(blockers))
    return request
