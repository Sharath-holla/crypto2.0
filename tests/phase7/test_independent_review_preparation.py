"""Independent review regressions for preparation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from crypto_ai.phase7 import preflight, training
from tests.phase7.test_pre_lightning_finalization import canonical
from tests.phase7.test_training_error_classification import _patch_harness, _synthetic_registry


def test_prepare_only_runner_publishes_one_cache_and_never_fits(tmp_path, monkeypatch):
    checkpoint_root, _, _ = _patch_harness(monkeypatch, tmp_path, fit_error=AssertionError("fit"))
    context = _synthetic_registry()
    root = tmp_path / "isolated" / "benchmark-only-review"
    store = replace(
        context.store(checkpoint_root), root=root / "checkpoints", run_identity=root.name
    )
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    monkeypatch.setenv("PHASE7_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setattr(training, "_run_one", lambda *_a, **_k: pytest.fail("fit/evaluate called"))
    result = training.run_phase7_training(
        canonical(),
        gold_manifest_path=tmp_path / "gold/manifest.json",
        registry=context.registry,
        universe=context.universe,
        expansion_policy=context.policy,
        descriptors=context.descriptors,
        checkpoint_store=store,
        run_root=root,
        resume=True,
        scope=training.PHASE7A_SCOPE,
        benchmark_spec_id="architecture-G0-A6-60m-raw",
        benchmark_fold_id="fold-000-test",
        prepare_only=True,
    )
    assert result["status"] == "PREPARED_ONLY"
    assert result["models_fitted"] == result["specs_completed"] == 0
    assert len(list((tmp_path / "cache").glob("*/CACHE_COMPLETE"))) == 1
    assert not list(root.rglob("model.joblib"))
    assert not list(root.rglob("report.json"))
    assert not list((root / "checkpoints").rglob("*.json"))


def test_model_only_is_detected_by_training_loop_before_fit(tmp_path, monkeypatch):
    checkpoint_root, root, fits = _patch_harness(
        monkeypatch,
        tmp_path,
        fit_error=AssertionError("must not fit"),
    )
    context = _synthetic_registry()
    model = root / "models/core/fold-000-test/architecture-G0-A6-60m-raw/model.joblib"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"opaque synthetic orphan -- never deserialize")
    before = model.read_bytes()
    with pytest.raises(ValueError, match="MODEL_ONLY"):
        training.run_phase7_training(
            training.Phase7Config(),
            gold_manifest_path=tmp_path / "gold/manifest.json",
            registry=context.registry,
            universe=context.universe,
            expansion_policy=context.policy,
            descriptors=context.descriptors,
            checkpoint_store=context.store(checkpoint_root),
            run_root=root,
            resume=True,
        )
    assert not fits
    assert model.read_bytes() == before


@pytest.mark.parametrize("mode", ["auto", "rebuild"])
def test_preparation_preflight_accepts_writable_cache_without_backend_fit(
    tmp_path, monkeypatch, mode
):
    for family in ("DATA", "GOLD", "ARTIFACT", "CACHE", "CHECKPOINT", "MODEL", "REPORT", "LOG"):
        path = tmp_path / family.lower()
        path.mkdir()
        monkeypatch.setenv(f"PHASE7_{family}_ROOT", str(path))
    monkeypatch.setenv("PHASE7_CACHE_MODE", mode)
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    manifest = tmp_path / "gold/manifest.json"
    manifest.write_text("{}")
    monkeypatch.setattr(
        preflight,
        "system_snapshot",
        lambda _p: {
            "ram_available_bytes": 64 * 1024**3,
            "disk_free_bytes": 64 * 1024**3,
        },
    )
    monkeypatch.setattr(
        preflight,
        "validate_gold_manifest",
        lambda _p: (
            manifest,
            {"dataset_id": "synthetic", "row_count": 1},
            [],
        ),
    )
    monkeypatch.setattr(preflight, "_validated_gold_report", lambda *_a, **_k: {"status": "PASS"})
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_: pytest.fail("backend fitted"))
    result = preflight.build_preflight_report(
        Path("configs/phase7/research_core20_primary_v1.toml"),
        gold_validation_report=tmp_path / "report.json",
        preparation_only=True,
        run_backend_smoke=False,
    )
    assert result["status"] == "PASS", result["blocking_errors"]
    assert result["preparation_readiness"] == "READY"
    assert result["training_readiness"] == "NOT_READY"
    assert result["backend_smoke"] is None
