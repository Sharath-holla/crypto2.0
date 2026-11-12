"""Causal feature-only context, independent of future target values and availability.

The projection uses the producer's existing scalar/rolling helpers and contiguous
segments. It computes only the six inputs needed to rebind fold context, preserving
all candle keys (including warmup NaNs). Gold remains the target authority.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import atomic_json
from crypto_ai.phase7.config import FEATURE_VERSION, FeatureConfig
from crypto_ai.phase7.features import (
    FOLD_CONTEXT_SOURCE_COLUMNS,
    _contiguous_segments,
    _float_column,
    _lag_return,
    _rolling_mean,
    _rolling_std,
    _safe_divide,
)

SIDECAR_SCHEMA = "phase7_feature_context_sidecar_v1"
SIDECAR_ENV = "PHASE7_FEATURE_CONTEXT_SIDECAR"
CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)


def context_source_projection(candles: pa.Table, config: FeatureConfig) -> pa.Table:
    """One context-source row per observed 5m candle; never read a label column."""
    table = candles.sort_by([("symbol", "ascending"), ("open_time", "ascending")])
    symbols = np.asarray(table["symbol"].to_pylist(), dtype=object)
    times = table["open_time"].cast(pa.timestamp("us", tz="UTC")).cast(pa.int64()).to_numpy()
    close = _float_column(table, "close")
    quote = _float_column(table, "quote_volume")
    trades = _float_column(table, "trade_count")
    buy = _float_column(table, "taker_buy_quote_volume")
    if np.any(quote < 0) or np.any(buy < 0) or np.any(buy > quote):
        raise ValueError("invalid quote/taker volume relationship")
    arrays = {name: np.full(len(times), np.nan) for name in FOLD_CONTEXT_SOURCE_COLUMNS[2:]}
    for symbol in np.unique(symbols):
        rows = np.flatnonzero(symbols == symbol)
        if np.any(np.diff(times[rows]) <= 0):
            raise ValueError("duplicate or out-of-order candle key")
        for segment in _contiguous_segments(times[rows], 300_000_000):
            selected = rows[segment]
            returns = _lag_return(close[selected], 1)
            logs = np.full(len(selected), np.nan)
            valid = np.isfinite(returns) & (returns > -1)
            logs[valid] = np.log1p(returns[valid])
            share = _safe_divide(buy[selected], quote[selected])
            values = (
                returns,
                _rolling_std(logs, 12),
                share - (1.0 - share),
                _rolling_mean(quote[selected], config.liquidity_window_rows),
                _rolling_std(logs, config.seven_day_volatility_rows),
                _safe_divide(
                    trades[selected],
                    _rolling_mean(trades[selected], config.liquidity_window_rows),
                ),
            )
            for name, values_for_segment in zip(arrays, values, strict=True):
                arrays[name][selected] = values_for_segment
    return pa.table(
        {
            "symbol": pa.array(symbols.tolist()),
            "feature_time": pa.array(times + 300_000_000, type=pa.timestamp("us", tz="UTC")),
            **{name: pa.array(values) for name, values in arrays.items()},
        }
    )


def sidecar_code_identity() -> dict[str, str]:
    root = Path(__file__).parent
    return {name: file_sha256(root / name) for name in ("context_sidecar.py", "features.py")}


def write_sidecar(root: Path, parts: Iterable[pa.Table], identity: Mapping[str, Any]) -> Path:
    """Publish an isolated immutable sidecar; an interrupted build has no completion marker."""
    required = {
        "gold_manifest_sha256",
        "registry_hash",
        "universe_hash",
        "silver_manifests",
        "configuration_hash",
        "registry_sha256",
        "universe_sha256",
    }
    if not required <= identity.keys():
        raise ValueError("sidecar missing input identities")
    root.mkdir(parents=True, exist_ok=False)
    records = []
    last_by_symbol: dict[str, int] = {}
    for index, table in enumerate(parts):
        if tuple(table.column_names) != FOLD_CONTEXT_SOURCE_COLUMNS:
            raise ValueError("sidecar must contain only the declared feature-context source")
        table = table.sort_by([("symbol", "ascending"), ("feature_time", "ascending")])
        if not table.num_rows:
            continue
        if table["feature_time"].null_count or table["symbol"].null_count:
            raise ValueError("null sidecar key")
        times = table["feature_time"].cast(pa.int64()).to_numpy()
        symbols = np.asarray(table["symbol"].to_pylist(), dtype=object)
        if table.schema.field("feature_time").type != pa.timestamp("us", tz="UTC"):
            raise ValueError("sidecar requires UTC microsecond timestamps")
        if np.any(times >= int(CUTOFF.timestamp() * 1_000_000)):
            raise ValueError("sidecar reaches forbidden July/August range")
        for symbol in np.unique(symbols):
            values = times[symbols == symbol]
            if np.any(np.diff(values) <= 0) or values[0] <= last_by_symbol.get(str(symbol), -1):
                raise ValueError("duplicate/overlapping sidecar keys")
            last_by_symbol[str(symbol)] = int(values[-1])
        for name in FOLD_CONTEXT_SOURCE_COLUMNS[2:]:
            if table.schema.field(name).type != pa.float64():
                raise ValueError("sidecar values must be float64")
            if np.isinf(table[name].to_numpy()).any():
                raise ValueError("infinite sidecar value")
        path = root / f"part-{index:04d}.parquet"
        pq.write_table(table, path, compression="zstd")
        records.append(
            {
                "path": path.name,
                "sha256": file_sha256(path),
                "rows": table.num_rows,
                "first_us": int(times.min()),
                "last_us": int(times.max()),
                "symbols": sorted(set(symbols.tolist())),
                "schema": str(table.schema),
            }
        )
    if not records:
        raise ValueError("empty sidecar")
    manifest = {
        "schema": SIDECAR_SCHEMA,
        "context_source": "FEATURE_CONTEXT_SIDECAR",
        "feature_version": FEATURE_VERSION,
        "code_identity": sidecar_code_identity(),
        "identity": dict(identity),
        "partitions": records,
        "rows": sum(r["rows"] for r in records),
        "research_cutoff_exclusive": CUTOFF.isoformat(),
        "holdout": {"status": "LOCKED_UNUSED", "used": False, "evaluation_authorized": False},
        "july_2026_used": False,
    }
    path = root / "manifest.json"
    atomic_json(path, manifest)
    (root / "SIDECAR_COMPLETE").write_text(file_sha256(path) + "\n", encoding="utf-8")
    return path


def read_sidecar(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    marker = path.parent / "SIDECAR_COMPLETE"
    if not marker.is_file() or marker.read_text().strip() != file_sha256(path):
        raise ValueError("SIDECAR_INCOMPLETE_OR_HASH_MISMATCH")
    if (
        manifest.get("schema") != SIDECAR_SCHEMA
        or manifest.get("feature_version") != FEATURE_VERSION
    ):
        raise ValueError("SIDECAR_SCHEMA_OR_FEATURE_MISMATCH")
    if manifest.get("code_identity") != sidecar_code_identity():
        raise ValueError("SIDECAR_CODE_IDENTITY_MISMATCH")
    if (
        manifest.get("holdout")
        != {
            "status": "LOCKED_UNUSED",
            "used": False,
            "evaluation_authorized": False,
        }
        or manifest.get("july_2026_used") is not False
    ):
        raise ValueError("SIDECAR_HOLDOUT_VIOLATION")
    return manifest


def sidecar_cache_identity(
    path: Path,
    *,
    gold_manifest_sha256: str,
    registry_hash: str,
    universe_hash: str,
    configuration_hash: str | None = None,
) -> dict[str, str]:
    manifest = read_sidecar(path)
    expected_inputs = {
        "gold_manifest_sha256": gold_manifest_sha256,
        "registry_hash": registry_hash,
        "universe_hash": universe_hash,
    }
    if configuration_hash is not None:
        expected_inputs["configuration_hash"] = configuration_hash
    for name, expected in expected_inputs.items():
        if manifest["identity"].get(name) != expected:
            raise ValueError(f"SIDECAR_INPUT_IDENTITY_MISMATCH: {name}")
    return {"source": "FEATURE_CONTEXT_SIDECAR", "manifest_sha256": file_sha256(path)}


def load_sidecar_source(path: Path, start: datetime, end: datetime) -> pa.Table:
    manifest = read_sidecar(path)
    if not start < end <= CUTOFF:
        raise ValueError("invalid or forbidden sidecar window")
    first, last = int(start.timestamp() * 1_000_000), int(end.timestamp() * 1_000_000)
    tables = []
    for record in manifest["partitions"]:
        if record["last_us"] < first or record["first_us"] >= last:
            continue
        partition = (path.parent / record["path"]).resolve()
        if not partition.is_relative_to(path.parent.resolve()):
            raise ValueError("sidecar partition escapes root")
        if file_sha256(partition) != record["sha256"]:
            raise ValueError("SIDECAR_PARTITION_HASH_MISMATCH")
        table = pq.ParquetFile(partition).read()
        if (
            table.num_rows != record["rows"]
            or tuple(table.column_names) != FOLD_CONTEXT_SOURCE_COLUMNS
        ):
            raise ValueError("SIDECAR_PARTITION_SCHEMA_OR_ROWS_MISMATCH")
        tables.append(
            table.filter(
                pc.and_(
                    pc.greater_equal(table["feature_time"], start),
                    pc.less(table["feature_time"], end),
                )
            )
        )
    if not tables:
        raise ValueError("sidecar has no rows for requested fold")
    return pa.concat_tables(tables)
