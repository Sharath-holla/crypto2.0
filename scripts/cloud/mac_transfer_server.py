#!/usr/bin/env python3
"""Read-only, token-protected, manifest-restricted file server for Mac -> Claude cloud transfer.

ADDED BY CLAUDE (2026-11-14). Standard library only; runs on the Mac (data source only, never
training). Pair it with a Cloudflare Quick Tunnel pointing at the localhost port.

Security properties:
* binds to 127.0.0.1 only; reachable from outside only through the tunnel you start;
* serves ONLY files named in the committed 2,777-file manifest (optionally narrowed to a batch
  list), looked up by exact manifest path; no directory listing, no other paths, no writes;
* every request needs ``Authorization: Bearer <token>``; the token is 256-bit random, generated
  at start, written to a 0600 file outside the repository and NEVER printed or logged;
* the server and token expire after ``--ttl-minutes`` (default 240) and the process exits;
* it exits after ``--max-auth-failures`` (default 30) rejected requests;
* access log lines contain time, method, status, path and bytes only (never headers);
* files are opened read-only; startup verifies presence and size of every served file
  (``--verify-sha256`` additionally hashes each one).

Optional RESULT RECEIVING (``--receive-dir``, off by default) for VM -> Mac export of checkpoints,
logs and reports: ``PUT /upload/<relative path>`` with headers ``X-Upload-Offset``,
``X-Upload-Total`` and ``X-Content-SHA256`` (whole file). Chunks (<= 64 MiB, below Cloudflare's
100 MB request limit) append to ``<path>.part`` only at the expected offset (409 + current size
otherwise, so uploads resume); the completed file is SHA-256-verified, fsynced and renamed.
Create-only: an existing different file is never overwritten (409). Paths are restricted to
``[A-Za-z0-9._=-]`` components under the receive directory, which must be outside ``--root``;
per-file and total byte caps apply. Nothing can be read back through this endpoint.

Endpoints: ``GET|HEAD /files/<url-quoted manifest path>`` (single HTTP Range supported),
``GET /healthz`` (counts and expiry). Everything else -> 404; unauthenticated -> 401.

  STAGE=/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107
  python3 scripts/cloud/mac_transfer_server.py --root "$STAGE"
"""

from __future__ import annotations

import argparse
import contextlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("transfer_set", HERE / "transfer_set.py")
transfer_set = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transfer_set)  # type: ignore[union-attr]

CHUNK = 1024 * 1024
RANGE = re.compile(r"^bytes=(\d+)-(\d*)$")
SAFE_UPLOAD = re.compile(r"^[A-Za-z0-9_=-][A-Za-z0-9._=-]*(/[A-Za-z0-9_=-][A-Za-z0-9._=-]*)*$")
MAX_CHUNK = 64 * 1024 * 1024


class State:
    def __init__(
        self, files: dict[str, dict[str, Any]], token: str, expires_at: float, max_failures: int
    ) -> None:
        self.files = files
        self.token = token.encode()
        self.expires_at = expires_at
        self.max_failures = max_failures
        self.failures = 0
        self.lock = threading.Lock()
        self.bytes_sent = 0
        self.upload_lock = threading.Lock()
        self.receive_dir: Path | None = None
        self.max_file_bytes = 1024**3
        self.max_receive_bytes = 4 * 1024**3
        self.bytes_received = 0


def build_files(
    root: Path, records: list[dict[str, Any]], allow: set[str] | None, verify_sha: bool
) -> dict[str, dict[str, Any]]:
    root_real = root.resolve()
    files: dict[str, dict[str, Any]] = {}
    for record in records:
        if allow is not None and record["path"] not in allow:
            continue
        path = (root / record["path"]).resolve()
        if not path.is_relative_to(root_real):
            raise SystemExit(f"REFUSED: {record['path']} resolves outside the root")
        if not path.is_file() or path.stat().st_size != int(record["bytes"]):
            raise SystemExit(f"REFUSED: missing or wrong size: {record['path']}")
        if verify_sha and transfer_set.sha256_file(path) != record["sha256"]:
            raise SystemExit(f"REFUSED: SHA-256 mismatch: {record['path']}")
        files[record["path"]] = {
            "path": path,
            "bytes": int(record["bytes"]),
            "sha256": record["sha256"],
        }
    if allow is not None and set(allow) - set(files):
        raise SystemExit(
            f"REFUSED: batch names files outside the manifest: "
            f"{sorted(set(allow) - set(files))[:5]}"
        )
    return files


