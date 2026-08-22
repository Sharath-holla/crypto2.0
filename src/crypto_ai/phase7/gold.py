from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import atomic_json, write_partitioned_table
from crypto_ai.phase7.config import FEATURE_VERSION, TARGET_VERSION, stable_hash
from crypto_ai.phase7.features import (
    ANCHOR_CONTEXT_COLUMNS,
    BASE_FEATURE_COLUMNS,
    COIN_CONTEXT_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
    MultiAssetFeatureResult,
)
from crypto_ai.phase7.targets import MultiAssetTargetResult


@dataclass(frozen=True, slots=True)
class MultiAssetGoldResult:
    dataset_id: str
    root: Path
    manifest_path: Path
    partition_paths: tuple[Path, ...]
    row_count: int
    feature_groups: dict[str, tuple[str, ...]]


def _joined_gold_table(
    features: MultiAssetFeatureResult,
    targets: MultiAssetTargetResult,
    *,
    research_cutoff: datetime,
    prospective_holdout_start: datetime,
) -> pa.Table:
    joined = features.table.join(
        targets.table,
        keys=["symbol", "feature_time"],
        join_type="inner",
    ).sort_by(
        [("feature_time", "ascending"), ("symbol", "ascending"), ("horizon_minutes", "ascending")]
    )
    cutoff_us = int(research_cutoff.astimezone(UTC).timestamp() * 1_000_000)
    holdout_us = int(prospective_holdout_start.astimezone(UTC).timestamp() * 1_000_000)
    feature_times = joined.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    label_ends = joined.column("label_end_time").combine_chunks().cast(pa.int64()).to_numpy()
    if len(feature_times) and (
        np.max(feature_times) >= cutoff_us or np.max(label_ends) >= cutoff_us
    ):
        raise ValueError("Phase 7 Gold crossed the exclusive research cutoff")
    if len(feature_times) and (
        np.max(feature_times) >= holdout_us or np.max(label_ends) >= holdout_us
    ):
        raise ValueError("Phase 7 Gold touched the prospective holdout")
    return joined


