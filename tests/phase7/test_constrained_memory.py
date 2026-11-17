"""Tiny artificial arrays and local child-process guards; no research data or cloud."""

import json
import os
import subprocess
import sys
import time

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7 import memory_profile as m
from crypto_ai.phase7.config import ModelConfig
from crypto_ai.phase7.models import _matrix
from crypto_ai.phase7.run_contract import smoke_resource_errors, validate_environment


def test_standard_floor_does_not_change(monkeypatch):
    monkeypatch.delenv(m.PROFILE_ENV, raising=False)
    snapshot = {
        "ram_total_bytes": 50_000_000_000,
        "cpu_count": 9,
        "disk_total_bytes": 200_000_000_000,
    }
    assert smoke_resource_errors(snapshot) == ["effective RAM >=64 GiB"]
    monkeypatch.setenv(m.PROFILE_ENV, m.CONSTRAINED)
    assert smoke_resource_errors(snapshot) == []
    snapshot["ram_total_bytes"] = 43 * m.GIB
    assert smoke_resource_errors(snapshot)


def test_profile_is_explicit_and_environment_is_whitelisted(monkeypatch):
    monkeypatch.setenv(m.PROFILE_ENV, "typo")
    with pytest.raises(ValueError, match="UNKNOWN_RESOURCE_PROFILE"):
        m.minimum_ram()
    assert (
        len(
            validate_environment(
                {
                    m.PROFILE_ENV: m.CONSTRAINED,
                    "PHASE7_MEMORY_GUARD_CONFIG": "private",
                    "PHASE7_MEMORY_QUALIFICATION_FILE": "private",
                }
            )
        )
        == 3
    )


@pytest.mark.parametrize(
    "ratio,free,status",
    [
        (0.74, 12, "NORMAL"),
        (0.75, 12, "WARNING"),
        (0.82, 9, "HIGH"),
        (0.88, 12, "STOP_MEMORY_GUARD"),
        (0.70, 7.9, "STOP_MEMORY_GUARD"),
        (None, 20, "STOP_TELEMETRY_UNAVAILABLE"),
    ],
)
def test_guard_uses_ratio_and_absolute_headroom(ratio, free, status):
    assert m.severity({"cgroup_ratio": ratio, "ram_available_bytes": int(free * m.GIB)}) == status


def test_matrix_conversion_remains_exact_float64():
    table = pa.table({"a": [1.0, 2.0, 3.0], "b": [5.0, 6.0, 7.0]})
    actual = _matrix(table, ("b", "a"))
    assert actual.dtype == np.float64
    assert np.array_equal(actual, np.column_stack([table["b"].to_numpy(), table["a"].to_numpy()]))
    with pytest.raises(ValueError, match="finite"):
        _matrix(pa.table({"a": [float("nan")]}), ("a",))


def test_missing_and_stale_guard_cannot_fit(tmp_path, monkeypatch):
    monkeypatch.setenv(m.PROFILE_ENV, m.CONSTRAINED)
    cfg = {
        "heartbeat": str(tmp_path / "heartbeat"),
        "contract_sha256": "contract",
        "local_root": str(tmp_path),
        "timeline": str(tmp_path / "timeline"),
    }
    m.atomic(tmp_path / "config", cfg)
    monkeypatch.setenv("PHASE7_MEMORY_GUARD_CONFIG", str(tmp_path / "config"))
    with pytest.raises(FileNotFoundError):
        m.checkpoint("FIT")
    m.atomic(
        tmp_path / "heartbeat",
        {"epoch": time.time() - 10, "contract_sha256": "contract", "guard_pid": os.getpid()},
    )
    with pytest.raises(MemoryError, match="FRESH_MEMORY_GUARD_REQUIRED"):
        m.checkpoint("FIT")


def test_probe_fingerprint_binds_weights_targets_parameters_and_threads():
    a = np.ones((20, 3), dtype=np.float64)
    y = np.arange(20, dtype=np.float64)
    cfg = ModelConfig()
    before = m.fit_fingerprint(cfg, 1, a, y, a, y, None)
    assert before != m.fit_fingerprint(cfg, 2, a, y, a, y, None)
    assert before != m.fit_fingerprint(cfg, 1, a, y + 1, a, y, None)
    assert before != m.fit_fingerprint(cfg, 1, a, y, a, y, np.ones(20))
    assert before != m.fit_fingerprint(
        cfg.model_copy(update={"n_estimators": 5}), 1, a, y, a, y, None
    )


