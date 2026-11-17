"""Atomic native partial models and graceful preemption; mid-fit continuation is unqualified.

Checkpointing never publishes a canonical model/result. Normal fits retain the existing
parameters, early-stopping callback and observer. No production path uses init_model.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import atomic_json, fsync_directory
from crypto_ai.phase7.config import stable_hash

SCHEMA = "phase7_partial_booster_checkpoint_v1"
CAPABILITY = "MID_FIT_RESUME_NOT_QUALIFIED"
CONFIG_ENV = "PHASE7_PREEMPTION_CONFIG"
_BINDING: ContextVar[dict[str, Any] | None] = ContextVar("phase7_preemption_binding", default=None)


class TrainingPreempted(RuntimeError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__("PREEMPTED_RESTART_REQUIRED")
        self.receipt = receipt


def refuse_mid_fit_resume() -> None:
    raise ValueError(CAPABILITY + ": restart the one model from round 0 on its qualified cache")


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def durable_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def copy_verified_tree(
    source: Path,
    destination: Path,
    *,
    reserve_bytes: int = 0,
    expected_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Add-only publication. Copy completion appears only after all bytes are verified.

    Used after cache qualification, never while a cache writer owns the entry. Source
    metadata is rechecked; neither source data nor an existing destination is overwritten.
    """
    source = source.resolve()
    destination = destination.absolute()
    if destination.is_symlink() or destination.resolve().is_relative_to(source):
        raise ValueError("PERSISTENT_COPY_PATH_INVALID")
    files = sorted(p for p in source.rglob("*") if p.is_file())
    if not files or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("PERSISTENT_COPY_EMPTY_OR_ALIASED")
    records = {
        str(p.relative_to(source)): {
            "bytes": p.stat().st_size,
            "sha256": expected_files[str(p.relative_to(source))]
            if expected_files is not None
            else file_sha256(p),
        }
        for p in files
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
        if actual != set(records) or any(
            file_sha256(destination / name) != rec["sha256"] for name, rec in records.items()
        ):
            raise ValueError("PERSISTENT_COPY_CONFLICT")
        return {"status": "PASS", "path": str(destination), "reused": True, "files": records}
    incoming = sum(rec["bytes"] for rec in records.values())
    if shutil.disk_usage(destination.parent).free < incoming + reserve_bytes:
        raise OSError("PERSISTENT_CAPACITY_INSUFFICIENT")
    temporary = destination.with_name("." + destination.name + ".copy-" + uuid.uuid4().hex)
    temporary.mkdir()
    # Keep incomplete copies as forensic evidence. They have no publication directory/receipt.
    markers = {"CACHE_COMPLETE", "CHECKPOINT_COMPLETE"}
    for name in sorted(records, key=lambda name: Path(name).name in markers):
        src, dst = source / name, temporary / name
        before = src.stat()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        durable_file(dst)
        after = src.stat()
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size,
            after.st_mtime_ns,
        ) or file_sha256(dst) != records[name]["sha256"]:
            raise ValueError("PERSISTENT_COPY_HASH_MISMATCH")
    fsync_directory(temporary)
    if destination.exists():
        raise ValueError("PERSISTENT_COPY_DESTINATION_RACE")
    temporary.rename(destination)
    fsync_directory(destination.parent)
    return {"status": "PASS", "path": str(destination), "bytes": incoming, "files": records}


def retain_latest_three(root: Path, logical_run_id: str) -> None:
    """Prune only newly managed, verified partial payloads; keep immutable audit manifests."""
    verified = []
    for p in root.glob("*/iter-*/checkpoint.json"):
        try:
            data = verify_partial(p.parent, load_native=False)
        except (OSError, ValueError, KeyError):
            continue  # Preserve corrupt/incomplete evidence; never let it evict a valid fallback.
        if data["logical_run_id"] == logical_run_id:
            verified.append((data["timestamp"], p.parent, data))
    for _, path, data in sorted(verified, reverse=True, key=lambda x: x[0])[3:]:
        if path.parent.parent != root or not path.name.startswith("iter-") or path.is_symlink():
            raise ValueError("PARTIAL_RETENTION_SCOPE_REFUSED")
        atomic_json(root / "retention-audit" / (path.name + ".json"), data)
        shutil.rmtree(path)
        fsync_directory(path.parent)


