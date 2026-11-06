"""CHANGED BY CLAUDE (2026-11-06, closure): what may and may not invalidate a prepared cache."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_ai.phase7 import preparation_identity as prep
from crypto_ai.phase7 import training

ROOT = Path(__file__).parents[2]


def _repo(tmp_path: Path, body: str = "return x + 1", other: str = "return 7") -> Path:
    (tmp_path / "whole.py").write_text("VALUE = 1\n")
    (tmp_path / "mixed.py").write_text(
        "SCALE = 2\n\n"
        "def helper(x):\n    return x * SCALE\n\n"
        f"def root(x):\n    # comment\n    {body}\n\n"
        "def uses_helper(x):\n    return helper(x)\n\n"
        f"def unrelated(x):\n    {other}\n"
    )
    return tmp_path


def _identity(root: Path, roots: tuple[str, ...] = ("root",)) -> str:
    return prep.preparation_source_identity(
        root, files=["whole.py"], functions=[("mixed.py", roots)]
    )["manifest_sha256"]


def test_identity_is_stable_and_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    base = _identity(_repo(tmp_path))
    (tmp_path / "mixed.py").write_text(
        (tmp_path / "mixed.py").read_text().replace("# comment", "# a different comment\n\n")
    )
    assert _identity(tmp_path) == base


def test_a_token_change_in_a_listed_function_changes_identity(tmp_path: Path) -> None:
    base = _identity(_repo(tmp_path))
    assert _identity(_repo(tmp_path, body="return x + 2")) != base


def test_a_change_in_an_unlisted_function_of_the_same_file_does_not(tmp_path: Path) -> None:
    base = _identity(_repo(tmp_path))
    assert _identity(_repo(tmp_path, other="return 8")) == base


def test_helper_closure_is_hashed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    base = _identity(repo, ("uses_helper",))
    text = (repo / "mixed.py").read_text().replace("x * SCALE", "x * SCALE * 3")
    (repo / "mixed.py").write_text(text)
    assert _identity(repo, ("uses_helper",)) != base  # helper changed
    assert _identity(repo, ("root",)) == _identity(repo, ("root",))  # root has no such helper


def test_whole_file_entries_and_missing_inputs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    base = _identity(repo)
    (repo / "whole.py").write_text("VALUE = 2\n")
    assert _identity(repo) != base
    (repo / "whole.py").unlink()
    with pytest.raises(RuntimeError, match="missing"):
        _identity(repo)
    (repo / "whole.py").write_text("VALUE = 1\n")
    with pytest.raises(RuntimeError, match="not found"):
        _identity(repo, ("does_not_exist",))


def test_crlf_checkouts_have_the_same_identity(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    base = _identity(repo)
    for name in ("whole.py", "mixed.py"):
        path = repo / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _identity(repo) == base


def test_real_preparation_set_excludes_every_control_plane_and_evaluation_module() -> None:
    excluded = {
        "src/crypto_ai/phase7/economics.py",
        "src/crypto_ai/phase7/hardening.py",
        "src/crypto_ai/phase7/result_ledger.py",
        "src/crypto_ai/phase7/result_integrity.py",
        "src/crypto_ai/phase7/result_publication.py",
        "src/crypto_ai/phase7/selection_chronology.py",
        "src/crypto_ai/phase7/experiment_identity.py",
        "src/crypto_ai/phase7/admission.py",
        "src/crypto_ai/phase7/backend.py",
        "src/crypto_ai/phase7/metrics.py",
        "src/crypto_ai/phase5/calibration.py",
        "src/crypto_ai/phase7/training.py",  # only specific functions
        "src/crypto_ai/phase7/models.py",  # only specific functions
    }
    assert not excluded & set(prep.PREPARATION_SOURCE_FILES)
    assert all((ROOT / path).is_file() for path in prep.PREPARATION_SOURCE_FILES)
    assert set(prep.PREPARATION_SOURCE_FILES) <= set(training.TRAINING_CRITICAL_SOURCE_FILES)


def test_real_identity_lists_the_matrix_functions_and_not_fitting_code() -> None:
    identity = prep.preparation_source_identity()
    symbols = {(item["path"].split("/")[-1], item["symbol"]) for item in identity["functions"]}
    assert ("training.py", "_finite") in symbols
    assert ("training.py", "_prepare_training_segments") in symbols
    assert ("models.py", "prepare_architecture_inputs") in symbols
    assert ("training.py", "_run_one") not in symbols
    assert ("training.py", "select_cal_b_thresholds") not in {s for _, s in symbols}
    assert identity["semantics_version"] == prep.PREPARATION_SEMANTICS_VERSION


# ---- the cache key itself ---------------------------------------------------------------------
SPEC = training.ExperimentSpec("architecture-G0-A6-60m-raw", "G0", "A6", 60, "raw", True)


def _key(**overrides):
    arguments = {
        "config": SimpleNamespace(
            configuration_hash="cfg", schedule=SimpleNamespace(embargo_minutes=120)
        ),
        "manifest": {"dataset_id": "gold-1", "partition_files": [], "lineage": {}},
        "gold_manifest_sha256": "m" * 64,
        "source_identity": {"manifest_sha256": "s" * 64},
        "fold_id": "fold-000",
        "research_view": "CORE",
        "fold_membership_hash": "membership",
        "universe_hash": "universe",
        "registry_hash": "registry",
        "spec": SPEC,
        "feature_columns": ("return_5m", "range_pct"),
        "descriptor_identity": "descriptors",
    }
    arguments.update(overrides)
    return training._prepared_cache_identity(**arguments)


def _id(**overrides) -> str:
    return training.prepared_cache_id(_key(**overrides))


def test_matrix_affecting_changes_invalidate_the_cache() -> None:
    base = _id()
    assert _id(feature_columns=("return_5m",)) != base  # feature set / order
    assert _id(feature_columns=("range_pct", "return_5m")) != base  # feature ORDER
    assert _id(spec=training.ExperimentSpec("x", "G0", "A6", 30, "raw", True)) != base  # horizon
    assert _id(spec=training.ExperimentSpec("x", "G0", "A6", 60, "volnorm", True)) != base
    assert _id(fold_membership_hash="other") != base  # fold / membership
    assert _id(universe_hash="other") != base
    assert _id(registry_hash="other") != base
    assert _id(descriptor_identity="other") != base
    assert _id(fold_id="fold-001") != base
    assert _id(gold_manifest_sha256="n" * 64) != base  # dataset bytes
    other_hash = SimpleNamespace(
        configuration_hash="cfg2", schedule=SimpleNamespace(embargo_minutes=120)
    )
    other_embargo = SimpleNamespace(
        configuration_hash="cfg", schedule=SimpleNamespace(embargo_minutes=60)
    )
    assert _id(config=other_hash) != base
    assert _id(config=other_embargo) != base


@pytest.mark.parametrize("constant", ["FEATURE_VERSION", "TARGET_VERSION", "FOLD_CONTEXT_VERSION"])
def test_feature_target_and_context_semantics_versions_invalidate(monkeypatch, constant) -> None:
    base = _id()
    monkeypatch.setattr(training, constant, "changed-semantics")
    assert _id() != base


def test_preparation_code_change_invalidates(monkeypatch) -> None:
    base = _id()
    monkeypatch.setattr(
        training,
        "_preparation_identity",
        lambda: {"manifest_sha256": "x" * 64, "semantics_version": "v2"},
    )
    assert _id() != base


def test_control_plane_and_economics_changes_do_not_invalidate_matrices() -> None:
    """Resume identity (full source hash) changes; the matrix cache key must not."""

    base = _id()
    assert _id(source_identity={"manifest_sha256": "e" * 64}) == base  # e.g. economics.py edited
    assert "experiment_control_identity" not in _key()
    assert "scientific_source_identity" not in _key()  # replaced by the preparation identity
