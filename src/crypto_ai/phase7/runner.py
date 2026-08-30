from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.phase5.folds import calibration_split_time, plan_folds
from crypto_ai.phase7.artifacts import resource_snapshot
from crypto_ai.phase7.config import TARGET_VERSION, FeatureConfig, Phase7Config
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import (
    FIXTURE_SYMBOLS,
    fixture_universe_config,
    synthetic_candles,
    synthetic_descriptors,
    synthetic_registry,
)
from crypto_ai.phase7.metrics import evaluate_predictions
from crypto_ai.phase7.sources import source_verification_manifest
from crypto_ai.phase7.targets import generate_multiasset_targets
from crypto_ai.phase7.universe import build_expansion_policy, select_core_universe


def validate_phase7_configuration(config: Phase7Config) -> dict[str, Any]:
    missing_inputs = [
        str(path)
        for path in (config.binance_config, config.quality_config)
        if not path.resolve().is_file()
    ]
    phase7_root = config.paths.artifact_root.resolve()
    protected = {
        Path("local_artifacts/phase5").resolve(),
        Path("local_artifacts/phase5_hardening").resolve(),
        Path("local_artifacts/phase6").resolve(),
    }
    if phase7_root in protected:
        raise ValueError("Phase 7 artifact_root must not reuse a prior-phase artifact root")
    if missing_inputs:
        raise FileNotFoundError(f"Phase 7 input configs do not exist: {missing_inputs}")
    return {
        "status": "VALID",
        "configuration_hash": config.configuration_hash,
        "mode": config.mode,
        "data_start": config.data_start.isoformat(),
        "research_cutoff_exclusive": config.research_cutoff.isoformat(),
        **config.holdout_status_payload(),
        "july_2026_used": False,
        "api_key_required": False,
        "private_api_used": False,
        "heavy_local_execution_locked": True,
        "phase7_research_status": "NOT_RUN",
        "qualified_model": "NONE",
        "target_version": TARGET_VERSION,
        "target_decision_latency_bars": config.targets.decision_latency_bars,
        "artifact_root": str(phase7_root),
        "gold_root": str(config.paths.gold_root.resolve()),
    }


def phase7_plan(config: Phase7Config) -> dict[str, Any]:
    validation = validate_phase7_configuration(config)
    folds = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    years = config.research_cutoff.year - config.data_start.year + 1
    fold_payloads: list[dict[str, Any]] = []
    for fold in folds:
        split = calibration_split_time(fold)
        fold_payloads.append(
            fold.to_dict()
            | {
                "cal_a_start": fold.calibration_start.isoformat(),
                "cal_a_end": split.isoformat(),
                "cal_b_start": split.isoformat(),
                "cal_b_end": fold.calibration_end.isoformat(),
                "purge_rule": "previous_segment.label_end_time < next_segment.start",
                "embargo_minutes": config.schedule.embargo_minutes,
            }
        )
    return validation | {
        "operation": "PLAN_ONLY",
        "network_used": False,
        "candidate_symbol_pool": (
            "official USD-M historical/current registry; membership is recomputed causally "
            "at each fold TRAIN end"
        ),
        "research_views": ["CORE", "EXPANDING"],
        "core_universe_version": "core_universe_v1",
        "core_universe_target_size": config.universe.core_target_size,
        "core_universe_selection_cutoff": (config.universe.core_selection_cutoff.isoformat()),
        "expansion_universe_version": "expansion_universe_v2",
        "expansion_as_of": config.universe.expansion_as_of,
        "expansion_max_symbols_per_fold": config.universe.expansion_max_symbols_per_fold,
        "total_max_symbols_per_fold": config.universe.total_max_symbols_per_fold,
        "estimated_symbol_year_partitions": (
            config.universe.total_max_symbols_per_fold * len(config.required_intervals) * years
        ),
        "calendar_fold_count": len(folds),
        "estimated_walk_forward_folds": len(folds),
        "fold_count_source": "DERIVED_FROM_CONFIGURED_CALENDAR_BOUNDARIES",
        "folds": fold_payloads,
        "architectures": list(config.models.architectures),
        "target_horizons_minutes": list(config.targets.horizons_minutes),
        "target_decision_latency_bars": config.targets.decision_latency_bars,
        "target_types": list(config.targets.target_types),
        "feature_ablation_order": ["A0", "A1", "A2", "A3", "A4", "A5", "A6"],
        "stages": ["registry", "universe", "data", "gold", "train", "report"],
        "resource_controls": config.resources.model_dump(mode="json"),
        "resource_snapshot": resource_snapshot(Path.cwd()),
        "cloud_storage_root": config.paths.resolved_cloud_storage_root(),
        "secondary_tree_benchmarks": "deferred unless installed and explicitly configured",
    }