def copy_qualified_cache(
    source: Path, destination: Path, expected_cache_id: str, *, available_bytes: int | None = None
) -> dict[str, Any]:
    """Copy a complete hash-bound cache; caller performs canonical row qualification."""
    manifest_path = source / "manifest.json"
    marker = source / "CACHE_COMPLETE"
    if (
        not marker.is_file()
        or marker.is_symlink()
        or marker.read_text().strip() != file_sha256(manifest_path)
    ):
        raise ValueError("CACHE_COPY_INCOMPLETE")
    manifest = read(manifest_path)
    if manifest["cache_id"] != expected_cache_id:
        raise ValueError("CACHE_COPY_IDENTITY_MISMATCH")
    expected = {name: record["sha256"] for name, record in manifest["files"].items()}
    expected["manifest.json"] = file_sha256(manifest_path)
    expected["CACHE_COMPLETE"] = file_sha256(marker)
    size = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
    reserve = 5 * 1024**3
    if available_bytes is not None and size + reserve > available_bytes:
        raise OSError("PERSISTENT_CAPACITY_INSUFFICIENT")
    return copy_verified_tree(source, destination, reserve_bytes=reserve, expected_files=expected)


def verify_partial(
    path: Path, expected_binding: dict[str, Any] | None = None, *, load_native: bool = True
) -> dict[str, Any]:
    import lightgbm as lgb

    if path.is_symlink() or not path.is_dir():
        raise ValueError("PARTIAL_CHECKPOINT_PATH_INVALID")
    manifest = path / "checkpoint.json"
    if manifest.is_symlink() or (path / "CHECKPOINT_COMPLETE").is_symlink():
        raise ValueError("PARTIAL_CHECKPOINT_ALIASED")
    digest = file_sha256(manifest)
    if (path / "CHECKPOINT_COMPLETE").read_text().strip() != digest:
        raise ValueError("PARTIAL_CHECKPOINT_MARKER_MISMATCH")
    payload = read(manifest)
    if not isinstance(payload, dict):
        raise ValueError("PARTIAL_CHECKPOINT_SCHEMA_MISMATCH")
    if (payload.get("schema"), payload.get("status"), payload.get("resume_capability")) != (
        SCHEMA,
        "TRAINING_PARTIAL_CHECKPOINT",
        CAPABILITY,
    ):
        raise ValueError("PARTIAL_CHECKPOINT_SCHEMA_MISMATCH")
    if expected_binding is not None and payload["binding"] != expected_binding:
        raise ValueError("RESUME_IDENTITY_MISMATCH")
    if payload["binding_sha256"] != stable_hash(payload["binding"], length=64):
        raise ValueError("PARTIAL_BINDING_HASH_MISMATCH")
    if (
        payload["binding"]["lightgbm_version"] != lgb.__version__
        or payload["binding"]["python_version"] != platform.python_version()
    ):
        raise ValueError("RESUME_IDENTITY_MISMATCH")
    for name, record in payload["files"].items():
        if name not in {"model.txt", "model.sha256", "telemetry-tail.jsonl"}:
            raise ValueError("PARTIAL_CHECKPOINT_INVENTORY_INVALID")
        target = path / name
        if target.is_symlink() or file_sha256(target) != record["sha256"]:
            raise ValueError("PARTIAL_CHECKPOINT_HASH_MISMATCH")
    if set(payload["files"]) != {"model.txt", "model.sha256", "telemetry-tail.jsonl"}:
        raise ValueError("PARTIAL_CHECKPOINT_INVENTORY_INCOMPLETE")
    if (path / "model.sha256").read_text().strip() != file_sha256(path / "model.txt"):
        raise ValueError("PARTIAL_MODEL_HASH_MISMATCH")
    if load_native:
        try:
            model = lgb.Booster(model_file=path / "model.txt")
        except lgb.basic.LightGBMError as exc:
            raise ValueError("PARTIAL_NATIVE_MODEL_INVALID") from exc
        if (model.current_iteration(), model.num_trees()) != (
            payload["completed_rounds"],
            payload["tree_count"],
        ):
            raise ValueError("PARTIAL_MODEL_ITERATION_MISMATCH")
        if model.feature_name() != payload["native_feature_names"] or model.num_feature() != len(
            payload["binding"]["feature_columns"]
        ):
            raise ValueError("PARTIAL_FEATURE_ORDER_MISMATCH")
    if not 0 < payload["completed_rounds"] <= payload["maximum_rounds"]:
        raise ValueError("PARTIAL_MAXIMUM_ROUNDS_INVALID")
    return {
        **payload,
        "checkpoint_sha256": digest,
        "checkpoint_path": str(path),
        "verification": "PASS",
        "native_parse_verified": load_native,
    }


