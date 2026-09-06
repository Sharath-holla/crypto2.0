from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.folds import add_calendar_months, plan_folds
from crypto_ai.phase7.acquisition import (
    acquire_candle_family,
    acquire_derivative_family,
    acquire_discovery_daily,
    align_derivatives,
    load_candle_family,
    validated_candle_manifest_range,
)
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json, resource_snapshot
from crypto_ai.phase7.config import TARGET_VERSION, UNIVERSE_VERSION, Phase7Config
from crypto_ai.phase7.discovery_checkpoint import DiscoverySymbolCheckpointStore
from crypto_ai.phase7.features import (
    MultiAssetFeatureResult,
    build_higher_timeframe_context,
    generate_multiasset_features,
)
from crypto_ai.phase7.gold import build_multiasset_gold_chunks
from crypto_ai.phase7.progress import ProgressReporter
from crypto_ai.phase7.quality import build_point_in_time_descriptors
from crypto_ai.phase7.registry import (
    SymbolRegistry,
    build_symbol_registry,
    read_registry,
    write_registry,
)
from crypto_ai.phase7.segments import CausalDataGap
from crypto_ai.phase7.sources import (
    BinancePublicDiscoveryClient,
    source_verification_manifest,
)
from crypto_ai.phase7.targets import MultiAssetTargetResult, generate_multiasset_targets
from crypto_ai.phase7.training import run_phase7_training
from crypto_ai.phase7.universe import (
    ExpansionUniversePolicy,
    FrozenUniverse,
    SymbolDescriptor,
    build_expansion_policy,
    read_expansion_policy,
    read_universe,
    research_universe_identity,
    select_core_universe,
    select_fold_active_universe,
    write_expansion_policy,
    write_universe,
)

STAGES = ("registry", "universe", "data", "gold", "train", "report")
DATA_CANDLE_COVERAGE_CONTRACT_VERSION = "phase7_full_causal_candle_coverage_v1"


def _validated_range_payload(manifest: str) -> dict[str, str]:
    start, end = validated_candle_manifest_range(manifest)
    return {"start": start.isoformat(), "end_exclusive": end.isoformat()}


def _run_context(config: Phase7Config) -> tuple[str, Path, datetime]:
    run_identity = f"phase7-{config.configuration_hash}"
    run_root = config.paths.artifact_root.resolve() / run_identity
    path = run_root / "run.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("configuration_hash") != config.configuration_hash:
            raise ValueError("Phase 7 run identity/configuration mismatch")
        started_at = datetime.fromisoformat(payload["started_at"])
    else:
        started_at = datetime.now(UTC)
        atomic_json(
            path,
            {
                "run_identity": run_identity,
                "configuration_hash": config.configuration_hash,
                "phase": 7,
                "mode": config.mode,
                "started_at": started_at.isoformat(),
                "resources": resource_snapshot(Path.cwd()),
                "research_cutoff": config.research_cutoff.isoformat(),
                **config.holdout_status_payload(),
            },
        )
    return run_identity, run_root, started_at.astimezone(UTC)


def _required_stage_files(run_root: Path, stage: str) -> tuple[Path, ...]:
    mapping = {
        "registry": (run_root / "registry" / "symbol_registry.json",),
        "universe": (
            run_root / "universe" / "core_universe.json",
            run_root / "universe" / "expansion_policy.json",
            run_root / "universe" / "fold_memberships.json",
        ),
        "data": (run_root / "data" / "data_manifest.json",),
        "gold": (run_root / "gold" / "result.json",),
        "train": (run_root / "training_summary.json",),
        "report": (run_root / "phase7_report.json",),
    }
    return mapping[stage]


def _registry_stage(
    config: Phase7Config,
    run_root: Path,
    observed_at: datetime,
) -> tuple[SymbolRegistry, list[Path]]:
    print("[phase7:registry] discovering official current and historical symbols", flush=True)
    with BinancePublicDiscoveryClient() as client:
        exchange_info = client.fetch_exchange_info()
        historical = client.historical_evidence(intervals=config.required_intervals)
    registry = build_symbol_registry(
        exchange_info,
        historical,
        observed_at=observed_at,
        research_cutoff=config.research_cutoff,
    )
    root = run_root / "registry"
    registry_path = write_registry(root / "symbol_registry.json", registry)
    source_path = atomic_json(
        root / "source_verification.json",
        source_verification_manifest(verified_at=observed_at),
    )
    catalog_path = atomic_json(
        root / "catalog_summary.json",
        {
            "current_exchange_info_symbols": len(exchange_info.get("symbols", [])),
            "historical_archive_symbols": len(historical),
            "registry_symbols": len(registry.records),
            "registry_hash": registry.registry_hash,
        },
    )
    return registry, [registry_path, source_path, catalog_path]


