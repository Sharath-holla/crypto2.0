from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

from crypto_ai.phase7.config import ModelConfig
from crypto_ai.phase7.device_evidence import fit_with_device_evidence
from crypto_ai.phase7.equivalence import assess_equivalence
from crypto_ai.research.metrics import regression_metrics

BackendName = Literal["cpu", "gpu", "cuda"]


@dataclass(frozen=True, slots=True)
class LightGBMBackend:
    name: BackendName
    gpu_requested: bool
    bitwise_reproducible: bool


def resolve_lightgbm_backend(value: str | None = None) -> LightGBMBackend:
    requested = (value or os.environ.get("PHASE7_LGBM_DEVICE", "cpu")).strip().lower()
    if requested not in {"cpu", "gpu", "cuda"}:
        raise ValueError("PHASE7_LGBM_DEVICE must be cpu, gpu, or cuda")
    return LightGBMBackend(
        name=requested,  # type: ignore[arg-type]
        gpu_requested=requested != "cpu",
        bitwise_reproducible=requested == "cpu",
    )


def lightgbm_version() -> str:
    import lightgbm as lgb

    return str(lgb.__version__)


def gpu_snapshot() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,driver_version,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"detected": False, "error": str(exc)}
    devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    details = []
    fields = (
        "ordinal",
        "uuid",
        "name",
        "driver_version",
        "memory_total_mib",
        "memory_used_mib",
        "utilization_percent",
    )
    for line in devices:
        values = [value.strip() for value in line.split(",")]
        if len(values) == len(fields):
            details.append(dict(zip(fields, values, strict=True)))
    return {
        "detected": bool(devices),
        "devices": devices,
        "device_details": details,
        "cuda_opencl_runtime_info": "NOT_OBSERVED_BY_THIS_QUERY",
    }


def lightgbm_estimator_parameters(
    config: ModelConfig,
    *,
    model_threads: int,
    backend: LightGBMBackend | None = None,
) -> dict[str, Any]:
    selected = backend or resolve_lightgbm_backend()
    parameters: dict[str, Any] = {
        "objective": "regression",
        "learning_rate": config.learning_rate,
        "n_estimators": config.n_estimators,
        "num_leaves": config.num_leaves,
        "max_depth": config.max_depth,
        "min_child_samples": config.min_child_samples,
        "subsample": config.subsample,
        "subsample_freq": 1,
        "colsample_bytree": config.colsample_bytree,
        "reg_alpha": config.reg_alpha,
        "reg_lambda": config.reg_lambda,
        "random_state": config.seed,
        "n_jobs": model_threads,
        "verbosity": -1,
        "device_type": selected.name,
    }
    if selected.name == "cpu":
        parameters.update(deterministic=True, force_col_wise=True)
    elif selected.name == "gpu":
        # OpenCL defaults to float32 accumulation. Preserve double precision;
        # CUDA has a separate implementation and must be evaluated separately.
        parameters["gpu_use_dp"] = True
    # LightGBM's deterministic/force_col_wise controls are CPU-specific. GPU
    # backends retain the frozen seed and scientific hyperparameters, while
    # artifacts explicitly record that reproducibility is scientific rather
    # than bitwise.
    return parameters


def backend_metadata(backend: LightGBMBackend | None = None) -> dict[str, Any]:
    selected = backend or resolve_lightgbm_backend()
    return {
        **asdict(selected),
        "lightgbm_version": lightgbm_version(),
        "gpu": gpu_snapshot() if selected.gpu_requested else {"detected": False},
    }


def _backend_error(backend: LightGBMBackend, exc: BaseException) -> RuntimeError:
    return RuntimeError(
        "Requested LightGBM backend failed without CPU fallback: "
        + json.dumps(
            {
                "requested_backend": backend.name,
                "lightgbm_version": lightgbm_version(),
                "gpu": gpu_snapshot(),
                "error": str(exc),
                "remediation": (
                    "Install/build LightGBM with the requested GPU or CUDA backend and rerun "
                    "the Phase 7 GPU smoke test."
                ),
            },
            sort_keys=True,
        )
    )


