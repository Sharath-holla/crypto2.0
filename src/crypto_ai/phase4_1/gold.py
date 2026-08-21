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
from crypto_ai.phase4.features import ExternalTables
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase4_1.config import GoldV2_1Config
from crypto_ai.phase4_1.features import (
    FEATURE_GROUPS_V2_1,
    FEATURE_V2_1_VERSION,
    FeatureV2_1Result,
    generate_features_v2_1,
)
from crypto_ai.research.config import DatasetBuildConfig, LabelConfig
from crypto_ai.research.gold import TARGET_COLUMN, _atomic_write_parquet, _load_silver
from crypto_ai.research.metrics import distribution_summary, feature_distribution

GOLD_V2_1_SCHEMA_VERSION = "2.1.0"


@dataclass(frozen=True, slots=True)
class GoldV2_1Result:
    dataset_version: str
    dataset_path: Path
    manifest_path: Path
    row_count: int
    feature_columns: tuple[str, ...]
    feature_groups: tuple[str, ...]
    reused: bool = False


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


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


def _load_silver_sources(
    config: GoldV2_1Config,
) -> tuple[pa.Table, list[dict[str, Any]], list[dict[str, Any]]]:
    tables: list[pa.Table] = []
    manifests: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for manifest_path in config.silver_manifests:
        dataset_config = DatasetBuildConfig(
            silver_manifest=manifest_path,
            symbol=config.symbol,
            interval=config.interval,
            start_time=config.start_time,
            end_time=config.end_time,
        )
        table, manifest, files = _load_silver(dataset_config)
        tables.append(table)
        manifests.append(manifest)
        records.extend(files)
    combined = pa.concat_tables(tables).sort_by([("open_time", "ascending")])
    times = combined.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    if np.any(np.diff(times) <= 0):
        raise ValueError("Combined Silver sources overlap or contain duplicate candles")
    return combined, manifests, records


