from pathlib import Path

from crypto_ai.audit.artifacts import ALGORITHM, fingerprint_artifacts


def test_artifact_fingerprint_is_order_independent_and_detects_mutation(tmp_path: Path) -> None:
    (tmp_path / "data" / "z").mkdir(parents=True)
    (tmp_path / "local_artifacts").mkdir()
    (tmp_path / "data" / "z" / "b.bin").write_bytes(b"b")
    (tmp_path / "data" / "a.bin").write_bytes(b"a")
    (tmp_path / "local_artifacts" / "m.bin").write_bytes(b"m")
    first = fingerprint_artifacts(tmp_path, (Path("local_artifacts"), Path("data")))
    second = fingerprint_artifacts(tmp_path, (Path("data"), Path("local_artifacts")))
    assert first == second
    assert first.algorithm == ALGORITHM
    assert first.file_count == 3
    assert first.byte_count == 3
    (tmp_path / "data" / "a.bin").write_bytes(b"changed")
    changed = fingerprint_artifacts(tmp_path, (Path("data"), Path("local_artifacts")))
    assert changed.sha256 != first.sha256