def make_handler(state: State, log: Any) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "crypto2-transfer"
        sys_version = ""

        def log_message(self, *_args: Any) -> None:  # silence default logging (no headers)
            return

        def _log(self, status: int, sent: int = 0) -> None:
            path = urllib.parse.urlsplit(self.path).path[:300]
            log.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                f"{self.command} {status} {path} {sent}\n"
            )
            log.flush()

        def _send(self, status: int, body: bytes = b"", headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self._log(status, len(body))

        def _authorized(self) -> bool:
            if time.time() >= state.expires_at:
                return False
            header = self.headers.get("Authorization", "")
            supplied = header[7:].encode() if header.startswith("Bearer ") else b""
            if hmac.compare_digest(supplied, state.token):
                return True
            with state.lock:
                state.failures += 1
                if state.failures >= state.max_failures:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
            return False

        def do_POST(self) -> None:  # noqa: N802
            self._send(405)

        do_DELETE = do_PATCH = do_OPTIONS = do_POST  # noqa: N815

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload).encode(), {"Content-Type": "application/json"})

        def _drain(self, length: int) -> None:
            while length > 0:
                block = self.rfile.read(min(CHUNK, length))
                if not block:
                    break
                length -= len(block)

        def do_PUT(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if state.receive_dir is None:
                self._drain(length)
                self._send(405)
                return
            if not self._authorized():
                self._drain(length)
                self._send(401, b"unauthorized\n", {"WWW-Authenticate": "Bearer"})
                return
            path = urllib.parse.urlsplit(self.path).path
            relative = (
                urllib.parse.unquote(path[len("/upload/") :]) if path.startswith("/upload/") else ""
            )
            try:
                offset = int(self.headers["X-Upload-Offset"])
                total = int(self.headers["X-Upload-Total"])
                digest = self.headers["X-Content-SHA256"].strip().lower()
            except (KeyError, ValueError, AttributeError):
                self._drain(length)
                self._json(400, {"error": "upload headers required"})
                return
            if (
                not SAFE_UPLOAD.match(relative)
                or len(relative) > 400
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or relative.endswith(".part")
            ):
                self._drain(length)
                self._json(400, {"error": "bad path or digest"})
                return
            target = (state.receive_dir / relative).resolve()
            if not target.is_relative_to(state.receive_dir.resolve()):
                self._drain(length)
                self._json(400, {"error": "path escapes receive dir"})
                return
            if length > MAX_CHUNK or total > state.max_file_bytes or offset < 0 or total < 0:
                self._drain(length)
                self._json(413, {"error": "chunk or file too large"})
                return
            with state.upload_lock:
                if target.exists():
                    self._drain(length)
                    same = target.stat().st_size == total and (
                        transfer_set.sha256_file(target) == digest
                    )
                    self._json(200 if same else 409, {"complete": same, "exists": True})
                    return
                part = target.with_name(target.name + ".part")
                current = part.stat().st_size if part.exists() else 0
                if offset != current:
                    self._drain(length)
                    self._json(409, {"received": current, "complete": False})
                    return
                if state.bytes_received + length > state.max_receive_bytes or (
                    offset + length > total
                ):
                    self._drain(length)
                    self._json(413, {"error": "receive budget or declared size exceeded"})
                    return
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                remaining = length
                with part.open("ab") as handle:
                    while remaining:
                        block = self.rfile.read(min(CHUNK, remaining))
                        if not block:
                            break
                        handle.write(block)
                        remaining -= len(block)
                state.bytes_received += length - remaining
                size = part.stat().st_size
                if size < total:
                    self._json(200, {"received": size, "complete": False})
                    return
                if transfer_set.sha256_file(part) != digest:
                    part.unlink()
                    self._json(422, {"error": "SHA-256 mismatch; partial upload discarded"})
                    return
                with part.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(part, target)
                self._json(201, {"received": size, "complete": True})

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send(401, b"unauthorized\n", {"WWW-Authenticate": "Bearer"})
                return
            path = urllib.parse.urlsplit(self.path).path
            if path == "/healthz":
                body = json.dumps(
                    {
                        "files": len(state.files),
                        "expires_in_seconds": int(state.expires_at - time.time()),
                    }
                )
                self._send(200, body.encode(), {"Content-Type": "application/json"})
                return
            if not path.startswith("/files/"):
                self._send(404)
                return
            entry = state.files.get(urllib.parse.unquote(path[len("/files/") :]))
            if entry is None:
                self._send(404)
                return
            size = entry["bytes"]
            start, end = 0, size - 1
            status = 200
            range_header = self.headers.get("Range")
            if range_header:
                match = RANGE.match(range_header.strip())
                if not match or int(match.group(1)) >= size:
                    self._send(416, headers={"Content-Range": f"bytes */{size}"})
                    return
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
                if end < start:
                    self._send(416, headers={"Content-Range": f"bytes */{size}"})
                    return
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-SHA256", entry["sha256"])
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            sent = 0
            if self.command != "HEAD":
                with open(entry["path"], "rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining:
                        block = handle.read(min(CHUNK, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        sent += len(block)
                        remaining -= len(block)
            with state.lock:
                state.bytes_sent += sent
            self._log(status, sent)

    return Handler


def serve(
    root: Path,
    *,
    port: int,
    ttl_minutes: float,
    allow: set[str] | None,
    verify_sha: bool,
    token_file: Path,
    log_file: Path,
    max_failures: int,
    records: list[dict[str, Any]] | None = None,
    ready: Any = None,
    receive_dir: Path | None = None,
    max_receive_bytes: int = 4 * 1024**3,
) -> State:
    files = build_files(
        root,
        records if records is not None else transfer_set.load_manifest(),
        allow,
        verify_sha,
    )
    token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    state = State(files, token, time.time() + ttl_minutes * 60, max_failures)
    if receive_dir is not None:
        receive = receive_dir.resolve()
        if receive.is_relative_to(root.resolve()) or root.resolve().is_relative_to(receive):
            raise SystemExit("REFUSED: --receive-dir must be outside the data root")
        receive.mkdir(parents=True, exist_ok=True, mode=0o700)
        state.receive_dir = receive
        state.max_receive_bytes = max_receive_bytes
    log = log_file.open("a", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, log))
    timer = threading.Timer(ttl_minutes * 60, server.shutdown)
    timer.daemon = True
    timer.start()
    print(
        json.dumps(
            {
                "listening": f"http://127.0.0.1:{server.server_address[1]}",
                "files_served": len(files),
                "bytes_served_max": sum(f["bytes"] for f in files.values()),
                "token_file": str(token_file),
                "access_log": str(log_file),
                "expires_in_minutes": ttl_minutes,
                "receive_dir": str(state.receive_dir) if state.receive_dir else None,
            }
        ),
        flush=True,
    )
    if ready is not None:
        ready(server, state)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        timer.cancel()
        with contextlib.suppress(OSError):
            token_file.unlink()
        log.close()
        print(
            json.dumps(
                {
                    "stopped": True,
                    "bytes_sent": state.bytes_sent,
                    "bytes_received": state.bytes_received,
                    "auth_failures": state.failures,
                }
            ),
            flush=True,
        )
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="staging root containing crypto2-persistent/ and the sidecar",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ttl-minutes", type=float, default=240)
    parser.add_argument(
        "--batch-file", type=Path, help="serve only these manifest paths (one per line)"
    )
    parser.add_argument("--verify-sha256", action="store_true")
    parser.add_argument("--max-auth-failures", type=int, default=30)
    parser.add_argument(
        "--receive-dir", type=Path, help="enable result uploads into this folder (outside --root)"
    )
    parser.add_argument("--max-receive-gb", type=float, default=4.0)
    parser.add_argument(
        "--token-file", type=Path, default=Path.home() / ".crypto2-transfer" / "token"
    )
    parser.add_argument(
        "--log-file", type=Path, default=Path.home() / ".crypto2-transfer" / "access.log"
    )
    args = parser.parse_args(argv)
    allow = None
    if args.batch_file:
        allow = {line.strip() for line in args.batch_file.read_text().splitlines() if line.strip()}
    args.log_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    serve(
        args.root,
        port=args.port,
        ttl_minutes=args.ttl_minutes,
        allow=allow,
        verify_sha=args.verify_sha256,
        token_file=args.token_file,
        log_file=args.log_file,
        max_failures=args.max_auth_failures,
        receive_dir=args.receive_dir,
        max_receive_bytes=int(args.max_receive_gb * 1024**3),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
