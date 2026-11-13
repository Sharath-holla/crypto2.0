from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import FoldPlan, HardenedFoldData, plan_folds, slice_hardened_fold
from crypto_ai.phase7.config import UniverseConfig
from crypto_ai.phase7.features import bind_fold_cross_sectional_context
from crypto_ai.phase7.registry import SymbolRegistry
from crypto_ai.phase7.segments import CausalDataGap
from crypto_ai.phase7.universe import (
    ExpansionUniversePolicy,
    FrozenUniverse,
    SymbolDescriptor,
    build_expansion_policy,
    latest_descriptors,
    select_fold_active_universe,
)


# CHANGED BY CLAUDE (2026-11-02, finding M-06): typed error so operators and tests can tell a
# post-TRAIN data gap (a data defect that blocks the fold) from any other ValueError.
class PostTrainDataGapError(ValueError):
    """An active symbol has an unusable data gap after TRAIN; the whole fold is blocked.

    Subclasses ValueError and keeps the original message text, so existing handlers and
    ``pytest.raises(ValueError, match="post-TRAIN data-quality gaps")`` still work.
    Deliberately NOT an IneligibleFoldError: it must never be recorded as INELIGIBLE.
    """

    def __init__(self, fold_id: str, gaps: list[dict[str, str]]) -> None:
        self.fold_id = fold_id
        self.gaps = gaps
        self.symbols = sorted({gap["symbol"] for gap in gaps})
        listing = sorted(
            f"{gap['symbol']}:{gap['interval']}:{gap['partition']}[{gap['start']} -> {gap['end']}]"
            for gap in gaps
        )
        super().__init__(
            f"{fold_id} has post-TRAIN data-quality gaps for active symbols; "
            f"TRAIN membership is unchanged; explicit data-quality review required: {listing}"
        )


# CHANGED BY CLAUDE (2026-11-02, finding M-02): raised when TEST is read out of order.
class TestAccessViolation(RuntimeError):
    """TEST rows were requested in a way that could let them influence selection."""

    __test__ = False  # not a pytest test class despite the name


class IneligibleFoldError(ValueError):
    """A fold/experiment cannot run under the configured eligibility minimums.

    Only this exception type may be recorded as an ``INELIGIBLE`` experiment
    report. Any other failure is a defect and must propagate (fail closed).
    """


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
    # CHANGED BY CLAUDE (2026-11-02, finding M-02): measured ledger of every TEST release.
    _test_access_log: list[dict[str, Any]] = field(default_factory=list)

    # OLD CODE (kept for reference): the gate only checked that an identity string existed.
    # def release_test(self, *, frozen_identity: str) -> pa.Table:
    #     if not frozen_identity:
    #         raise ValueError("test release requires frozen model/calibrator/policy identity")
    #     return self._test
    def release_test(
        self,
        *,
        frozen_identity: str,
        expected_identity: str | None = None,
        consumer: str | None = None,
    ) -> pa.Table:
        """Release TEST rows once a model/calibrator/policy identity is frozen.

        ``expected_identity`` (when given) is re-derived by the caller from the live frozen
        objects and must equal ``frozen_identity``. ``consumer`` names the experiment taking
        the rows; a consumer that already received TEST under a *different* identity has
        touched TEST before its selection was frozen, which fails loudly. Every release is
        logged with the row count and feature-time range actually handed out.
        """

        if not frozen_identity:
            raise ValueError("test release requires frozen model/calibrator/policy identity")
        if expected_identity is not None and expected_identity != frozen_identity:
            raise TestAccessViolation(
                f"{self.plan.fold_id}: frozen identity does not match the re-derived identity"
            )
        if consumer is not None:
            for entry in self._test_access_log:
                if entry["consumer"] == consumer and entry["frozen_identity"] != frozen_identity:
                    raise TestAccessViolation(
                        f"{self.plan.fold_id}: {consumer} already read TEST under a different "
                        "frozen identity; selection must be frozen before TEST is touched"
                    )
        first = last = None
        if self._test.num_rows and "feature_time" in self._test.column_names:
            bounds = pc.min_max(self._test.column("feature_time")).as_py()
            first, last = bounds["min"], bounds["max"]
        self._test_access_log.append(
            {
                "consumer": consumer,
                "frozen_identity": frozen_identity,
                "rows": int(self._test.num_rows),
                "feature_time_min": None if first is None else first.isoformat(),
                "feature_time_max": None if last is None else last.isoformat(),
            }
        )
        return self._test

    def test_touched_by(self, consumer: str) -> bool:
        """True if ``consumer`` has already been handed TEST rows (measured, not asserted)."""

        return any(entry["consumer"] == consumer for entry in self._test_access_log)

    def test_access_summary(self, consumer: str | None = None) -> dict[str, Any]:
        entries = [
            dict(entry)
            for entry in self._test_access_log
            if consumer is None or entry["consumer"] == consumer
        ]
        return {"test_release_count": len(entries), "releases": entries}


