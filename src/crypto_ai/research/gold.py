from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.schema import DECIMAL_TYPE, candle_schema
from crypto_ai.data.storage import file_sha256, read_candle_parquet
from crypto_ai.features import FeatureGenerationResult, generate_baseline_features
from crypto_ai.labels import LabelGenerationResult, generate_forward_return_labels
from crypto_ai.research.config import DatasetBuildConfig, FeatureConfig, LabelConfig
from crypto_ai.research.metrics import distribution_summary, feature_distribution

logger = logging.getLogger(__name__)

GOLD_SCHEMA_VERSION = "1.0.0"
TARGET_COLUMN = "future_return_60m"


@dataclass(frozen=True, slots=True)
class GoldBuildResult:
    dataset_version: str
    dataset_path: Path
    manifest_path: Path
    row_count: int
    feature_columns: tuple[str, ...]
    target_column: str
    source_silver_version: str
    summary: dict[str, Any]
    reused: bool = False


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


def _atomic_write_parquet(path: Path, table: pa.Table) -> str:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable Gold dataset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary, compression="zstd", write_statistics=True)
        if path.exists():
            raise FileExistsError(f"Gold dataset appeared during write: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return file_sha256(path)


def _utc_iso_from_us(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000, tz=UTC).isoformat()


def _load_silver(
    config: DatasetBuildConfig,
) -> tuple[pa.Table, dict[str, Any], list[dict[str, Any]]]:
    manifest_path = config.silver_manifest.resolve()
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)
    if manifest.get("quality_status") not in {"PASS", "WARN"}:
        raise ValueError("Silver manifest does not carry an eligible Phase 2 quality status")
    silver_version = manifest.get("silver_dataset_version")
    if not silver_version:
        raise ValueError("Silver manifest is missing silver_dataset_version")
    root = manifest_path.parent.parent
    output_records = manifest.get("output_files")
    if not isinstance(output_records, list) or not output_records:
        raise ValueError("Silver manifest has no output files")

    source_records: list[dict[str, Any]] = []
    tables: list[pa.Table] = []
    for record in output_records:
        if not isinstance(record, dict) or not record.get("file") or not record.get("sha256"):
            raise ValueError("Silver output record is incomplete")
        path = root / str(record["file"])
        if not path.exists():
            raise FileNotFoundError(path)
        checksum = file_sha256(path)
        if checksum != record["sha256"]:
            raise ValueError(f"Silver checksum mismatch: {path}")
        table = read_candle_parquet(path)
        metadata = {
            key.decode(): value.decode() for key, value in (table.schema.metadata or {}).items()
        }
        if metadata.get("silver_dataset_version") != silver_version:
            raise ValueError(f"Silver lineage mismatch: {path}")
        if metadata.get("symbol") != config.symbol or metadata.get("interval") != config.interval:
            raise ValueError(f"Silver identity mismatch: {path}")
        tables.append(table.replace_schema_metadata(candle_schema().metadata))
        source_records.append(
            {"file": str(path.resolve()), "sha256": checksum, "row_count": table.num_rows}
        )
    table = pa.concat_tables(tables).sort_by([("open_time", "ascending")])
    open_times = table.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    if len(open_times) and np.any(np.diff(open_times) <= 0):
        raise ValueError("Silver candles must be strictly chronological and duplicate-free")

    mask = np.ones(table.num_rows, dtype=bool)
    if config.start_time is not None:
        start_us = int(config.start_time.timestamp() * 1_000_000)
        mask &= open_times >= start_us
    if config.end_time is not None:
        end_us = int(config.end_time.timestamp() * 1_000_000)
        mask &= open_times < end_us
    if not np.all(mask):
        table = table.filter(pa.array(mask))
    if table.num_rows == 0:
        raise ValueError("Configured Silver range contains no candles")
    return table, manifest, source_records


