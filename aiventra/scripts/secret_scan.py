"""Scan staged Git blobs and optionally history; report locations, never secret values."""

import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMATS = {
    "provider/GitHub token": re.compile(
        rb"\b(?:sk-[A-Za-z0-9_-]{24,}|gsk_[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9_]{24,}|github_pat_[A-Za-z0-9_]{24,})\b"
    ),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "JWT": re.compile(rb"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
}


def git(*args):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True)
    return result.stdout


def configured_secrets():
    values = dict(os.environ)
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                name, value = line.split("=", 1)
                values.setdefault(name, value.strip().strip("\"'"))
    return {
        value.encode()
        for name, value in values.items()
        if any(word in name.upper() for word in ("PASSWORD", "TOKEN", "SECRET", "API_KEY"))
        and len(value) >= 12
        and not value.startswith("replace-with-")
    }


def findings(path, content, secrets):
    result = set()
    name = Path(path).name
    if (name.startswith(".env") and name != ".env.example") or name in {
        "id_rsa",
        "id_ed25519",
        "credentials.json",
    }:
        result.add("private configuration filename")
    for value in secrets:
        if value in content:
            result.add("configured secret")
    for label, pattern in FORMATS.items():
        for match in pattern.finditer(content):
            if match.group(0).startswith((b"sk-test-", b"ghp_test_")):
                continue
            if path == "tests/test_security.py":
                if match.group(0) == b"sk-" + b"abcdefghijklmnopqrstuvwxyz":
                    continue
                if (
                    label == "private key"
                    and b"-----BEGIN" + b" PRIVATE KEY-----\\nSECRET\\n-----END PRIVATE KEY-----" in content
                ):
                    continue
            result.add(label)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    secrets = configured_secrets()
    errors = []
    checked = 0
    for raw in git("ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        path = raw.decode()
        content = git("show", ":" + path)
        checked += 1
        errors.extend((path, label) for label in findings(path, content, secrets))
    if args.history:
        # Scan publishable branch/remote history. App-owned local checkpoint refs are not pushed.
        refs = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").decode().splitlines()
        history = git("rev-list", "--objects", *refs).splitlines() if refs else []
        for line in history:
            parts = line.decode().split(" ", 1)
            if len(parts) != 2 or git("cat-file", "-t", parts[0]).strip() != b"blob":
                continue
            checked += 1
            errors.extend(
                ("history:" + parts[1], label)
                for label in findings(parts[1], git("cat-file", "blob", parts[0]), secrets)
            )
    for path, label in sorted(set(errors)):
        print(f"BLOCKED {path}: {label}")
    print(f"Secret scan: {checked} blobs checked; {len(set(errors))} findings. Values are never printed.")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