def _universe_stage(
    config: Phase7Config,
    run_root: Path,
    registry: SymbolRegistry,
    run_identity: str,
    resume: bool,
    reporter: ProgressReporter | None = None,
) -> tuple[
    FrozenUniverse,
    ExpansionUniversePolicy,
    list[SymbolDescriptor],
    tuple[str, ...],
    list[Path],
]:
    completion_store = DiscoverySymbolCheckpointStore(
        config,
        registry,
        run_identity=run_identity,
    )
    discovery_result = acquire_discovery_daily(
        config,
        registry,
        progress=(
            lambda completed, total, symbol, interval, status, checkpoint_hit: (
                reporter.progress(
                    stage="discovery",
                    completed=completed,
                    total=total,
                    current=symbol,
                    interval=interval,
                    status=status,
                    checkpoint_hit=checkpoint_hit,
                )
                if reporter is not None
                else None
            )
        ),
        completion_store=completion_store,
        resume=resume,
    )
    discovery = discovery_result.manifests
    discovery_gaps = discovery_result.gaps
    discovery_exclusions = discovery_result.exclusions
    start = config.universe.core_selection_cutoff - timedelta(
        days=config.universe.selection_lookback_days
    )
    registry_map = registry.by_symbol()

    def window_manifests(window_start: datetime, window_end: datetime) -> dict[str, str]:
        return {
            symbol: manifest
            for symbol, manifest in discovery.items()
            if registry_map[symbol].causal_available_from < window_end
            and (
                registry_map[symbol].available_until is None
                or registry_map[symbol].available_until > window_start
            )
        }

    daily = load_candle_family(
        window_manifests(start, config.universe.core_selection_cutoff),
        interval="1d",
        start=start,
        end=config.universe.core_selection_cutoff,
    )
    core_descriptors = build_point_in_time_descriptors(
        daily,
        registry,
        as_of=config.universe.core_selection_cutoff,
        lookback_days=config.universe.selection_lookback_days,
        unusable_segments=discovery_gaps,
    )
    core_universe = select_core_universe(
        registry,
        core_descriptors,
        selection_cutoff=config.universe.core_selection_cutoff,
        config=config.universe,
    )
    expansion_policy = build_expansion_policy(core_universe, config.universe)
    plans = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    core_gap = next(
        (
            gap
            for gap in discovery_gaps
            if gap.symbol in core_universe.symbols
            and any(gap.intersects(plan.train_start, plan.test_end) for plan in plans)
        ),
        None,
    )
    if core_gap is not None:
        raise ValueError(
            "Required core symbol has an unrecoverable causal segment: "
            f"{core_gap.symbol} {core_gap.interval} {core_gap.partition}"
        )
    descriptor_by_key = {(item.symbol, item.as_of): item for item in core_descriptors}
    memberships = []
    for plan in plans:
        descriptor_start = plan.train_end - timedelta(days=config.universe.selection_lookback_days)
        fold_daily = load_candle_family(
            window_manifests(descriptor_start, plan.train_end),
            interval="1d",
            start=descriptor_start,
            end=plan.train_end,
        )
        fold_descriptors = build_point_in_time_descriptors(
            fold_daily,
            registry,
            as_of=plan.train_end,
            lookback_days=config.universe.selection_lookback_days,
            unusable_segments=discovery_gaps,
        )
        for descriptor in fold_descriptors:
            descriptor_by_key[(descriptor.symbol, descriptor.as_of)] = descriptor
        memberships.append(
            select_fold_active_universe(
                registry,
                list(descriptor_by_key.values()),
                fold_id=plan.fold_id,
                train_end=plan.train_end,
                core_universe=core_universe,
                expansion_policy=expansion_policy,
                config=config.universe,
                research_view="EXPANDING",
                unusable_segments=discovery_gaps,
                required_start=plan.train_start,
                required_end=plan.test_end,
            )
        )
    descriptors = sorted(descriptor_by_key.values(), key=lambda item: (item.as_of, item.symbol))
    acquisition_symbols = tuple(
        sorted({symbol for membership in memberships for symbol in membership.active_symbols})
    )
    if not set(core_universe.symbols).issubset(acquisition_symbols):
        raise ValueError("Causal acquisition plan unexpectedly omitted a core benchmark symbol")
    root = run_root / "universe"
    discovery_path = atomic_json(
        root / "discovery_data.json",
        {
            "daily_silver_manifests": discovery,
            **discovery_result.model_dump(),
        },
    )
    descriptor_path = atomic_json(
        root / "selection_descriptors.json",
        {
            "descriptor_rule": "source_time_strictly_before_fold_train_end",
            "descriptors": [item.model_dump(mode="json") for item in descriptors],
        },
    )
    core_path = write_universe(root / "core_universe.json", core_universe)
    policy_path = write_expansion_policy(root / "expansion_policy.json", expansion_policy)
    memberships_path = atomic_json(
        root / "fold_memberships.json",
        {
            "definition_version": UNIVERSE_VERSION,
            "core_universe_hash": core_universe.universe_hash,
            "expansion_policy_hash": expansion_policy.policy_hash,
            "fold_count": len(memberships),
            "acquisition_symbols": list(acquisition_symbols),
            "data_quality_exclusions": [
                outcome.model_dump(mode="json") for outcome in discovery_exclusions
            ],
            "folds": [item.model_dump(mode="json") for item in memberships],
            **config.holdout_status_payload(),
            "july_2026_used": False,
        },
    )
    files = [discovery_path, descriptor_path, core_path, policy_path, memberships_path]
    files.extend(Path(value) for value in discovery.values())
    files.extend(
        Path(outcome.exclusion_evidence)
        for outcome in discovery_exclusions
        if outcome.exclusion_evidence is not None
    )
    for gap in discovery_gaps:
        files.extend(
            Path(value)
            for value in (
                gap.quality_report,
                gap.quarantine,
                gap.rest_manifest,
                gap.comparison_report,
            )
        )
    return core_universe, expansion_policy, descriptors, acquisition_symbols, files