def _external(
    path: Path | None, kind: MarketDataKind
) -> tuple[pa.Table | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    return read_market_dataset(path, kind)


def _coverage_report(features: FeatureV2_1Result, feature_times: np.ndarray) -> dict[str, Any]:
    source_by_group = {
        "price": "BTCUSDT USD-M 5m Silver klines",
        "trend": "BTCUSDT USD-M 5m Silver klines",
        "momentum": "BTCUSDT USD-M 5m Silver klines",
        "volatility": "BTCUSDT USD-M 5m Silver klines",
        "volume": "BTCUSDT USD-M 5m Silver klines",
        "taker_flow": "BTCUSDT USD-M 5m Silver kline taker volumes",
        "regime": "causal derivatives of BTCUSDT USD-M 5m Silver klines",
        "time": "UTC feature timestamp",
        "funding": "BTCUSDT USD-M funding-event Silver dataset",
        "mark_index_basis": "BTCUSDT USD-M mark/index 5m Silver datasets",
        "open_interest": "BTCUSDT USD-M open-interest Silver dataset",
    }

    def availability_summary(group: str, available: np.ndarray) -> dict[str, Any]:
        positions = np.flatnonzero(available)
        padded = np.concatenate(([False], available, [False])).astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        longest_available_run = int(np.max(ends - starts)) if len(starts) else 0
        missing = ~available
        padded_missing = np.concatenate(([False], missing, [False])).astype(np.int8)
        missing_changes = np.diff(padded_missing)
        missing_starts = np.flatnonzero(missing_changes == 1)
        missing_ends = np.flatnonzero(missing_changes == -1)
        longest_missing_run = (
            int(np.max(missing_ends - missing_starts)) if len(missing_starts) else 0
        )
        count = int(np.count_nonzero(available))
        return {
            "feature_group": group,
            "availability_start": (
                datetime.fromtimestamp(feature_times[positions[0]] / 1_000_000, tz=UTC).isoformat()
                if len(positions)
                else None
            ),
            "availability_end": (
                datetime.fromtimestamp(feature_times[positions[-1]] / 1_000_000, tz=UTC).isoformat()
                if len(positions)
                else None
            ),
            "expected_rows": len(available),
            "available_rows": count,
            "coverage_percentage": float(100.0 * count / len(available)),
            "maximum_gap_rows": longest_missing_run,
            "maximum_gap_minutes": longest_missing_run * 5,
            "maximum_contiguous_available_rows": longest_available_run,
            "missing_reason": (
                None
                if count == len(available)
                else "causal feature warm-up, source gap, source staleness, or unavailable source"
            ),
            "source_dataset": source_by_group[group],
        }

    rows: dict[str, Any] = {}
    for name in features.columns:
        finite = np.isfinite(features.values[name])
        positions = np.flatnonzero(finite)
        rows[name] = {
            "group": next(group for group in features.groups if name in FEATURE_GROUPS_V2_1[group]),
            "candidate_rows": len(finite),
            "available_rows": int(np.count_nonzero(finite)),
            "coverage_ratio": float(np.mean(finite)),
            "first_available_time": (
                datetime.fromtimestamp(feature_times[positions[0]] / 1_000_000, tz=UTC).isoformat()
                if len(positions)
                else None
            ),
            "last_available_time": (
                datetime.fromtimestamp(feature_times[positions[-1]] / 1_000_000, tz=UTC).isoformat()
                if len(positions)
                else None
            ),
        }
    return {
        "schema_version": "1.0.0",
        "feature_version": FEATURE_V2_1_VERSION,
        "candidate_rows": len(feature_times),
        "features": rows,
        "groups": {
            group: availability_summary(
                group,
                np.logical_and.reduce(
                    [np.isfinite(features.values[name]) for name in FEATURE_GROUPS_V2_1[group]]
                ),
            )
            for group in features.groups
        },
        "unavailable_or_intentionally_excluded_groups": {
            group: availability_summary(
                group,
                np.zeros(len(feature_times), dtype=bool),
            )
            | {
                "status": "UNAVAILABLE_OR_NOT_ENABLED",
                "feature_columns": list(columns),
                "missing_reason": (
                    "source not enabled or no legitimate coverage for this dataset family"
                ),
            }
            for group, columns in FEATURE_GROUPS_V2_1.items()
            if group not in features.groups
        },
    }


def _month_labels(times_us: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    months = times_us.astype("datetime64[us]").astype("datetime64[M]").astype(np.int64)
    return np.unique(months, return_inverse=True)


def _month_name(value: int) -> str:
    return str(np.datetime64("1970-01") + np.timedelta64(int(value), "M"))


def _stability_report(table: pa.Table, columns: tuple[str, ...]) -> dict[str, Any]:
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    months, inverse = _month_labels(times)
    month_indices = [np.flatnonzero(inverse == index) for index in range(len(months))]
    result: dict[str, Any] = {}
    for name in columns:
        values = table.column(name).combine_chunks().to_numpy()
        global_q25, global_median, global_q75 = np.percentile(values, [25, 50, 75])
        global_iqr = max(float(global_q75 - global_q25), 1e-12)
        monthly: list[dict[str, Any]] = []
        for month, indices in zip(months, month_indices, strict=True):
            selected = values[indices]
            q25, median, q75 = np.percentile(selected, [25, 50, 75])
            extreme = np.abs(selected - global_median) > 10.0 * global_iqr
            monthly.append(
                {
                    "month": _month_name(int(month)),
                    "count": len(indices),
                    "missing_ratio": 0.0,
                    "median": float(median),
                    "iqr": float(q75 - q25),
                    "extreme_value_rate": float(np.mean(extreme)),
                    "median_shift_in_global_iqr": float((median - global_median) / global_iqr),
                }
            )
        result[name] = {
            "global_median": float(global_median),
            "global_iqr": global_iqr,
            "extreme_definition": "abs(value-global_median) > 10*global_IQR",
            "monthly": monthly,
        }
    return {
        "schema_version": "1.0.0",
        "feature_version": FEATURE_V2_1_VERSION,
        "distribution_drift_metric": "monthly median shift divided by full-sample IQR",
        "features": result,
    }


def _target_report(table: pa.Table, near_zero: float) -> dict[str, Any]:
    target = table.column(TARGET_COLUMN).combine_chunks().to_numpy()
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    years = times.astype("datetime64[us]").astype("datetime64[Y]").astype(np.int64) + 1970
    by_year = {
        str(year): distribution_summary(target[years == year], near_zero_threshold=near_zero)
        for year in np.unique(years)
    }
    regimes: dict[str, Any] = {}
    for name in (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ):
        mask = table.column(name).combine_chunks().to_numpy() > 0
        if np.any(mask):
            regimes[name] = distribution_summary(target[mask], near_zero_threshold=near_zero)
    normal_volatility = ~(
        (table.column("high_volatility_regime").combine_chunks().to_numpy() > 0)
        | (table.column("low_volatility_regime").combine_chunks().to_numpy() > 0)
    )
    if np.any(normal_volatility):
        regimes["normal_volatility_regime"] = distribution_summary(
            target[normal_volatility], near_zero_threshold=near_zero
        )
    return {
        "schema_version": "1.0.0",
        "overall": distribution_summary(target, near_zero_threshold=near_zero),
        "by_year": by_year,
        "by_causal_regime": regimes,
    }


def build_gold_v2_1(config: GoldV2_1Config, label_config: LabelConfig) -> GoldV2_1Result:
    candles, silver_manifests, silver_files = _load_silver_sources(config)
    funding, funding_manifest = _external(config.funding_manifest, MarketDataKind.FUNDING)
    mark, mark_manifest = _external(config.mark_manifest, MarketDataKind.MARK_KLINE)
    index, index_manifest = _external(config.index_manifest, MarketDataKind.INDEX_KLINE)
    oi, oi_manifest = _external(config.open_interest_manifest, MarketDataKind.OPEN_INTEREST)
    features = generate_features_v2_1(
        candles,
        interval=config.interval,
        external=ExternalTables(funding=funding, mark=mark, index=index, open_interest=oi),
    )
    labels = generate_forward_return_labels(candles, interval=config.interval, config=label_config)
    usable = features.valid_mask & labels.valid_mask
    indices = np.flatnonzero(usable)
    if not len(indices):
        raise ValueError("No causally complete market_v2_1 rows have Label V1 targets")

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
        "feature_version": [FEATURE_V2_1_VERSION] * len(indices),
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
        "schema_version": GOLD_V2_1_SCHEMA_VERSION,
        "silver_versions": [item["silver_dataset_version"] for item in silver_manifests],
        "silver_sha256": [item["sha256"] for item in silver_files],
        "external_versions": {
            name: manifest["dataset_version"] for name, manifest in external_manifests.items()
        },
        "configuration": config.model_dump(mode="json"),
        "feature_version": FEATURE_V2_1_VERSION,
        "feature_columns": features.columns,
        "label": label_config.model_dump(mode="json"),
        "join_policy": "availability_time<=feature_time; source-frequency staleness limits",
    }
    dataset_version = f"gold-v2-1-{_hash(identity)}"
    directory = config.output_root.resolve() / dataset_version
    dataset_path, manifest_path = directory / "dataset.parquet", directory / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None:
        if not dataset_path.exists() or file_sha256(dataset_path) != existing.get("sha256"):
            raise ValueError(f"Gold V2.1 checksum mismatch: {dataset_path}")
        return GoldV2_1Result(
            dataset_version,
            dataset_path,
            manifest_path,
            int(existing["row_count"]),
            tuple(existing["feature_columns"]),
            tuple(existing["feature_groups"]),
            True,
        )

    metadata = {
        b"schema_version": GOLD_V2_1_SCHEMA_VERSION.encode(),
        b"dataset_version": dataset_version.encode(),
        b"layer": b"gold",
        b"feature_version": FEATURE_V2_1_VERSION.encode(),
        b"label_version": label_config.version.encode(),
        b"feature_columns": json.dumps(features.columns).encode(),
        b"feature_groups": json.dumps(features.groups).encode(),
    }
    checksum = _atomic_write_parquet(dataset_path, table.replace_schema_metadata(metadata))
    feature_times = candle_times + 300_000_000
    coverage = _coverage_report(features, feature_times)
    stability = _stability_report(table, features.columns)
    target = _target_report(table, near_zero=label_config.near_zero_threshold_bps / 10_000)
    coverage_path = directory / "feature_coverage.json"
    stability_path = directory / "feature_stability.json"
    target_path = directory / "target_analysis.json"
    write_manifest(coverage_path, coverage)
    write_manifest(stability_path, stability)
    write_manifest(target_path, target)
    feature_summaries = {
        name: feature_distribution(table.column(name).combine_chunks().to_numpy())
        for name in features.columns
    }
    manifest = {
        "dataset_version": dataset_version,
        "dataset_family": config.dataset_family,
        "schema_version": GOLD_V2_1_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "research_cutoff_exclusive": config.end_time.isoformat(),
        "file": "dataset.parquet",
        "sha256": checksum,
        "row_count": table.num_rows,
        "symbol": config.symbol,
        "interval": config.interval,
        "source_silver_manifests": [str(path.resolve()) for path in config.silver_manifests],
        "source_silver_versions": [item["silver_dataset_version"] for item in silver_manifests],
        "source_silver_files": silver_files,
        "external_sources": {
            name: {
                "manifest": str(getattr(config, f"{name}_manifest", "")),
                "dataset_version": source["dataset_version"],
                "sha256": source["sha256"],
            }
            for name, source in external_manifests.items()
        },
        "feature_version": FEATURE_V2_1_VERSION,
        "feature_count": len(features.columns),
        "feature_columns": list(features.columns),
        "feature_groups": list(features.groups),
        "feature_group_columns": {
            group: list(FEATURE_GROUPS_V2_1[group]) for group in features.groups
        },
        "feature_diagnostics": features.diagnostics,
        "feature_distributions": feature_summaries,
        "feature_coverage_report": {
            "file": coverage_path.name,
            "sha256": file_sha256(coverage_path),
        },
        "feature_stability_report": {
            "file": stability_path.name,
            "sha256": file_sha256(stability_path),
        },
        "target_analysis_report": {
            "file": target_path.name,
            "sha256": file_sha256(target_path),
        },
        "target_column": TARGET_COLUMN,
        "target_distribution": target["overall"],
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
            "missing_behavior": "exclude; never backward-fill or encode unavailable as zero",
        },
        "build_summary": {
            "candidate_rows": candles.num_rows,
            "feature_valid_rows": int(np.count_nonzero(features.valid_mask)),
            "label_valid_rows": labels.valid_count,
            "final_rows": table.num_rows,
        },
        "code_version": "phase4.1-1.0.0",
    }
    write_manifest(manifest_path, manifest)
    return GoldV2_1Result(
        dataset_version,
        dataset_path,
        manifest_path,
        table.num_rows,
        features.columns,
        features.groups,
    )


def read_gold_v2_1(manifest_path: Path) -> tuple[pa.Table, dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(manifest_path)
    path = manifest_path.parent / str(manifest.get("file", "dataset.parquet"))
    if not path.exists() or file_sha256(path) != manifest.get("sha256"):
        raise ValueError(f"Gold V2.1 checksum mismatch: {path}")
    table = pq.ParquetFile(path).read()
    if (table.schema.metadata or {}).get(b"dataset_version", b"").decode() != manifest.get(
        "dataset_version"
    ):
        raise ValueError("Gold V2.1 Parquet/manifest lineage mismatch")
    return table, manifest
