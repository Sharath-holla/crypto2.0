"""ONE fail-closed admission function for every official Phase 7 training/preparation path.

CHANGED BY CLAUDE (2026-11-06, smoke-readiness closure) - new file. Before this, only
``benchmark_one_spec --execute`` and ``scripts/run_phase7a_pipeline.py`` enforced the runtime
contract; ``crypto-ai phase7-research --stage train`` reached ``run_phase7_training`` through a
weaker RAM guard. Now:

* the generic ``phase7-research`` training stages fail with ``NON_CANONICAL_RESEARCH_ENTRYPOINT``;
* the canonical entrypoints call :func:`admit_official_training` (same checks, same order);
* the backend is checked again inside ``run_phase7_training`` (:func:`assert_backend_admitted`),
  so a direct call cannot silently switch to a GPU that has no recorded approval;
* the smoke protocol is CPU-only with one logical worker, and no environment variable can change
  that without the admission raising.

Every failure message starts with a stable code so tests and operators can match on it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

NON_CANONICAL = "NON_CANONICAL_RESEARCH_ENTRYPOINT"
CANONICAL_ENTRYPOINTS = frozenset({"benchmark_one_spec", "run_phase7a_pipeline"})
APPROVED_CONFIGURATION_HASHES = frozenset({"93f987736b1a79d26b773957"})  # Phase 7A / Core20
GPU_APPROVAL_FILE_ENV = "PHASE7_GPU_APPROVAL_FILE"
DEVICE_ENV = "PHASE7_LGBM_DEVICE"


class AdmissionError(RuntimeError):
    """A run was refused. The message starts with a stable upper-case code."""


def reject_noncanonical(entrypoint: str) -> None:
    if entrypoint not in CANONICAL_ENTRYPOINTS:
        raise AdmissionError(
            f"{NON_CANONICAL}: '{entrypoint}' is not an approved Phase 7 training entrypoint; "
            "use `python -m crypto_ai.phase7.benchmark_one_spec` (one spec) or "
            "`scripts/run_phase7a_pipeline.py` (approved pipeline)"
        )


def assert_backend_admitted(backend: Any, environ: Mapping[str, str] | None = None) -> None:
    """CPU is always admitted. GPU needs an APPROVED qualification file (never implicit)."""

    env = os.environ if environ is None else environ
    if not getattr(backend, "gpu_requested", False):
        return
    path = env.get(GPU_APPROVAL_FILE_ENV, "").strip()
    if not path:
        raise AdmissionError(
            "GPU_NOT_QUALIFIED: a GPU backend was requested but "
            f"{GPU_APPROVAL_FILE_ENV} names no approval file; CPU is the scientific baseline"
        )
    try:
        approval = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdmissionError(f"GPU_NOT_QUALIFIED: approval file unreadable ({exc})") from exc
    if approval.get("status") != "APPROVED" or not approval.get("evidence_hash"):
        raise AdmissionError("GPU_NOT_QUALIFIED: approval file is not APPROVED with evidence")


def _cpu_only(environ: Mapping[str, str]) -> None:
    device = environ.get(DEVICE_ENV, "cpu").strip().lower() or "cpu"
    if device != "cpu":
        raise AdmissionError(f"SMOKE_REQUIRES_CPU: {DEVICE_ENV}={device!r}; GPU is not allowed")


def admit_official_training(
    *,
    entrypoint: str,
    config: Any,
    mode: str,
    output_root: Path | None,
    smoke: bool = True,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run every admission check; return the record of what was verified or raise.

    ``mode`` is ``"train"`` or ``"prepare"``. ``smoke`` enforces CPU and one logical worker.
    """

    env = os.environ if environ is None else environ
    if mode not in {"train", "prepare"}:
        raise AdmissionError(f"BAD_ADMISSION_MODE: {mode!r}")
    reject_noncanonical(entrypoint)
    config.assert_cloud_execution_allowed()
    if config.configuration_hash not in APPROVED_CONFIGURATION_HASHES:
        raise AdmissionError(f"CONFIG_NOT_APPROVED: {config.configuration_hash}")
    if (
        config.prospective_holdout_status != "LOCKED_UNUSED"
        or config.prospective_holdout_used
        or config.prospective_holdout_evaluation_authorized
    ):
        raise AdmissionError("HOLDOUT_NOT_LOCKED: August must be LOCKED_UNUSED and unauthorised")

    from crypto_ai.phase7.resources import (
        configured_floor,
        require_preparation_runtime_contract,
        require_training_runtime_contract,
    )
    from crypto_ai.phase7.runtime import ComputeBudget, RuntimePaths

    try:
        if mode == "train":
            require_training_runtime_contract()
        else:
            require_preparation_runtime_contract()
    except ValueError as exc:
        raise AdmissionError(f"RUNTIME_CONTRACT: {exc}") from exc
    if configured_floor("PHASE7_MIN_FREE_DISK_GIB", "PHASE7_MIN_FREE_DISK_GB") <= 0:
        raise AdmissionError("RUNTIME_CONTRACT: an explicit positive PHASE7_MIN_FREE_DISK_GIB")

    budget = ComputeBudget.resolve(config.resources)
    if smoke:
        _cpu_only(env)
        if budget.model_parallelism != 1:
            raise AdmissionError(
                f"SMOKE_REQUIRES_ONE_WORKER: PHASE7_MODEL_PARALLELISM={budget.model_parallelism}"
            )
    else:
        from crypto_ai.phase7.backend import resolve_lightgbm_backend

        assert_backend_admitted(resolve_lightgbm_backend(), env)

    runtime = RuntimePaths.resolve(config.paths)
    if output_root is None:
        raise AdmissionError("OUTPUT_ROOT_REQUIRED: an isolated output root must be given")
    resolved = output_root.resolve()
    production = runtime.artifact_root.resolve()
    if resolved == production or production.is_relative_to(resolved):
        raise AdmissionError(f"OUTPUT_ROOT_NOT_ISOLATED: {resolved} is/contains {production}")

    from crypto_ai.phase7.experiment_identity import experiment_control_identity
    from crypto_ai.phase7.hardening import current_config
    from crypto_ai.phase7.result_publication import selection_protocol_identity

    control = experiment_control_identity(asdict(current_config()))["manifest_sha256"]
    protocol = selection_protocol_identity()
    # CHANGED BY CLAUDE (2026-11-06, closure): from here on this process is a research process; the
    # order-capable CoinSwitch client refuses to be constructed (see pipeline/coinswitch_client.py).
    # Only the real process environment is touched, never an injected test mapping.
    if environ is None:
        os.environ["CRYPTO_AI_RESEARCH_MODE"] = "1"
    return {
        "status": "ADMITTED",
        "entrypoint": entrypoint,
        "mode": mode,
        "smoke": smoke,
        "configuration_hash": config.configuration_hash,
        "backend": "cpu" if smoke else env.get(DEVICE_ENV, "cpu"),
        "model_parallelism": budget.model_parallelism,
        "cache_mode": env.get("PHASE7_CACHE_MODE", "auto"),
        "experiment_control_identity": control,
        **protocol,
        "output_root": str(resolved),
        "holdout": config.holdout_status_payload(),
        "checks": [
            "CANONICAL_ENTRYPOINT",
            "APPROVED_CONFIG",
            "HOLDOUT_LOCKED",
            "RUNTIME_CONTRACT",
            "BACKEND",
            "WORKERS",
            "OUTPUT_ROOT_ISOLATED",
            "EXPERIMENT_IDENTITY",
            "SELECTION_PROTOCOL",
        ],
    }
