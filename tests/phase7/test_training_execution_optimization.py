from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7 import training
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.models import _append_symbol_identity, _matrix
from crypto_ai.phase7.training import _finite, _restore_completed_g0, phase7_experiment_specs


def test_arrow_finite_filter_preserves_complete_case_semantics() -> None:
    table = pa.table(
        {
            "row": [0, 1, 2, 3, 4, 5],
            "f1": pa.chunked_array([[1.0, None, np.nan], [2.0, np.inf, 3.0]]),
            "f2": [1.0, 2.0, 3.0, -np.inf, 5.0, 6.0],
            "target": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        }
    )
    filtered = _finite(table, ("f1", "f2"), "target")
    assert filtered.column("row").to_pylist() == [0, 5]


def test_canonical_bundle_and_estimator_count_is_unchanged() -> None:
    config = load_phase7_config(Path("configs/phase7/research_v1.toml"))
    specs = phase7_experiment_specs(config)
    by_architecture = Counter(spec.architecture for spec in specs)
    assert by_architecture == {"G0": 34, "C0": 8, "P0": 8, "H0": 8}
    assert 16 * 2 * len(specs) == 1_856
    estimators_per_fold_view_at_30 = (
        by_architecture["G0"]
        + by_architecture["C0"] * config.models.cluster_count
        + by_architecture["P0"] * 30
        + by_architecture["H0"]
    )
    assert estimators_per_fold_view_at_30 == 314
    assert 16 * 2 * estimators_per_fold_view_at_30 == 10_048


def test_resume_loads_validated_completed_g0_for_h0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = {"configuration_hash": "config-a"}
    report_path = tmp_path / "report.json"
    model_path = tmp_path / "model.joblib"
    report_path.write_text(json.dumps({"checkpoint_identity": identity}), encoding="utf-8")
    model_path.write_bytes(b"model")
    model = SimpleNamespace(architecture="G0")
    validations: list[tuple[object, object]] = []
    monkeypatch.setattr(training, "load_model", lambda _: model)
    monkeypatch.setattr(
        training,
        "_validate_complete_orphan_report",
        lambda report, loaded: validations.append((report, loaded)),
    )
    loaded_report, loaded_model = _restore_completed_g0(
        report_path=report_path,
        model_path=model_path,
        expected_checkpoint_identity=identity,
    )
    assert loaded_model is model
    assert loaded_report["checkpoint_identity"] == identity
    assert validations == [(loaded_report, model)]


def test_resume_rejects_wrong_or_missing_g0_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "report.json"
    model_path = tmp_path / "model.joblib"
    report_path.write_text(
        json.dumps({"checkpoint_identity": {"configuration_hash": "wrong"}}),
        encoding="utf-8",
    )
    model_path.write_bytes(b"model")
    monkeypatch.setattr(training, "load_model", lambda _: SimpleNamespace(architecture="G0"))
    monkeypatch.setattr(training, "_validate_complete_orphan_report", lambda *_: None)
    with pytest.raises(ValueError, match="identity mismatch"):
        _restore_completed_g0(
            report_path=report_path,
            model_path=model_path,
            expected_checkpoint_identity={"configuration_hash": "expected"},
        )
    model_path.unlink()
    with pytest.raises(FileNotFoundError, match="missing"):
        _restore_completed_g0(
            report_path=report_path,
            model_path=model_path,
            expected_checkpoint_identity={"configuration_hash": "wrong"},
        )


def test_resume_propagates_corrupt_g0_load_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "report.json"
    model_path = tmp_path / "model.joblib"
    report_path.write_text(json.dumps({"checkpoint_identity": {}}), encoding="utf-8")
    model_path.write_bytes(b"corrupt")

    def fail(_: Path) -> object:
        raise ValueError("corrupt model")

    monkeypatch.setattr(training, "load_model", fail)
    with pytest.raises(ValueError, match="corrupt model"):
        _restore_completed_g0(
            report_path=report_path,
            model_path=model_path,
            expected_checkpoint_identity={},
        )


@pytest.mark.parametrize(
    "key", ["gold_dataset_id", "fold_id", "training_source_identity", "model_backend_semantics"]
)
def test_resume_rejects_every_scientific_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    expected = {
        "gold_dataset_id": "gold",
        "fold_id": "fold-1",
        "training_source_identity": {"manifest_sha256": "source"},
        "model_backend_semantics": "cpu",
    }
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"checkpoint_identity": {**expected, key: "changed"}}), encoding="utf-8"
    )
    model = tmp_path / "model.joblib"
    model.write_bytes(b"synthetic-model")
    monkeypatch.setattr(training, "load_model", lambda _: SimpleNamespace(architecture="G0"))
    monkeypatch.setattr(training, "_validate_complete_orphan_report", lambda *_: None)
    with pytest.raises(ValueError, match="identity mismatch"):
        _restore_completed_g0(
            report_path=report, model_path=model, expected_checkpoint_identity=expected
        )


def test_preallocated_matrices_and_symbol_encoding_are_exactly_equivalent() -> None:
    table = pa.table({"b": [1.25, 2.5, -3.75], "a": [4.0, -5.0, 6.0]})
    expected = np.column_stack([table.column(name).to_numpy() for name in ("a", "b")])
    actual = _matrix(table, ("a", "b"))
    assert actual.dtype == np.float64
    assert np.array_equal(actual, expected)
    symbols = np.array(["HNTUSDT", "BTCUSDT", "UNKNOWN"], dtype=object)
    encoded = np.array([[0, 1], [1, 0], [0, 0]], dtype=np.float64)
    assert np.array_equal(
        _append_symbol_identity(actual, symbols, ("BTCUSDT", "HNTUSDT")),
        np.column_stack((expected, encoded)),
    )