def _data_stage(
    config: Phase7Config,
    run_root: Path,
    registry: SymbolRegistry,
    universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy,
    acquisition_symbols: tuple[str, ...],
    reporter: ProgressReporter | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    candle_manifests: dict[str, dict[str, str]] = {}
    candle_outcomes: dict[str, dict[str, object]] = {}
    unusable_segments: list[dict[str, object]] = []
    for interval in config.required_intervals:
        acquisition = acquire_candle_family(
            config,
            registry,
            symbols=acquisition_symbols,
            interval=interval,
            start=config.data_start,
            end=config.research_cutoff,
            strict_symbols=frozenset(universe.symbols),
            progress=(
                lambda completed, total, symbol, current_interval, status, checkpoint_hit: (
                    reporter.progress(
                        stage=(
                            "required_5m_acquisition"
                            if current_interval == "5m"
                            else "higher_timeframe_acquisition"
                        ),
                        completed=completed,
                        total=total,
                        current=symbol,
                        interval=current_interval,
                        status=status,
                        checkpoint_hit=checkpoint_hit,
                    )
                    if reporter is not None
                    else None
                )
            ),
        )
        candle_manifests[interval] = acquisition.manifests
        candle_outcomes[interval] = acquisition.model_dump()
        unusable_segments.extend(gap.model_dump(mode="json") for gap in acquisition.gaps)
    derivatives = acquire_derivative_family(
        config,
        registry,
        symbols=acquisition_symbols,
        start=config.data_start,
        end=config.research_cutoff,
        progress=(
            lambda completed, total, symbol, current_interval, status, checkpoint_hit: (
                reporter.progress(
                    stage="derivative_acquisition",
                    completed=completed,
                    total=total,
                    current=symbol,
                    interval=current_interval,
                    status=status,
                    checkpoint_hit=checkpoint_hit,
                )
                if reporter is not None
                else None
            )
        ),
    )
    payload = {
        "universe_definition_version": UNIVERSE_VERSION,
        "core_universe_version": universe.version,
        "core_universe_hash": universe.universe_hash,
        "expansion_policy_version": expansion_policy.version,
        "expansion_policy_hash": expansion_policy.policy_hash,
        "research_universe_hash": research_universe_identity(
            universe, expansion_policy, acquisition_symbols
        ),
        "acquisition_symbols": list(acquisition_symbols),
        "acquisition_symbol_count": len(acquisition_symbols),
        "fold_active_symbol_cap": expansion_policy.total_max_symbols_per_fold,
        "registry_hash": registry.registry_hash,
        "range": {
            "start": config.data_start.isoformat(),
            "end_exclusive": config.research_cutoff.isoformat(),
        },
        "candle_silver_manifests": candle_manifests,
        "candle_coverage_contract": DATA_CANDLE_COVERAGE_CONTRACT_VERSION,
        "candle_validated_ranges": {
            interval: {
                symbol: _validated_range_payload(manifest)
                for symbol, manifest in sorted(family.items())
            }
            for interval, family in sorted(candle_manifests.items())
        },
        "candle_acquisition_outcomes": candle_outcomes,
        "unusable_segments": unusable_segments,
        "derivative_silver_manifests": derivatives,
        "api_key_required": False,
        **config.holdout_status_payload(),
    }
    manifest_path = atomic_json(run_root / "data" / "data_manifest.json", payload)
    files = [manifest_path]
    for family in candle_manifests.values():
        files.extend(Path(value) for value in family.values())
    for family in derivatives.values():
        files.extend(Path(value) for value in family.values())
    return payload, files


def _core_range(table: pa.Table, start: datetime, end: datetime, column: str) -> pa.Table:
    values = table.column(column).combine_chunks().cast(pa.int64()).to_numpy()
    start_us, end_us = int(start.timestamp() * 1_000_000), int(end.timestamp() * 1_000_000)
    return table.filter(pa.array((values >= start_us) & (values < end_us)))


def _gold_chunk(
    config: Phase7Config,
    registry: SymbolRegistry,
    data: dict[str, Any],
    start: datetime,
    end: datetime,
    reporter: ProgressReporter | None = None,
    chunk_position: int = 1,
    chunks_total: int = 1,
) -> tuple[str, MultiAssetFeatureResult, MultiAssetTargetResult]:
    if data.get("candle_coverage_contract") != DATA_CANDLE_COVERAGE_CONTRACT_VERSION:
        raise ValueError("Data manifest lacks the full causal candle-coverage contract")
    lookback = timedelta(
        minutes=5
        * max(
            config.features.correlation_window_rows,
            config.features.liquidity_window_rows,
            config.features.volatility_window_rows,
            config.features.seven_day_volatility_rows,
        )
    )
    feature_start = max(config.data_start, start - lookback)
    candle_end = min(config.research_cutoff, end + timedelta(minutes=125))
    candles_5m = load_candle_family(
        data["candle_silver_manifests"]["5m"],
        interval="5m",
        start=feature_start,
        end=candle_end,
        allow_lifecycle_absence=True,
    )
    if candles_5m is None:
        raise AssertionError("Required 5m candle family cannot be causally absent")
    candles_5m = align_derivatives(candles_5m, data["derivative_silver_manifests"])
    higher_start = max(config.data_start, start - timedelta(days=220))
    candles_12h = load_candle_family(
        data["candle_silver_manifests"]["12h"],
        interval="12h",
        start=higher_start,
        end=end,
        allow_lifecycle_absence=True,
    )
    candles_1d = load_candle_family(
        data["candle_silver_manifests"]["1d"],
        interval="1d",
        start=higher_start,
        end=end,
        allow_lifecycle_absence=True,
    )
    context = build_higher_timeframe_context(candles_12h, candles_1d)
    if reporter is not None:
        reporter.emit(
            "phase7_progress",
            stage="feature_construction",
            fields={
                "chunk": chunk_position,
                "chunks_total": chunks_total,
                "range_start": start.isoformat(),
                "range_end_exclusive": end.isoformat(),
                "input_rows": candles_5m.num_rows,
            },
        )
    features = generate_multiasset_features(
        candles_5m,
        registry=registry,
        config=config.features,
        higher_timeframe_context=context,
    )
    if reporter is not None:
        reporter.chunk_progress(
            stage="feature_construction",
            chunk=chunk_position,
            chunks_total=chunks_total,
            rows=features.table.num_rows,
            start=start,
            end=end,
        )
        reporter.emit(
            "phase7_progress",
            stage="target_construction",
            fields={
                "chunk": chunk_position,
                "chunks_total": chunks_total,
                "feature_rows": features.table.num_rows,
                "target_identity": TARGET_VERSION,
                "target_horizons_minutes": config.targets.horizons_minutes,
            },
        )
    targets = generate_multiasset_targets(
        candles_5m,
        features.table,
        config=config.targets,
        research_cutoff=config.research_cutoff,
    )
    if reporter is not None:
        reporter.chunk_progress(
            stage="target_construction",
            chunk=chunk_position,
            chunks_total=chunks_total,
            rows=targets.table.num_rows,
            start=start,
            end=end,
        )
    feature_table = _core_range(features.table, start, end, "feature_time")
    target_table = _core_range(targets.table, start, end, "feature_time")
    membership = {
        timestamp: symbols
        for timestamp, symbols in features.market_membership.items()
        if int(start.timestamp() * 1_000_000) <= timestamp < int(end.timestamp() * 1_000_000)
    }
    return (
        f"{start.year:04d}",
        MultiAssetFeatureResult(
            table=feature_table,
            feature_columns=features.feature_columns,
            feature_version=features.feature_version,
            market_context_version=features.market_context_version,
            market_membership=membership,
        ),
        MultiAssetTargetResult(
            table=target_table,
            target_version=targets.target_version,
            horizons_minutes=targets.horizons_minutes,
            reason_counts=targets.reason_counts,
        ),
    )


def _gold_stage(
    config: Phase7Config,
    run_root: Path,
    registry: SymbolRegistry,
    universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy,
    data: dict[str, Any],
    reporter: ProgressReporter | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    config.assert_cloud_execution_allowed()
    boundaries: list[tuple[datetime, datetime]] = []
    cursor = config.data_start
    while cursor < config.research_cutoff:
        end = min(add_calendar_months(cursor, 12), config.research_cutoff)
        boundaries.append((cursor, end))
        cursor = end
    first = _gold_chunk(
        config,
        registry,
        data,
        *boundaries[0],
        reporter=reporter,
        chunk_position=1,
        chunks_total=len(boundaries),
    )
    remaining = (
        _gold_chunk(
            config,
            registry,
            data,
            start,
            end,
            reporter=reporter,
            chunk_position=position,
            chunks_total=len(boundaries),
        )
        for position, (start, end) in enumerate(boundaries[1:], start=2)
    )
    data_manifest_path = (run_root / "data" / "data_manifest.json").resolve()
    lineage = {
        "data_manifest": str(data_manifest_path),
        "data_manifest_sha256": file_sha256(data_manifest_path),
        "configuration_hash": config.configuration_hash,
        "core_universe_hash": universe.universe_hash,
        "expansion_policy_hash": expansion_policy.policy_hash,
        "research_universe_hash": data["research_universe_hash"],
        "bounded_chunking": True,
    }
    result = build_multiasset_gold_chunks(
        itertools.chain((first,), remaining),
        feature_columns=first[1].feature_columns,
        output_root=config.paths.gold_root,
        universe_version=UNIVERSE_VERSION,
        universe_hash=data["research_universe_hash"],
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        research_cutoff=config.research_cutoff,
        prospective_holdout_start=config.prospective_holdout_start,
        lineage=lineage,
    )
    payload = {
        "dataset_id": result.dataset_id,
        "manifest": str(result.manifest_path),
        "row_count": result.row_count,
        "partition_count": len(result.partition_paths),
        "bounded_time_chunks": True,
    }
    result_path = atomic_json(run_root / "gold" / "result.json", payload)
    return payload, [result_path, result.manifest_path, *result.partition_paths]


def _fold_descriptors(
    config: Phase7Config,
    registry: SymbolRegistry,
    data: dict[str, Any],
) -> list[SymbolDescriptor]:
    plans = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    descriptors: list[SymbolDescriptor] = []
    unusable_segments = tuple(
        CausalDataGap.model_validate(item) for item in data.get("unusable_segments", [])
    )
    registry_map = registry.by_symbol()
    for plan in plans:
        start = plan.train_end - timedelta(days=config.universe.selection_lookback_days)
        manifests = {
            symbol: manifest
            for symbol, manifest in data["candle_silver_manifests"]["1d"].items()
            if registry_map[symbol].causal_available_from < plan.train_end
            and (
                registry_map[symbol].available_until is None
                or registry_map[symbol].available_until > start
            )
        }
        daily = load_candle_family(
            manifests,
            interval="1d",
            start=start,
            end=plan.train_end,
        )
        descriptors.extend(
            build_point_in_time_descriptors(
                daily,
                registry,
                as_of=plan.train_end,
                lookback_days=config.universe.selection_lookback_days,
                unusable_segments=unusable_segments,
            )
        )
    return descriptors


def _report_stage(config: Phase7Config, run_root: Path) -> tuple[dict[str, Any], list[Path]]:
    training = json.loads((run_root / "training_summary.json").read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for report in training["reports"]:
        if report.get("status") == "COMPLETE":
            grouped.setdefault((report["research_view"], report["spec"]["name"]), []).append(report)
    scorecard: list[dict[str, Any]] = []
    for (research_view, name), reports in sorted(grouped.items()):
        macro_ic = [
            item["test_metrics"]["macro"]["spearman_ic"]
            for item in reports
            if item["test_metrics"]["macro"]["spearman_ic"] is not None
        ]
        coverage = [item["test_metrics"]["coverage"]["coverage_ratio"] for item in reports]
        trade_count = [item["economic"]["trade_count"] for item in reports]
        scorecard.append(
            {
                "research_view": research_view,
                "experiment": name,
                "completed_folds": len(reports),
                "mean_macro_spearman_ic": float(np.mean(macro_ic)) if macro_ic else None,
                "mean_coverage_ratio": float(np.mean(coverage)),
                "total_trades": int(np.sum(trade_count)),
                "complexity_estimators": int(
                    np.mean([len(item["model"]["estimators"]) for item in reports])
                ),
            }
        )
    discovery = json.loads(
        (run_root / "universe" / "discovery_data.json").read_text(encoding="utf-8")
    )
    exclusions = discovery.get("data_quality_exclusions", [])
    payload = {
        "status": "PHASE7_CLOUD_RESEARCH_COMPLETE",
        "classification": "RETROSPECTIVE_RESEARCH_ONLY",
        "configuration_hash": config.configuration_hash,
        "scorecard": scorecard,
        "matched_architecture_comparisons": training["matched_architecture_comparisons"],
        "research_views": ["CORE", "EXPANDING"],
        "conclusion": (
            "Architecture evidence generated; no production or live-trading authorization implied."
        ),
        "qualified_model": "NONE",
        "data_quality_exclusion_count": len(exclusions),
        "data_quality_exclusions": exclusions,
        "model_qualification_performed": False,
        **config.holdout_status_payload(),
        "july_2026_used": False,
        "model_selected_for_live_trading": False,
    }
    report_path = atomic_json(run_root / "phase7_report.json", payload)
    return payload, [report_path]


def _load_stage_state(
    run_root: Path,
) -> tuple[SymbolRegistry, FrozenUniverse, ExpansionUniversePolicy, dict[str, Any]]:
    registry = read_registry(run_root / "registry" / "symbol_registry.json")
    universe = read_universe(run_root / "universe" / "core_universe.json")
    expansion_policy = read_expansion_policy(run_root / "universe" / "expansion_policy.json")
    data = json.loads((run_root / "data" / "data_manifest.json").read_text(encoding="utf-8"))
    return registry, universe, expansion_policy, data


def run_phase7_cloud(
    config: Phase7Config,
    *,
    stage: str | None,
    resume: bool,
) -> dict[str, Any]:
    """Run the non-interactive VM pipeline; the explicit environment guard is mandatory."""

    config.assert_cloud_execution_allowed()
    resources = resource_snapshot(Path.cwd())
    if resources["ram_gb"] is not None and resources["ram_gb"] < config.resources.memory_guard_gb:
        raise RuntimeError(
            f"Phase 7 requires at least {config.resources.memory_guard_gb} GB RAM; "
            f"detected {resources['ram_gb']:.2f} GB"
        )
    if resources["disk_free_gb"] < config.resources.memory_guard_gb:
        raise RuntimeError(
            f"Phase 7 disk safety reserve is {config.resources.memory_guard_gb} GB; "
            f"only {resources['disk_free_gb']:.2f} GB is free"
        )
    run_identity, run_root, observed_at = _run_context(config)
    reporter = ProgressReporter(
        config,
        run_identity=run_identity,
        run_started_at=observed_at,
        repository_root=Path.cwd(),
    )
    checkpoints = CheckpointStore(config.paths.checkpoint_root, run_identity)
    selected = (stage,) if stage else STAGES
    completed: list[str] = []
    for stage_position, current in enumerate(selected, start=1):
        if current not in STAGES:
            raise ValueError(f"Unknown Phase 7 stage: {current}")
        prior = STAGES[: STAGES.index(current)]
        missing = [name for name in prior if not checkpoints.is_complete(name)]
        if missing:
            raise RuntimeError(f"Stage {current} requires completed dependencies: {missing}")
        reporter.stage_started(current, stage_position, len(selected))
        if resume and checkpoints.is_complete(current):
            print(f"[phase7:{current}] checkpoint verified; reusing", flush=True)
            reporter.stage_completed(
                current,
                stage_position,
                len(selected),
                metadata={"checkpoint": "verified"},
                reused=True,
            )
            completed.append(current)
            continue
        if not resume and any(path.exists() for path in _required_stage_files(run_root, current)):
            raise FileExistsError(
                f"Stage {current} has artifacts without a reusable checkpoint; inspect before retry"
            )
        if current == "registry":
            _, files = _registry_stage(config, run_root, observed_at)
            metadata = {"network": "official_binance_public_only"}
        elif current == "universe":
            registry = read_registry(run_root / "registry" / "symbol_registry.json")
            universe, expansion_policy, _, acquisition_symbols, files = _universe_stage(
                config,
                run_root,
                registry,
                run_identity,
                resume,
                reporter,
            )
            metadata = {
                "core_universe_hash": universe.universe_hash,
                "expansion_policy_hash": expansion_policy.policy_hash,
                "acquisition_symbol_count": len(acquisition_symbols),
            }
        elif current == "data":
            registry = read_registry(run_root / "registry" / "symbol_registry.json")
            universe = read_universe(run_root / "universe" / "core_universe.json")
            expansion_policy = read_expansion_policy(
                run_root / "universe" / "expansion_policy.json"
            )
            membership_plan = json.loads(
                (run_root / "universe" / "fold_memberships.json").read_text(encoding="utf-8")
            )
            acquisition_symbols = tuple(membership_plan["acquisition_symbols"])
            data, files = _data_stage(
                config,
                run_root,
                registry,
                universe,
                expansion_policy,
                acquisition_symbols,
                reporter,
            )
            metadata = {
                "symbol_count": len(acquisition_symbols),
                "families": list(data),
                "research_universe_hash": data["research_universe_hash"],
            }
        elif current == "gold":
            registry, universe, expansion_policy, data = _load_stage_state(run_root)
            gold, files = _gold_stage(
                config,
                run_root,
                registry,
                universe,
                expansion_policy,
                data,
                reporter,
            )
            metadata = gold
        elif current == "train":
            registry, universe, expansion_policy, data = _load_stage_state(run_root)
            gold = json.loads((run_root / "gold" / "result.json").read_text(encoding="utf-8"))
            descriptors = _fold_descriptors(config, registry, data)
            descriptor_path = atomic_json(
                run_root / "fold_descriptors.json",
                {"descriptors": [item.model_dump(mode="json") for item in descriptors]},
            )
            summary = run_phase7_training(
                config,
                gold_manifest_path=Path(gold["manifest"]),
                registry=registry,
                universe=universe,
                expansion_policy=expansion_policy,
                descriptors=descriptors,
                unusable_segments=tuple(
                    CausalDataGap.model_validate(item) for item in data.get("unusable_segments", [])
                ),
                checkpoint_store=checkpoints,
                run_root=run_root,
                resume=resume,
                reporter=reporter,
            )
            files = [descriptor_path, run_root / "training_summary.json"]
            files.extend(run_root.glob("models/**/*.joblib"))
            files.extend(run_root.glob("models/**/report.json"))
            metadata = {
                "fold_count": summary["fold_count"],
                "completed_reports": summary["completed_reports"],
                "ineligible_reports": summary["ineligible_reports"],
            }
        else:
            report, files = _report_stage(config, run_root)
            metadata = {"scorecard_rows": len(report["scorecard"])}
        checkpoints.complete(current, list(files), metadata)
        reporter.stage_completed(
            current,
            stage_position,
            len(selected),
            metadata=metadata,
        )
        if current == "report":
            training = json.loads((run_root / "training_summary.json").read_text(encoding="utf-8"))
            reporter.final_summary(
                report,
                training,
                report_path=run_root / "phase7_report.json",
            )
        completed.append(current)
    return {
        "status": "COMPLETE",
        "run_identity": run_identity,
        "run_root": str(run_root),
        "stages_completed_or_reused": completed,
        "resume": resume,
        **config.holdout_status_payload(),
    }
