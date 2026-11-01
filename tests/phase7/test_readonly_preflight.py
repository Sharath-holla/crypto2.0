"""Read-only preflight must perform zero writes and reject input/output overlap (defect 14)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crypto_ai.phase7.runtime import RuntimePaths

OUTPUTS = ("artifact_root", "cache_root", "checkpoint_root", "model_root", "report_root", "log_root")


def _paths(tmp_path: Path, **overrides: Path) -> RuntimePaths:
    base = {
        "data_root": tmp_path / "data",
        "gold_root": tmp_path / "gold",
        "artifact_root": tmp_path / "out" / "artifacts",
        "cache_root": tmp_path / "out" / "cache",
        "checkpoint_root": tmp_path / "out" / "checkpoints",
        "model_root": tmp_path / "out" / "models",
        "report_root": tmp_path / "out" / "reports",
        "log_root": tmp_path / "out" / "logs",
    }
    base.update(overrides)
    return RuntimePaths(**base)


def _snapshot(root: Path) -> dict[str, tuple[bool, int, int]]:
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            path.stat().st_size if path.is_file() else 0,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    }


def test_read_only_validation_creates_nothing_when_outputs_are_absent(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.data_root.mkdir()
    paths.gold_root.mkdir()
    before = _snapshot(tmp_path)
    errors = paths.validate(create_outputs=False)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "out").exists()
    assert errors and all("is not writable" in item for item in errors)


def test_read_only_validation_writes_no_probe_files_when_outputs_exist(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for name in ("data_root", "gold_root", *OUTPUTS):
        getattr(paths, name).mkdir(parents=True, exist_ok=True)
    before = _snapshot(tmp_path)
    assert paths.validate(create_outputs=False) == []
    assert _snapshot(tmp_path) == before
    assert not list(tmp_path.rglob(".phase7-write-test-*"))


def test_creating_validation_still_probes_and_cleans_up(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.data_root.mkdir()
    paths.gold_root.mkdir()
    assert paths.validate(create_outputs=True) == []
    assert all(getattr(paths, name).is_dir() for name in OUTPUTS)
    assert not list(tmp_path.rglob(".phase7-write-test-*"))


@pytest.mark.parametrize("protected", ["data_root", "gold_root"])
@pytest.mark.parametrize("output", OUTPUTS)
@pytest.mark.parametrize("relation", ["inside", "contains", "equal"])
@pytest.mark.parametrize("create_outputs", [False, True])
def test_output_input_overlap_is_rejected_without_touching_the_filesystem(
    tmp_path: Path, protected: str, output: str, relation: str, create_outputs: bool
) -> None:
    protected_dir = tmp_path / "protected"
    protected_dir.mkdir()
    (protected_dir / "silver").mkdir()
    (protected_dir / "silver" / "evidence.parquet").write_bytes(b"immutable")
    target = {
        "inside": protected_dir / "silver" / "out",
        "contains": tmp_path,
        "equal": protected_dir,
    }[relation]
    other = "gold_root" if protected == "data_root" else "data_root"
    paths = _paths(tmp_path, **{protected: protected_dir, output: target, other: tmp_path / "other"})
    (tmp_path / "other").mkdir()
    before = _snapshot(tmp_path)
    errors = paths.validate(create_outputs=create_outputs)
    assert any("overlaps protected Gold/Silver input roots" in item for item in errors)
    assert _snapshot(tmp_path) == before
    assert (protected_dir / "silver" / "evidence.parquet").read_bytes() == b"immutable"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlinked_output_into_gold_is_rejected(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    (tmp_path / "data").mkdir()
    link = tmp_path / "innocent-looking-output"
    link.symlink_to(gold, target_is_directory=True)
    paths = _paths(tmp_path, model_root=link)
    errors = paths.validate(create_outputs=True)
    assert any("model_root overlaps protected" in item for item in errors)
    assert list(gold.iterdir()) == []
