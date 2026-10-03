"""Persistent single-writer run ownership; POSIX flock is production authority."""

from __future__ import annotations

import argparse
import json
import os
import socket
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import get_ident
from typing import Any

import psutil

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import atomic_json, fsync_directory


class RunLeaseError(RuntimeError):
    pass


def _lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def owner_liveness(owner: dict[str, Any]) -> str:
    if owner.get("hostname") != socket.gethostname():
        return "UNKNOWN_FOREIGN_HOST"
    try:
        pid = int(owner["pid"])
        if not psutil.pid_exists(pid):
            return "DEAD"
        process = psutil.Process(pid)
        if not process.is_running() or process.status() in {
            psutil.STATUS_ZOMBIE,
            psutil.STATUS_DEAD,
        }:
            return "DEAD"
        recorded = owner.get("process_start_time")
        if recorded is None:
            return "UNKNOWN_START_TIME"
        return "LIVE" if process.create_time() == float(recorded) else "DEAD_PID_REUSED"
    except psutil.NoSuchProcess:
        return "DEAD"
    except (psutil.AccessDenied, ValueError, TypeError, KeyError):
        return "UNKNOWN"


class RunLease:
    def __init__(self, root: Path, run_identity: str, scientific_identity: Any, *, mode: str):
        self.root = root.resolve()
        if self.root.name != run_identity or mode not in {"production", "benchmark"}:
            raise ValueError("lease root/run identity or mode mismatch")
        if mode == "benchmark" and not run_identity.startswith("benchmark-only-"):
            raise ValueError("benchmark lease requires an isolated benchmark-only run root")
        if mode == "production" and run_identity.startswith("benchmark-only-"):
            raise ValueError("production lease cannot own a benchmark root")
        self.run_identity = run_identity
        self.scientific_identity = scientific_identity
        self.mode = mode
        self.path = self.root / ".phase7-run-lease.json"
        self.descriptor: int | None = None
        self.owner: dict[str, Any] | None = None
        self.thread_id = get_ident()

    def _acquire_guard(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        guard = self.root / ".phase7-run-lease.guard"
        if guard.is_symlink() or self.path.is_symlink():
            raise RunLeaseError("lease files must not be symlinks")
        descriptor = os.open(guard, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
                os.fsync(descriptor)
            _lock(descriptor)
        except OSError as exc:
            os.close(descriptor)
            raise RunLeaseError("run already has an active filesystem lease") from exc
        self.descriptor = descriptor

    def _close_guard(self) -> None:
        if self.descriptor is not None:
            _unlock(self.descriptor)
            os.close(self.descriptor)
            self.descriptor = None

    def __enter__(self) -> RunLease:
        self._acquire_guard()
        try:
            if self.path.exists():
                raise RunLeaseError(
                    "run has retained lease evidence; explicit hash-bound recovery is required: "
                    + str(self.path)
                )
            try:
                process_start = psutil.Process().create_time()
            except psutil.AccessDenied:
                process_start = None
            self.owner = {
                "lease_schema": "phase7_single_run_lease_v1",
                "lease_id": uuid.uuid4().hex,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "process_start_time": process_start,
                "run_identity": self.run_identity,
                "scientific_identity": self.scientific_identity,
                "mode": self.mode,
                "acquired_at": datetime.now(UTC).isoformat(),
            }
            atomic_json(self.path, self.owner)
        except BaseException:
            self._close_guard()
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            # A handled failure is a clean process exit, not an abandoned lease.
            if self.owner is not None:
                current = json.loads(self.path.read_text(encoding="utf-8"))
                if current != self.owner:
                    raise RunLeaseError(
                        "lease evidence changed while held; preserve and investigate"
                    )
                self.path.unlink()
                fsync_directory(self.root)
        finally:
            self._close_guard()

    def recover(
        self, *, expected_sha256: str, reason: str, confirm_foreign_owner_dead: bool = False
    ):
        """Archive proven abandoned evidence under guard; never steal a live lease."""
        if not reason.strip():
            raise ValueError("explicit lease recovery reason is required")
        self._acquire_guard()
        try:
            if file_sha256(self.path) != expected_sha256:
                raise RunLeaseError("lease recovery checksum changed")
            owner = json.loads(self.path.read_text(encoding="utf-8"))
            if owner.get("run_identity") != self.run_identity or owner.get("mode") != self.mode:
                raise RunLeaseError("lease recovery run/mode identity mismatch")
            liveness = owner_liveness(owner)
            if not liveness.startswith("DEAD") and not (
                liveness == "UNKNOWN_FOREIGN_HOST" and confirm_foreign_owner_dead
            ):
                raise RunLeaseError(f"lease owner is not proven dead: {liveness}")
            archive = self.root / f".phase7-run-lease.abandoned.{uuid.uuid4().hex}.json"
            os.rename(self.path, archive)
            fsync_directory(self.root)
            atomic_json(
                archive.with_suffix(".recovery.json"),
                {
                    "prior_sha256": expected_sha256,
                    "reason": reason,
                    "liveness": liveness,
                    "recovered_at": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                },
            )
            return archive
        finally:
            self._close_guard()


_ACTIVE: dict[Path, RunLease] = {}


@contextmanager
def owned_run(root: Path, run_identity: str, scientific_identity: Any, *, mode: str):
    """Allow nested internal calls only beneath an already filesystem-owned run."""
    key = root.resolve()
    existing = _ACTIVE.get(key)
    if existing is not None:
        if (
            existing.run_identity != run_identity
            or existing.mode != mode
            or existing.scientific_identity != scientific_identity
            or existing.thread_id != get_ident()
            or existing.owner is None
            or existing.owner["pid"] != os.getpid()
        ):
            raise RunLeaseError("nested run ownership identity mismatch")
        yield existing
        return
    with RunLease(root, run_identity, scientific_identity, mode=mode) as lease:
        _ACTIVE[key] = lease
        try:
            yield lease
        finally:
            _ACTIVE.pop(key, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("production", "benchmark"), required=True)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--reason")
    parser.add_argument("--confirm-foreign-owner-dead", action="store_true")
    args = parser.parse_args()
    root = args.run_root.resolve()
    path = root / ".phase7-run-lease.json"
    if args.recover:
        if not args.expected_sha256 or not args.reason:
            parser.error("recovery requires exact reviewed --expected-sha256 and --reason")
        archived = RunLease(root, root.name, None, mode=args.mode).recover(
            expected_sha256=args.expected_sha256,
            reason=args.reason,
            confirm_foreign_owner_dead=args.confirm_foreign_owner_dead,
        )
        result = {"status": "RECOVERED", "archived_evidence": str(archived)}
    elif path.is_file():
        owner = json.loads(path.read_text(encoding="utf-8"))
        result = {"owner": owner, "sha256": file_sha256(path), "liveness": owner_liveness(owner)}
    else:
        result = {"status": "NO_RETAINED_OWNER"}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
