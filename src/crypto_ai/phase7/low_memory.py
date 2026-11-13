"""Opt-in, output-identical low-memory execution profile for Phase 7 preparation.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-low-memory-training).

Enabled ONLY by ``PHASE7_MEMORY_PROFILE=low_memory``. With the variable absent (or ``standard``)
every caller keeps its original code path, so the existing implementation and its 64 GiB smoke
admission are unchanged.

Every function here must return exactly the values, row order, schema and dtypes of the code it
replaces; ``tests/phase7/test_low_memory_equivalence.py`` compares both paths. Nothing here
changes a feature, target, fold boundary, purge, embargo, filter decision, model parameter or the
locked holdout. The techniques are:

* fold rows read in column groups and reordered with ONE shared stable sort index, so the full
  Arrow table is never held twice (``to_table().sort_by()`` materializes a second copy);
* ``filter_rows``: a zero-copy ``slice`` when the kept rows are one contiguous run (time-sorted
  ranges, purge and embargo boundaries), otherwise the original ``Table.filter``;
* a vectorized symbol filter that returns the input unchanged when every row is eligible;
* returning freed Arrow pool memory to the operating system between stages;
* sliced fold segments spilled to local Arrow IPC files and re-opened memory-mapped
  (page-cache backed, evictable) instead of anonymous memory;
* dense float64 model matrices built in row blocks directly into ``.npy`` memmaps, which the
  prepared cache then adopts by rename instead of writing a second copy.
"""

from __future__ import annotations

import contextlib
import contextvars
import gc
import json
import os
import shutil
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

PROFILE_ENV = "PHASE7_MEMORY_PROFILE"
STANDARD = "standard"
LOW_MEMORY = "low_memory"
PROFILES = frozenset({STANDARD, LOW_MEMORY})
COLUMN_GROUP_SIZE = 16
MATRIX_BLOCK_ROWS = 131_072
SPILL_DIRECTORY_PREFIX = ".low-memory-spill-"
_US_PER_MINUTE = 60_000_000

_MATRIX_DIRECTORY: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "phase7_low_memory_matrix_directory", default=None
)
_ACTIVE_SPILL: Path | None = None