def _fixture_features() -> tuple[pa.Table, Any, Any]:
    registry = synthetic_registry()
    universe_config = fixture_universe_config()
    universe = select_core_universe(
        registry,
        synthetic_descriptors(as_of=universe_config.selection_cutoff),
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    candles = synthetic_candles()
    feature_config = FeatureConfig(
        correlation_window_rows=24,
        liquidity_window_rows=24,
        volatility_window_rows=24,
        daily_volatility_rows=24,
        seven_day_volatility_rows=48,
        include_12h=False,
        include_1d=False,
        include_derivatives=False,
    )
    features = generate_multiasset_features(
        candles,
        registry=registry,
        config=feature_config,
    )
    return candles, features, universe


def test_phase7_universe(config: Phase7Config) -> dict[str, Any]:
    del config
    registry = synthetic_registry()
    universe_config = fixture_universe_config()
    descriptors = synthetic_descriptors(as_of=universe_config.selection_cutoff)
    baseline = select_core_universe(
        registry,
        descriptors,
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    future = descriptors + [
        item.model_copy(
            update={
                "as_of": datetime(2026, 6, 1, tzinfo=UTC),
                "trailing_quote_volume": item.trailing_quote_volume * 10_000,
            }
        )
        for item in descriptors
    ]
    perturbed = select_core_universe(
        registry,
        future,
        selection_cutoff=universe_config.selection_cutoff,
        config=universe_config,
    )
    invariant = baseline.universe_hash == perturbed.universe_hash
    if not invariant:
        raise AssertionError("future descriptors changed the frozen core universe")
    expansion_policy = build_expansion_policy(baseline, universe_config)
    return {
        "status": "PASS",
        "fixture_symbols": list(FIXTURE_SYMBOLS),
        "selected_symbols": list(baseline.symbols),
        "core_selection_cutoff": baseline.selection_cutoff.isoformat(),
        "core_universe_version": baseline.version,
        "expansion_universe_version": expansion_policy.version,
        "expansion_as_of": expansion_policy.as_of_rule,
        "total_max_symbols_per_fold": expansion_policy.total_max_symbols_per_fold,
        "future_descriptor_perturbation_invariant": invariant,
        "prospective_holdout_status": baseline.prospective_holdout_status,
        "prospective_holdout_used": baseline.prospective_holdout_used,
        "prospective_holdout_evaluation_authorized": (
            baseline.prospective_holdout_evaluation_authorized
        ),
        "universe_hash": baseline.universe_hash,
    }


def phase7_dry_run(config: Phase7Config) -> dict[str, Any]:
    validation = validate_phase7_configuration(config)
    candles, features, universe = _fixture_features()
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=config.targets,
        research_cutoff=config.research_cutoff,
    )
    target_times = targets.table.column("horizon_minutes").combine_chunks().to_numpy()
    sample = targets.table.filter(pa.array(target_times == 60))
    predicted = np.zeros(sample.num_rows, dtype=np.float64)
    metrics = evaluate_predictions(
        sample,
        predicted,
        np.ones(sample.num_rows, dtype=bool),
        target_column="raw_future_return",
    )
    return validation | {
        "operation": "LOCAL_DRY_RUN",
        "status": "PASS",
        "network_used": False,
        "files_written": 0,
        "heavy_training_executed": False,
        "symbols": list(universe.symbols),
        "universe_hash": universe.universe_hash,
        "candle_rows": candles.num_rows,
        "feature_rows": features.table.num_rows,
        "feature_count": len(features.feature_columns),
        "target_rows": targets.table.num_rows,
        "target_horizons_minutes": list(targets.horizons_minutes),
        "target_version": targets.target_version,
        "target_decision_latency_bars": config.targets.decision_latency_bars,
        "zero_baseline_metrics_60m": {
            "micro": metrics["micro"],
            "macro": metrics["macro"],
            "coverage": metrics["coverage"],
        },
        "source_contract": source_verification_manifest(),
    }
