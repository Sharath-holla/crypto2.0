#!/usr/bin/env python3
"""Push exported run artifacts from the cloud VM back to the owner's Mac through the tunnel.

ADDED BY CLAUDE (2026-11-14). Target: ``mac_transfer_server.py --receive-dir ...``. Authentication
is injected by the session proxy for the tunnel host (secure credential card); this script never
handles a token. Uploads are chunked (default 32 MiB, below Cloudflare's 100 MB request limit),
resume at the server-reported offset after interruptions, and each file is SHA-256-verified by
the Mac before it is renamed into place (create-only). ``PERSISTED_MANIFEST.json`` (if present)
is sent last, so its arrival marks a complete export. Dry run unless ``--execute``.

  uv run python scripts/cloud/push_to_mac.py --source DIR \\
      --base-url https://<name>.trycloudflare.com --dest-prefix fold0-g0/prepare-only [--execute]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

MANIFEST = "PERSISTED_MANIFEST.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plan(source: Path) -> list[Path]:
    files = sorted(
        p for p in source.rglob("*") if p.is_file() and not p.is_symlink() and p.suffix != ".part"
    )
    return [p for p in files if p.name != MANIFEST] + [p for p in files if p.name == MANIFEST]


def push_file(
    client: Any, base_url: str, local: Path, remote: str, chunk: int, retries: int = 5
) -> dict:
    total = local.stat().st_size
    digest = _sha256(local)
    url = f"{base_url.rstrip('/')}/upload/{urllib.parse.quote(remote, safe='/')}"
    offset = 0
    attempts = 0
    while True:
        with local.open("rb") as handle:
            handle.seek(offset)
            body = handle.read(chunk)
        headers = {
            "X-Upload-Offset": str(offset),
            "X-Upload-Total": str(total),
            "X-Content-SHA256": digest,
            "Content-Type": "application/octet-stream",
        }
        try:
            response = client.put(url, content=body, headers=headers)
        except Exception:  # network interruption: resume from the server's offset
            attempts += 1
            if attempts > retries:
                raise
            time.sleep(min(30, 2**attempts))
            continue
        payload = response.json() if response.content else {}
        if response.status_code in (200, 201) and payload.get("complete"):
            return {
                "path": remote,
                "bytes": total,
                "sha256": digest,
                "already_present": bool(payload.get("exists")),
            }
        if response.status_code == 200:
            offset = int(payload["received"])
            continue
        if response.status_code == 409 and "received" in payload:
            offset = int(payload["received"])  # resume where the Mac actually is
            attempts += 1
            if attempts > retries + 50:
                raise RuntimeError(f"upload not progressing: {remote}")
            continue
        raise RuntimeError(f"upload failed ({response.status_code} {payload}): {remote}")


def push(
    source: Path,
    *,
    base_url: str,
    dest_prefix: str,
    execute: bool,
    chunk_mb: int = 32,
    client: Any = None,
) -> dict[str, Any]:
    files = plan(source)
    prefix = dest_prefix.strip("/")
    entries = [(f, f"{prefix}/{f.relative_to(source).as_posix()}") for f in files]
    total = sum(f.stat().st_size for f in files)
    if not execute:
        return {
            "dry_run": True,
            "files": len(files),
            "bytes": total,
            "first": [remote for _, remote in entries[:5]],
        }
    if client is None:
        import httpx

        client = httpx.Client(timeout=httpx.Timeout(60.0, read=600.0, write=600.0))
    started = time.monotonic()
    results = [
        push_file(client, base_url, f, remote, chunk_mb * 1024 * 1024) for f, remote in entries
    ]
    elapsed = max(time.monotonic() - started, 1e-9)
    return {
        "dry_run": False,
        "files": len(results),
        "bytes": total,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_mb_per_s": round(total / elapsed / 1e6, 3),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--dest-prefix", required=True)
    parser.add_argument("--chunk-mb", type=int, default=32)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    result = push(
        args.source,
        base_url=args.base_url,
        dest_prefix=args.dest_prefix,
        execute=args.execute,
        chunk_mb=args.chunk_mb,
    )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