def memory_profile(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    value = env.get(PROFILE_ENV, STANDARD).strip() or STANDARD
    if value not in PROFILES:
        raise ValueError(f"UNKNOWN_MEMORY_PROFILE: {PROFILE_ENV}={value!r}")
    return value


def enabled(environ: Mapping[str, str] | None = None) -> bool:
    return memory_profile(environ) == LOW_MEMORY


def release_unused_memory() -> None:
    """Collect Python garbage and hand freed Arrow pool pages back to the OS (no semantics)."""

    gc.collect()
    pa.default_memory_pool().release_unused()


# --------------------------------------------------------------------------- row selection


def compact_variable_width(table: pa.Table) -> pa.Table:
    """Same logical table whose string/binary columns own compact buffers.

    A zero-copy slice of a variable-width column keeps parent bytes outside the selected value
    range; Arrow IPC writes those bytes, so a cache file would differ (bytewise only) from one
    written from ``Table.filter`` output. Fixed-width columns are left untouched (zero-copy).
    """

    columns = []
    changed = False
    for field, column in zip(table.schema, table.columns, strict=True):
        variable = (
            pa.types.is_string(field.type)
            or pa.types.is_large_string(field.type)
            or pa.types.is_binary(field.type)
            or pa.types.is_large_binary(field.type)
        )
        if variable and any(
            chunk.offset or chunk.buffers()[1] is not None for chunk in column.chunks
        ):
            column = pa.chunked_array(
                [
                    chunk.take(pa.array(np.arange(len(chunk), dtype=np.int64)))
                    for chunk in column.chunks
                ],
                type=field.type,
            )
            changed = True
        columns.append(column)
    return pa.Table.from_arrays(columns, schema=table.schema) if changed else table


def filter_rows(table: pa.Table, mask: Any) -> pa.Table:
    """Exactly ``table.filter(mask)`` (null mask entries drop rows), zero-copy when contiguous."""

    if isinstance(mask, pa.ChunkedArray | pa.Array):
        values = pc.fill_null(mask, False)
        values = values.to_numpy(zero_copy_only=False)
    else:
        values = np.asarray(mask)
    if values.dtype != np.bool_ or values.ndim != 1 or len(values) != table.num_rows:
        raise ValueError("row mask must be a boolean vector with one entry per row")
    kept = np.flatnonzero(values)
    if len(kept) == table.num_rows:
        return table
    if len(kept) == 0:
        return table.slice(0, 0)
    if int(kept[-1]) - int(kept[0]) + 1 == len(kept):
        return table.slice(int(kept[0]), len(kept))
    return table.filter(pa.array(values, type=pa.bool_()))


def filter_symbols(table: pa.Table, symbols: set[str]) -> pa.Table:
    """Same rows as ``phase7.folds._filter_symbols`` without a per-row Python list."""

    column = table.column("symbol")
    if pa.types.is_dictionary(column.type):
        column = column.cast(column.type.value_type)
    if not pa.types.is_string(column.type) and not pa.types.is_large_string(column.type):
        column = column.cast(pa.string())
    value_set = pa.array(sorted(str(symbol) for symbol in symbols), type=column.type)
    mask = pc.fill_null(pc.is_in(column, value_set=value_set), False)
    return filter_rows(table, mask)


def finite_rows(table: pa.Table, columns: tuple[str, ...], target: str) -> pa.Table:
    """Exactly ``training._finite``; contiguous selections stay zero-copy.

    With batch staging active (``PHASE7_STAGING_DAYS``) and a spill directory, a scattered
    selection is streamed block by block into a local IPC file and returned memory-mapped, so the
    filtered copy never sits in anonymous memory. Same rows, order and values.
    """

    names = columns + (target,)
    mask: pa.Array | pa.ChunkedArray = pc.is_finite(table.column(names[0]))
    for name in names[1:]:
        mask = pc.and_(mask, pc.is_finite(table.column(name)))
    valid = pc.fill_null(mask, False)
    if pc.all(valid).as_py() is True:
        return table
    spill = active_spill_directory()
    if spill is None or not os.environ.get("PHASE7_STAGING_DAYS", "").strip():
        return filter_rows(table, valid)
    values = valid.to_numpy(zero_copy_only=False)
    kept = np.flatnonzero(values)
    if len(kept) and int(kept[-1]) - int(kept[0]) + 1 == len(kept):
        return filter_rows(table, values)
    return stream_filter_to_file(table, values, spill)


_ADOPTABLE_TABLES: dict[int, tuple[pa.Table, Path]] = {}


def stream_filter_to_file(
    table: pa.Table, mask: np.ndarray, directory: Path, *, block_rows: int = MATRIX_BLOCK_ROWS
) -> pa.Table:
    """``table.filter(mask)`` written block by block to IPC and re-opened memory-mapped."""

    import pyarrow.ipc as ipc

    path = directory / f"filtered-{uuid.uuid4().hex}.arrow"
    schema = table.schema
    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, schema) as writer:
        wrote = False
        for start in range(0, table.num_rows, block_rows):
            block_mask = mask[start : start + block_rows]
            if not block_mask.any():
                continue
            block = table.slice(start, len(block_mask)).filter(pa.array(block_mask))
            writer.write_table(compact_variable_width(block))
            wrote = True
        if not wrote:
            writer.write_table(schema.empty_table())
    result = _read_ipc(path)
    if result.num_rows != int(mask.sum()) or result.schema != schema:
        raise RuntimeError("streamed filter does not round-trip")
    _ADOPTABLE_TABLES[id(result)] = (result, path)
    return result


def adopt_table_file(table: pa.Table, destination: Path) -> bool:
    """Move a streamed IPC file (written by this module, compact strings) into a cache entry."""

    entry = _ADOPTABLE_TABLES.get(id(table))
    spill = active_spill_directory()
    if entry is None or entry[0] is not table or spill is None:
        return False
    source = entry[1].resolve()
    if not source.is_relative_to(spill.resolve()) or not source.exists():
        return False
    os.replace(source, destination)
    del _ADOPTABLE_TABLES[id(table)]
    return True


