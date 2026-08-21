from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.schema import DECIMAL_TYPE
from crypto_ai.data.storage import file_sha256
from crypto_ai.labels import generate_forward_return_labels
from crypto_ai.phase4.config import GoldV2Config
from crypto_ai.phase4.features import (
    FEATURE_GROUPS,
    FEATURE_V2_VERSION,
    ExternalTables,
    generate_features_v2,
)
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.research.config import DatasetBuildConfig, LabelConfig
from crypto_ai.research.gold import TARGET_COLUMN, _atomic_write_parquet, _load_silver
from crypto_ai.research.metrics import distribution_summary, feature_distribution

GOLD_V2_SCHEMA_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class GoldV2Result:
    dataset_version: str
    dataset_path: Path
    manifest_path: Path
    row_count: int
    feature_columns: tuple[str, ...]
    feature_groups: tuple[str, ...]
    reused: bool = False


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]


def _external_table(
    path: Path | None, kind: MarketDataKind
) -> tuple[pa.Table | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    table, manifest = read_market_dataset(path, kind)
    return table, manifest


def _schema(columns: tuple[str, ...]) -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("interval", pa.string(), nullable=False),
            pa.field("prediction_candle_open_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("feature_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("entry_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("label_end_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("entry_reference_price", DECIMAL_TYPE, nullable=False),
            pa.field("future_reference_price", DECIMAL_TYPE, nullable=False),
        ]
        + [pa.field(name, pa.float64(), nullable=False) for name in columns]
        + [
            pa.field(TARGET_COLUMN, pa.float64(), nullable=False),
            pa.field("label_name", pa.string(), nullable=False),
            pa.field("label_version", pa.string(), nullable=False),
            pa.field("feature_version", pa.string(), nullable=False),
        ]
    )


def build_gold_v2(config: GoldV2Config, label_config: LabelConfig) -> GoldV2Result:
    phase3_config = DatasetBuildConfig(
        silver_manifest=config.silver_manifest,
        symbol=config.symbol,
        interval=config.interval,
        start_time=config.start_time,
        end_time=config.end_time,
    )
    candles, silver_manifest, silver_files = _load_silver(phase3_config)
    funding, funding_manifest = _external_table(config.funding_manifest, MarketDataKind.FUNDING)
    mark, mark_manifest = _external_table(config.mark_manifest, MarketDataKind.MARK_KLINE)
    index, index_manifest = _external_table(config.index_manifest, MarketDataKind.INDEX_KLINE)
    oi, oi_manifest = _external_table(config.open_interest_manifest, MarketDataKind.OPEN_INTEREST)
    external = ExternalTables(funding=funding, mark=mark, index=index, open_interest=oi)
    features = generate_features_v2(candles, interval=config.interval, external=external)
    labels = generate_forward_return_labels(candles, interval=config.interval, config=label_config)
    usable = features.valid_mask & labels.valid_mask
    indices = np.flatnonzero(usable)
    if not len(indices):
        raise ValueError("No causally complete Feature V2 rows have labels")

    opens = candles.column("open").combine_chunks().to_pylist()
    candle_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    columns: dict[str, Any] = {
        "symbol": [config.symbol] * len(indices),
        "interval": [config.interval] * len(indices),
        "prediction_candle_open_time": pa.array(
            candle_times[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "feature_time": pa.array(
            labels.feature_time_us[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "entry_time": pa.array(labels.entry_time_us[indices], type=pa.timestamp("us", tz="UTC")),
        "label_end_time": pa.array(
            labels.label_end_time_us[indices], type=pa.timestamp("us", tz="UTC")
        ),
        "entry_reference_price": [opens[int(labels.entry_indices[i])] for i in indices],
        "future_reference_price": [opens[int(labels.target_indices[i])] for i in indices],
        TARGET_COLUMN: labels.returns[indices],
        "label_name": [label_config.name] * len(indices),
        "label_version": [label_config.version] * len(indices),
        "feature_version": [FEATURE_V2_VERSION] * len(indices),
    }
    for name in features.columns:
        columns[name] = features.values[name][indices]
    table = pa.Table.from_pydict(columns, schema=_schema(features.columns))

    external_manifests = {
        name: manifest
        for name, manifest in (
            ("funding", funding_manifest),
            ("mark", mark_manifest),
            ("index", index_manifest),
            ("open_interest", oi_manifest),
        )
        if manifest is not None
    }
    identity = {
        "schema_version": GOLD_V2_SCHEMA_VERSION,
        "silver_version": silver_manifest["silver_dataset_version"],
        "silver_files": [{"sha256": item["sha256"]} for item in silver_files],
        "external_versions": {
            name: manifest["dataset_version"] for name, manifest in external_manifests.items()
        },
        "configuration": config.model_dump(mode="json"),
        "feature_version": FEATURE_V2_VERSION,
        "feature_columns": features.columns,
        "label": label_config.model_dump(mode="json"),
        "join_policy": "availability_time<=feature_time; dataset-specific maximum age",
    }
    dataset_version = f"gold-v2-{_hash(identity)}"
    directory = config.output_root.resolve() / dataset_version
    dataset_path, manifest_path = directory / "dataset.parquet", directory / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None:
        if not dataset_path.exists() or file_sha256(dataset_path) != existing.get("sha256"):
            raise ValueError(f"Gold V2 checksum mismatch: {dataset_path}")
        return GoldV2Result(
            dataset_version,
            dataset_path,
            manifest_path,
            int(existing["row_count"]),
            tuple(existing["feature_columns"]),
            tuple(existing["feature_groups"]),
            True,
        )

    metadata = {
        b"schema_version": GOLD_V2_SCHEMA_VERSION.encode(),
        b"dataset_version": dataset_version.encode(),
        b"layer": b"gold",
        b"feature_version": FEATURE_V2_VERSION.encode(),
        b"label_version": label_config.version.encode(),
        b"feature_columns": json.dumps(features.columns).encode(),
        b"feature_groups": json.dumps(features.groups).encode(),
    }
    checksum = _atomic_write_parquet(dataset_path, table.replace_schema_metadata(metadata))
    feature_summaries = {
        name: feature_distribution(table.column(name).combine_chunks().to_numpy())
        for name in features.columns
    }
    manifest = {
        "dataset_version": dataset_version,
        "schema_version": GOLD_V2_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "file": "dataset.parquet",
        "sha256": checksum,
        "row_count": table.num_rows,
        "symbol": config.symbol,
        "interval": config.interval,
        "source_silver_manifest": str(config.silver_manifest.resolve()),
        "source_silver_version": silver_manifest["silver_dataset_version"],
        "source_silver_files": silver_files,
        "external_sources": {
            name: {
                "manifest": str(getattr(config, f"{name}_manifest", "")),
                "dataset_version": source["dataset_version"],
                "sha256": source["sha256"],
            }
            for name, source in external_manifests.items()
        },
        "feature_version": FEATURE_V2_VERSION,
        "feature_count": len(features.columns),
        "feature_columns": list(features.columns),
        "feature_groups": list(features.groups),
        "feature_group_columns": {group: list(FEATURE_GROUPS[group]) for group in features.groups},
        "feature_diagnostics": features.diagnostics,
        "feature_distributions": feature_summaries,
        "target_column": TARGET_COLUMN,
        "target_distribution": distribution_summary(
            table.column(TARGET_COLUMN).combine_chunks().to_numpy(),
            near_zero_threshold=label_config.near_zero_threshold_bps / 10_000,
        ),
        "label_name": label_config.name,
        "label_version": label_config.version,
        "label_config": label_config.model_dump(mode="json"),
        "configuration": config.model_dump(mode="json"),
        "configuration_hash": config.config_hash,
        "join_policy": {
            "rule": "availability_time <= feature_time",
            "funding_max_age_hours": 12,
            "price_kline_max_age_minutes": 6,
            "open_interest_max_age_minutes": 10,
            "missing_behavior": "exclude row; never backward-fill or encode unavailable as zero",
        },
        "build_summary": {
            "candidate_rows": candles.num_rows,
            "feature_valid_rows": int(np.count_nonzero(features.valid_mask)),
            "label_valid_rows": labels.valid_count,
            "final_rows": table.num_rows,
        },
        "code_version": "phase4-1.0.0",
    }
    write_manifest(manifest_path, manifest)
    return GoldV2Result(
        dataset_version,
        dataset_path,
        manifest_path,
        table.num_rows,
        features.columns,
        features.groups,
    )


def read_gold_v2(manifest_path: Path) -> tuple[pa.Table, dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)
    path = manifest_path.parent / str(manifest.get("file", "dataset.parquet"))
    if not path.exists() or file_sha256(path) != manifest.get("sha256"):
        raise ValueError(f"Gold V2 checksum mismatch: {path}")
    table = pq.ParquetFile(path).read()
    if (table.schema.metadata or {}).get(b"dataset_version", b"").decode() != manifest.get(
        "dataset_version"
    ):
        raise ValueError("Gold V2 Parquet/manifest lineage mismatch")
    return table, manifest
