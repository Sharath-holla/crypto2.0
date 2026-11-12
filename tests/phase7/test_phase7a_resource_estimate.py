"""CHANGED BY CLAUDE (2026-11-06, final hardening): the resource estimate is pure and fails safe."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai.phase7.resource_estimate import (
    GIB,
    cgroup_limits,
    check_capacity,
    effective_ram_available,
    estimate_spec_resources,
)


def test_estimate_matches_hand_calculation() -> None:
    out = estimate_spec_resources(total_gold_rows=40_000_000, feature_count=109)
    rows = 10_000_000
    # CHANGED BY CLAUDE (2026-11-06, closure): "upper bound" was a misnomer (an average over
    # horizons plus fixed copy factors); keys are renamed and an Arrow-source term is included.
    # OLD CODE (kept for reference):
    # assert out["rows_per_horizon_upper_bound"] == rows
    # assert out["feature_matrix_bytes"] == rows * 109 * 8
    # assert out["ram_required_bytes"] == int(rows * 109 * 8 * 3.0 * 1.2)
    assert out["estimated_rows_per_horizon_average"] == rows
    assert out["rows_label"] == "ESTIMATED_AVERAGE"
    assert out["estimated_raw_matrix_bytes"] == rows * 109 * 8
    arrow = int(rows * 130 * 8 * 2.0)
    assert out["estimated_arrow_source_bytes"] == arrow
    assert out["ram_required_bytes"] == int((rows * 109 * 8 * 3.0 + arrow) * 1.2)
    assert out["ram_required_label"] == "ESTIMATED_HEURISTIC_PEAK"


def test_insufficient_capacity_is_reported_not_ignored() -> None:
    out = estimate_spec_resources(total_gold_rows=50_352_548, feature_count=109)
    errors = check_capacity(out, ram_available=8 * GIB, disk_free=10 * GIB)
    assert len(errors) == 2 and errors[0].startswith("RAM") and errors[1].startswith("DISK")
    assert check_capacity(out, ram_available=10_000 * GIB, disk_free=10_000 * GIB) == []


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        estimate_spec_resources(total_gold_rows=0, feature_count=109)


def test_no_estimate_is_called_an_upper_bound() -> None:
    text = json.dumps(estimate_spec_resources(total_gold_rows=40_000_000, feature_count=109))
    assert "upper_bound" not in text.lower()


def _fake_cgroup_v2(root: Path, memory: str, cpu: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "memory.max").write_text(memory + "\n")
    (root / "memory.current").write_text("0\n")
    (root / "cpu.max").write_text(cpu + "\n")
    return root


def test_cgroup_v2_limits_are_detected_and_bound_the_available_ram(tmp_path: Path) -> None:
    limits = cgroup_limits(_fake_cgroup_v2(tmp_path / "v2", str(8 * GIB), "200000 100000"))
    assert limits["cgroup_memory_limit_bytes"] == 8 * GIB
    assert limits["cgroup_cpu_quota_cpus"] == 2.0 and limits["label"] == "MEASURED"
    system = {"ram_available_bytes": 64 * GIB}
    assert effective_ram_available(system, limits) == 8 * GIB  # the container limit wins


def test_unlimited_or_missing_cgroup_does_not_invent_a_limit(tmp_path: Path) -> None:
    unlimited = cgroup_limits(_fake_cgroup_v2(tmp_path / "u", "max", "max 100000"))
    assert unlimited["cgroup_memory_limit_bytes"] is None
    assert unlimited["cgroup_cpu_quota_cpus"] is None and unlimited["observed"] is False
    assert cgroup_limits(tmp_path / "does-not-exist")["observed"] is False
    assert effective_ram_available({"ram_available_bytes": 5 * GIB}, unlimited) == 5 * GIB


# --- CHANGED BY CLAUDE (2026-11-06, RunPod review): container-aware RAM ---
def test_container_limit_caps_total_and_available_ram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from crypto_ai.phase7 import resource_estimate, runtime

    root = _fake_cgroup_v2(tmp_path / "cg", str(32 * GIB), "max 100000")
    (root / "memory.current").write_text(str(10 * GIB) + "\n")
    real = resource_estimate.cgroup_limits
    monkeypatch.setattr(resource_estimate, "cgroup_limits", lambda *a, **k: real(root))
    total, available = runtime._container_adjusted_memory(1000 * GIB, 900 * GIB)
    assert total == 32 * GIB and available == 22 * GIB  # host says 900 GiB, the pod has 22


def test_no_container_limit_leaves_psutil_values_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crypto_ai.phase7 import resource_estimate, runtime

    empty = {"cgroup_memory_limit_bytes": None, "cgroup_memory_current_bytes": None}
    monkeypatch.setattr(resource_estimate, "cgroup_limits", lambda *a, **k: empty)
    assert runtime._container_adjusted_memory(16 * GIB, 5 * GIB) == (16 * GIB, 5 * GIB)