def read_sorted_fold_rows(
    dataset: ds.Dataset,
    condition: ds.Expression,
    columns: list[str] | None,
    *,
    group_size: int = COLUMN_GROUP_SIZE,
) -> pa.Table:
    """``dataset.to_table(filter, columns).sort_by([(feature_time), (symbol)])`` in column groups.

    Arrow's sort is stable; the same ordered scan is repeated per group and every group is
    reordered with one shared index, so row order and values equal the single-table path.
    """

    names = list(dataset.schema.names) if columns is None else list(columns)
    if not names:
        raise ValueError("at least one column is required")
    keys = dataset.to_table(filter=condition, columns=["feature_time", "symbol"])
    order = pc.sort_indices(
        keys, sort_keys=[("feature_time", "ascending"), ("symbol", "ascending")]
    )
    expected_rows = keys.num_rows
    del keys
    arrays: dict[str, pa.Array] = {}
    fields: dict[str, pa.Field] = {}
    for start in range(0, len(names), group_size):
        group = names[start : start + group_size]
        part = dataset.to_table(filter=condition, columns=group)
        if part.num_rows != expected_rows:
            raise RuntimeError("fold scan returned a different row count between column groups")
        part = part.take(order)
        for name in group:
            arrays[name] = part.column(name).combine_chunks()
            fields[name] = part.schema.field(name)
        del part
        release_unused_memory()
    return pa.Table.from_arrays(
        [arrays[name] for name in names], schema=pa.schema([fields[name] for name in names])
    )


# ------------------------------------------------------------------- hardened fold slicing


def _times(table: pa.Table, column: str) -> np.ndarray:
    return table.column(column).combine_chunks().cast(pa.int64()).to_numpy()


def _range(table: pa.Table, start: datetime, end: datetime) -> pa.Table:
    values = _times(table, "feature_time")
    start_us, end_us = int(start.timestamp() * 1_000_000), int(end.timestamp() * 1_000_000)
    return filter_rows(table, (values >= start_us) & (values < end_us))


def _prepare_previous(table: pa.Table, next_start: datetime) -> tuple[pa.Table, int]:
    before = table.num_rows
    boundary_us = int(next_start.timestamp() * 1_000_000)
    kept = filter_rows(table, _times(table, "label_end_time") < boundary_us)
    return kept, before - kept.num_rows


def _embargo(table: pa.Table, start: datetime, minutes: int) -> tuple[pa.Table, int]:
    if minutes == 0:
        return table, 0
    before = table.num_rows
    embargo_end_us = int(start.timestamp() * 1_000_000) + minutes * _US_PER_MINUTE
    kept = filter_rows(table, _times(table, "feature_time") >= embargo_end_us)
    return kept, before - kept.num_rows


