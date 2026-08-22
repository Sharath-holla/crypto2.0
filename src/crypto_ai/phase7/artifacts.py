from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.config import PHASE7_VERSION, stable_hash


def atomic_json(path: Path, payload: dict[str, Any], *, immutable: bool = True) -> Path:
    path = path.resolve()
    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    if path.exists():
        if immutable and path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"Refusing to overwrite different artifact: {path}")
        if immutable:
            return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def atomic_parquet(path: Path, table: pa.Table) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary, compression="zstd", write_statistics=True)
        checksum = file_sha256(temporary)
        if path.exists():
            if file_sha256(path) != checksum:
                raise FileExistsError(f"Refusing to overwrite different Parquet artifact: {path}")
            return path
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


@dataclass(frozen=True, slots=True)
class CheckpointStore:
    root: Path
    run_identity: str

    def checkpoint_path(self, stage: str) -> Path:
        return self.root.resolve() / self.run_identity / f"{stage}.json"

    def is_complete(
        self,
        stage: str,
        *,
        expected_metadata: dict[str, Any] | None = None,
    ) -> bool:
        path = self.checkpoint_path(stage)
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if (
            payload.get("status") != "complete"
            or payload.get("run_identity") != self.run_identity
            or payload.get("stage") != stage
        ):
            return False
        if expected_metadata is not None and payload.get("metadata") != expected_metadata:
            return False
        for item in payload.get("files", []):
            target = Path(item["path"])
            if not target.exists() or file_sha256(target) != item["sha256"]:
                return False
        identity_payload = dict(payload)
        claimed = identity_payload.pop("checkpoint_hash", None)
        return claimed == stable_hash(identity_payload)

    def complete(self, stage: str, files: list[Path], metadata: dict[str, Any]) -> Path:
        records = [
            {"path": str(path.resolve()), "sha256": file_sha256(path.resolve())}
            for path in sorted(files, key=lambda item: str(item))
        ]
        payload: dict[str, Any] = {
            "phase7_version": PHASE7_VERSION,
            "run_identity": self.run_identity,
            "stage": stage,
            "status": "complete",
            "completed_at": datetime.now(UTC).isoformat(),
            "files": records,
            "metadata": metadata,
        }
        payload["checkpoint_hash"] = stable_hash(payload)
        return atomic_json(self.checkpoint_path(stage), payload)


def _total_ram_bytes() -> int | None:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
        return None
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else None
    page_count = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    return int(page_size * page_count) if page_size and page_count else None


def resource_snapshot(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path.resolve())
    ram = _total_ram_bytes()
    return {
        "cpu_count": os.cpu_count(),
        "ram_gb": ram / 1024**3 if ram is not None else None,
        "disk_free_gb": usage.free / 1024**3,
        "disk_total_gb": usage.total / 1024**3,
        "python_version": sys.version.split()[0],
        "os": platform.platform(),
        "gpu_required": False,
    }


def write_partitioned_table(
    root: Path,
    table: pa.Table,
    *,
    symbol_column: str = "symbol",
    time_column: str = "feature_time",
) -> list[Path]:
    symbols = table.column(symbol_column).combine_chunks().to_pylist()
    times = table.column(time_column).combine_chunks().cast(pa.int64()).to_numpy()
    groups: dict[tuple[str, int], list[int]] = {}
    for index, (symbol, timestamp) in enumerate(zip(symbols, times, strict=True)):
        year = datetime.fromtimestamp(int(timestamp) / 1_000_000, tz=UTC).year
        groups.setdefault((str(symbol), year), []).append(index)
    written: list[Path] = []
    for (symbol, year), indices in sorted(groups.items()):
        partition = table.take(pa.array(indices, type=pa.int64()))
        partition_times = partition.column(time_column).combine_chunks().cast(pa.int64())
        partition_identity = {
            "symbol": symbol,
            "year": year,
            "row_count": partition.num_rows,
            "first_time_us": partition_times[0].as_py(),
            "last_time_us": partition_times[-1].as_py(),
            "schema": str(partition.schema),
        }
        digest = stable_hash(partition_identity, length=20)
        path = root / f"symbol={symbol}" / f"year={year}" / f"part-{digest}.parquet"
        written.append(atomic_parquet(path, partition))
    return written


def scan_partitioned_batches(
    root: Path,
    *,
    columns: list[str] | None = None,
    batch_size: int = 250_000,
) -> Iterator[pa.RecordBatch]:
    dataset = ds.dataset(root.resolve(), format="parquet", partitioning="hive")
    yield from dataset.to_batches(columns=columns, batch_size=batch_size)