def _gold_schema(feature_columns: tuple[str, ...]) -> pa.Schema:
    fields = [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("interval", pa.string(), nullable=False),
        pa.field("prediction_candle_open_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("feature_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("entry_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("label_end_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("entry_reference_price", DECIMAL_TYPE, nullable=False),
        pa.field("future_reference_price", DECIMAL_TYPE, nullable=False),
    ]
    fields.extend(pa.field(name, pa.float64(), nullable=False) for name in feature_columns)
    fields.extend(
        [
            pa.field(TARGET_COLUMN, pa.float64(), nullable=False),
            pa.field("label_name", pa.string(), nullable=False),
            pa.field("label_version", pa.string(), nullable=False),
            pa.field("feature_version", pa.string(), nullable=False),
        ]
    )
    return pa.schema(fields)


def _build_gold_table(
    candles: pa.Table,
    features: FeatureGenerationResult,
    labels: LabelGenerationResult,
    *,
    interval: str,
    feature_config: FeatureConfig,
    label_config: LabelConfig,
) -> tuple[pa.Table, np.ndarray]:
    if np.any(features.unexpected_invalid_mask):
        count = int(np.count_nonzero(features.unexpected_invalid_mask))
        raise ValueError(f"Feature generation produced {count} unexpected invalid rows")
    usable = features.valid_mask & labels.valid_mask
    indices = np.flatnonzero(usable)
    if not len(indices):
        raise ValueError(
            "No usable Gold rows remain after feature warm-up and label availability checks"
        )
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    opens = candles.column("open").combine_chunks().to_pylist()
    entry_prices = [opens[int(labels.entry_indices[index])] for index in indices]
    future_prices = [opens[int(labels.target_indices[index])] for index in indices]
    schema = _gold_schema(feature_config.columns)
    columns: dict[str, Any] = {
        "symbol": [candles.column("symbol")[int(index)].as_py() for index in indices],
        "interval": [interval] * len(indices),
        "prediction_candle_open_time": pa.array(
            open_times[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "feature_time": pa.array(
            labels.feature_time_us[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "entry_time": pa.array(labels.entry_time_us[indices], type=pa.timestamp("us", tz="UTC")),
        "label_end_time": pa.array(
            labels.label_end_time_us[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "entry_reference_price": entry_prices,
        "future_reference_price": future_prices,
        TARGET_COLUMN: labels.returns[indices],
        "label_name": [label_config.name] * len(indices),
        "label_version": [label_config.version] * len(indices),
        "feature_version": [feature_config.version] * len(indices),
    }
    for name in feature_config.columns:
        columns[name] = features.values[name][indices]
    return pa.Table.from_pydict(columns, schema=schema), usable


def build_gold_dataset(
    dataset_config: DatasetBuildConfig,
    feature_config: FeatureConfig,
    label_config: LabelConfig,
) -> GoldBuildResult:
    started = time.perf_counter()
    candles, silver_manifest, source_records = _load_silver(dataset_config)
    source_hashes_before = {Path(item["file"]): item["sha256"] for item in source_records}
    features = generate_baseline_features(
        candles, interval=dataset_config.interval, config=feature_config
    )
    labels = generate_forward_return_labels(
        candles, interval=dataset_config.interval, config=label_config
    )
    gold, usable = _build_gold_table(
        candles,
        features,
        labels,
        interval=dataset_config.interval,
        feature_config=feature_config,
        label_config=label_config,
    )
    source_silver_version = str(silver_manifest["silver_dataset_version"])
    identity = {
        "gold_schema_version": GOLD_SCHEMA_VERSION,
        "source_silver_version": source_silver_version,
        "source_files": [
            {"sha256": item["sha256"], "row_count": item["row_count"]} for item in source_records
        ],
        "dataset_selection_hash": dataset_config.content_hash,
        "feature_config": feature_config.model_dump(mode="json"),
        "label_config": label_config.model_dump(mode="json"),
    }
    dataset_version = f"gold-{_stable_hash(identity)}"
    output_directory = dataset_config.output_root.resolve() / dataset_version
    dataset_path = output_directory / "dataset.parquet"
    manifest_path = output_directory / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None:
        if existing.get("dataset_version") != dataset_version:
            raise ValueError(f"Existing Gold manifest identity mismatch: {manifest_path}")
        if not dataset_path.exists() or file_sha256(dataset_path) != existing.get("sha256"):
            raise ValueError(f"Existing Gold dataset checksum mismatch: {dataset_path}")
        return GoldBuildResult(
            dataset_version=dataset_version,
            dataset_path=dataset_path,
            manifest_path=manifest_path,
            row_count=int(existing["row_count"]),
            feature_columns=tuple(existing["feature_columns"]),
            target_column=str(existing["target_column"]),
            source_silver_version=source_silver_version,
            summary=dict(existing["build_summary"]),
            reused=True,
        )
    if dataset_path.exists():
        raise FileExistsError(f"Orphan Gold dataset exists without manifest: {dataset_path}")

    combined_config_hash = _stable_hash(
        {
            "dataset": dataset_config.content_hash,
            "features": feature_config.config_hash,
            "labels": label_config.config_hash,
        }
    )
    metadata = {
        b"schema_version": GOLD_SCHEMA_VERSION.encode(),
        b"layer": b"gold",
        b"dataset_version": dataset_version.encode(),
        b"source_silver_version": source_silver_version.encode(),
        b"source_silver_manifest": str(dataset_config.silver_manifest.resolve()).encode(),
        b"feature_version": feature_config.version.encode(),
        b"feature_config_hash": feature_config.config_hash.encode(),
        b"label_version": label_config.version.encode(),
        b"label_config_hash": label_config.config_hash.encode(),
        b"configuration_hash": combined_config_hash.encode(),
        b"feature_columns": json.dumps(feature_config.columns).encode(),
        b"target_column": TARGET_COLUMN.encode(),
    }
    gold = gold.replace_schema_metadata(metadata)
    checksum = _atomic_write_parquet(dataset_path, gold)
    for path, before in source_hashes_before.items():
        if file_sha256(path) != before:
            raise RuntimeError(f"Silver source changed during Gold construction: {path}")

    target_values = gold.column(TARGET_COLUMN).combine_chunks().to_numpy()
    target_summary = distribution_summary(
        target_values, near_zero_threshold=label_config.near_zero_threshold_bps / 10_000.0
    )
    feature_summaries = {
        name: feature_distribution(gold.column(name).combine_chunks().to_numpy())
        for name in feature_config.columns
    }
    build_summary = {
        "total_candidate_observations": candles.num_rows,
        "rows_removed_feature_warmup": int(np.count_nonzero(features.warmup_mask)),
        "rows_with_unexpected_feature_missingness": int(
            np.count_nonzero(features.unexpected_invalid_mask)
        ),
        "valid_feature_vectors": features.valid_count,
        "valid_labeled_observations": labels.valid_count,
        "unlabelable_observations": int(candles.num_rows - labels.valid_count),
        "label_reason_counts": labels.reason_counts,
        "final_gold_rows": gold.num_rows,
        "rows_excluded_from_gold": int(candles.num_rows - np.count_nonzero(usable)),
    }
    manifest = {
        "dataset_version": dataset_version,
        "schema_version": GOLD_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_silver_manifest": str(dataset_config.silver_manifest.resolve()),
        "source_silver_version": source_silver_version,
        "source_silver_files": source_records,
        "source_bronze_manifest": silver_manifest.get("source_manifest"),
        "source_bronze_dataset_version": silver_manifest.get("source_dataset_version"),
        "validation_report_id": silver_manifest.get("validation_report_id"),
        "symbol": dataset_config.symbol,
        "interval": dataset_config.interval,
        "start_time": _utc_iso_from_us(
            int(gold.column("feature_time")[0].cast(pa.int64()).as_py())
        ),
        "end_time": _utc_iso_from_us(int(gold.column("feature_time")[-1].cast(pa.int64()).as_py())),
        "row_count": gold.num_rows,
        "feature_columns": list(feature_config.columns),
        "feature_count": len(feature_config.columns),
        "feature_version": feature_config.version,
        "feature_config": feature_config.model_dump(mode="json"),
        "label_name": label_config.name,
        "label_version": label_config.version,
        "label_config": label_config.model_dump(mode="json"),
        "target_column": TARGET_COLUMN,
        "configuration_hash": combined_config_hash,
        "file": "dataset.parquet",
        "sha256": checksum,
        "build_summary": build_summary,
        "target_distribution": target_summary,
        "feature_distributions": feature_summaries,
        "constant_features": [
            name for name, summary in feature_summaries.items() if summary["constant"]
        ],
        "near_constant_features": [
            name for name, summary in feature_summaries.items() if summary["near_constant"]
        ],
        "code_version": "phase3-1.0.0",
    }
    write_manifest(manifest_path, manifest)
    logger.info(
        "Gold dataset created",
        extra={
            "event": "dataset_created",
            "dataset_version": dataset_version,
            "feature_version": feature_config.version,
            "label_version": label_config.version,
            "rows": gold.num_rows,
            "duration_seconds": time.perf_counter() - started,
        },
    )
    return GoldBuildResult(
        dataset_version=dataset_version,
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        row_count=gold.num_rows,
        feature_columns=feature_config.columns,
        target_column=TARGET_COLUMN,
        source_silver_version=source_silver_version,
        summary=build_summary,
    )


def read_gold_dataset(manifest_path: Path) -> tuple[pa.Table, dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)
    dataset_path = manifest_path.parent / str(manifest.get("file", "dataset.parquet"))
    if not dataset_path.exists():
        raise FileNotFoundError(dataset_path)
    if file_sha256(dataset_path) != manifest.get("sha256"):
        raise ValueError(f"Gold checksum mismatch: {dataset_path}")
    table = pq.ParquetFile(dataset_path).read()
    metadata = {
        key.decode(): value.decode() for key, value in (table.schema.metadata or {}).items()
    }
    if metadata.get("dataset_version") != manifest.get("dataset_version"):
        raise ValueError("Gold Parquet and manifest dataset versions differ")
    return table, manifest
