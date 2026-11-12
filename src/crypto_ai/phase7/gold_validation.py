from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase6.features import FEATURE_GROUPS_V3_RESEARCH, _higher_timeframe_values
from crypto_ai.phase7.config import (
    FEATURE_VERSION,
    MARKET_CONTEXT_VERSION,
    TARGET_VERSION,
)
from crypto_ai.phase7.features import (
    ANCHOR_CONTEXT_COLUMNS,
    BASE_FEATURE_COLUMNS,
    COIN_CONTEXT_COLUMNS,
    CROSS_SECTIONAL_SOURCE_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
)
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.targets import FIVE_MINUTES_US
from crypto_ai.phase7.telemetry import instrument

EXPECTED_GOLD_DATASET_ID = "gold-phase7-0cbf2910e8d96c9d19826598"
EXPECTED_GOLD_PARTITIONS = 138
EXPECTED_GOLD_ROWS = 50_352_548
RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
HOLDOUT_START = datetime(2026, 8, 1, tzinfo=UTC)
CORE20 = {
    "BTCUSDT",
    "ETHUSDT",
    "ZRXUSDT",
    "NEOUSDT",
    "FLMUSDT",
    "KNCUSDT",
    "ONTUSDT",
    "BLZUSDT",
    "HNTUSDT",
    "UNIUSDT",
    "TRXUSDT",
    "KSMUSDT",
    "COMPUSDT",
    "IOTAUSDT",
    "STORJUSDT",
    "OMGUSDT",
    "ZECUSDT",
    "FILUSDT",
    "BCHUSDT",
    "DOGEUSDT",
}


def native_feature_columns() -> tuple[str, ...]:
    values: list[str] = []
    for name in (
        BASE_FEATURE_COLUMNS
        + COIN_CONTEXT_COLUMNS
        + ANCHOR_CONTEXT_COLUMNS
        + MARKET_CONTEXT_COLUMNS
    ):
        if name not in values:
            values.append(name)
    return tuple(values)


def production_feature_columns() -> tuple[str, ...]:
    """Physical feature order from the producer, independent of grouping order.

    The HTF producer defines dict insertion order; the Phase 7 context builder
    and as-of join preserve it. A zero-row schema probe creates no research data.
    Group catalogs constrain inventory, not the order of persisted columns.
    """
    empty = pa.table(
        {
            "open_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
            **{
                name: pa.array([], type=pa.float64())
                for name in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "quote_volume",
                    "trade_count",
                    "taker_buy_quote_volume",
                )
            },
        }
    )
    higher: tuple[str, ...] = ()
    for interval, count in (("12h", 22), ("1d", 33)):
        columns = tuple(_higher_timeframe_values(empty, interval))
        catalog = FEATURE_GROUPS_V3_RESEARCH[f"higher_timeframe_{interval}"]
        if len(columns) != count or len(catalog) != count or set(columns) != set(catalog):
            raise AssertionError(f"production {interval} feature inventory drifted")
        higher += columns
    return native_feature_columns() + higher


def production_a6_model_columns() -> tuple[str, ...]:
    """Established model order; not the physical storage order."""
    return feature_ablation_sets(production_feature_columns())["A6"]


def production_gold_schema() -> dict[str, pa.DataType]:
    fields = {
        name: pa.float64()
        for name in production_feature_columns()
        + CROSS_SECTIONAL_SOURCE_COLUMNS
        + (
            "raw_future_return",
            "normalized_future_return",
            "ex_ante_volatility_scale",
            "mfe_long",
            "mae_long",
            "mfe_short",
            "mae_short",
        )
    }
    fields.update(
        {
            name: pa.string()
            for name in (
                "symbol",
                "feature_version",
                "market_context_version",
                "market_membership_hash",
                "cross_sectional_context_scope",
                "target_version",
            )
        }
    )
    fields.update(
        {
            name: pa.timestamp("us", tz="UTC")
            for name in ("open_time", "feature_time", "entry_time", "label_end_time")
        }
    )
    fields["horizon_minutes"] = pa.int64()
    return fields