def slice_hardened_fold(table: pa.Table, plan: Any, schedule: Any, holdout_start: datetime) -> Any:
    """Zero-copy twin of ``phase5.folds.slice_hardened_fold`` (Phase 5 stays untouched).

    Same segments, purge (actual ``label_end_time``), embargo, size/holdout/separation checks and
    report; only ``Table.filter`` copies of contiguous runs become slices.
    """

    from crypto_ai.phase5.folds import (
        HardenedFoldData,
        _utc,
        calibration_split_time,
        check_calibration_separation,
    )

    holdout_start = _utc(holdout_start)
    if plan.test_end > holdout_start:
        raise ValueError("fold test period crosses the prospective holdout")
    split_time = calibration_split_time(plan)
    raw = {
        "train": _range(table, plan.train_start, plan.train_end),
        "validation": _range(table, plan.validation_start, plan.validation_end),
        "calibration_a": _range(table, plan.calibration_start, split_time),
        "calibration_b": _range(table, split_time, plan.calibration_end),
        "test": _range(table, plan.test_start, plan.test_end),
    }
    train, train_purged = _prepare_previous(raw["train"], plan.validation_start)
    validation, validation_purged = _prepare_previous(raw["validation"], plan.calibration_start)
    calibration_a, calibration_a_purged = _prepare_previous(raw["calibration_a"], split_time)
    calibration_b, calibration_b_purged = _prepare_previous(raw["calibration_b"], plan.test_start)
    validation, validation_embargoed = _embargo(
        validation, plan.validation_start, schedule.embargo_minutes
    )
    calibration_a, calibration_a_embargoed = _embargo(
        calibration_a, plan.calibration_start, schedule.embargo_minutes
    )
    calibration_b, calibration_b_embargoed = _embargo(
        calibration_b, split_time, schedule.embargo_minutes
    )
    test, test_embargoed = _embargo(raw["test"], plan.test_start, schedule.embargo_minutes)
    prepared = {
        "train": train,
        "validation": validation,
        "calibration_a": calibration_a,
        "calibration_b": calibration_b,
        "test": test,
    }
    too_small = {
        name: segment.num_rows
        for name, segment in prepared.items()
        if segment.num_rows < schedule.minimum_rows_per_segment
    }
    if too_small:
        raise ValueError(f"{plan.fold_id} has undersized hardened segments: {too_small}")
    holdout_us = int(holdout_start.timestamp() * 1_000_000)
    for name, segment in prepared.items():
        if np.any(_times(segment, "feature_time") >= holdout_us):
            raise ValueError(f"{name} contains prospective holdout rows")
    check_calibration_separation(calibration_a, calibration_b)

    def entry(name: str, start: datetime, end: datetime, purged: int, embargoed: int) -> dict:
        return {
            "range": [start.isoformat(), end.isoformat()],
            "before": raw[name].num_rows,
            "purged": purged,
            "embargoed": embargoed,
            "remaining": prepared[name].num_rows,
        }

    report = {
        "fold_id": plan.fold_id,
        "boundaries": plan.to_dict(),
        "calibration_split_time": split_time.isoformat(),
        "embargo_minutes": schedule.embargo_minutes,
        "segments": {
            "train": entry("train", plan.train_start, plan.train_end, train_purged, 0),
            "validation": entry(
                "validation",
                plan.validation_start,
                plan.validation_end,
                validation_purged,
                validation_embargoed,
            ),
            "calibration_a": entry(
                "calibration_a",
                plan.calibration_start,
                split_time,
                calibration_a_purged,
                calibration_a_embargoed,
            ),
            "calibration_b": entry(
                "calibration_b",
                split_time,
                plan.calibration_end,
                calibration_b_purged,
                calibration_b_embargoed,
            ),
            "test": entry("test", plan.test_start, plan.test_end, 0, test_embargoed),
        },
    }
    return HardenedFoldData(train, validation, calibration_a, calibration_b, test, report)


# ------------------------------------------------------------------------- spill to disk


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_stale_spill_directories(root: Path) -> list[str]:
    """Delete spill directories whose owning process no longer exists (same host only)."""

    removed: list[str] = []
    if not root.is_dir():
        return removed
    for candidate in root.iterdir():
        if not candidate.name.startswith(SPILL_DIRECTORY_PREFIX) or not candidate.is_dir():
            continue
        owner = candidate / "OWNER.json"
        try:
            payload = json.loads(owner.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("host") == os.uname().nodename and not _pid_alive(int(payload["pid"])):
            shutil.rmtree(candidate, ignore_errors=True)
            removed.append(candidate.name)
    return removed


@contextlib.contextmanager
def spill_session(cache_root: Path) -> Iterator[Path | None]:
    """Process-private spill directory beside the cache (same filesystem: rename-adoptable)."""

    global _ACTIVE_SPILL
    if not enabled():
        yield None
        return
    cache_root.mkdir(parents=True, exist_ok=True)
    remove_stale_spill_directories(cache_root)
    directory = cache_root / f"{SPILL_DIRECTORY_PREFIX}{os.getpid()}-{uuid.uuid4().hex[:12]}"
    directory.mkdir()
    (directory / "OWNER.json").write_text(
        json.dumps({"pid": os.getpid(), "host": os.uname().nodename, "started": time.time()}),
        encoding="utf-8",
    )
    previous, _ACTIVE_SPILL = _ACTIVE_SPILL, directory
    try:
        yield directory
    finally:
        _ACTIVE_SPILL = previous
        shutil.rmtree(directory, ignore_errors=True)


def active_spill_directory() -> Path | None:
    return _ACTIVE_SPILL if enabled() else None


def _write_ipc(path: Path, table: pa.Table) -> None:
    import pyarrow.ipc as ipc

    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)


