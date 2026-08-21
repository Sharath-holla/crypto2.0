from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION, schema_errors


class ImmutablePartitionError(RuntimeError):
    """Raised when a bronze partition would be silently replaced."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_candle_parquet(path: Path) -> pa.Table:
    # ParquetFile reads the file exactly as written and does not infer Hive
    # partition columns from parent directory names.
    table = pq.ParquetFile(path).read()
    errors = schema_errors(table.schema)
    if errors:
        raise ValueError(f"Invalid candle schema in {path}: {'; '.join(errors)}")
    return table


def write_immutable(
    path: Path,
    table: pa.Table,
    *,
    metadata: dict[str, str],
) -> str:
    if path.exists():
        raise ImmutablePartitionError(f"Refusing to overwrite immutable partition: {path}")
    errors = schema_errors(table.schema)
    if errors:
        raise ValueError(f"Cannot write invalid candle schema: {'; '.join(errors)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    merged_metadata = dict(table.schema.metadata or {})
    merged_metadata[b"schema_version"] = CANDLE_SCHEMA_VERSION.encode("ascii")
    for key, value in metadata.items():
        merged_metadata[key.encode("utf-8")] = value.encode("utf-8")
    table = table.replace_schema_metadata(merged_metadata)

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=["symbol", "source"],
            write_statistics=True,
        )
        if path.exists():
            raise ImmutablePartitionError(f"Partition appeared during write: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return file_sha256(path)
