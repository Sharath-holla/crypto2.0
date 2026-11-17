"""Tiny artificial CPU fixtures; no market dataset, cloud or order access."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from crypto_ai.phase7 import preemption as p
from crypto_ai.phase7.config import ModelConfig
from crypto_ai.phase7.models import _fit
from crypto_ai.phase7.training_metrics import training_metric_scope


@pytest.fixture
def small():
    rng = np.random.default_rng(33)
    x = rng.normal(size=(220, 8)).astype(np.float64)
    y = (x[:, 0] * 0.01 + x[:, 3] * 0.005 + rng.normal(0, 0.004, 220)).astype(np.float64)
    return x[:140], y[:140], x[140:], y[140:], np.linspace(0.5, 1.5, 140)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = {
        "schema": "phase7_preemption_config_v1",
        "logical_run_id": "fixture-logical",
        "execution_session_id": "session-one",
        "pod_id": "fixture-one",
        "interval_rounds": 10,
        "local_root": str(tmp_path / "local"),
        "persistent_root": str(tmp_path / "persistent"),
        "request_path": str(tmp_path / "control/request.json"),
        "receipt_path": str(tmp_path / "control/receipt.json"),
        "expected_scientific_ids": {"fixture": "not-market-data"},
        "expected_cache_id": "fixture-cache",
    }
    path = tmp_path / "config.json"
    p.atomic_json(path, config)
    monkeypatch.setenv(p.CONFIG_ENV, str(path))
    monkeypatch.setattr("crypto_ai.phase7.models.resource_admission", lambda *a, **k: None)
    binding = {
        "spec_id": "architecture-G0-A6-60m-raw",
        "maximum_rounds": 50,
        "early_stopping_rounds": 10,
        "scientific_ids": config["expected_scientific_ids"],
        "prepared_cache_id": config["expected_cache_id"],
        "feature_columns": [f"Column_{i}" for i in range(8)],
        "target_column": "fixture_y",
    }
    return config, binding


def fit(small, setup, directory):
    _, binding = setup
    x, y, vx, vy, weights = small
    with p.preemption_scope(binding=binding), training_metric_scope(directory, fixture=True):
        return _fit(
            x,
            y,
            vx,
            vy,
            config=ModelConfig(n_estimators=50, min_child_samples=5, early_stopping_rounds=10),
            model_threads=1,
            sample_weight=weights,
        )


def test_periodic_serialization_does_not_change_normal_model(small, setup, tmp_path, monkeypatch):
    enabled = fit(small, setup, tmp_path / "with-checkpoints")
    monkeypatch.delenv(p.CONFIG_ENV)
    plain = fit(small, setup, tmp_path / "without-checkpoints")
    assert np.array_equal(enabled.predict(small[2]), plain.predict(small[2]))
    assert enabled.booster_.model_to_string(num_iteration=-1) == plain.booster_.model_to_string(
        num_iteration=-1
    )
    config, _ = setup
    published = list(Path(config["persistent_root"]).glob("*/iter-*/CHECKPOINT_COMPLETE"))
    assert 1 <= len(published) <= 3
    for marker in published:
        verified = p.verify_partial(marker.parent)
        assert verified["status"] == "TRAINING_PARTIAL_CHECKPOINT"
        assert verified["resume_capability"] == p.CAPABILITY
    assert not list(tmp_path.rglob("*.joblib"))


def test_request_preempts_before_returning_a_completed_model(small, setup, tmp_path):
    config, _ = setup
    p.atomic_json(
        Path(config["request_path"]),
        {"request_id": "low-wallet-123", "reason": "LOW_WALLET_PREEMPTION"},
    )
    with pytest.raises(p.TrainingPreempted) as info:
        fit(small, setup, tmp_path / "metrics")
    receipt = info.value.receipt
    saved = p.verify_partial(Path(receipt["checkpoint_path"]))
    assert saved["completed_rounds"] == 1
    assert saved["remaining_rounds_if_continuation_were_qualified"] == 49
    assert saved["request_id"] == "low-wallet-123"
    assert not list(tmp_path.rglob("report.json")) and not list(tmp_path.rglob("model.joblib"))
    events = [
        json.loads(line)["event"]
        for file in (tmp_path / "metrics").glob("fit-*.jsonl")
        for line in file.read_text().splitlines()
    ]
    assert "PREEMPTED_RESTART_REQUIRED" in events and "FIT_FINISHED" not in events
    persisted = Path(receipt["telemetry"]["path"]).read_text().splitlines()
    assert len(persisted) == len(set(persisted))
    assert [json.loads(line)["event"] for line in persisted] == events


def test_corrupt_latest_falls_back_to_verified_previous(small, setup, tmp_path):
    fit(small, setup, tmp_path / "metrics")
    root = Path(setup[0]["persistent_root"])
    latest = p.latest_verified(root)
    path = Path(latest["checkpoint_path"])
    with (path / "model.txt").open("a") as stream:
        stream.write("corrupt")
    fallback = p.latest_verified(root)
    assert fallback["checkpoint_sha256"] != latest["checkpoint_sha256"]
    assert len(list(root.glob("*/iter-*/checkpoint.json"))) <= 3
    assert list((root / "retention-audit").glob("*.json"))


def test_identity_change_refuses_checkpoint(small, setup, tmp_path):
    fit(small, setup, tmp_path / "metrics")
    latest = p.latest_verified(Path(setup[0]["persistent_root"]))
    with pytest.raises(ValueError, match="RESUME_IDENTITY_MISMATCH"):
        p.verify_partial(
            Path(latest["checkpoint_path"]), {**latest["binding"], "prepared_cache_id": "wrong"}
        )


def test_network_copy_failure_is_not_completion(small, setup, tmp_path, monkeypatch):
    monkeypatch.setattr(
        p, "copy_verified_tree", lambda *a, **k: (_ for _ in ()).throw(OSError("network"))
    )
    with pytest.raises(OSError, match="network"):
        fit(small, setup, tmp_path / "metrics")
    assert not Path(setup[0]["receipt_path"]).exists()
    assert not list(Path(setup[0]["persistent_root"]).glob("*/iter-*/CHECKPOINT_COMPLETE"))


def test_signal_handler_only_sets_request_flag(setup, tmp_path):
    callback = p.PartialCheckpointCallback(setup[0], setup[1], None)
    import signal

    callback.request_signal(signal.SIGTERM, None)
    assert callback.signal_requested == signal.SIGTERM
    assert not Path(setup[0]["receipt_path"]).exists()


def test_unqualified_resume_is_unconditionally_disabled():
    with pytest.raises(ValueError, match="MID_FIT_RESUME_NOT_QUALIFIED"):
        p.refuse_mid_fit_resume()


def test_partial_keeps_all_trees_after_best_iteration(small, setup, tmp_path):
    x, y, vx, vy, weights = small
    model = fit((x, y, vx, -vy, weights), setup, tmp_path / "metrics")
    saved = p.latest_verified(Path(setup[0]["persistent_root"]))
    assert saved["tree_count"] == saved["completed_rounds"]
    assert saved["tree_count"] > model.booster_.num_trees()
    assert saved["best_iteration"] < saved["completed_rounds"]


def test_authorized_new_session_restarts_round_zero_exactly(small, setup, tmp_path, monkeypatch):
    config, binding = setup
    p.atomic_json(Path(config["request_path"]), {"request_id": "pause", "reason": "OWNER_STOP"})
    with pytest.raises(p.TrainingPreempted) as paused:
        fit(small, setup, tmp_path / "session-one-metrics")
    config.update(
        execution_session_id="session-two",
        pod_id="fixture-two",
        restart_checkpoint=paused.value.receipt["checkpoint_path"],
        request_path=str(tmp_path / "new-session/request.json"),
    )
    p.atomic_json(Path(tmp_path / "config.json"), config, immutable=False)
    restarted = fit(small, (config, binding), tmp_path / "session-two-metrics")
    monkeypatch.delenv(p.CONFIG_ENV)
    uninterrupted = fit(small, setup, tmp_path / "reference")
    assert np.array_equal(restarted.predict(small[2]), uninterrupted.predict(small[2]))
    assert restarted.booster_.model_to_string(
        num_iteration=-1
    ) == uninterrupted.booster_.model_to_string(num_iteration=-1)
    events = [
        json.loads(line)
        for file in (tmp_path / "session-two-metrics").glob("fit-*.jsonl")
        for line in file.read_text().splitlines()
    ]
    restart = next(
        event for event in events if event["event"] == "MODEL_RESTARTED_AFTER_PREEMPTION"
    )
    assert restart["restart_round"] == 0 and restart["previous_checkpoint_iteration"] == 1
    assert not any(event["event"] == "TRAINING_RESUMED" for event in events)


def test_partial_cache_copy_missing_corrupt_and_capacity(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "matrix.npy").write_bytes(b"artificial-fixture-not-market-data")
    p.atomic_json(
        source / "manifest.json",
        {
            "cache_id": "fixture",
            "files": {"matrix.npy": {"sha256": p.file_sha256(source / "matrix.npy")}},
        },
    )
    with pytest.raises(ValueError, match="CACHE_COPY_INCOMPLETE"):
        p.copy_qualified_cache(source, tmp_path / "destination", "fixture")
    (source / "CACHE_COMPLETE").write_text(p.file_sha256(source / "manifest.json"))
    with pytest.raises(ValueError, match="CACHE_COPY_IDENTITY_MISMATCH"):
        p.copy_qualified_cache(source, tmp_path / "destination", "wrong")
    with pytest.raises(OSError, match="CAPACITY"):
        p.copy_qualified_cache(source, tmp_path / "destination", "fixture", available_bytes=10)
    copied = p.copy_qualified_cache(source, tmp_path / "destination", "fixture")
    assert copied["status"] == "PASS"
    (source / "matrix.npy").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        p.copy_qualified_cache(source, tmp_path / "bad-destination", "fixture")
    assert not (tmp_path / "bad-destination").exists()


def test_training_wrapper_partial_never_marks_experiment_complete(tmp_path, monkeypatch):
    from crypto_ai.phase7 import training
    from crypto_ai.phase7.artifacts import CheckpointStore
    from crypto_ai.phase7.config import load_phase7_config

    config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    monkeypatch.setattr("crypto_ai.phase7.admission.admit_official_training", lambda **kw: {})
    monkeypatch.setattr(
        training,
        "_run_phase7_training_owned",
        lambda *a, **kw: (_ for _ in ()).throw(p.TrainingPreempted({"persistent": True})),
    )
    root = tmp_path / "isolated-fixture"
    result = training.run_phase7_training(
        config,
        run_root=root,
        checkpoint_store=CheckpointStore(root / "checkpoints", root.name),
        scope=training.PHASE7A_SCOPE,
    )
    assert result["status"] == "PREEMPTED_RESTART_REQUIRED" and result["models_completed"] == 0
    assert not list(root.rglob("model.joblib")) and not list(root.rglob("report.json"))
    assert not (root / "canonical-results").exists()
