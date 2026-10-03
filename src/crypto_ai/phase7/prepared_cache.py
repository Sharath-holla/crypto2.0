from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.config import stable_hash
from crypto_ai.phase7.folds import MultiAssetFoldData
from crypto_ai.phase7.models import PreparedArchitectureInputs
from crypto_ai.phase7.runtime import CacheMode, emit_event, memory_snapshot

PREPARED_CACHE_SCHEMA = "phase7_prepared_matrix_cache_v1"
PREPROCESSING_VERSION = "phase7_train_finite_filter_v1"


class PreparedCacheMissError(LookupError):
    pass


class PreparedCacheValidationError(ValueError):
    pass


class PreparedCacheCorruptError(PreparedCacheValidationError):
    pass


class PreparedCacheIdentityError(PreparedCacheValidationError):
    pass


class PreparedCacheReadOnlyError(RuntimeError):
    pass


class PreparedCacheCapacityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedTrainingSegments:
    fold_id: str
    research_view: str
    feature_columns: tuple[str, ...]
    target_column: str
    train: pa.Table
    validation: pa.Table
    calibration_a: pa.Table
    calibration_b: pa.Table
    model_inputs: PreparedArchitectureInputs


@dataclass(frozen=True, slots=True)
class CachedPreparedData:
    cache_id: str
    fold: MultiAssetFoldData
    prepared: PreparedTrainingSegments


def prepared_cache_id(identity: dict[str, Any]) -> str:
    return stable_hash(identity, length=64)


def _write_table(path: Path, table: pa.Table) -> None:
    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)


def _read_table(path: Path) -> pa.Table:
    with pa.memory_map(str(path), "r") as source, ipc.open_file(source) as reader:
        return reader.read_all()


def _symbol_array(values: np.ndarray) -> np.ndarray:
    strings = [str(value) for value in np.asarray(values, dtype=object)]
    width = max((len(value) for value in strings), default=1)
    return np.asarray(strings, dtype=f"<U{width}")


def _fsync_file(path: Path) -> None:
    if os.name == "nt":
        # The production target is Linux. Windows Python can expose file
        # descriptors that do not support fsync; close-on-write plus atomic
        # replace remains the portable local-development guarantee.
        return
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def capacity_projection(current_bytes: int, incoming_bytes: int) -> int:
    """Current excludes the incoming directory; equality with the cap is allowed."""
    if min(current_bytes, incoming_bytes) < 0:
        raise ValueError("cache capacity byte counts must be nonnegative")
    return current_bytes + incoming_bytes


def cache_max_bytes_from_environment() -> int | None:
    value = os.environ.get("PHASE7_CACHE_MAX_GB", "").strip()
    if not value:
        return None
    gigabytes = float(value)
    if not math.isfinite(gigabytes) or gigabytes <= 0:
        raise ValueError("PHASE7_CACHE_MAX_GB must be positive when configured")
    return int(gigabytes * 1024**3)


def cache_size_report(root: Path) -> dict[str, Any]:
    """Report durable cache size without treating temp/quarantine dirs as entries."""

    resolved = root.resolve()
    entries: list[dict[str, Any]] = []
    if resolved.is_dir():
        for path in sorted(resolved.iterdir(), key=lambda item: item.name):
            if (
                path.is_dir()
                and len(path.name) == 64
                and all(character in "0123456789abcdef" for character in path.name)
            ):
                entries.append({"cache_id": path.name, "bytes": _directory_size(path)})
    published = sum(int(item["bytes"]) for item in entries)
    total = _directory_size(resolved) if resolved.is_dir() else 0
    maximum = cache_max_bytes_from_environment()
    return {
        "root": str(resolved),
        "entries": entries,
        "entry_count": len(entries),
        "total_bytes": total,
        "published_bytes": published,
        "temporary_and_quarantine_bytes": total - published,
        "configured_max_bytes": maximum,
        "remaining_bytes": None if maximum is None else maximum - total,
    }


def referenced_cache_ids(*roots: Path) -> set[str]:
    """Conservatively discover cache IDs mentioned by artifact/checkpoint JSON."""

    referenced: set[str] = set()
    for root in roots:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise PreparedCacheValidationError(f"reference root is not readable: {resolved}")
        for path in resolved.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                # Cleanup is fail-closed: an unreadable JSON file means the
                # operator must repair or move it before deleting any cache.
                raise PreparedCacheValidationError(
                    f"cannot prove cache references because JSON is invalid: {path}"
                ) from exc
            stack: list[Any] = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    cache_id = value.get("prepared_cache_id")
                    if isinstance(cache_id, str) and cache_id != "DISABLED":
                        referenced.add(cache_id)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
    return referenced


