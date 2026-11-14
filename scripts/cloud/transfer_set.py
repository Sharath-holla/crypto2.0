#!/usr/bin/env python3
"""Verified Mac -> private GCS -> cloud VM transfer of the Phase 7 data-only set.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-cloud-training-prep). Standard library only
(``httpx`` is imported lazily for ``fetch``), so the same file runs on the Mac and on the VM.

The reference is the COMMITTED manifest
``docs/reviews/evidence_combined_closure_20261108/runpod_data_only_manifest.json``:
2,777 files / 10,998,003,736 bytes, each with a SHA-256. Nothing here downloads from Binance,
modifies a source file, or prints a credential.

Commands (all read-only unless ``--execute`` is given):

  verify  --root DIR [--record OUT]   size + SHA-256 of every listed file under DIR
  plan    --root DIR                  what is missing/invalid, bytes to fetch, disk check, cost
  fetch   --root DIR (--base-url URL | --bucket B --prefix P) [--path P ...|--batch-file F]
          [--execute]
                                      download only missing/invalid files by EXACT object name
                                      (no bucket listing), resumable (.part + HTTP Range), each
                                      file SHA-256-verified before an atomic rename; progress is
                                      appended to DIR/.transfer-state/progress.jsonl.
                                      Authentication is injected by the session's network proxy
                                      for storage.googleapis.com; this script never handles it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs/reviews/evidence_combined_closure_20261108/runpod_data_only_manifest.json"
EXPECTED_FILES = 2777
EXPECTED_BYTES = 10_998_003_736
EXPECTED_LIST_SHA256 = "5ebe6f7a60565afa4be6a6bd1d27855e9a3fec52959c94160cfe0277a01905b3"
SAFETY_BYTES = 2 * 10**9
EGRESS_USD_PER_GB = (0.12, 0.23)  # internet egress list-price range; free in the same region
CHUNK = 8 * 1024 * 1024


def load_manifest(path: Path = MANIFEST) -> list[dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    records = manifest["records"]
    if (
        manifest["file_count"] != EXPECTED_FILES
        or len(records) != EXPECTED_FILES
        or manifest["bytes"] != EXPECTED_BYTES
        or sum(int(r["bytes"]) for r in records) != EXPECTED_BYTES
        or manifest["file_list_sha256"] != EXPECTED_LIST_SHA256
        or len({r["path"] for r in records}) != EXPECTED_FILES
    ):
        raise SystemExit("TRANSFER_MANIFEST_MISMATCH: committed manifest is not the verified set")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts or len(record["sha256"]) != 64:
            raise SystemExit(f"TRANSFER_MANIFEST_UNSAFE_ENTRY: {record['path']}")
    return records


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def file_state(root: Path, record: dict[str, Any], *, hash_files: bool) -> str:
    target = root / record["path"]
    if not target.is_file():
        return "MISSING"
    if target.stat().st_size != int(record["bytes"]):
        return "WRONG_SIZE"
    if hash_files and sha256_file(target) != record["sha256"]:
        return "WRONG_SHA256"
    return "OK"


def verify(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    problems: dict[str, list[str]] = {}
    for index, record in enumerate(records, start=1):
        state = file_state(root, record, hash_files=True)
        if state != "OK":
            problems.setdefault(state, []).append(record["path"])
        if index % 250 == 0 or index == len(records):
            print(f"verified {index}/{len(records)}", file=sys.stderr, flush=True)
    ok = not problems
    return {
        "schema": "phase7_transfer_set_verification_v1",
        "status": "VERIFIED" if ok else "FAILED",
        "files": len(records),
        "bytes": sum(int(r["bytes"]) for r in records),
        "file_list_sha256": EXPECTED_LIST_SHA256,
        "manifest_sha256": sha256_file(MANIFEST),
        "problems": {key: value[:50] for key, value in problems.items()},
        "problem_counts": {key: len(value) for key, value in problems.items()},
        "root": str(root.resolve()),
        "verified_at_unix": time.time(),
    }


def plan(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    pending = [r for r in records if file_state(root, r, hash_files=False) != "OK"]
    need = sum(int(r["bytes"]) for r in pending)
    probe = root if root.exists() else next(p for p in root.parents if p.exists())
    free = shutil.disk_usage(probe).free
    gigabytes = need / 1e9
    return {
        "files_total": len(records),
        "files_to_fetch": len(pending),
        "bytes_to_fetch": need,
        "free_bytes": free,
        "free_after_fetch_bytes": free - need,
        "disk_ok": free - need >= SAFETY_BYTES,
        "estimated_egress_usd": [round(gigabytes * rate, 2) for rate in EGRESS_USD_PER_GB],
        "note": "presence/size only; run `verify` for SHA-256 of every file",
    }


def object_url(bucket: str, prefix: str, relative: str) -> str:
    name = f"{prefix.strip('/')}/{relative}" if prefix.strip("/") else relative
    return (
        f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket, safe='')}"
        f"/o/{urllib.parse.quote(name, safe='')}?alt=media"
    )


def _log(state_dir: Path, event: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "progress.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"t": time.time(), **event}) + "\n")


def tunnel_url(base_url: str, relative: str) -> str:
    """Object URL on the Mac transfer server (scripts/cloud/mac_transfer_server.py)."""

    return f"{base_url.rstrip('/')}/files/{urllib.parse.quote(relative, safe='/')}"


def select(records: list[dict[str, Any]], paths: list[str] | None) -> list[dict[str, Any]]:
    """Restrict to a batch; every requested path must be in the verified manifest."""

    if not paths:
        return records
    wanted = set(paths)
    chosen = [r for r in records if r["path"] in wanted]
    unknown = wanted - {r["path"] for r in chosen}
    if unknown:
        raise SystemExit(f"NOT_IN_MANIFEST: {sorted(unknown)[:5]}")
    return chosen


def fetch_one(client: Any, url: str, record: dict[str, Any], root: Path, state_dir: Path) -> str:
    target = root / record["path"]
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    offset = part.stat().st_size if part.exists() else 0
    if offset > int(record["bytes"]):
        part.unlink()
        offset = 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with client.stream("GET", url, headers=headers) as response:
        served_sha = response.headers.get("x-content-sha256")
        if served_sha is not None and served_sha != record["sha256"]:
            raise RuntimeError(
                f"SOURCE_MANIFEST_MISMATCH: server SHA-256 differs for {record['path']}"
            )
        if response.status_code == 416 and offset == int(record["bytes"]):
            pass
        elif response.status_code == 200 and offset:
            part.unlink()  # server ignored Range: restart cleanly
            offset = 0
            with part.open("wb") as handle:
                for block in response.iter_bytes(CHUNK):
                    handle.write(block)
        elif response.status_code in (200, 206):
            with part.open("ab" if offset else "wb") as handle:
                for block in response.iter_bytes(CHUNK):
                    handle.write(block)
        else:
            raise RuntimeError(f"HTTP {response.status_code} for {record['path']}")
    if part.stat().st_size != int(record["bytes"]):
        raise RuntimeError(f"size mismatch after download: {record['path']}")
    if sha256_file(part) != record["sha256"]:
        part.unlink()
        _log(state_dir, {"path": record["path"], "event": "SHA256_MISMATCH_DISCARDED"})
        raise RuntimeError(f"SHA-256 mismatch (discarded): {record['path']}")
    with part.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(part, target)
    _log(state_dir, {"path": record["path"], "event": "VERIFIED", "bytes": int(record["bytes"])})
    return "FETCHED"


def fetch(
    root: Path,
    records: list[dict[str, Any]],
    *,
    bucket: str | None = None,
    prefix: str | None = None,
    base_url: str | None = None,
    execute: bool,
    client: Any = None,
    retries: int = 4,
) -> dict[str, Any]:
    summary = plan(root, records)
    if not execute:
        return {**summary, "dry_run": True}
    if not summary["disk_ok"]:
        raise SystemExit("DISK_MARGIN_UNSAFE: refusing to download (see plan)")
    state_dir = root / ".transfer-state"
    if client is None:
        import httpx

        client = httpx.Client(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True)
    if (base_url is None) == (bucket is None):
        raise SystemExit("give exactly one source: --base-url or --bucket/--prefix")
    pending = [r for r in records if file_state(root, r, hash_files=False) != "OK"]
    fetched = 0
    fetched_bytes = 0
    started = time.monotonic()
    for index, record in enumerate(pending, start=1):
        if base_url is not None:
            url = tunnel_url(base_url, record["path"])
        else:
            url = object_url(bucket, prefix or "", record["path"])
        for attempt in range(retries + 1):
            try:
                fetch_one(client, url, record, root, state_dir)
                fetched += 1
                fetched_bytes += int(record["bytes"])
                break
            except Exception as exc:  # retried, then surfaced with the file name
                _log(state_dir, {"path": record["path"], "event": "RETRY", "error": str(exc)})
                if attempt == retries:
                    raise
                time.sleep(min(30, 2**attempt))
        print(f"fetched {index}/{len(pending)} {record['path']}", file=sys.stderr, flush=True)
    elapsed = max(time.monotonic() - started, 1e-9)
    return {
        **plan(root, records),
        "dry_run": False,
        "fetched": fetched,
        "fetched_bytes": fetched_bytes,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_mb_per_s": round(fetched_bytes / elapsed / 1e6, 3),
        "label": "MEASURED (includes per-file SHA-256 verification)",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "plan", "fetch"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--path", action="append", help="limit to this manifest path")
        command.add_argument("--batch-file", type=Path, help="limit to manifest paths listed")
        if name == "verify":
            command.add_argument("--record", type=Path)
        if name == "fetch":
            command.add_argument("--base-url", help="https://<name>.trycloudflare.com")
            command.add_argument("--bucket")
            command.add_argument("--prefix")
            command.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    paths = list(args.path or [])
    if args.batch_file:
        paths += [line.strip() for line in args.batch_file.read_text().splitlines() if line.strip()]
    records = select(load_manifest(), paths)
    if args.command == "verify":
        result = verify(args.root, records)
        if args.record:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            args.record.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "problems"}, indent=1))
        return 0 if result["status"] == "VERIFIED" else 3
    if args.command == "plan":
        result = plan(args.root, records)
        print(json.dumps(result, indent=1))
        return 0 if result["disk_ok"] else 2
    result = fetch(
        args.root,
        records,
        bucket=args.bucket,
        prefix=args.prefix,
        base_url=args.base_url,
        execute=args.execute,
    )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
