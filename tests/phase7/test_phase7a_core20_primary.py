from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_ai.phase7 import training
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.runner import phase7_plan
from crypto_ai.phase7.segments import CandleFamilyAcquisition
from scripts.phase7a_feasibility_gate import evaluate
from scripts.phase7a_vm_supervisor import GRACEFUL_STOP_AFTER, WallClockPolicy
from scripts.run_phase7a_pipeline import (
    _phase7a_data_stage,
    _training_patches,
    primary_specs,
    run_identity,
    validate_phase7a_config,
)


def test_phase7a_profile_is_distinct_and_preserves_canonical_identity() -> None:
    canonical = load_phase7_config(Path("configs/phase7/research_v1.toml"))
    phase7a = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    assert canonical.configuration_hash == "cc550337f1f4ee4654124bf6"
    validate_phase7a_config(phase7a, canonical)
    assert phase7a.configuration_hash == "93f987736b1a79d26b773957"
    assert phase7a.configuration_hash != canonical.configuration_hash
    assert run_identity(phase7a) == "phase7a-core20-primary-93f987736b1a79d26b773957"
    assert phase7_plan(phase7a)["estimated_walk_forward_folds"] == 16


def test_phase7a_has_exactly_the_existing_48_primary_a6_specs() -> None:
    phase7a = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    specs = primary_specs(phase7a)
    assert len(specs) == 48
    assert {spec.feature_group for spec in specs} == {"A6"}
    assert not any(spec.name.startswith("feature-ablation-") for spec in specs)
    assert not any(spec.name.startswith("htf-control-") for spec in specs)
    assert {spec.architecture for spec in specs} == {"G0", "C0", "P0", "H0"}


def test_phase7a_training_surface_is_scoped_and_restores_canonical_globals() -> None:
    phase7a = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    canonical_views = training.RESEARCH_VIEWS
    canonical_count = len(training.phase7_experiment_specs(phase7a))
    with _training_patches(phase7a):
        assert training.RESEARCH_VIEWS == ("CORE",)
        assert len(training.phase7_experiment_specs(phase7a)) == 48
        assert "scripts/run_phase7a_pipeline.py" in training.TRAINING_CRITICAL_SOURCE_FILES
    assert training.RESEARCH_VIEWS == canonical_views == ("CORE", "EXPANDING")
    assert len(training.phase7_experiment_specs(phase7a)) == canonical_count == 58


def test_phase7a_data_stage_enables_run_scoped_symbol_resume(monkeypatch: object) -> None:
    phase7a = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    completion_store = object()
    calls: list[dict[str, object]] = []

    def fake_store(*args: object, **kwargs: object) -> object:
        assert kwargs["run_identity"] == run_identity(phase7a)
        assert kwargs["require_full_request_coverage"] is True
        return completion_store

    def fake_acquire(*args: object, **kwargs: object) -> CandleFamilyAcquisition:
        calls.append(kwargs)
        return CandleFamilyAcquisition(())

    def fake_data_stage(*args: object, **kwargs: object) -> tuple[dict[str, object], list[Path]]:
        from crypto_ai.phase7 import pipeline

        pipeline.acquire_candle_family(
            phase7a,
            object(),
            symbols=("BTCUSDT",),
            interval="5m",
            start=phase7a.data_start,
            end=phase7a.research_cutoff,
        )
        return {}, []

    monkeypatch.setattr("scripts.run_phase7a_pipeline.DiscoverySymbolCheckpointStore", fake_store)
    monkeypatch.setattr("scripts.run_phase7a_pipeline.pipeline.acquire_candle_family", fake_acquire)
    monkeypatch.setattr("scripts.run_phase7a_pipeline.pipeline._data_stage", fake_data_stage)

    _phase7a_data_stage(
        phase7a,
        Path("."),
        object(),  # type: ignore[arg-type]
        object(),
        object(),
        ("BTCUSDT",),
        object(),  # type: ignore[arg-type]
    )

    assert len(calls) == 1
    assert calls[0]["completion_store"] is completion_store
    assert calls[0]["resume"] is True
    assert calls[0]["backfill_completion"] is True


def test_wall_clock_guard_starts_before_hard_cap() -> None:
    launched = datetime(2026, 9, 4, tzinfo=UTC)
    policy = WallClockPolicy(launched)
    assert policy.snapshot(launched + GRACEFUL_STOP_AFTER - timedelta(seconds=1))["level"] == (
        "NORMAL"
    )
    stopped = policy.snapshot(launched + GRACEFUL_STOP_AFTER)
    assert stopped["level"] == "HARD_STOP"
    assert stopped["hard_cap_seconds"] == 86_400


def test_canary_gate_fails_closed_when_conservative_projection_exceeds_cap() -> None:
    launched = datetime(2026, 9, 4, tzinfo=UTC)
    summary = {
        "status": "CANARY_COMPLETE",
        "folds_attempted": 1,
        "fold_count": 16,
        "fold_timings": [{"fold_id": "fold-01", "wall_seconds": 4_000.0}],
    }
    result = evaluate(summary, launched, launched + timedelta(seconds=5_000))
    assert result["continuation_allowed"] is False
    assert result["status"] == "PAUSED_PROJECTED_OVER_24H"


def test_canary_gate_allows_only_a_conservative_fit() -> None:
    launched = datetime(2026, 9, 4, tzinfo=UTC)
    summary = {
        "status": "CANARY_COMPLETE",
        "folds_attempted": 1,
        "fold_count": 16,
        "fold_timings": [{"fold_id": "fold-01", "wall_seconds": 1_000.0}],
    }
    result = evaluate(summary, launched, launched + timedelta(seconds=2_000))
    assert result["continuation_allowed"] is True
    assert float(result["conservative_total_seconds"]) < 85_500