def _filter_symbols(table: pa.Table, symbols: set[str]) -> pa.Table:
    # CHANGED BY CLAUDE (2026-11-13, low-memory profile): opt-in vectorized filter with the same
    # rows and order; returns the input unchanged when every row is eligible.
    from crypto_ai.phase7 import low_memory

    if low_memory.enabled():
        return low_memory.filter_symbols(table, symbols)
    values = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    mask = pa.array([str(value) in symbols for value in values], type=pa.bool_())
    return table.filter(mask)


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


def fold_membership(
    plan: FoldPlan,
    *,
    registry: SymbolRegistry,
    universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy | None,
    research_view: Literal["CORE", "EXPANDING"],
    descriptors: list[SymbolDescriptor],
    universe_config: UniverseConfig,
    unusable_segments: tuple[CausalDataGap, ...] = (),
) -> tuple[Any, Any, set[str]]:
    """Point-in-time fold membership and post-TRAIN gap gate (extracted, unchanged)."""

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
        unusable_segments=unusable_segments,
        required_start=plan.train_start,
        required_end=plan.test_end,
    )
    eligible_symbols = set(membership.active_symbols)
    if not eligible_symbols:
        raise IneligibleFoldError(f"{plan.fold_id} has no point-in-time eligible symbols")
    # CHANGED BY CLAUDE (2026-11-02, finding M-06): the gap list now keeps symbol, interval,
    # partition and the gap's time range so the error can name them.
    # OLD CODE (kept for reference):
    # later_gaps = sorted(
    #     {
    #         f"{gap.symbol}:{gap.interval}:{gap.partition}"
    #         for gap in unusable_segments
    #         if gap.symbol in eligible_symbols and gap.intersects(plan.train_end, plan.test_end)
    #     }
    # )
    later_gaps = sorted(
        (
            {
                "symbol": gap.symbol,
                "interval": gap.interval,
                "partition": gap.partition,
                "start": gap.start.isoformat(),
                "end": gap.end.isoformat(),
            }
            for gap in unusable_segments
            if gap.symbol in eligible_symbols and gap.intersects(plan.train_end, plan.test_end)
        ),
        key=lambda item: (item["symbol"], item["interval"], item["partition"], item["start"]),
    )
    if later_gaps:
        # Do not replace a noncausal symbol exclusion with permissive partial OOS
        # evaluation. Preserve membership and stop the entire affected fold as
        # a data defect (never INELIGIBLE or a completed scientific result).
        # OLD CODE (kept for reference):
        # raise ValueError(
        #     f"{plan.fold_id} has post-TRAIN data-quality gaps for active symbols; "
        #     f"TRAIN membership is unchanged; explicit data-quality review required: "
        #     f"{later_gaps}"
        # )
        raise PostTrainDataGapError(plan.fold_id, later_gaps)
    return policy, membership, eligible_symbols