@dataclass(frozen=True, slots=True)
class GoldValidationExpectations:
    dataset_id: str = EXPECTED_GOLD_DATASET_ID
    partitions: int = EXPECTED_GOLD_PARTITIONS
    rows: int = EXPECTED_GOLD_ROWS
    symbols: frozenset[str] = frozenset(CORE20)
    horizons: frozenset[int] = frozenset({15, 30, 60, 120})
    research_cutoff: datetime = RESEARCH_CUTOFF
    holdout_start: datetime = HOLDOUT_START
    total_files: int | None = EXPECTED_GOLD_PARTITIONS + 1


class GoldValidationError(ValueError):
    pass


class HoldoutViolationError(GoldValidationError):
    pass


DEFAULT_GOLD_EXPECTATIONS = GoldValidationExpectations()


def locate_gold_manifest(gold_root: Path, dataset_id: str = EXPECTED_GOLD_DATASET_ID) -> Path:
    root = gold_root.expanduser().resolve()
    direct = root / "manifest.json"
    candidates = [direct] if direct.is_file() else []
    candidates.extend(
        path for path in root.glob(f"**/{dataset_id}/manifest.json") if path not in candidates
    )
    if len(candidates) != 1:
        raise GoldValidationError(
            f"expected exactly one {dataset_id} manifest below {root}; found {len(candidates)}"
        )
    return candidates[0]


def _partition_path(manifest_path: Path, record: dict[str, Any]) -> Path:
    path = Path(str(record["path"]))
    root = manifest_path.parent.resolve()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise GoldValidationError(f"partition path escapes dataset root: {path}")
    return resolved