def feature_ablation_sets(feature_columns: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    derivatives = ("funding_zscore", "mark_index_basis", "contract_mark_basis")
    excluded_base = set(derivatives)
    normalized_coin = tuple(
        name
        for name in BASE_FEATURE_COLUMNS + COIN_CONTEXT_COLUMNS
        if name in feature_columns and name not in excluded_base
    )
    btc = tuple(
        name
        for name in ANCHOR_CONTEXT_COLUMNS
        if name.startswith("btc_") and name in feature_columns
    )
    eth = tuple(
        name
        for name in ANCHOR_CONTEXT_COLUMNS
        if name.startswith("eth_") and name in feature_columns
    )
    market = tuple(name for name in MARKET_CONTEXT_COLUMNS if name in feature_columns)
    twelve_hour = tuple(name for name in feature_columns if name.startswith("htf_12h_"))
    daily = tuple(name for name in feature_columns if name.startswith("htf_1d_"))

    def cumulative(*groups: tuple[str, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for group in groups:
            for name in group:
                if name not in result:
                    result.append(name)
        return tuple(result)

    return {
        "A0": normalized_coin,
        "A1": cumulative(normalized_coin, btc),
        "A2": cumulative(normalized_coin, btc, eth),
        "A3": cumulative(normalized_coin, btc, eth, market),
        "A4": cumulative(normalized_coin, btc, eth, market, twelve_hour),
        "A5": cumulative(normalized_coin, btc, eth, market, twelve_hour, daily),
        "A6": cumulative(
            normalized_coin,
            btc,
            eth,
            market,
            twelve_hour,
            daily,
            tuple(name for name in derivatives if name in feature_columns),
        ),
        "BASE": normalized_coin,
        "BASE_PLUS_12H": cumulative(normalized_coin, twelve_hour),
        "BASE_PLUS_1D": cumulative(normalized_coin, daily),
        "BASE_PLUS_12H_1D": cumulative(normalized_coin, twelve_hour, daily),
    }


def _finite_coverage(table: pa.Table, columns: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in columns:
        values = np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)
        finite = np.isfinite(values)
        result[name] = {
            "available_rows": int(np.count_nonzero(finite)),
            "coverage_ratio": float(np.mean(finite)) if len(finite) else 0.0,
        }
    return result


def build_multiasset_gold(
    features: MultiAssetFeatureResult,
    targets: MultiAssetTargetResult,
    *,
    output_root: Path,
    universe_version: str,
    universe_hash: str,
    registry_version: str,
    registry_hash: str,
    research_cutoff: datetime,
    prospective_holdout_start: datetime,
    lineage: dict[str, Any],
) -> MultiAssetGoldResult:
    if research_cutoff.tzinfo is None or prospective_holdout_start.tzinfo is None:
        raise ValueError("Gold boundaries must be timezone-aware")
    joined = _joined_gold_table(
        features,
        targets,
        research_cutoff=research_cutoff,
        prospective_holdout_start=prospective_holdout_start,
    )
    groups = feature_ablation_sets(features.feature_columns)
    identity = {
        "feature_version": FEATURE_VERSION,
        "target_version": TARGET_VERSION,
        "universe_version": universe_version,
        "universe_hash": universe_hash,
        "registry_version": registry_version,
        "registry_hash": registry_hash,
        "research_cutoff": research_cutoff.astimezone(UTC).isoformat(),
        "prospective_holdout_start": prospective_holdout_start.astimezone(UTC).isoformat(),
        "rows": joined.num_rows,
        "feature_columns": list(features.feature_columns),
        "feature_groups": {name: list(values) for name, values in groups.items()},
        "lineage": lineage,
    }
    dataset_id = f"gold-phase7-{stable_hash(identity)}"
    root = output_root.resolve() / dataset_id
    partitions = tuple(write_partitioned_table(root / "dataset", joined))
    manifest = identity | {
        "dataset_id": dataset_id,
        "classification": "RETROSPECTIVE_MULTI_ASSET_RESEARCH",
        "partitioned_by": ["symbol", "year"],
        "partition_files": [
            {
                "path": path.resolve().relative_to(root.resolve()).as_posix(),
                "sha256": file_sha256(path),
            }
            for path in partitions
        ],
        "feature_coverage": _finite_coverage(joined, features.feature_columns),
        "prospective_holdout_used": False,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_evaluation_authorized": False,
        "july_2026_used": False,
        "row_count": joined.num_rows,
    }
    manifest_path = atomic_json(root / "manifest.json", manifest)
    return MultiAssetGoldResult(
        dataset_id=dataset_id,
        root=root,
        manifest_path=manifest_path,
        partition_paths=partitions,
        row_count=joined.num_rows,
        feature_groups=groups,
    )


def build_multiasset_gold_chunks(
    chunks: Iterable[tuple[str, MultiAssetFeatureResult, MultiAssetTargetResult]],
    *,
    feature_columns: tuple[str, ...],
    output_root: Path,
    universe_version: str,
    universe_hash: str,
    registry_version: str,
    registry_hash: str,
    research_cutoff: datetime,
    prospective_holdout_start: datetime,
    lineage: dict[str, Any],
) -> MultiAssetGoldResult:
    """Write bounded time chunks so the full multi-year feature matrix is never resident."""

    groups = feature_ablation_sets(feature_columns)
    identity = {
        "feature_version": FEATURE_VERSION,
        "target_version": TARGET_VERSION,
        "universe_version": universe_version,
        "universe_hash": universe_hash,
        "registry_version": registry_version,
        "registry_hash": registry_hash,
        "research_cutoff": research_cutoff.astimezone(UTC).isoformat(),
        "prospective_holdout_start": prospective_holdout_start.astimezone(UTC).isoformat(),
        "feature_columns": list(feature_columns),
        "feature_groups": {name: list(values) for name, values in groups.items()},
        "lineage": lineage,
        "storage_mode": "bounded_time_chunks",
    }
    dataset_id = f"gold-phase7-{stable_hash(identity)}"
    root = output_root.resolve() / dataset_id
    partitions: list[Path] = []
    chunk_records: list[dict[str, Any]] = []
    available = {name: 0 for name in feature_columns}
    total_rows = 0
    for chunk_id, features, targets in chunks:
        if features.feature_columns != feature_columns:
            raise ValueError(f"Feature schema drift in Gold chunk {chunk_id}")
        joined = _joined_gold_table(
            features,
            targets,
            research_cutoff=research_cutoff,
            prospective_holdout_start=prospective_holdout_start,
        )
        written = write_partitioned_table(root / "dataset", joined)
        partitions.extend(written)
        total_rows += joined.num_rows
        for name in feature_columns:
            values = np.asarray(joined.column(name).combine_chunks().to_pylist(), dtype=np.float64)
            available[name] += int(np.count_nonzero(np.isfinite(values)))
        chunk_records.append(
            {
                "chunk_id": chunk_id,
                "row_count": joined.num_rows,
                "partition_count": len(written),
            }
        )
    if not partitions or not total_rows:
        raise ValueError("Chunked Phase 7 Gold produced no rows")
    resolved = [path.resolve() for path in partitions]
    if len(resolved) != len(set(resolved)):
        raise ValueError("Chunked Gold attempted to write the same partition twice")
    manifest = identity | {
        "dataset_id": dataset_id,
        "classification": "RETROSPECTIVE_MULTI_ASSET_RESEARCH",
        "partitioned_by": ["symbol", "year"],
        "partition_files": [
            {
                "path": path.resolve().relative_to(root.resolve()).as_posix(),
                "sha256": file_sha256(path),
            }
            for path in partitions
        ],
        "feature_coverage": {
            name: {
                "available_rows": count,
                "coverage_ratio": count / total_rows,
            }
            for name, count in available.items()
        },
        "chunks": chunk_records,
        "prospective_holdout_used": False,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_evaluation_authorized": False,
        "july_2026_used": False,
        "row_count": total_rows,
    }
    manifest_path = atomic_json(root / "manifest.json", manifest)
    return MultiAssetGoldResult(
        dataset_id=dataset_id,
        root=root,
        manifest_path=manifest_path,
        partition_paths=tuple(partitions),
        row_count=total_rows,
        feature_groups=groups,
    )
