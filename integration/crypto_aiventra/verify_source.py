"""Read-only vendored provenance and staged-secret checks; never print secret values."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*arguments):
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments], check=True, capture_output=True
    ).stdout


def secret_values(values):
    # This schema field contains a PUBLIC environment-variable name, not its token.
    # Do not exempt its value if it also appears as an actual credential elsewhere.
    return {
        value.encode()
        for name, value in values.items()
        if name != "GITHUB_PUBLICATION_TOKEN_ENV"
        and any(word in name.upper() for word in ("PASSWORD", "TOKEN", "SECRET", "API_KEY"))
        and len(value) >= 12
        and not value.startswith("replace-with-")
    }


def scan_staged():
    spec = importlib.util.spec_from_file_location(
        "upstream_secret_scan", ROOT / "aiventra/scripts/secret_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Read configured secrets in memory only, including both private integration profiles.
    values = dict(os.environ)
    private = ROOT / "aiventra/.env"
    if private.is_file():
        for line in private.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                name, value = line.split("=", 1)
                values.setdefault(name, value.strip().strip("\"'"))
    secrets = secret_values(values)
    profile = ROOT / "aiventra/.env.crypto-integration"
    if profile.is_file():
        secrets.add(profile.read_text(encoding="utf-8").strip().encode())
    findings = []
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
    for raw in filter(None, paths):
        path = raw.decode()
        normalized = path.removeprefix("aiventra/") if path.startswith("aiventra/") else path
        findings.extend(
            {"path": path, "kind": kind}
            for kind in module.findings(normalized, git("show", ":" + path), secrets)
        )
    return {
        "checked_staged_blobs": len(list(filter(None, paths))),
        "findings": findings,
        "status": "PASS" if not findings else "BLOCKED",
        "secret_values_printed": False,
    }


def provenance(archive):
    modifications, missing, original_hashes = [], [], {}
    with tarfile.open(archive, "r") as source:
        for member in source:
            if member.isdir():
                continue
            if (
                not member.isfile()
                or Path(member.name).is_absolute()
                or ".." in Path(member.name).parts
            ):
                raise ValueError("Only safe tracked regular-file archives are supported")
            original = source.extractfile(member).read()
            expected = hashlib.sha256(original).hexdigest()
            original_hashes[member.name] = expected
            imported = ROOT / "aiventra" / member.name
            if not imported.is_file():
                missing.append(member.name)
            elif hashlib.sha256(imported.read_bytes()).hexdigest() != expected:
                modifications.append(member.name)
    return {
        "upstream_commit": "1d8b479d48a4f208529d71f0cd355853a9288776",
        "archive_sha256": hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
        "tracked_files": len(original_hashes),
        "missing_tracked_files": missing,
        "local_modifications": modifications,
        "original_file_sha256": original_hashes,
        "nested_git": (ROOT / "aiventra/.git").exists(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path)
    args = parser.parse_args()
    result = provenance(args.source_archive) if args.source_archive else scan_staged()
    print(json.dumps(result, indent=2, sort_keys=True))
    return (
        1
        if result.get("status") == "BLOCKED"
        or result.get("missing_tracked_files")
        or result.get("nested_git")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