def _read_ipc(path: Path) -> pa.Table:
    import pyarrow.ipc as ipc

    with pa.memory_map(str(path), "r") as source, ipc.open_file(source) as reader:
        return reader.read_all()


def spill_fold(fold: Any, directory: Path | None = None) -> Any:
    """Return the same MultiAssetFoldData with its five segments memory-mapped from local IPC.

    The IPC round trip is exact (same schema, values and order). Callers must drop every other
    reference to the in-memory segments for the anonymous memory to be released.
    """

    root = directory or active_spill_directory()
    if root is None:
        return fold
    target = root / f"{fold.plan.fold_id}-{uuid.uuid4().hex[:12]}"
    target.mkdir()
    names = ("train", "validation", "calibration_a", "calibration_b", "_test")
    for name in names:
        _write_ipc(target / f"{name}.arrow", getattr(fold, name))
    mapped = {name: _read_ipc(target / f"{name}.arrow") for name in names}
    for name in names:
        before, after = getattr(fold, name), mapped[name]
        if before.schema != after.schema or before.num_rows != after.num_rows:
            raise RuntimeError(f"spilled segment {name} does not round-trip")
    return replace(fold, **mapped)


def discard_spilled(fold: Any) -> None:
    """Delete a fold's spill files; live memory maps stay valid until released (POSIX)."""

    root = active_spill_directory()
    if root is None:
        return
    for directory in root.glob(f"{fold.plan.fold_id}-*"):
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------- disk-backed matrices


@contextlib.contextmanager
def matrix_storage(directory: Path | None) -> Iterator[None]:
    token = _MATRIX_DIRECTORY.set(directory)
    try:
        yield
    finally:
        _MATRIX_DIRECTORY.reset(token)


def matrix_storage_directory() -> Path | None:
    return _MATRIX_DIRECTORY.get() if enabled() else None


def build_matrix(
    table: pa.Table,
    columns: tuple[str, ...],
    directory: Path,
    floats: Callable[[pa.Table, str], np.ndarray],
    *,
    block_rows: int = MATRIX_BLOCK_ROWS,
) -> np.memmap:
    """float64 matrix identical to ``models._matrix`` written in row blocks into a .npy memmap.

    Row blocks keep every write inside one contiguous region of the row-major file; the
    column-at-a-time fill used for in-memory matrices was measured at 589 s on a memmap.
    """

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"matrix-{uuid.uuid4().hex}.npy"
    matrix = np.lib.format.open_memmap(
        path, mode="w+", dtype=np.float64, shape=(table.num_rows, len(columns))
    )
    for start in range(0, table.num_rows, block_rows):
        block = table.slice(start, block_rows)
        stop = start + block.num_rows
        for index, name in enumerate(columns):
            matrix[start:stop, index] = floats(block, name)
        if not np.all(np.isfinite(matrix[start:stop])):
            raise ValueError("Phase 7 model features must be a finite matrix")
    matrix.flush()
    return matrix


def adopt_matrix_file(array: Any, destination: Path) -> bool:
    """Move a low-memory matrix file into a cache directory instead of writing a copy.

    Only a C-contiguous float64 ``np.memmap`` created by :func:`build_matrix` inside the
    active spill directory qualifies; its bytes are exactly what ``np.save`` writes.
    """

    spill = active_spill_directory()
    if spill is None or not isinstance(array, np.memmap) or array.filename is None:
        return False
    source = Path(array.filename).resolve()
    if not source.is_relative_to(spill.resolve()) or not source.name.startswith("matrix-"):
        return False
    if array.dtype != np.float64 or not array.flags.c_contiguous or array.ndim != 2:
        return False
    array.flush()
    os.replace(source, destination)
    return True