def cleanup_cache_entries(
    root: Path,
    cache_ids: tuple[str, ...],
    *,
    reference_roots: tuple[Path, ...],
    offline: bool = False,
) -> list[str]:
    """Delete explicitly named, unreferenced cache entries under ``root`` only."""

    resolved_root = root.resolve()
    if not offline or not reference_roots:
        raise PreparedCacheReadOnlyError("cleanup requires offline mode and reference roots")
    if not resolved_root.is_dir():
        raise PreparedCacheValidationError(f"cache root is not a directory: {resolved_root}")
    protected_ids = referenced_cache_ids(*reference_roots)
    removed: list[str] = []
    targets: list[tuple[str, Path]] = []
    for cache_id in dict.fromkeys(cache_ids):
        if len(cache_id) != 64 or any(
            character not in "0123456789abcdef" for character in cache_id
        ):
            raise ValueError(f"invalid prepared-cache ID: {cache_id!r}")
        if cache_id in protected_ids:
            raise PreparedCacheReadOnlyError(
                f"prepared cache {cache_id} is referenced by an artifact/checkpoint"
            )
        candidate = resolved_root / cache_id
        target = candidate.resolve()
        if candidate.is_symlink() or target.name != cache_id:
            raise ValueError("prepared-cache cleanup refuses aliased or symlink entries")
        if target.parent != resolved_root:
            raise ValueError("prepared-cache cleanup target escaped the configured root")
        if target.exists():
            if not target.is_dir():
                raise PreparedCacheValidationError(f"cache entry is not a directory: {target}")
            targets.append((cache_id, target))
    # The operator must stop training first. A global publication lock also
    # serializes deletion with writers; validate all targets before deleting.
    with PreparedDataCache(resolved_root, "auto")._publication_lock("publication"):
        protected_ids = referenced_cache_ids(*reference_roots)
        if protected_ids.intersection(cache_ids):
            raise PreparedCacheReadOnlyError("cache became referenced before cleanup")
        for cache_id, target in targets:
            shutil.rmtree(target)
            removed.append(cache_id)
    if removed:
        _fsync_directory(resolved_root)
    return removed


