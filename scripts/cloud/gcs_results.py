#!/usr/bin/env python3
"""Persist exported run artifacts to the PRIVATE GCS bucket (the GitHub repository is public).

ADDED BY CLAUDE (2026-11-13). Works on a directory produced by
``python -m crypto_ai.phase7.run_persistence export`` (it must contain PERSISTED_MANIFEST.json).

  push  --source DIR --bucket B --prefix phase7-results/<run> [--execute]
        uploads every file in the manifest, then the manifest itself, CREATE-ONLY
        (``ifGenerationMatch=0``: an existing object is never overwritten), verifying the MD5
        GCS reports for each object against the local file.
  pull  --bucket B --prefix phase7-results/<run> --destination DIR [--execute]
        downloads the manifest, then each listed file by exact name, verifying SHA-256.

Dry run unless ``--execute``. Authentication is injected by the session's network proxy for
storage.googleapis.com (owner-scoped short-lived token); this script never handles a credential.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

API = "https://storage.googleapis.com"


def _object(bucket: str, name: str) -> str:
    quoted = urllib.parse.quote(name, safe="")
    return f"{API}/storage/v1/b/{urllib.parse.quote(bucket, safe='')}/o/{quoted}"


def _upload_url(bucket: str, name: str) -> str:
    return (
        f"{API}/upload/storage/v1/b/{urllib.parse.quote(bucket, safe='')}/o"
        f"?uploadType=media&ifGenerationMatch=0&name={urllib.parse.quote(name, safe='')}"
    )


def _client(client: Any) -> Any:
    if client is not None:
        return client
    import httpx

    return httpx.Client(timeout=httpx.Timeout(60.0, read=300.0))


def push(
    source: Path, *, bucket: str, prefix: str, execute: bool, client: Any = None
) -> dict[str, Any]:
    manifest_path = source / "PERSISTED_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [record["path"] for record in manifest["files"]] + ["PERSISTED_MANIFEST.json"]
    total = sum((source / name).stat().st_size for name in names)
    if not execute:
        return {
            "dry_run": True,
            "objects": len(names),
            "bytes": total,
            "destination": f"gs://{bucket}/{prefix.strip('/')}/",
        }
    http = _client(client)
    uploaded = already = 0
    for name in names:
        local = source / name
        if name != "PERSISTED_MANIFEST.json":
            expected = next(r["sha256"] for r in manifest["files"] if r["path"] == name)
            if hashlib.sha256(local.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"local artifact changed since export: {name}")
        body = local.read_bytes()
        object_name = f"{prefix.strip('/')}/{name}"
        response = http.post(
            _upload_url(bucket, object_name),
            content=body,
            headers={"Content-Type": "application/octet-stream"},
        )
        if response.status_code == 412:
            already += 1  # exists: never overwritten; verify it is the same bytes below
            response = http.get(_object(bucket, object_name))
        if response.status_code != 200:
            raise RuntimeError(f"GCS {response.status_code} for {object_name}")
        remote_md5 = response.json().get("md5Hash")
        local_md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
        if remote_md5 != local_md5:
            raise RuntimeError(f"REMOTE_OBJECT_DIFFERS: {object_name}")
        uploaded += 1
    return {
        "dry_run": False,
        "verified_objects": uploaded,
        "pre_existing_identical": already,
        "destination": f"gs://{bucket}/{prefix.strip('/')}/",
    }


def pull(
    *, bucket: str, prefix: str, destination: Path, execute: bool, client: Any = None
) -> dict[str, Any]:
    http = _client(client)
    base = prefix.strip("/")
    response = http.get(_object(bucket, f"{base}/PERSISTED_MANIFEST.json") + "?alt=media")
    if response.status_code != 200:
        raise RuntimeError(f"GCS {response.status_code} for the persisted manifest")
    manifest = json.loads(response.content)
    if not execute:
        return {"dry_run": True, "objects": len(manifest["files"]) + 1}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "PERSISTED_MANIFEST.json").write_bytes(response.content)
    for record in manifest["files"]:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe path in manifest: {record['path']}")
        data = http.get(_object(bucket, f"{base}/{record['path']}") + "?alt=media")
        if data.status_code != 200 or hashlib.sha256(data.content).hexdigest() != record["sha256"]:
            raise RuntimeError(f"PULLED_ARTIFACT_INVALID: {record['path']}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.content)
    return {
        "dry_run": False,
        "objects": len(manifest["files"]) + 1,
        "destination": str(destination),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pusher = sub.add_parser("push")
    pusher.add_argument("--source", type=Path, required=True)
    puller = sub.add_parser("pull")
    puller.add_argument("--destination", type=Path, required=True)
    for command in (pusher, puller):
        command.add_argument("--bucket", required=True)
        command.add_argument("--prefix", required=True)
        command.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "push":
        result = push(args.source, bucket=args.bucket, prefix=args.prefix, execute=args.execute)
    else:
        result = pull(
            bucket=args.bucket,
            prefix=args.prefix,
            destination=args.destination,
            execute=args.execute,
        )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
