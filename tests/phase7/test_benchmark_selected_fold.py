"""The one-spec benchmark trains exactly the canonical fold chosen by --fold-index."""

from __future__ import annotations

from dataclasses import replace

import pytest

from crypto_ai.phase7 import training
from tests.phase7.test_pre_lightning_finalization import canonical
from tests.phase7.test_training_error_classification import (
    _fold_data,
    _fold_table,
    _patch_harness,
    _synthetic_registry,
)


def _run(tmp_path, monkeypatch, fold_id):
    checkpoint_root, _, _ = _patch_harness(monkeypatch, tmp_path, fit_error=AssertionError("fit"))
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    monkeypatch.setenv("PHASE7_CACHE_ROOT", str(tmp_path / "cache"))
    first = _fold_data(tmp_path).plan
    later = replace(first, fold_id="fold-001-test")
    monkeypatch.setattr(training, "plan_folds", lambda *_a, **_k: (first, later))
    loaded = []

    def load_rows(_manifest, plan, *_a, **_k):
        loaded.append(plan.fold_id)
        return _fold_table()

    monkeypatch.setattr(training, "_load_fold_rows", load_rows)
    monkeypatch.setattr(
        training,
        "slice_multiasset_fold",
        lambda _table, plan, **_k: replace(_fold_data(tmp_path), plan=plan),
    )
    monkeypatch.setattr(training, "_run_one", lambda *_a, **_k: pytest.fail("fit/evaluate called"))
    context = _synthetic_registry()
    root = tmp_path / "isolated" / "benchmark-only-selected"
    store = replace(
        context.store(checkpoint_root), root=root / "checkpoints", run_identity=root.name
    )
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
        benchmark_fold_id=fold_id,
        prepare_only=True,
    )
    return result, loaded


def test_benchmark_prepares_only_the_selected_later_fold(tmp_path, monkeypatch):
    result, loaded = _run(tmp_path, monkeypatch, "fold-001-test")
    assert result["status"] == "PREPARED_ONLY"
    assert loaded and set(loaded) == {"fold-001-test"}


def test_benchmark_first_fold_is_unchanged(tmp_path, monkeypatch):
    result, loaded = _run(tmp_path, monkeypatch, "fold-000-test")
    assert result["status"] == "PREPARED_ONLY"
    assert loaded and set(loaded) == {"fold-000-test"}


def test_benchmark_rejects_a_fold_outside_the_canonical_plan(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="one canonical fold"):
        _run(tmp_path, monkeypatch, "fold-099-unknown")