class PreparedDataCache:
    def __init__(self, root: Path, mode: CacheMode) -> None:
        self.root = root.resolve()
        self.mode = mode

    def cache_path(self, identity: dict[str, Any]) -> Path:
        return self.root / prepared_cache_id(identity)

    def open_published(self, identity: dict[str, Any], plan: FoldPlan) -> CachedPreparedData:
        """Validate a just-published entry, independently of lookup/rebuild policy."""
        return self._load_validated(self.cache_path(identity), identity, plan)

    @contextmanager
    def _publication_lock(self, cache_id: str, *, timeout_seconds: float = 60.0) -> Iterator[None]:
        lock = self.root / f".{cache_id}.lock"
        deadline = time.monotonic() + timeout_seconds
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for prepared-cache lock: {lock}"
                    ) from exc
                time.sleep(0.05)
        try:
            os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
            os.fsync(descriptor)
            yield
        finally:
            os.close(descriptor)
            lock.unlink(missing_ok=True)

    def _move_directory(self, source: Path, destination: Path) -> None:
        if source.parent != self.root or destination.parent != self.root:
            raise ValueError("prepared-cache directory move escaped the configured cache root")
        if destination.exists():
            raise FileExistsError(destination)
        try:
            source.rename(destination)
        except OSError:
            # Windows cannot use os.replace() for non-empty directories. The
            # publication lock guarantees a single writer, and shutil.move()
            # is used only while the destination is known not to exist.
            shutil.move(str(source), str(destination))
        _fsync_directory(self.root)

    def _quarantine(self, path: Path, cache_id: str) -> Path:
        quarantine = self.root / f".{cache_id}.invalid.{uuid.uuid4().hex}"
        self._move_directory(path, quarantine)
        emit_event("CACHE_QUARANTINED", cache_id=cache_id, path=quarantine)
        return quarantine

    def load(self, identity: dict[str, Any], plan: FoldPlan) -> CachedPreparedData:
        cache_id = prepared_cache_id(identity)
        path = self.root / cache_id
        emit_event("CACHE_LOOKUP", cache_id=cache_id, path=path, mode=self.mode)
        if self.mode in {"disabled", "rebuild"}:
            emit_event("CACHE_MISS", cache_id=cache_id)
            raise PreparedCacheMissError(f"prepared cache is absent: {path}")
        if not path.is_dir():
            emit_event("CACHE_MISS", cache_id=cache_id)
            if self.mode == "read_only":
                raise PreparedCacheReadOnlyError(f"read_only prepared cache is absent: {path}")
            raise PreparedCacheMissError(f"prepared cache is absent: {path}")
        try:
            result = self._load_validated(path, identity, plan)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            emit_event("CACHE_REJECTED", cache_id=cache_id, reason=str(exc))
            validation_error = (
                exc
                if isinstance(exc, PreparedCacheValidationError)
                else PreparedCacheCorruptError(
                    f"prepared cache {cache_id} failed validation: {exc}"
                )
            )
            if self.mode == "read_only":
                raise PreparedCacheReadOnlyError(
                    f"read_only prepared cache {cache_id} is invalid: {exc}"
                ) from exc
            with self._publication_lock("publication"):
                if path.exists():
                    try:
                        return self._load_validated(path, identity, plan)
                    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                        self._quarantine(path, cache_id)
            raise PreparedCacheMissError(
                f"prepared cache {cache_id} was invalid and quarantined"
            ) from validation_error
        emit_event("CACHE_HIT", cache_id=cache_id, **memory_snapshot())
        return result

    def _load_validated(
        self, path: Path, identity: dict[str, Any], plan: FoldPlan
    ) -> CachedPreparedData:
        manifest_path = path / "manifest.json"
        marker_path = path / "CACHE_COMPLETE"
        if not manifest_path.is_file() or not marker_path.is_file():
            raise PreparedCacheCorruptError("manifest or completion marker is missing")
        manifest_sha = file_sha256(manifest_path)
        if marker_path.read_text(encoding="ascii").strip() != manifest_sha:
            raise PreparedCacheCorruptError("completion marker does not match manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or any(
            not isinstance(manifest.get(name), dict)
            for name in ("files", "arrays", "tables", "fold_metadata")
        ):
            raise PreparedCacheCorruptError("cache manifest has malformed metadata sections")
        cache_id = prepared_cache_id(identity)
        if (
            manifest.get("schema_version") != PREPARED_CACHE_SCHEMA
            or manifest.get("cache_id") != cache_id
            or manifest.get("identity") != identity
        ):
            raise PreparedCacheIdentityError("cache identity mismatch")
        expected_arrays = {
            "train_x.npy",
            "validation_x.npy",
            "train_y.npy",
            "validation_y.npy",
            "train_symbols.npy",
            "validation_symbols.npy",
            "calibration_symbols.npy",
        }
        expected_tables = {
            "train.arrow",
            "validation.arrow",
            "calibration_a.arrow",
            "calibration_b.arrow",
            "test.arrow",
        }
        if (
            set(manifest["arrays"]) != expected_arrays
            or set(manifest["tables"]) != expected_tables
            or set(manifest["files"]) != expected_arrays | expected_tables
        ):
            raise PreparedCacheCorruptError("cache file inventory is incomplete or unexpected")
        for name, record in manifest["files"].items():
            target = path / name
            if not target.is_file() or file_sha256(target) != record["sha256"]:
                raise PreparedCacheCorruptError(f"checksum mismatch: {name}")

        arrays: dict[str, np.ndarray] = {}
        for name, record in manifest["arrays"].items():
            array = np.load(path / name, mmap_mode="r", allow_pickle=False)
            if list(array.shape) != record["shape"] or str(array.dtype) != record["dtype"]:
                raise PreparedCacheCorruptError(f"array shape/dtype mismatch: {name}")
            arrays[name] = array
        for name in ("train_x.npy", "validation_x.npy", "train_y.npy", "validation_y.npy"):
            if arrays[name].dtype != np.float64:
                raise PreparedCacheCorruptError(f"scientific matrix is not float64: {name}")

        tables = {
            name.removesuffix(".arrow"): _read_table(path / name) for name in manifest["tables"]
        }
        for name, table in tables.items():
            expected_rows = manifest["tables"][f"{name}.arrow"]["rows"]
            if table.num_rows != expected_rows:
                raise PreparedCacheCorruptError(f"table row count mismatch: {name}")
            if "feature_time" not in table.column_names:
                raise PreparedCacheCorruptError(f"table lacks feature_time: {name}")
            if str(table.schema) != manifest["tables"][f"{name}.arrow"]["schema"]:
                raise PreparedCacheCorruptError(f"table schema mismatch: {name}")

        metadata = manifest["fold_metadata"]
        if metadata["fold_id"] != plan.fold_id:
            raise PreparedCacheIdentityError("fold plan identity mismatch")
        fold = MultiAssetFoldData(
            plan=plan,
            train=tables["train"],
            validation=tables["validation"],
            calibration_a=tables["calibration_a"],
            calibration_b=tables["calibration_b"],
            _test=tables["test"],
            eligibility_manifest=metadata["eligibility_manifest"],
            cluster_mapping={
                str(key): int(value) for key, value in metadata["cluster_mapping"].items()
            },
            liquidity_tiers={
                str(key): str(value) for key, value in metadata["liquidity_tiers"].items()
            },
            age_buckets={str(key): str(value) for key, value in metadata["age_buckets"].items()},
            research_view=metadata["research_view"],
            report=metadata["report"],
        )
        feature_columns = tuple(identity["feature_columns"])
        target_column = str(identity["target_column"])
        prepared = PreparedTrainingSegments(
            fold_id=plan.fold_id,
            research_view=fold.research_view,
            feature_columns=feature_columns,
            target_column=target_column,
            train=tables["train"],
            validation=tables["validation"],
            calibration_a=tables["calibration_a"],
            calibration_b=tables["calibration_b"],
            model_inputs=PreparedArchitectureInputs(
                feature_columns=feature_columns,
                target_column=target_column,
                train_x=arrays["train_x.npy"],
                validation_x=arrays["validation_x.npy"],
                train_y=arrays["train_y.npy"],
                validation_y=arrays["validation_y.npy"],
                train_symbols=np.asarray(arrays["train_symbols.npy"], dtype=object),
                validation_symbols=np.asarray(arrays["validation_symbols.npy"], dtype=object),
                calibration_symbols=np.asarray(arrays["calibration_symbols.npy"], dtype=object),
            ),
        )
        if prepared.model_inputs.train_x.shape != (
            prepared.train.num_rows,
            len(feature_columns),
        ):
            raise PreparedCacheCorruptError("train matrix dimensions do not match table")
        if prepared.model_inputs.validation_x.shape != (
            prepared.validation.num_rows,
            len(feature_columns),
        ):
            raise PreparedCacheCorruptError("validation matrix dimensions do not match table")
        for segment in ("train", "validation"):
            row_count = tables[segment].num_rows
            for name in (f"{segment}_y.npy", f"{segment}_symbols.npy"):
                if arrays[name].shape != (row_count,):
                    raise PreparedCacheCorruptError(f"vector dimensions do not match table: {name}")
            if not np.all(np.isfinite(arrays[f"{segment}_x.npy"])) or not np.all(
                np.isfinite(arrays[f"{segment}_y.npy"])
            ):
                raise PreparedCacheCorruptError(f"cached {segment} matrix/target is not finite")
        if arrays["calibration_symbols.npy"].shape != (prepared.calibration_a.num_rows,):
            raise PreparedCacheCorruptError("calibration symbol dimensions do not match table")
        return CachedPreparedData(cache_id, fold, prepared)

    def write(
        self,
        identity: dict[str, Any],
        fold: MultiAssetFoldData,
        prepared: PreparedTrainingSegments,
    ) -> Path | None:
        if self.mode in {"disabled", "read_only"}:
            if self.mode == "read_only":
                raise PreparedCacheReadOnlyError("read_only cache mode forbids cache creation")
            return None
        self.root.mkdir(parents=True, exist_ok=True)
        cache_id = prepared_cache_id(identity)
        final = self.root / cache_id
        temporary = self.root / f".{cache_id}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        maximum = cache_max_bytes_from_environment()
        if final.exists() and self.mode != "rebuild":
            try:
                self._load_validated(final, identity, fold.plan)
            except (OSError, ValueError, KeyError, TypeError):
                pass  # Publication still quarantines invalid evidence under the lock.
            else:
                return final
        # Size Arrow IPC without materializing another serialized buffer. Reserve
        # manifest/NPY headers as well; final publication also checks exact bytes.
        incoming = 64 * 1024
        for table in (
            prepared.train,
            prepared.validation,
            prepared.calibration_a,
            prepared.calibration_b,
            fold._test,
        ):
            sink = pa.MockOutputStream()
            with ipc.new_file(sink, table.schema) as writer:
                writer.write_table(table)
            incoming += sink.size()
        inputs = prepared.model_inputs
        incoming += sum(
            array.nbytes
            for array in (inputs.train_x, inputs.validation_x, inputs.train_y, inputs.validation_y)
        )
        for symbols in (
            inputs.train_symbols,
            inputs.validation_symbols,
            inputs.calibration_symbols,
        ):
            width = max((len(str(item)) for item in symbols), default=1)
            incoming += len(symbols) * width * 4
        current = int(cache_size_report(self.root)["total_bytes"])
        projected = capacity_projection(current, incoming)
        if maximum is not None and projected > maximum:
            raise PreparedCacheCapacityError(
                f"prepared-cache construction would exceed capacity: current={current}, "
                f"incoming_estimate={incoming}, projected={projected}, maximum={maximum}"
            )
        if shutil.disk_usage(self.root).free < incoming:
            raise PreparedCacheCapacityError(
                "insufficient free disk for prepared-cache construction"
            )
        emit_event("CACHE_BUILD_START", cache_id=cache_id, path=final, **memory_snapshot())
        temporary.mkdir()
        try:
            table_values = {
                "train.arrow": prepared.train,
                "validation.arrow": prepared.validation,
                "calibration_a.arrow": prepared.calibration_a,
                "calibration_b.arrow": prepared.calibration_b,
                "test.arrow": fold._test,
            }
            for name, table in table_values.items():
                _write_table(temporary / name, table)
            input_values = prepared.model_inputs
            array_values = {
                "train_x.npy": np.asarray(input_values.train_x, dtype=np.float64),
                "validation_x.npy": np.asarray(input_values.validation_x, dtype=np.float64),
                "train_y.npy": np.asarray(input_values.train_y, dtype=np.float64),
                "validation_y.npy": np.asarray(input_values.validation_y, dtype=np.float64),
                "train_symbols.npy": _symbol_array(input_values.train_symbols),
                "validation_symbols.npy": _symbol_array(input_values.validation_symbols),
                "calibration_symbols.npy": _symbol_array(input_values.calibration_symbols),
            }
            for name, array in array_values.items():
                np.save(temporary / name, array, allow_pickle=False)
            data_files = sorted(table_values) + sorted(array_values)
            files = {name: {"sha256": file_sha256(temporary / name)} for name in data_files}
            manifest = {
                "schema_version": PREPARED_CACHE_SCHEMA,
                "cache_id": cache_id,
                "identity": identity,
                "files": files,
                "arrays": {
                    name: {"shape": list(value.shape), "dtype": str(value.dtype)}
                    for name, value in array_values.items()
                },
                "tables": {
                    name: {"rows": value.num_rows, "schema": str(value.schema)}
                    for name, value in table_values.items()
                },
                "fold_metadata": {
                    "fold_id": fold.plan.fold_id,
                    "research_view": fold.research_view,
                    "eligibility_manifest": fold.eligibility_manifest,
                    "cluster_mapping": fold.cluster_mapping,
                    "liquidity_tiers": fold.liquidity_tiers,
                    "age_buckets": fold.age_buckets,
                    "report": fold.report,
                },
            }
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            for name in data_files + ["manifest.json"]:
                _fsync_file(temporary / name)
            (temporary / "CACHE_COMPLETE").write_text(
                file_sha256(manifest_path) + "\n", encoding="ascii", newline="\n"
            )
            _fsync_file(temporary / "CACHE_COMPLETE")
            _fsync_directory(temporary)
            with self._publication_lock("publication"):
                backup: Path | None = None
                if final.exists():
                    if self.mode != "rebuild":
                        try:
                            self._load_validated(final, identity, fold.plan)
                        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                            self._quarantine(final, cache_id)
                        else:
                            return final
                    else:
                        backup = self.root / f".{cache_id}.old.{uuid.uuid4().hex}"
                        self._move_directory(final, backup)
                maximum = cache_max_bytes_from_environment()
                if maximum is not None:
                    current = int(cache_size_report(self.root)["total_bytes"])
                    incoming_bytes = _directory_size(temporary)
                    projected = capacity_projection(current - incoming_bytes, incoming_bytes)
                    if projected > maximum:
                        if backup is not None and backup.exists():
                            self._move_directory(backup, final)
                        raise PreparedCacheCapacityError(
                            "prepared-cache publication would exceed PHASE7_CACHE_MAX_GB: "
                            f"projected={projected} bytes, maximum={maximum} bytes"
                        )
                try:
                    self._move_directory(temporary, final)
                    self._load_validated(final, identity, fold.plan)
                except Exception:
                    if final.exists():
                        self._quarantine(final, cache_id)
                    if backup is not None and backup.exists():
                        self._move_directory(backup, final)
                    raise
                if backup is not None and backup.exists():
                    shutil.rmtree(backup)
                    _fsync_directory(self.root)
            emit_event("CACHE_BUILD_DONE", cache_id=cache_id, path=final, **memory_snapshot())
            return final
        finally:
            if temporary.exists():
                # The target is an explicitly created child of cache root.
                shutil.rmtree(temporary)
