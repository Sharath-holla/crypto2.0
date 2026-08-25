from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pyarrow as pa
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan, HardenedFoldData, plan_folds, slice_hardened_fold
from crypto_ai.phase7.config import UniverseConfig
from crypto_ai.phase7.features import bind_fold_cross_sectional_context
from crypto_ai.phase7.registry import SymbolRegistry
from crypto_ai.phase7.universe import (
    ExpansionUniversePolicy,
    FrozenUniverse,
    SymbolDescriptor,
    build_expansion_policy,
    latest_descriptors,
    select_fold_active_universe,
)


@dataclass(frozen=True, slots=True)
class MultiAssetFoldData:
    plan: FoldPlan
    train: pa.Table
    validation: pa.Table
    calibration_a: pa.Table
    calibration_b: pa.Table
    _test: pa.Table
    eligibility_manifest: dict[str, Any]
    cluster_mapping: dict[str, int]
    liquidity_tiers: dict[str, str]
    age_buckets: dict[str, str]
    research_view: Literal["CORE", "EXPANDING"]
    report: dict[str, Any]

    def release_test(self, *, frozen_identity: str) -> pa.Table:
        if not frozen_identity:
            raise ValueError("test release requires frozen model/calibrator/policy identity")
        return self._test


def _filter_symbols(table: pa.Table, symbols: set[str]) -> pa.Table:
    values = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    return table.filter(pa.array(np.asarray([str(value) in symbols for value in values])))


def _descriptor_matrix(symbols: list[str], descriptors: dict[str, SymbolDescriptor]) -> np.ndarray:
    rows: list[list[float]] = []
    for symbol in symbols:
        item = descriptors[symbol]
        rows.append(
            [
                np.log1p(item.trailing_quote_volume),
                item.realized_volatility,
                item.btc_beta if item.btc_beta is not None else 0.0,
                item.btc_correlation if item.btc_correlation is not None else 0.0,
                item.funding_variability if item.funding_variability is not None else 0.0,
                np.log1p(item.trade_intensity),
                np.log1p(item.history_days),
            ]
        )
    return np.asarray(rows, dtype=np.float64)


