"""Adversarial synthetic checks; no production data, network or real training."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import models, preflight, runtime
from crypto_ai.phase7.config import ModelConfig
from crypto_ai.phase7.prepared_cache import (
    PreparedCacheMissError,
    PreparedCacheReadOnlyError,
    PreparedDataCache,
)
from crypto_ai.phase7.training_metrics import training_metric_scope
from tests.phase7.test_prepared_cache import _fixture

CONFIG = Path("configs/phase7/research_core20_primary_v1.toml")


def _paths(tmp_path):
    return runtime.RuntimePaths(
        **{name: tmp_path / name for name in runtime.RuntimePaths.__dataclass_fields__}
    )


def test_no_create_validation_never_opens_a_write_probe(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    for name in paths.__dataclass_fields__:
        getattr(paths, name).mkdir()
    monkeypatch.setattr(runtime.tempfile, "NamedTemporaryFile", lambda **_k: pytest.fail("write"))
    assert paths.validate(create_outputs=False) == []


@pytest.mark.parametrize("floor", ["nan", "-1", "invalid", "0"])
def test_invalid_preflight_contract_returns_fail_without_smoke_or_gold(
    tmp_path, monkeypatch, floor
):
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", floor)
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    monkeypatch.setattr(runtime.RuntimePaths, "resolve", lambda _c: _paths(tmp_path))
    monkeypatch.setattr(runtime.RuntimePaths, "validate", lambda *_a, **_k: [])
    monkeypatch.setattr(preflight, "validate_gold_manifest", lambda *_a: pytest.fail("Gold read"))
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_a: pytest.fail("fit"))
    report = preflight.build_preflight_report(CONFIG, create_outputs=False)
    assert report["status"] == "FAIL" and report["training_readiness"] == "NOT_READY"
    assert any("RAM" in error for error in report["blocking_errors"])
    assert report["backend_smoke"] is None


def test_preflight_rejects_unsafe_paths_before_gold_inspection(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths = replace(paths, model_root=paths.gold_root / "models")
    monkeypatch.setattr(runtime.RuntimePaths, "resolve", lambda _c: paths)
    monkeypatch.setattr(preflight, "validate_gold_manifest", lambda *_a: pytest.fail("Gold read"))
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_a: pytest.fail("fit"))
    report = preflight.build_preflight_report(CONFIG, create_outputs=False)
    assert report["status"] == "FAIL" and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "name",
    [
        "train_x",
        "train_y",
        "validation_x",
        "validation_y",
        "train_symbols",
        "validation_symbols",
        "calibration_symbols",
    ],
)
def test_cache_refuses_self_consistent_hashes_with_misaligned_matrix_values(tmp_path, name):
    plan, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "auto")
    path = cache.write(identity, fold, prepared)
    array_path = path / f"{name}.npy"
    values = np.load(array_path, allow_pickle=False)
    if values.dtype.kind in "US":
        values[0] = "WRONG"
    else:
        values.flat[0] += 1.0
    np.save(array_path, values, allow_pickle=False)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][array_path.name]["sha256"] = file_sha256(array_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (path / "CACHE_COMPLETE").write_text(file_sha256(manifest_path), encoding="ascii")
    with pytest.raises(PreparedCacheReadOnlyError, match="alignment"):
        PreparedDataCache(tmp_path, "read_only").load(identity, plan)
    assert path.is_dir()  # Read-only rejection preserves the evidence.
    with pytest.raises(PreparedCacheMissError, match="quarantined"):
        cache.load(identity, plan)
    assert not path.exists() and list(tmp_path.glob(".*.invalid.*"))


def test_invalid_cache_rebuild_preserves_previously_valid_entry(tmp_path):
    plan, fold, prepared, identity = _fixture()
    path = PreparedDataCache(tmp_path, "auto").write(identity, fold, prepared)
    before = (path / "manifest.json").read_bytes()
    altered_y = prepared.model_inputs.train_y.copy() + 1.0
    prepared = replace(prepared, model_inputs=replace(prepared.model_inputs, train_y=altered_y))
    with pytest.raises(ValueError, match="alignment"):
        PreparedDataCache(tmp_path, "rebuild").write(identity, fold, prepared)
    assert (path / "manifest.json").read_bytes() == before
    assert PreparedDataCache(tmp_path, "read_only").load(identity, plan).cache_id == path.name


def test_rejected_cache_drops_traceback_references_before_closing_mmaps(tmp_path):
    _, fold, prepared, identity = _fixture()
    prepared = replace(
        prepared,
        model_inputs=replace(
            prepared.model_inputs, train_y=prepared.model_inputs.train_y.copy() + 1.0
        ),
    )
    with pytest.raises(ValueError, match="alignment") as caught:
        PreparedDataCache(tmp_path, "auto").write(identity, fold, prepared)
    trace = caught.value.__traceback__
    cleared_frames = 0
    while trace is not None:
        if trace.tb_frame.f_code.co_name in {
            "_load_validated_content",
            "_validate_matrix_alignment",
        }:
            assert trace.tb_frame.f_locals == {}
            cleared_frames += 1
        trace = trace.tb_next
    assert cleared_frames == 2
    assert not list(tmp_path.glob(".*.tmp.*"))


@pytest.mark.parametrize("payload", [[], None])
def test_gold_validation_evidence_rejects_wrong_json_container(tmp_path, payload):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible"):
        preflight._validated_gold_report(path, dataset_id="fixture", manifest_sha256="sha")


def test_fit_failure_emits_sanitized_failure_event_and_keeps_original_exception(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    failure = RuntimeError("fixture-sensitive-detail")

    def failed_fit(*_a, **_k):
        raise failure

    monkeypatch.setattr(models, "fit_with_device_evidence", failed_fit)
    with (
        training_metric_scope(tmp_path, spec_id="synthetic"),
        pytest.raises(RuntimeError) as caught,
    ):
        models._fit(
            np.ones((2, 1)),
            np.ones(2),
            np.ones((2, 1)),
            np.ones(2),
            config=ModelConfig(),
            model_threads=1,
            sample_weight=None,
        )
    assert caught.value is failure
    lines = next(tmp_path.glob("*.jsonl")).read_text()
    assert "fixture-sensitive-detail" not in lines
    event = json.loads(lines.splitlines()[-1])
    assert event["event"] == "FIT_FAILED" and event["error_type"] == "RuntimeError"


def test_filesystem_capacity_failure_is_reported_without_backend_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.RuntimePaths, "resolve", lambda _c: _paths(tmp_path))
    monkeypatch.setattr(runtime.RuntimePaths, "validate", lambda *_a, **_k: [])

    def unavailable(*_a):
        raise OSError("synthetic volume unavailable")

    monkeypatch.setattr(preflight, "system_snapshot", unavailable)
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_a: pytest.fail("fit"))
    report = preflight.build_preflight_report(CONFIG, create_outputs=False)
    assert report["status"] == "FAIL"
    assert all(item["disk_free_bytes"] is None for item in report["filesystem_capacity"].values())
    assert any("filesystem capacity" in error for error in report["blocking_errors"])