def validate_gold_manifest(
    gold_root: Path,
    expectations: GoldValidationExpectations = DEFAULT_GOLD_EXPECTATIONS,
) -> tuple[Path, dict[str, Any], list[Path]]:
    manifest_path = locate_gold_manifest(gold_root, expectations.dataset_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    required_manifest_fields = {
        "classification",
        "dataset_id",
        "feature_columns",
        "feature_groups",
        "feature_version",
        "july_2026_used",
        "lineage",
        "partition_files",
        "partitioned_by",
        "prospective_holdout_evaluation_authorized",
        "prospective_holdout_start",
        "prospective_holdout_status",
        "prospective_holdout_used",
        "registry_hash",
        "registry_version",
        "research_cutoff",
        "target_version",
        "universe_hash",
        "universe_version",
    }
    missing_manifest_fields = sorted(required_manifest_fields - set(manifest))
    if missing_manifest_fields:
        errors.append(f"manifest is missing required fields: {missing_manifest_fields}")
    if manifest.get("dataset_id") != expectations.dataset_id:
        errors.append("dataset ID mismatch")
    if manifest.get("classification") != "RETROSPECTIVE_MULTI_ASSET_RESEARCH":
        errors.append("classification mismatch")
    if manifest.get("partitioned_by") != ["symbol", "year"]:
        errors.append("partitioning contract mismatch")
    records = manifest.get("partition_files")
    if not isinstance(records, list) or len(records) != expectations.partitions:
        errors.append(
            f"partition count mismatch: expected {expectations.partitions}, got "
            f"{len(records) if isinstance(records, list) else 'invalid'}"
        )
        records = records if isinstance(records, list) else []
    rows = manifest.get("rows", manifest.get("row_count"))
    if rows != expectations.rows:
        errors.append(f"manifest row count mismatch: expected {expectations.rows}, got {rows}")
    if manifest.get("feature_version") != FEATURE_VERSION:
        errors.append("feature version mismatch")
    if manifest.get("target_version") != TARGET_VERSION:
        errors.append("target version mismatch")
    expected_features = production_feature_columns()
    manifest_features = manifest.get("feature_columns")
    if not isinstance(manifest_features, list) or tuple(manifest_features) != expected_features:
        errors.append("production feature count/order mismatch (native feature contract included)")
        manifest_features = manifest_features if isinstance(manifest_features, list) else []
    groups = manifest.get("feature_groups")
    if not isinstance(groups, dict) or groups.get("A6") != list(production_a6_model_columns()):
        errors.append("A6 feature-group ordering mismatch")
    if manifest.get("research_cutoff") != expectations.research_cutoff.isoformat():
        errors.append("research cutoff mismatch")
    if manifest.get("prospective_holdout_start") != expectations.holdout_start.isoformat():
        errors.append("prospective holdout start mismatch")
    for name in ("universe_version", "universe_hash", "registry_version", "registry_hash"):
        if not isinstance(manifest.get(name), str) or not manifest.get(name):
            errors.append(f"manifest {name} is missing")
    if not isinstance(manifest.get("lineage"), dict) or not manifest.get("lineage"):
        errors.append("manifest lineage is missing")
    if (
        manifest.get("prospective_holdout_status") != "LOCKED_UNUSED"
        or manifest.get("prospective_holdout_used") is not False
        or manifest.get("prospective_holdout_evaluation_authorized") is not False
        or manifest.get("july_2026_used") is not False
    ):
        raise HoldoutViolationError("HOLDOUT_VIOLATION: Gold manifest holdout flags are unsafe")
    paths: list[Path] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            errors.append("partition record is malformed")
            continue
        path = _partition_path(manifest_path, record)
        if not path.is_file():
            errors.append(f"partition is missing: {path}")
        paths.append(path)
    physical_partitions = sorted(manifest_path.parent.glob("dataset/**/*.parquet"))
    if len(physical_partitions) != expectations.partitions:
        errors.append(
            f"physical Parquet partition count mismatch: expected {expectations.partitions}, "
            f"got {len(physical_partitions)}"
        )
    if {path.resolve() for path in physical_partitions} != {path.resolve() for path in paths}:
        errors.append("manifest and physical Parquet partition sets differ")
    if len(paths) != len(set(paths)):
        errors.append("duplicate manifest partition records")
    total_files = sum(1 for path in manifest_path.parent.rglob("*") if path.is_file())
    if expectations.total_files is not None and total_files != expectations.total_files:
        errors.append(
            f"total file count mismatch: expected {expectations.total_files}, got {total_files}"
        )
    if errors:
        raise GoldValidationError("; ".join(errors))
    return manifest_path, manifest, paths


def _timestamp_type_is_utc(data_type: pa.DataType) -> bool:
    return pa.types.is_timestamp(data_type) and getattr(data_type, "tz", None) == "UTC"


@instrument("GOLD_VALIDATE")
def validate_phase7_gold(
    gold_root: Path,
    *,
    expectations: GoldValidationExpectations = DEFAULT_GOLD_EXPECTATIONS,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    manifest_path, manifest, paths = validate_gold_manifest(gold_root, expectations)
    required_features = production_feature_columns()
    if len(required_features) != 109:
        raise AssertionError(
            f"production Phase 7 feature contract drifted: {len(required_features)}"
        )
    required_columns = {
        *production_gold_schema(),
        "feature_version",
        "market_context_version",
        "symbol",
        "feature_time",
        "entry_time",
        "label_end_time",
        "horizon_minutes",
        "raw_future_return",
        "normalized_future_return",
        "ex_ante_volatility_scale",
        "mfe_long",
        "mae_long",
        "mfe_short",
        "mae_short",
        "target_version",
        "cross_sectional_context_scope",
        *required_features,
    }
    symbols: set[str] = set()
    horizons: set[int] = set()
    total_rows = 0
    numeric_audit_columns = (
        required_features
        + CROSS_SECTIONAL_SOURCE_COLUMNS
        + (
            "raw_future_return",
            "normalized_future_return",
            "ex_ante_volatility_scale",
            "mfe_long",
            "mae_long",
            "mfe_short",
            "mae_short",
        )
    )
    nan_counts = {name: 0 for name in numeric_audit_columns}
    inf_counts = {name: 0 for name in numeric_audit_columns}
    scope_status = "ACQUISITION_UNION_PREVIEW_REQUIRES_FOLD_REBIND"
    last_key_by_symbol: dict[str, tuple[int, int]] = {}
    partition_reports: list[dict[str, Any]] = []
    reference_schema: pa.Schema | None = None
    cutoff_us = int(expectations.research_cutoff.timestamp() * 1_000_000)
    holdout_us = int(expectations.holdout_start.timestamp() * 1_000_000)
    records = manifest["partition_files"]
    for record, path in zip(records, paths, strict=True):
        if verify_hashes:
            if not record.get("sha256"):
                raise GoldValidationError(f"partition checksum is missing: {path}")
            if file_sha256(path) != record["sha256"]:
                raise GoldValidationError(f"partition checksum mismatch: {path}")
        table = pq.ParquetFile(path).read()
        if reference_schema is None:
            reference_schema = table.schema
        elif not table.schema.equals(reference_schema, check_metadata=True):
            raise GoldValidationError(f"partition schema mismatch: {path}")
        missing = sorted(required_columns - set(table.column_names))
        if missing:
            raise GoldValidationError(f"partition {path} is missing required columns: {missing}")
        unexpected = sorted(set(table.column_names) - required_columns)
        if unexpected:
            raise GoldValidationError(f"partition {path} has unexpected columns: {unexpected}")
        for name, expected_type in production_gold_schema().items():
            if table.schema.field(name).type != expected_type:
                raise GoldValidationError(f"partition {path} has wrong type for {name}")
        physical_native_order = tuple(
            name for name in table.column_names if name in required_features
        )
        if physical_native_order != required_features:
            raise GoldValidationError(f"production feature column order mismatch in {path}")
        for name in ("feature_time", "entry_time", "label_end_time"):
            if not _timestamp_type_is_utc(table.schema.field(name).type):
                raise GoldValidationError(f"partition {path} has invalid {name} type")
            if table.column(name).null_count:
                raise GoldValidationError(f"partition {path} has null {name}")
        for name in numeric_audit_columns:
            if table.schema.field(name).type != pa.float64():
                raise GoldValidationError(f"partition {path} has non-float64 {name}")
        if table.column("symbol").null_count or table.column("horizon_minutes").null_count:
            raise GoldValidationError(f"null symbol/horizon key in {path}")
        table_symbols = np.asarray(
            table.column("symbol").combine_chunks().to_numpy(zero_copy_only=False),
            dtype=object,
        )
        feature_times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
        label_ends = table.column("label_end_time").combine_chunks().cast(pa.int64()).to_numpy()
        table_horizons = np.asarray(
            table.column("horizon_minutes").to_numpy(zero_copy_only=False), dtype=np.int64
        )
        entry_times = table.column("entry_time").combine_chunks().cast(pa.int64()).to_numpy()
        if np.any(entry_times - feature_times != FIVE_MINUTES_US):
            raise GoldValidationError(f"open[i+2] entry timing mismatch in {path}")
        if np.any(label_ends - entry_times != table_horizons * 60_000_000):
            raise GoldValidationError(f"label_end_time/horizon mismatch in {path}")
        versions = set(table.column("target_version").to_pylist())
        if versions != {TARGET_VERSION}:
            raise GoldValidationError(f"target version values mismatch in {path}: {versions}")
        feature_versions = set(table.column("feature_version").to_pylist())
        if feature_versions != {FEATURE_VERSION}:
            raise GoldValidationError(f"feature version values mismatch in {path}")
        market_versions = set(table.column("market_context_version").to_pylist())
        if market_versions != {MARKET_CONTEXT_VERSION}:
            raise GoldValidationError(f"market-context version values mismatch in {path}")
        if np.any(feature_times >= holdout_us) or np.any(label_ends >= holdout_us):
            raise HoldoutViolationError(f"HOLDOUT_VIOLATION: August row found in {path}")
        if np.any(feature_times >= cutoff_us) or np.any(label_ends >= cutoff_us):
            raise HoldoutViolationError(f"HOLDOUT_VIOLATION: post-cutoff row found in {path}")
        symbols.update(str(value) for value in np.unique(table_symbols))
        horizons.update(int(value) for value in np.unique(table_horizons))
        order = np.lexsort((table_horizons, feature_times, table_symbols.astype(str)))
        ordered_symbols = table_symbols[order]
        ordered_times = feature_times[order]
        ordered_horizons = table_horizons[order]
        duplicate = (
            (ordered_symbols[1:] == ordered_symbols[:-1])
            & (ordered_times[1:] == ordered_times[:-1])
            & (ordered_horizons[1:] == ordered_horizons[:-1])
        )
        if np.any(duplicate):
            raise GoldValidationError(f"duplicate primary key in {path}")
        for symbol in np.unique(ordered_symbols):
            rows = np.flatnonzero(ordered_symbols == symbol)
            first = (int(ordered_times[rows[0]]), int(ordered_horizons[rows[0]]))
            if symbol in last_key_by_symbol and first <= last_key_by_symbol[str(symbol)]:
                raise GoldValidationError(f"duplicate/out-of-order partition boundary for {symbol}")
            last_key_by_symbol[str(symbol)] = (
                int(ordered_times[rows[-1]]),
                int(ordered_horizons[rows[-1]]),
            )
        for name in numeric_audit_columns:
            values = np.asarray(
                table.column(name).combine_chunks().to_numpy(zero_copy_only=False),
                dtype=np.float64,
            )
            nan_counts[name] += int(np.count_nonzero(np.isnan(values)))
            inf_counts[name] += int(np.count_nonzero(np.isinf(values)))
        scopes = set(table.column("cross_sectional_context_scope").to_pylist())
        if scopes != {"ACQUISITION_UNION_PREVIEW"}:
            raise GoldValidationError(f"invalid cross-sectional context scope in {path}: {scopes}")
        if record.get("row_count") is not None and record["row_count"] != table.num_rows:
            raise GoldValidationError(f"partition manifest row count mismatch: {path}")
        total_rows += table.num_rows
        partition_reports.append(
            {
                "path": str(path),
                "rows": table.num_rows,
                "sha256": record.get("sha256"),
                "schema": str(table.schema),
            }
        )
    if total_rows != expectations.rows:
        raise GoldValidationError(
            f"physical row count mismatch: expected {expectations.rows}, got {total_rows}"
        )
    if symbols != set(expectations.symbols):
        raise GoldValidationError(
            f"symbol universe mismatch: missing={sorted(set(expectations.symbols) - symbols)}, "
            f"extra={sorted(symbols - set(expectations.symbols))}"
        )
    if horizons != set(expectations.horizons):
        raise GoldValidationError(f"horizon values mismatch: {sorted(horizons)}")
    if any(inf_counts.values()):
        raise GoldValidationError(f"infinite numeric values found: {inf_counts}")
    return {
        "status": "PASS" if verify_hashes else "INCOMPLETE_HASH_VERIFICATION",
        "partition_hashes_verified": verify_hashes,
        "manifest_path": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "dataset_id": manifest["dataset_id"],
        "partitions": len(paths),
        "rows": total_rows,
        "symbols": sorted(symbols),
        "horizons": sorted(horizons),
        "native_feature_count": len(native_feature_columns()),
        "native_features": list(native_feature_columns()),
        "production_feature_count": len(required_features),
        "production_features": list(required_features),
        "a6_model_features": list(production_a6_model_columns()),
        "production_schema": {name: str(value) for name, value in production_gold_schema().items()},
        "nan_counts": nan_counts,
        "infinite_counts": inf_counts,
        "cross_sectional_context_scope": scope_status,
        "research_cutoff_exclusive": expectations.research_cutoff.isoformat(),
        "holdout_start": expectations.holdout_start.isoformat(),
        "holdout_status": "LOCKED_UNUSED",
        "expectations": asdict(expectations),
        "partition_reports": partition_reports,
    }
