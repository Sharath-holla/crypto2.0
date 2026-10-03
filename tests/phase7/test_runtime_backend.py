from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import pytest

from crypto_ai.phase7.backend import resolve_lightgbm_backend, smoke_test_backend
from crypto_ai.phase7.config import PathConfig, ResourceConfig
from crypto_ai.phase7.runtime import ComputeBudget, RuntimePaths, cache_mode_from_environment


def test_runtime_paths_use_environment_without_changing_scientific_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = PathConfig()
    monkeypatch.setenv("PHASE7_GOLD_ROOT", str(tmp_path / "gold"))
    monkeypatch.setenv("PHASE7_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PHASE7_CACHE_ROOT", str(tmp_path / "cache"))
    paths = RuntimePaths.resolve(defaults)
    assert paths.gold_root == (tmp_path / "gold").resolve()
    assert paths.artifact_root == (tmp_path / "artifacts").resolve()
    assert paths.cache_root == (tmp_path / "cache").resolve()
    assert defaults.gold_root == Path("data/gold/phase7")


def test_compute_budget_never_oversubscribes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crypto_ai.phase7.runtime.os.cpu_count", lambda: 8)
    monkeypatch.setenv("PHASE7_TOTAL_CPU_THREADS", "8")
    monkeypatch.setenv("PHASE7_MODEL_PARALLELISM", "4")
    monkeypatch.setenv("PHASE7_LIGHTGBM_THREADS_PER_MODEL", "4")
    budget = ComputeBudget.resolve(ResourceConfig())
    assert budget.model_parallelism * budget.lightgbm_threads_per_model <= 8
    assert budget.lightgbm_threads_per_model == 2


def test_cache_mode_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHASE7_CACHE_MODE", "unsafe")
    with pytest.raises(ValueError, match="PHASE7_CACHE_MODE"):
        cache_mode_from_environment()


def test_cache_mode_defaults_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHASE7_CACHE_MODE", raising=False)
    assert cache_mode_from_environment() == "auto"


def test_compute_budget_reports_invalid_parallelism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE7_TOTAL_CPU_THREADS", "2")
    monkeypatch.setenv("PHASE7_MODEL_PARALLELISM", "4")
    monkeypatch.setenv("PHASE7_LIGHTGBM_THREADS_PER_MODEL", "1")
    with pytest.raises(ValueError, match="less than"):
        ComputeBudget.resolve(ResourceConfig())


def test_requested_gpu_backend_never_silently_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenGPURegressor:
        def __init__(self, **_: object) -> None:
            pass

        def fit(self, *_: object, **__: object) -> None:
            raise RuntimeError("GPU backend was not enabled in this build")

    monkeypatch.setattr(lgb, "LGBMRegressor", BrokenGPURegressor)
    with pytest.raises(RuntimeError, match="without CPU fallback"):
        smoke_test_backend("gpu")


def test_cpu_backend_smoke_test_is_available() -> None:
    assert resolve_lightgbm_backend("cpu").bitwise_reproducible is True
    assert smoke_test_backend("cpu")["status"] == "PASS"
