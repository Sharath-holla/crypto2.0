"""ADDED BY CLAUDE (2026-11-13): admission for the opt-in low-memory profile.

The standard profile keeps the 64 GiB / 8 CPU / 150 GB smoke floor. Only an explicit
PHASE7_MEMORY_PROFILE=low_memory selects the measured floors, a separate owner binding, and (for
training) a VALIDATED cached-versus-uncached record bound to the current source.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_ai.phase7 import low_memory_validation
from crypto_ai.phase7.admission import AdmissionError, admit_official_training
from crypto_ai.phase7.config import load_phase7_config

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "configs/phase7/research_core20_primary_v1.toml"
GIB = 1024**3
# Measured on the Claude Code cloud VM used for this experiment.
CLOUD_VM = {
    "ram_total_bytes": 14_337_294_336,
    "cpu_count": 4,
    "disk_total_bytes": 270_553_174_016,
    "disk_free_bytes": 19 * 10**9,
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "1")
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    monkeypatch.setenv("PHASE7_MODEL_PARALLELISM", "1")
    monkeypatch.setenv("PHASE7_TOTAL_CPU_THREADS", "1")
    monkeypatch.delenv("PHASE7_MEMORY_PROFILE", raising=False)
    monkeypatch.delenv(low_memory_validation.VALIDATION_ENV, raising=False)
    return monkeypatch


def _snapshot(monkeypatch: pytest.MonkeyPatch, **overrides: int) -> None:
    from crypto_ai.phase7 import runtime

    monkeypatch.setattr(runtime, "system_snapshot", lambda _: {**CLOUD_VM, **overrides})


def _approve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> None:
    from crypto_ai.phase7 import run_contract

    # Unit-test fixture only: the binding function is replaced, so no real run is approved.
    monkeypatch.setattr(run_contract, "approval_binding", lambda *a, **k: {"fixture": "lm"})
    approval = tmp_path / f"fixture-approval-{mode}.json"
    approval.write_text(
        json.dumps(
            {
                "schema": "phase7_owner_smoke_approval_v1",
                "status": "APPROVED",
                "owner": "unit test fixture",
                "binding": {"fixture": "lm"},
                "mode": mode,
                "stop_deadline_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "cost_ceiling": 1,
                "cost_currency": "USD",
            }
        )
    )
    monkeypatch.setenv("PHASE7_OWNER_APPROVAL_FILE", str(approval))


def _admit(tmp_path: Path, mode: str):
    return admit_official_training(
        entrypoint="benchmark_one_spec",
        config=load_phase7_config(CONFIG),
        mode=mode,
        output_root=tmp_path / "isolated",
        smoke=True,
    )


@pytest.mark.parametrize("mode", ["prepare", "train"])
def test_standard_profile_keeps_the_64_gib_guard_on_this_vm(env, tmp_path, mode) -> None:
    env.setenv("PHASE7_CACHE_MODE", "auto" if mode == "prepare" else "read_only")
    _snapshot(env)
    _approve(env, tmp_path, mode)
    with pytest.raises(AdmissionError, match="SMOKE_RESOURCES_REQUIRED: effective RAM >=64 GiB"):
        _admit(tmp_path, mode)


def test_low_memory_prepare_is_admitted_on_this_vm(env, tmp_path) -> None:
    env.setenv("PHASE7_CACHE_MODE", "rebuild")
    env.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    _snapshot(env)
    _approve(env, tmp_path, "prepare")
    record = _admit(tmp_path, "prepare")
    assert record["status"] == "ADMITTED"
    assert record["memory_profile"] == "low_memory"
    assert record["model_parallelism"] == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ram_total_bytes": 12 * GIB}, "effective RAM >=13 GiB"),
        ({"cpu_count": 2}, "effective CPUs >=4"),
        ({"disk_free_bytes": 10 * GIB}, "free cache-filesystem space >=14 GiB for prepare"),
    ],
)
def test_low_memory_floors_fail_closed(env, tmp_path, overrides, message) -> None:
    env.setenv("PHASE7_CACHE_MODE", "rebuild")
    env.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    _snapshot(env, **overrides)
    _approve(env, tmp_path, "prepare")
    with pytest.raises(AdmissionError, match=f"LOW_MEMORY_RESOURCES_REQUIRED: .*{message}"):
        _admit(tmp_path, "prepare")


def test_unknown_memory_profile_is_refused(env, tmp_path) -> None:
    env.setenv("PHASE7_CACHE_MODE", "rebuild")
    env.setenv("PHASE7_MEMORY_PROFILE", "squeezed")
    _snapshot(env)
    _approve(env, tmp_path, "prepare")
    with pytest.raises(AdmissionError, match="UNKNOWN_MEMORY_PROFILE"):
        _admit(tmp_path, "prepare")


def _real_binding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> dict:
    """Exercise the REAL approval_binding with synthetic Gold/sidecar identity inputs."""

    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7 import gold_validation, identity_summary, run_contract

    manifest = tmp_path / "gold-manifest.json"
    manifest.write_text(json.dumps({"dataset_id": "synthetic-gold"}))
    monkeypatch.setattr(gold_validation, "locate_gold_manifest", lambda _root: manifest)
    monkeypatch.setattr(identity_summary, "identity_summary", lambda *_: {"FIXTURE": "identity"})
    monkeypatch.setenv("PHASE7_FEATURE_CONTEXT_SIDECAR", str(tmp_path / "sidecar"))
    config = load_phase7_config(CONFIG)
    first = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    return run_contract.approval_binding(config, run_contract.SMOKE_SPEC, first.fold_id, mode=mode)


def test_standard_binding_is_unchanged_and_low_memory_binding_differs(env, tmp_path) -> None:
    standard = _real_binding(env, tmp_path, "prepare")
    assert standard["minimum_effective_ram_bytes"] == 64 * GIB
    assert standard["minimum_local_disk_bytes"] == 150_000_000_000
    assert "memory_profile" not in standard
    env.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    low = _real_binding(env, tmp_path, "prepare")
    assert low["memory_profile"] == "low_memory"
    assert low["minimum_effective_ram_bytes"] == 13 * GIB
    assert low["minimum_effective_cpus"] == 4
    assert low != standard, "a standard-profile approval must never satisfy the low-memory one"


def test_low_memory_training_requires_a_validation_record(env, tmp_path) -> None:
    env.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    with pytest.raises(ValueError, match="LOW_MEMORY_VALIDATION_REQUIRED"):
        _real_binding(env, tmp_path, "train")


def _record(tmp_path: Path, **changes) -> Path:
    record = {
        "schema": low_memory_validation.VALIDATION_SCHEMA,
        "status": "VALIDATED",
        "differences": [],
        **low_memory_validation.current_source_digests(),
        **changes,
    }
    path = tmp_path / "validation.json"
    path.write_text(json.dumps(record))
    return path


def test_validation_record_must_be_validated_and_current(env, tmp_path) -> None:
    # Real current digests (no sidecar configured, as in the record).
    env.setenv(low_memory_validation.VALIDATION_ENV, str(_record(tmp_path)))
    assert len(low_memory_validation.require_validation()["sha256"]) == 64
    for changes, message in (
        ({"status": "FAILED"}, "not VALIDATED"),
        ({"differences": ["/tables/train"]}, "lists differences"),
        ({"preparation_digest": "0" * 64}, "LOW_MEMORY_VALIDATION_STALE"),
        ({"scientific_source_digest": "0" * 64}, "LOW_MEMORY_VALIDATION_STALE"),
    ):
        env.setenv(low_memory_validation.VALIDATION_ENV, str(_record(tmp_path, **changes)))
        with pytest.raises(ValueError, match=message):
            low_memory_validation.require_validation()


def test_low_memory_training_binding_names_the_exact_validation_record(env, tmp_path) -> None:
    # The scientific digest also covers the configured sidecar; pin it for this binding test.
    fixed = {"scientific_source_digest": "a" * 64, "preparation_digest": "b" * 64}
    env.setattr(low_memory_validation, "current_source_digests", lambda: fixed)
    record = _record(tmp_path, **fixed)
    env.setenv(low_memory_validation.VALIDATION_ENV, str(record))
    expected = low_memory_validation.require_validation()["sha256"]
    env.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    assert _real_binding(env, tmp_path, "train")["low_memory_validation_sha256"] == expected


def test_new_environment_names_are_known() -> None:
    from crypto_ai.phase7.run_contract import validate_environment

    names = {
        "PHASE7_MEMORY_PROFILE": "low_memory",
        "PHASE7_LOW_MEMORY_VALIDATION_FILE": "x",
        "PHASE7_UNCACHED_DIGEST_FILE": "y",
    }
    assert set(validate_environment(names)) == set(names)


def _binding_for(monkeypatch, tmp_path, spec_id: str, fold_index: int = 0, low: bool = True):
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7 import gold_validation, identity_summary, run_contract

    manifest = tmp_path / "gold-manifest.json"
    manifest.write_text(json.dumps({"dataset_id": "synthetic-gold"}))
    monkeypatch.setattr(gold_validation, "locate_gold_manifest", lambda _root: manifest)
    monkeypatch.setattr(identity_summary, "identity_summary", lambda *_: {"FIXTURE": "identity"})
    monkeypatch.setenv("PHASE7_FEATURE_CONTEXT_SIDECAR", str(tmp_path / "sidecar"))
    if low:
        monkeypatch.setenv("PHASE7_MEMORY_PROFILE", "low_memory")
    else:
        monkeypatch.delenv("PHASE7_MEMORY_PROFILE", raising=False)
    config = load_phase7_config(CONFIG)
    fold = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[fold_index]
    return run_contract.approval_binding(config, spec_id, fold.fold_id, mode="prepare")


def test_v3_scope_admits_exactly_the_fold0_60m_raw_group(env, tmp_path) -> None:
    from crypto_ai.phase7.phase7a import enumerate_specs
    from crypto_ai.phase7.run_contract import LOW_MEMORY_FOLD0_SCOPE_V3

    names = {s["name"] for s in enumerate_specs(load_phase7_config(CONFIG))["specs"]}
    group = {n for n in names if n.startswith("architecture-") and n.endswith("-A6-60m-raw")}
    assert group == LOW_MEMORY_FOLD0_SCOPE_V3 and len(group) == 6
    for spec in sorted(group):
        assert _binding_for(env, tmp_path, spec)["spec_id"] == spec


def test_v3_scope_refuses_other_specs_folds_and_the_standard_profile(env, tmp_path) -> None:
    for spec, fold, low in (
        ("architecture-C0-A6-15m-raw", 0, True),
        ("architecture-C0-A6-60m-volatility_normalized", 0, True),
        ("feature-ablation-G0-A0-60m-raw", 0, True),
        ("architecture-C0-A6-60m-raw", 1, True),
        ("architecture-C0-A6-60m-raw", 0, False),
    ):
        with pytest.raises(ValueError, match="OWNER_SCOPE_REFUSED"):
            _binding_for(env, tmp_path, spec, fold, low)
    assert _binding_for(env, tmp_path, "architecture-G0-A6-60m-raw", 0, False)["spec_id"]