def smoke_test_backend(name: BackendName, *, rows: int = 512, features: int = 8) -> dict[str, Any]:
    import lightgbm as lgb

    backend = resolve_lightgbm_backend(name)
    rng = np.random.default_rng(42)
    matrix = rng.normal(size=(rows, features)).astype(np.float64)
    target = (matrix[:, 0] * 0.3 - matrix[:, 1] * 0.2 + rng.normal(0, 0.01, rows)).astype(
        np.float64
    )
    params = lightgbm_estimator_parameters(
        ModelConfig(n_estimators=20, early_stopping_rounds=5),
        model_threads=1,
        backend=backend,
    )
    started = time.perf_counter()
    try:
        model = lgb.LGBMRegressor(**params)
        fit_with_device_evidence(
            model,
            backend,
            matrix[:400],
            target[:400],
            eval_X=matrix[400:],
            eval_y=target[400:],
        )
    except Exception as exc:
        if backend.gpu_requested:
            raise _backend_error(backend, exc) from exc
        raise
    return {
        "status": "PASS",
        "requested_backend": name,
        "actual_backend": backend.name,
        "fit_success": True,
        "device": gpu_snapshot() if backend.gpu_requested else {"name": "CPU"},
        "lightgbm_version": lightgbm_version(),
        "elapsed_seconds": time.perf_counter() - started,
        "device_attestation": getattr(model, "phase7_device_evidence_", {"status": "CPU_ONLY"}),
    }


def compare_cpu_gpu_backends(
    requested: Literal["gpu", "cuda"],
    *,
    rows: int = 2_000,
    features: int = 16,
    tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    import lightgbm as lgb

    rng = np.random.default_rng(42)
    matrix = rng.normal(size=(rows, features)).astype(np.float64)
    target = matrix[:, :4] @ np.asarray([0.2, -0.1, 0.05, 0.15]) + rng.normal(0, 0.02, rows)
    weights = np.linspace(0.75, 1.25, rows, dtype=np.float64)
    split = int(rows * 0.75)
    config = ModelConfig(n_estimators=100, early_stopping_rounds=10)
    results: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    for name in ("cpu", requested):
        backend = resolve_lightgbm_backend(name)
        params = lightgbm_estimator_parameters(config, model_threads=1, backend=backend)
        started = time.perf_counter()
        try:
            model = lgb.LGBMRegressor(**params)
            fit_with_device_evidence(
                model,
                backend,
                matrix[:split],
                target[:split],
                sample_weight=weights[:split],
                eval_X=matrix[split:],
                eval_y=target[split:],
                callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(0)],
            )
        except Exception as exc:
            if backend.gpu_requested:
                raise _backend_error(backend, exc) from exc
            raise
        predicted = np.asarray(model.predict(matrix[split:]), dtype=np.float64)
        predictions[name] = predicted
        metrics = regression_metrics(target[split:], predicted)
        results[name] = {
            "metrics": metrics,
            "best_iteration": int(model.best_iteration_ or config.n_estimators),
            "runtime_seconds": time.perf_counter() - started,
            "backend_metadata": backend_metadata(backend),
            "device_attestation": getattr(model, "phase7_device_evidence_", {"status": "CPU_ONLY"}),
        }
    assessment = assess_equivalence(
        target[split:],
        predictions["cpu"],
        predictions[requested],
        limits=tolerances,
        cpu_best_iteration=results["cpu"]["best_iteration"],
        gpu_best_iteration=results[requested]["best_iteration"],
    )
    return {
        **assessment,
        "rows": rows,
        "features": features,
        "seed": config.seed,
        "parameters": config.model_dump(mode="json"),
        "cpu": results["cpu"],
        requested: results[requested],
    }