def fold_metadata(
    plan: FoldPlan,
    *,
    policy: Any,
    membership: Any,
    eligible_symbols: set[str],
    universe: FrozenUniverse,
    research_view: Literal["CORE", "EXPANDING"],
    descriptors: list[SymbolDescriptor],
    cluster_count: int,
    seed: int,
    unusable_segments: tuple[CausalDataGap, ...] = (),
) -> dict[str, Any]:
    """TRAIN-only clusters/tiers and the eligibility manifest (extracted, unchanged)."""

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
        "gap_gate_policy": membership.gap_gate_policy,
        "fold_membership": [item.model_dump(mode="json") for item in membership.members],
        "unusable_segments": [
            gap.model_dump(mode="json")
            for gap in unusable_segments
            if gap.intersects(plan.train_start, plan.test_end)
        ],
        "unusable_segments_role": "FOLD_COVERAGE_DIAGNOSTICS_NOT_MEMBERSHIP_SELECTION",
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
    return {
        "clusters": clusters,
        "cluster_report": cluster_report,
        "liquidity": liquidity,
        "age_buckets": age_buckets,
        "eligibility_manifest": eligibility_manifest,
    }


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
    unusable_segments: tuple[CausalDataGap, ...] = (),
    context_source: pa.Table | None = None,
) -> MultiAssetFoldData:
    # CHANGED BY CLAUDE (2026-11-13): membership/gap gating and fold metadata were extracted
    # verbatim into helpers so the opt-in staged slicer reuses them; values are unchanged.
    policy, membership, eligible_symbols = fold_membership(
        plan,
        registry=registry,
        universe=universe,
        expansion_policy=expansion_policy,
        research_view=research_view,
        descriptors=descriptors,
        universe_config=universe_config,
        unusable_segments=unusable_segments,
    )
    eligible_table = _filter_symbols(table, eligible_symbols)
    if eligible_table.num_rows == 0:
        # Eligible symbols exist, yet this fold table carries no rows for them:
        # a Gold/data coverage defect, not an eligibility outcome. Crash loudly.
        raise ValueError(
            f"{plan.fold_id} has point-in-time eligible symbols but zero rows "
            "in the fold table; Gold coverage defect, not an INELIGIBLE outcome"
        )
    # Cross-sectional context must be built from all horizons' feature rows (a
    # horizon-invariant superset), never from the rows that happen to carry a valid
    # label for this horizon; otherwise context at time t reveals future label
    # availability (M-01). The source is restricted to the same eligible symbols.
    eligible_context = (
        _filter_symbols(context_source, eligible_symbols) if context_source is not None else None
    )
    eligible_table = bind_fold_cross_sectional_context(
        eligible_table, context_source=eligible_context
    )
    # CHANGED BY CLAUDE (2026-11-13, low-memory profile): opt-in zero-copy twin of the Phase 5
    # slicer (identical segments, purge, embargo, checks and report); Phase 5 is untouched.
    from crypto_ai.phase7 import low_memory

    slicer = low_memory.slice_hardened_fold if low_memory.enabled() else slice_hardened_fold
    sliced: HardenedFoldData = slicer(
        eligible_table,
        plan,
        schedule,
        holdout_start,
    )
    del eligible_table
    metadata = fold_metadata(
        plan,
        policy=policy,
        membership=membership,
        eligible_symbols=eligible_symbols,
        universe=universe,
        research_view=research_view,
        descriptors=descriptors,
        cluster_count=cluster_count,
        seed=seed,
        unusable_segments=unusable_segments,
    )
    return MultiAssetFoldData(
        plan=plan,
        train=sliced.train,
        validation=sliced.validation,
        calibration_a=sliced.calibration_a,
        calibration_b=sliced.calibration_b,
        _test=sliced._test,
        eligibility_manifest=metadata["eligibility_manifest"],
        cluster_mapping=metadata["clusters"],
        liquidity_tiers=metadata["liquidity"],
        age_buckets=metadata["age_buckets"],
        research_view=research_view,
        report=sliced.report,
    )
