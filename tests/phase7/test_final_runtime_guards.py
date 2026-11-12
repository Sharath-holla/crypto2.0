"""Resource ceilings, portable identity, and owner-bound admission regression tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_ai.phase7 import resource_estimate, runtime, training
from crypto_ai.phase7.config import ResourceConfig
from crypto_ai.phase7.run_contract import validate_environment, validate_owner_approval


@pytest.mark.parametrize(
    "host,affinity,quota,expected",
    [(64, 8, 3.5, 3), (64, 2, 8, 2), (4, 8, None, 4), (64, 8, 0.5, 1)],
)
def test_cpu_budget_respects_all_effective_ceilings(monkeypatch, host, affinity, quota, expected):
    monkeypatch.setattr(runtime.os, "cpu_count", lambda: host)
    monkeypatch.setattr(
        runtime.os, "sched_getaffinity", lambda _: set(range(affinity)), raising=False
    )
    monkeypatch.setattr(
        resource_estimate, "cgroup_limits", lambda: {"cgroup_cpu_quota_cpus": quota}
    )
    for key in (
        "PHASE7_TOTAL_CPU_THREADS",
        "PHASE7_MODEL_PARALLELISM",
        "PHASE7_LIGHTGBM_THREADS_PER_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    assert runtime.effective_cpu_count() == expected
    budget = runtime.ComputeBudget.resolve(ResourceConfig())
    assert budget.total_cpu_threads == expected
    assert budget.model_parallelism * budget.lightgbm_threads_per_model <= expected
    monkeypatch.setenv("PHASE7_TOTAL_CPU_THREADS", str(expected + 1))
    with pytest.raises(ValueError, match="effective affinity/cgroup"):
        runtime.ComputeBudget.resolve(ResourceConfig())


def test_nested_cgroup_parent_headroom_and_quota_are_binding(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    child = root / "parent" / "child"
    child.mkdir(parents=True)
    for path, limit, current, cpu in (
        (root / "parent", 100, 99, "250000 100000"),
        (child, 20, 1, "max 100000"),
    ):
        (path / "memory.max").write_text(str(limit))
        (path / "memory.current").write_text(str(current))
        (path / "cpu.max").write_text(cpu)
    membership = tmp_path / "membership"
    membership.write_text("0::/parent/child\n")
    limits = resource_estimate.cgroup_limits(root, membership_path=membership)
    assert limits["cgroup_memory_limit_bytes"] == 20
    assert limits["cgroup_memory_available_bytes"] == 1
    assert limits["cgroup_cpu_quota_cpus"] == 2.5
    monkeypatch.setattr(resource_estimate, "cgroup_limits", lambda: limits)
    assert runtime._container_adjusted_memory(1000, 500) == (20, 1)


def test_v1_controller_limits_and_missing_usage_fail_closed(tmp_path, monkeypatch):
    memory = tmp_path / "memory" / "nested"
    cpu = tmp_path / "cpu,cpuacct" / "nested"
    memory.mkdir(parents=True)
    cpu.mkdir(parents=True)
    (memory / "memory.limit_in_bytes").write_text("100")
    (cpu / "cpu.cfs_quota_us").write_text("150000")
    (cpu / "cpu.cfs_period_us").write_text("100000")
    membership = tmp_path / "membership"
    membership.write_text("2:memory:/nested\n3:cpu,cpuacct:/nested\n")
    limits = resource_estimate.cgroup_limits(tmp_path, membership_path=membership)
    assert limits["cgroup_memory_limit_bytes"] == 100
    assert limits["cgroup_cpu_quota_cpus"] == 1.5
    monkeypatch.setattr(resource_estimate, "cgroup_limits", lambda: limits)
    assert runtime._container_adjusted_memory(50, 30) == (50, 0)


@pytest.mark.parametrize("dataset_id", ["unknown", "gold-phase7-0cbf2910e8d96c9d19826598"])
def test_every_dataset_requires_verified_feature_only_context(monkeypatch, dataset_id):
    monkeypatch.delenv(training.SIDECAR_ENV, raising=False)
    with pytest.raises(ValueError, match="M01_FEATURE_CONTEXT_SIDECAR_REQUIRED"):
        training._context_sidecar_path({"dataset_id": dataset_id})


def test_unknown_environment_is_an_error_without_logging_values():
    with pytest.raises(ValueError, match="UNKNOWN_PHASE7_ENVIRONMENT: PHASE7_CAHCE_MODE") as error:
        validate_environment({"PHASE7_CAHCE_MODE": "secret-value"})
    assert "secret-value" not in str(error.value)
    assert validate_environment({"PHASE7_LEGACY_GOLD_ROOT": "/old", "HOME": "/home"}) == [
        "PHASE7_LEGACY_GOLD_ROOT"
    ]


def test_owner_contract_binds_identity_mode_cost_and_deadline(tmp_path):
    now = datetime(2026, 11, 7, tzinfo=UTC)
    binding = {"science": "abc", "spec_id": "one", "fold_id": "fold-000"}
    payload = {
        "schema": "phase7_owner_smoke_approval_v1",
        "status": "APPROVED",
        "owner": "test fixture",
        "binding": binding,
        "mode": "prepare",
        "stop_deadline_utc": (now + timedelta(hours=1)).isoformat(),
        "cost_ceiling": 1,
        "cost_currency": "USD",
    }
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(payload))
    assert (
        validate_owner_approval(path, expected=binding, mode="prepare", now=now)["binding"]
        == binding
    )
    for expected, mode in (({**binding, "science": "changed"}, "prepare"), (binding, "train")):
        with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
            validate_owner_approval(path, expected=expected, mode=mode, now=now)
    with pytest.raises(ValueError, match="EXPIRED"):
        validate_owner_approval(
            path, expected=binding, mode="prepare", now=now + timedelta(hours=2)
        )
    payload["cost_ceiling"] = float("nan")
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="COST_DEADLINE"):
        validate_owner_approval(path, expected=binding, mode="prepare", now=now)


def test_fold_estimator_counts_only_canonical_rows_and_half_open_windows(tmp_path):
    from crypto_ai.phase5.folds import calibration_split_time, plan_folds
    from crypto_ai.phase7.config import load_phase7_config

    config_path = Path(__file__).parents[2] / "configs/phase7/research_core20_primary_v1.toml"
    config = load_phase7_config(config_path)
    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    times = [
        plan.train_start,
        plan.train_end,
        plan.validation_end,
        calibration_split_time(plan),
        plan.test_start,
        plan.test_end,
    ]
    table = pa.table(
        {
            "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
            "horizon_minutes": [60] * len(times),
        }
    )
    pq.write_table(table, tmp_path / "selected.parquet")
    pq.write_table(table, tmp_path / "unreferenced.parquet")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"partition_files": [{"path": "selected.parquet"}]}))
    observed = resource_estimate.observed_fold_rows(manifest, config_path, 0, 60)
    assert observed["segment_rows"] == {
        "TRAIN": 1,
        "Validation": 1,
        "Cal-A": 1,
        "Cal-B": 1,
        "TEST": 1,
    }
    assert observed["total_rows"] == 5 and observed["label"] == "MEASURED"
    estimate = resource_estimate.estimate_spec_resources(
        total_gold_rows=100, feature_count=109, observed_rows=5
    )
    assert estimate["matrix_rows"] == 5 and estimate["rows_label"] == "MEASURED"
    assert estimate["ram_required_label"] == "ESTIMATED_HEURISTIC_PEAK"
    with pytest.raises(ValueError, match="outside"):
        resource_estimate.observed_fold_rows(manifest, config_path, -1, 60)


def test_portable_summary_uses_real_frozen_sidecar_and_rejects_other_gold(tmp_path):
    from crypto_ai.data.storage import file_sha256
    from crypto_ai.phase7.context_sidecar import context_source_projection, write_sidecar
    from crypto_ai.phase7.identity_summary import identity_summary
    from tests.phase7.test_context_sidecar import _candles, _config, _identity

    gold = tmp_path / "gold.json"
    gold.write_text('{"dataset_id": "synthetic-identity-fixture"}\n')
    source = context_source_projection(_candles(), _config())
    sidecar = write_sidecar(
        tmp_path / "sidecar", [source], {**_identity(), "gold_manifest_sha256": file_sha256(gold)}
    )
    first = identity_summary(gold, sidecar)
    assert len(first) == 6 and all(len(value) == 64 for value in first.values())
    # Relocation changes paths, never source or input content identities.
    import shutil

    shutil.copytree(tmp_path / "sidecar", tmp_path / "relocated")
    assert identity_summary(gold, tmp_path / "relocated/manifest.json") == first
    gold.write_text('{"changed": true}\n')
    with pytest.raises(ValueError, match="GOLD_IDENTITY_MISMATCH"):
        identity_summary(gold, sidecar)


def test_source_export_verifies_without_git_and_rejects_tampering(tmp_path):
    import hashlib

    from crypto_ai.data.storage import file_sha256
    from crypto_ai.phase7.source_freeze import verify_source_freeze

    source = tmp_path / "module.py"
    source.write_text("VALUE = 1\n")
    records = [{"path": "module.py", "bytes": source.stat().st_size, "sha256": file_sha256(source)}]
    manifest = tmp_path / "source-freeze.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "phase7_committed_source_export_v1",
                "commit": "test-commit",
                "files": records,
                "files_sha256": hashlib.sha256(
                    json.dumps(records, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    )
    assert verify_source_freeze(tmp_path, manifest)["status"] == "PASS"
    source.write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="FILE_MISMATCH"):
        verify_source_freeze(tmp_path, manifest)


def test_filesystem_primitives_use_real_native_processes(tmp_path):
    from crypto_ai.phase7.filesystem_probe import qualify_filesystem

    result = qualify_filesystem(tmp_path, require_linux=False)
    assert result["status"] == "PASS" and len(result["checks"]) == 6
    assert Path(result["path"]).is_relative_to(tmp_path.resolve())


def test_linux_filesystem_qualification_cannot_claim_mac_as_linux(tmp_path):
    import sys

    from crypto_ai.phase7.filesystem_probe import qualify_filesystem

    if sys.platform == "linux":
        # The real primitive test above runs on Linux too. No fabricated OS result.
        return
    result = qualify_filesystem(tmp_path)
    assert result["status"] == "FAIL" and result["filesystem_validation"] == "NOT_RUN"
    assert not list(tmp_path.iterdir())


def test_smoke_hardware_floor_rejects_host_resources_outside_container():
    from crypto_ai.phase7.run_contract import smoke_resource_errors

    assert smoke_resource_errors(
        {"ram_total_bytes": 16 * 1024**3, "cpu_count": 2, "disk_total_bytes": 100_000_000_000}
    ) == ["effective RAM >=64 GiB", "effective CPUs >=8", "local filesystem capacity >=150 GB"]
    assert (
        smoke_resource_errors(
            {"ram_total_bytes": 64 * 1024**3, "cpu_count": 8, "disk_total_bytes": 150_000_000_000}
        )
        == []
    )