def fit_train_only_clusters(
    descriptors: list[SymbolDescriptor],
    *,
    train_end: datetime,
    eligible_symbols: set[str],
    cluster_count: int,
    seed: int,
) -> tuple[dict[str, int], dict[str, Any]]:
    point_in_time = latest_descriptors(descriptors, as_of=train_end)
    symbols = sorted(symbol for symbol in eligible_symbols if symbol in point_in_time)
    if not symbols:
        raise ValueError("cluster fit needs train-known eligible descriptors")
    actual_clusters = min(cluster_count, len(symbols))
    matrix = _descriptor_matrix(symbols, point_in_time)
    scaled = StandardScaler().fit_transform(matrix)
    if actual_clusters == 1:
        labels = np.zeros(len(symbols), dtype=np.int64)
    else:
        labels = KMeans(
            n_clusters=actual_clusters,
            random_state=seed,
            n_init=10,
        ).fit_predict(scaled)
    mapping = {symbol: int(label) for symbol, label in zip(symbols, labels, strict=True)}
    cluster_report: dict[str, Any] = {}
    for cluster_id in sorted(set(mapping.values())):
        members = [symbol for symbol in symbols if mapping[symbol] == cluster_id]
        cluster_report[str(cluster_id)] = {
            "symbols": members,
            "size": len(members),
            "median_volatility": float(
                np.median([point_in_time[symbol].realized_volatility for symbol in members])
            ),
            "median_liquidity": float(
                np.median([point_in_time[symbol].trailing_quote_volume for symbol in members])
            ),
            "median_btc_beta": float(
                np.median([point_in_time[symbol].btc_beta or 0.0 for symbol in members])
            ),
            "median_btc_correlation": float(
                np.median([point_in_time[symbol].btc_correlation or 0.0 for symbol in members])
            ),
        }
    identity = hashlib.sha256(
        json.dumps(
            {
                "train_end": train_end.isoformat(),
                "mapping": mapping,
                "descriptors": {
                    symbol: point_in_time[symbol].model_dump(mode="json") for symbol in symbols
                },
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:24]
    return mapping, {"identity": identity, "fit_source": "TRAIN_ONLY", "clusters": cluster_report}


def fit_train_only_liquidity_tiers(
    descriptors: list[SymbolDescriptor],
    *,
    train_end: datetime,
    eligible_symbols: set[str],
) -> dict[str, str]:
    point_in_time = latest_descriptors(descriptors, as_of=train_end)
    symbols = sorted(symbol for symbol in eligible_symbols if symbol in point_in_time)
    values = np.asarray(
        [point_in_time[symbol].trailing_quote_volume for symbol in symbols], dtype=np.float64
    )
    low, high = np.quantile(values, [1 / 3, 2 / 3]) if len(values) > 1 else (values[0], values[0])
    result: dict[str, str] = {}
    for symbol, value in zip(symbols, values, strict=True):
        if value >= high:
            result[symbol] = "HIGH_LIQUIDITY"
        elif value >= low:
            result[symbol] = "MEDIUM_LIQUIDITY"
        else:
            result[symbol] = "LOWER_LIQUIDITY"
    return result


def plan_multiasset_folds(
    *,
    data_start: datetime,
    research_cutoff: datetime,
    holdout_start: datetime,
    schedule: ScheduleConfig,
) -> tuple[FoldPlan, ...]:
    """Derive calendar folds from configuration boundaries, never observed row maxima."""

    return plan_folds(data_start, research_cutoff, holdout_start, schedule)


def slice_multiasset_fold(
    table: pa.Table,
    plan: FoldPlan,
    *,
    registry: SymbolRegistry,
    universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy | None = None,
    research_view: Literal["CORE", "EXPANDING"] = "CORE",
    descriptors: list[SymbolDescriptor],
    universe_config: UniverseConfig,
    schedule: ScheduleConfig,
    holdout_start: datetime,
    cluster_count: int,
    seed: int,
) -> MultiAssetFoldData:
    policy = expansion_policy or build_expansion_policy(universe, universe_config)
    membership = select_fold_active_universe(
        registry,
        descriptors,
        fold_id=plan.fold_id,
        train_end=plan.train_end,
        core_universe=universe,
        expansion_policy=policy,
        config=universe_config,
        research_view=research_view,
    )
    eligible_symbols = set(membership.active_symbols)
    if not eligible_symbols:
        raise ValueError(f"{plan.fold_id} has no point-in-time eligible symbols")
    eligible_table = bind_fold_cross_sectional_context(_filter_symbols(table, eligible_symbols))
    sliced: HardenedFoldData = slice_hardened_fold(
        eligible_table,
        plan,
        schedule,
        holdout_start,
    )
    clusters, cluster_report = fit_train_only_clusters(
        descriptors,
        train_end=plan.train_end,
        eligible_symbols=eligible_symbols,
        cluster_count=cluster_count,
        seed=seed,
    )
    liquidity = fit_train_only_liquidity_tiers(
        descriptors,
        train_end=plan.train_end,
        eligible_symbols=eligible_symbols,
    )
    age_buckets = {
        member.symbol: member.age_bucket
        for member in membership.members
        if member.symbol in eligible_symbols
    }
    eligibility_manifest = {
        "fold_id": plan.fold_id,
        "eligibility_as_of": plan.train_end.isoformat(),
        "research_view": research_view,
        "eligible_symbols": sorted(eligible_symbols),
        "core_eligible_symbols": list(membership.core_eligible_symbols),
        "expansion_eligible_symbols": list(membership.expansion_eligible_symbols),
        "fold_active_symbols": list(membership.active_symbols),
        "fold_membership_hash": membership.membership_hash,
        "fold_membership": [item.model_dump(mode="json") for item in membership.members],
        "core_universe_version": universe.version,
        "core_universe_hash": universe.universe_hash,
        "core_candidate_symbols": list(universe.symbols),
        "expansion_policy_version": policy.version,
        "expansion_policy_hash": policy.policy_hash,
        "total_max_symbols_per_fold": policy.total_max_symbols_per_fold,
        "expansion_max_symbols_per_fold": policy.expansion_max_symbols_per_fold,
        "ineligible_symbols": [
            {
                "symbol": member.symbol,
                "source": member.source,
                "status": member.quality_status,
                "reasons": [member.reason],
            }
            for member in membership.members
            if not member.eligible
        ],
        "cluster_mapping": clusters,
        "cluster_report": cluster_report,
        "liquidity_tiers": liquidity,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
    }
    return MultiAssetFoldData(
        plan=plan,
        train=sliced.train,
        validation=sliced.validation,
        calibration_a=sliced.calibration_a,
        calibration_b=sliced.calibration_b,
        _test=sliced._test,
        eligibility_manifest=eligibility_manifest,
        cluster_mapping=clusters,
        liquidity_tiers=liquidity,
        age_buckets=age_buckets,
        research_view=research_view,
        report=sliced.report,
    )