def test_no_unqualified_full_fit_or_cache_substitution(tmp_path, monkeypatch):
    monkeypatch.setenv(m.PROFILE_ENV, m.CONSTRAINED)
    monkeypatch.setattr(m, "checkpoint", lambda stage: None)
    cfgpath = tmp_path / "config"
    proof = tmp_path / "proof"
    manifest = tmp_path / "manifest"
    manifest.write_text("qualified")
    m.atomic(cfgpath, {"contract_sha256": "contract"})
    monkeypatch.setenv("PHASE7_MEMORY_GUARD_CONFIG", str(cfgpath))
    monkeypatch.setenv("PHASE7_MEMORY_QUALIFICATION_FILE", str(proof))
    a = np.ones((20, 3))
    y = np.arange(20, dtype=np.float64)
    cfg = ModelConfig()
    with pytest.raises(FileNotFoundError):
        m.admit_fit(cfg, 1, a, y, a, y, None)
    fp = m.fit_fingerprint(cfg, 1, a, y, a, y, None)
    m.atomic(
        proof,
        {
            "status": "PASS",
            "contract_sha256": "contract",
            "fit_fingerprint": fp,
            "cache_manifest": str(manifest),
            "cache_manifest_sha256": m.hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    )
    m.admit_fit(cfg, 1, a, y, a, y, None)
    with pytest.raises(MemoryError, match="INPUT_MISMATCH"):
        m.admit_fit(cfg, 2, a, y, a, y, None)
    manifest.write_text("different")
    with pytest.raises(MemoryError, match="CACHE_MISMATCH"):
        m.admit_fit(cfg, 1, a, y, a, y, None)


def test_guard_stops_only_its_owned_local_fixture_child(tmp_path, monkeypatch):
    monkeypatch.setenv(m.PROFILE_ENV, m.CONSTRAINED)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    monkeypatch.setattr(
        m,
        "record",
        lambda stage, root: {
            "stage": stage,
            "cgroup_ratio": 0.89,
            "ram_available_bytes": 12 * m.GIB,
        },
    )
    cfg = {
        "local_root": str(tmp_path),
        "timeline": str(tmp_path / "timeline"),
        "heartbeat": str(tmp_path / "heartbeat"),
        "contract_sha256": "fixture",
        "stage": "fixture",
        "emergency_evidence": str(tmp_path / "persisted"),
    }
    try:
        m.watch(cfg, child.pid)
        assert child.poll() is not None
        assert (
            json.loads((tmp_path / "control/STOP_REQUEST.json").read_text())["reason"]
            == "RESOURCE_FAILURE"
        )
        assert (tmp_path / "persisted").exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def test_constrained_monitor_does_not_change_native_model(tmp_path, monkeypatch):
    from crypto_ai.phase7.models import _fit
    from crypto_ai.phase7.training_metrics import training_metric_scope

    rng = np.random.default_rng(73)
    x = rng.normal(size=(400, 6)).astype(np.float64)
    y = x[:, 0] * 0.01 + rng.normal(0, 0.003, 400)
    weights = np.linspace(0.5, 1.5, 260)
    cfg = ModelConfig(n_estimators=30, min_child_samples=5, early_stopping_rounds=5)
    monkeypatch.setattr("crypto_ai.phase7.models.resource_admission", lambda *a, **k: None)
    monkeypatch.setenv(m.PROFILE_ENV, "standard_smoke")
    with training_metric_scope(tmp_path / "standard"):
        original = _fit(
            x[:260], y[:260], x[260:], y[260:], config=cfg, model_threads=1, sample_weight=weights
        )
    cfgfile = tmp_path / "guard"
    proof = tmp_path / "proof"
    manifest = tmp_path / "cache-manifest"
    manifest.write_text("fixture-exact-cache")
    m.atomic(cfgfile, {"contract_sha256": "fixture"})
    m.atomic(
        proof,
        {
            "status": "PASS",
            "contract_sha256": "fixture",
            "fit_fingerprint": m.fit_fingerprint(
                cfg, 1, x[:260], y[:260], x[260:], y[260:], weights
            ),
            "cache_manifest": str(manifest),
            "cache_manifest_sha256": m.hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    )
    monkeypatch.setenv(m.PROFILE_ENV, m.CONSTRAINED)
    monkeypatch.setenv("PHASE7_MEMORY_GUARD_CONFIG", str(cfgfile))
    monkeypatch.setenv("PHASE7_MEMORY_QUALIFICATION_FILE", str(proof))
    monkeypatch.setattr(m, "checkpoint", lambda stage: {"fixture": True})
    with training_metric_scope(tmp_path / "constrained"):
        constrained = _fit(
            x[:260], y[:260], x[260:], y[260:], config=cfg, model_threads=1, sample_weight=weights
        )
    assert np.array_equal(original.predict(x), constrained.predict(x))
    assert original.best_iteration_ == constrained.best_iteration_
    assert original.booster_.model_to_string() == constrained.booster_.model_to_string()