def latest_verified(root: Path, expected_binding: dict[str, Any] | None = None) -> dict[str, Any]:
    candidates = sorted(
        root.glob("*/iter-*/checkpoint.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True
    )
    errors = []
    for path in candidates:
        try:
            return verify_partial(path.parent, expected_binding)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(type(exc).__name__)
    raise ValueError("NO_VERIFIED_PARTIAL_CHECKPOINT: " + ",".join(errors))


@contextmanager
def preemption_scope(*, binding: dict[str, Any]) -> Iterator[None]:
    token = _BINDING.set(binding)
    try:
        yield
    finally:
        _BINDING.reset(token)


class PartialCheckpointCallback:
    order = 25  # observer=20, canonical early stopping=30; no callback state is modified.
    before_iteration = False

    def __init__(self, config: dict[str, Any], binding: dict[str, Any], observer: Any):
        self.config, self.binding, self.observer = config, binding, observer
        self.best_l2 = float("inf")
        self.best_iteration = 0
        self.signal_requested: int | None = None
        self.last_receipt: dict[str, Any] | None = None
        self.serialization_seconds: list[float] = []
        self.telemetry_offset = 0

    def request_signal(self, signum: int, frame: Any) -> None:
        # No I/O, serialization, allocation-heavy operations, or exceptions in a signal handler.
        self.signal_requested = signum

    def publish(self, env: Any, request: dict[str, Any] | None) -> dict[str, Any]:
        started = time.monotonic()
        iteration = env.model.current_iteration()
        local = Path(self.config["local_root"])
        session = self.config["execution_session_id"]
        name = f"iter-{iteration:06d}-{uuid.uuid4().hex}"
        parent = local / session
        parent.mkdir(parents=True, exist_ok=True)
        temporary = parent / ("." + name + ".tmp")
        temporary.mkdir()
        model_path = temporary / "model.txt"
        env.model.save_model(model_path, num_iteration=-1)  # Never default to best_iteration.
        durable_file(model_path)
        model_hash = file_sha256(model_path)
        (temporary / "model.sha256").write_text(model_hash + "\n")
        tail = b""
        if self.observer is not None and self.observer.path.is_file():
            with self.observer.path.open("rb") as stream:
                stream.seek(max(0, self.observer.path.stat().st_size - 65536))
                tail = stream.read()
                if stream.tell() > len(tail):
                    tail = tail.partition(b"\n")[2]  # Don't publish a truncated JSONL record.
        (temporary / "telemetry-tail.jsonl").write_bytes(tail)
        for p in temporary.iterdir():
            durable_file(p)
        payload = {
            "schema": SCHEMA,
            "status": "TRAINING_PARTIAL_CHECKPOINT",
            "resume_capability": CAPABILITY,
            "restart_required": True,
            "cache_retained": bool(self.config.get("cache_retained", False)),
            "logical_run_id": self.config["logical_run_id"],
            "execution_session_id": session,
            "pod_id": self.config["pod_id"],
            "timestamp": datetime.now(UTC).isoformat(),
            "completed_rounds": iteration,
            "tree_count": env.model.num_trees(),
            "native_feature_names": env.model.feature_name(),
            "best_iteration": self.best_iteration,
            "best_validation_rmse": self.best_l2**0.5,
            "rounds_since_best": iteration - self.best_iteration,
            "early_stopping_state": {
                "metric": "validation/l2",
                "best_l2": self.best_l2,
                "best_iteration": self.best_iteration,
                "patience": self.binding["early_stopping_rounds"],
            },
            "maximum_rounds": self.binding["maximum_rounds"],
            "remaining_rounds_if_continuation_were_qualified": self.binding["maximum_rounds"]
            - iteration,
            "binding": self.binding,
            "binding_sha256": stable_hash(self.binding, length=64),
            "request_id": None if request is None else request["request_id"],
            "reason": "PERIODIC" if request is None else request["reason"],
            "files": {p.name: {"sha256": file_sha256(p)} for p in temporary.iterdir()},
        }
        atomic_json(temporary / "checkpoint.json", payload)
        marker = temporary / "CHECKPOINT_COMPLETE"
        marker.write_text(file_sha256(temporary / "checkpoint.json") + "\n")
        durable_file(marker)
        fsync_directory(temporary)
        final = parent / name
        temporary.rename(final)
        fsync_directory(parent)
        # Parse native models only in an independent process; do not perturb fit threads.
        verify_partial(final, self.binding, load_native=False)
        persistent = Path(self.config["persistent_root"]) / session / name
        copy_verified_tree(final, persistent)
        verified = verify_partial(persistent, self.binding, load_native=False)
        if request is not None and self.observer is not None:
            self.observer.emit(
                "PREEMPTED_RESTART_REQUIRED",
                checkpoint_path=str(persistent),
                completed_rounds=iteration,
                request_id=request["request_id"],
                resume_capability=CAPABILITY,
            )
        telemetry_record = None
        if self.observer is not None and self.observer.path.is_file():
            telemetry_path = (
                Path(self.config["persistent_root"])
                / session
                / "telemetry"
                / self.observer.path.name
            )
            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            existing = telemetry_path.stat().st_size if telemetry_path.exists() else 0
            if existing != self.telemetry_offset:
                raise ValueError("APPEND_ONLY_TELEMETRY_OFFSET_MISMATCH")
            with self.observer.path.open("rb") as src, telemetry_path.open("ab") as dst:
                src.seek(self.telemetry_offset)
                shutil.copyfileobj(src, dst, length=65536)
                dst.flush()
                os.fsync(dst.fileno())
                self.telemetry_offset = dst.tell()
            telemetry_record = {
                "path": str(telemetry_path),
                "bytes": self.telemetry_offset,
                "sha256": file_sha256(telemetry_path),
            }
        receipt = {
            "state": "EVIDENCE_EXPORTED",
            "persistent": True,
            "request_id": payload["request_id"],
            "logical_run_id": payload["logical_run_id"],
            "execution_session_id": session,
            "checkpoint_path": str(persistent),
            "checkpoint_sha256": verified["checkpoint_sha256"],
            "completed_rounds": iteration,
            "best_iteration": self.best_iteration,
            "best_validation_rmse": payload["best_validation_rmse"],
            "timestamp": payload["timestamp"],
            "resume_capability": CAPABILITY,
        }
        receipt["telemetry"] = telemetry_record
        receipt["cache_retained"] = bool(self.config.get("cache_retained", False))
        receipt["checkpoint_wall_seconds"] = time.monotonic() - started
        atomic_json(Path(self.config["receipt_path"]), receipt, immutable=False)
        self.last_receipt = receipt
        self.serialization_seconds.append(time.monotonic() - started)
        retain_latest_three(Path(self.config["persistent_root"]), self.config["logical_run_id"])
        retain_latest_three(local, self.config["logical_run_id"])
        return receipt

    def __call__(self, env: Any) -> None:
        validation = [
            float(x[2])
            for x in env.evaluation_result_list or []
            if x[0] == "validation" and x[1] == "l2"
        ]
        if len(validation) != 1:
            raise ValueError("PREEMPTION_REQUIRES_CANONICAL_VALIDATION_L2")
        if validation[0] < self.best_l2:
            self.best_l2, self.best_iteration = validation[0], env.iteration + 1
        request = None
        path = Path(self.config["request_path"])
        if path.exists():
            request = read(path)
            if not request.get("request_id") or not request.get("reason"):
                raise ValueError("INVALID_CHECKPOINT_REQUEST")
        elif self.signal_requested:
            request = {
                "request_id": uuid.uuid4().hex,
                "reason": signal.Signals(self.signal_requested).name,
            }
        if request is not None or (env.iteration + 1) % self.config["interval_rounds"] == 0:
            if request and self.observer is not None:
                self.observer.emit(
                    "CHECKPOINT_REQUESTED",
                    request_id=request["request_id"],
                    reason=request["reason"],
                )
            receipt = self.publish(env, request)
            if request is not None:
                raise TrainingPreempted(receipt)


@contextmanager
def checkpoint_callback(
    *, parameters: dict[str, Any], model_threads: int, sample_weight: Any, observer: Any
) -> Iterator[PartialCheckpointCallback | None]:
    config_path = os.environ.get(CONFIG_ENV)
    if not config_path:
        yield None
        return
    import lightgbm as lgb
    import numpy as np

    config = read(Path(config_path))
    binding = _BINDING.get()
    if binding is None or binding.get("spec_id") != "architecture-G0-A6-60m-raw":
        raise ValueError("PREEMPTION_SCOPE_REQUIRES_ONE_CANONICAL_G0_SMOKE")
    if (
        config.get("schema") != "phase7_preemption_config_v1"
        or not 1 <= config["interval_rounds"] <= 50
    ):
        raise ValueError("PREEMPTION_CONFIG_INVALID")
    if config.get("resume_from_partial"):
        refuse_mid_fit_resume()
    for field in ("logical_run_id", "execution_session_id", "pod_id"):
        if not isinstance(config.get(field), str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", config[field]
        ):
            raise ValueError("PREEMPTION_RUN_SESSION_ID_INVALID")
    binding = {
        **binding,
        "parameters": parameters,
        "model_threads": model_threads,
        "lightgbm_version": lgb.__version__,
        "python_version": platform.python_version(),
        "weights_sha256": hashlib.sha256(
            np.asarray(sample_weight, dtype=np.float64).tobytes()
        ).hexdigest()
        if sample_weight is not None
        else "UNIT_WEIGHTS",
    }
    if parameters.get("device_type") != "cpu" or lgb.__version__ != "4.7.0":
        raise ValueError("PREEMPTION_REQUIRES_LOCKED_CPU_LIGHTGBM_4_7_0")
    if config.get("expected_scientific_ids") != binding.get("scientific_ids") or config.get(
        "expected_cache_id"
    ) != binding.get("prepared_cache_id"):
        raise ValueError("RESUME_IDENTITY_MISMATCH")
    previous_checkpoint = None
    if config.get("restart_checkpoint"):
        previous_checkpoint = verify_partial(Path(config["restart_checkpoint"]), binding)
        if previous_checkpoint["logical_run_id"] != config["logical_run_id"]:
            raise ValueError("RESUME_IDENTITY_MISMATCH")
        if previous_checkpoint["execution_session_id"] == config["execution_session_id"]:
            raise ValueError("NEW_OWNER_EXECUTION_SESSION_REQUIRED")
    callback = PartialCheckpointCallback(config, binding, observer)
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for kind in (signal.SIGTERM, signal.SIGINT):
            previous[kind] = signal.signal(kind, callback.request_signal)
    try:
        if observer is not None:
            observer.emit(
                "PREEMPTION_POLICY",
                capability=CAPABILITY,
                logical_run_id=config["logical_run_id"],
                execution_session_id=config["execution_session_id"],
                round_offset=0,
                restart_from_round_zero=True,
            )
            if previous_checkpoint is not None:
                observer.emit(
                    "MODEL_RESTARTED_AFTER_PREEMPTION",
                    previous_pod_id=previous_checkpoint["pod_id"],
                    new_pod_id=config["pod_id"],
                    previous_checkpoint_iteration=previous_checkpoint["completed_rounds"],
                    checkpoint_sha256=previous_checkpoint["checkpoint_sha256"],
                    restart_round=0,
                    reason=CAPABILITY,
                )
        yield callback
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify"])
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--expect-identities", required=True, type=Path)
    parser.add_argument("--request-id")
    args = parser.parse_args()
    result = verify_partial(args.checkpoint)
    if result["binding"].get("scientific_ids") != read(args.expect_identities):
        raise ValueError("RESUME_IDENTITY_MISMATCH")
    if args.request_id and result.get("request_id") != args.request_id:
        raise ValueError("CHECKPOINT_REQUEST_ID_MISMATCH")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "logical_run_id",
                    "execution_session_id",
                    "completed_rounds",
                    "best_iteration",
                    "best_validation_rmse",
                    "checkpoint_sha256",
                    "checkpoint_path",
                    "request_id",
                    "timestamp",
                    "resume_capability",
                    "cache_retained",
                    "native_parse_verified",
                    "verification",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
