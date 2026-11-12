import subprocess

import pytest
from company_os.config import settings
from company_os.repositories import apply_files, discover, git, safe_repository


def test_i_import_is_read_only_and_excludes_secrets(company):
    root = settings().repository_root / "crypto"
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"scripts":{"test":"node --test"}}')
    (root / "index.js").write_text("export const network='testnet';")
    (root / ".env").write_text("PRIVATE_KEY=secret-wallet-value")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    report = discover(safe_repository("crypto"))
    assert report["read_only"]
    assert ".env" not in report["files"]
    assert "secret-wallet-value" not in str(report)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    assert report["baseline_tests"].startswith("Not executed")


@pytest.mark.parametrize(
    "path", ["../escape.py", "/absolute.py", "C:/escape.py", ".git/config", ".env", "private.key"]
)
def test_patch_traversal_and_secret_paths_rejected(tmp_path, path):
    with pytest.raises(PermissionError):
        apply_files(tmp_path, [{"path": path, "content": "safe source"}])


def test_patch_batch_is_validated_before_any_write(tmp_path):
    with pytest.raises(PermissionError):
        apply_files(
            tmp_path,
            [{"path": "valid.py", "content": "value=1"}, {"path": "../bad.py", "content": "value=2"}],
        )
    assert not (tmp_path / "valid.py").exists()


def test_valid_patch_creates_verifiable_source(tmp_path):
    apply_files(tmp_path, [{"path": "src/feature.py", "content": "def add(a,b):\n    return a+b\n"}])
    assert (tmp_path / "src/feature.py").read_text() == "def add(a,b):\n    return a+b\n"


@pytest.mark.parametrize("preference", ["global", "system"])
def test_git_sanitization_preserves_only_safe_global_line_ending_preference(
    tmp_path, monkeypatch, preference
):
    root = tmp_path / "line-endings"
    root.mkdir()
    for args in (
        ["init"],
        ["config", "user.email", "test@local.invalid"],
        ["config", "user.name", "Test Fixture"],
    ):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True, timeout=20)
    source = root / "README.md"
    source.write_bytes(b"portable\r\n")
    subprocess.run(
        ["git", "-c", "core.autocrlf=true", "-C", str(root), "add", "README.md"],
        capture_output=True,
        check=True,
        timeout=20,
    )
    subprocess.run(
        ["git", "-c", "core.autocrlf=true", "-C", str(root), "commit", "-m", "baseline"],
        capture_output=True,
        check=True,
        timeout=20,
    )
    monkeypatch.setattr(
        "company_os.repositories._global_autocrlf", lambda: "true" if preference == "global" else None
    )
    monkeypatch.setattr(
        "company_os.repositories._system_autocrlf", lambda: "true" if preference == "system" else None
    )
    assert git(root, "status", "--porcelain") == ""
    source.write_bytes(b"changed\r\n")
    assert git(root, "status", "--porcelain") == "M README.md"
