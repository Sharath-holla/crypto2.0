from __future__ import annotations

import hashlib
import json
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds

from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.calibration import fit_calibrator
from crypto_ai.phase5.folds import FoldPlan, plan_folds
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json
from crypto_ai.phase7.config import (
    FEATURE_VERSION,
    PHASE7_VERSION,
    TARGET_VERSION,
    UNIVERSE_VERSION,
    Phase7Config,
    stable_hash,
)
from crypto_ai.phase7.economics import (
    adaptive_policy_cost_stress,
    build_oos_trades,
    fixed_policy_cost_stress,
    select_cal_b_thresholds,
)
from crypto_ai.phase7.folds import (
    IneligibleFoldError,
    MultiAssetFoldData,
    slice_multiasset_fold,
)
from crypto_ai.phase7.metrics import (
    asset_concentration,
    evaluate_predictions,
    time_concentration,
)
from crypto_ai.phase7.models import fit_architecture, load_model, save_model
from crypto_ai.phase7.progress import ProgressReporter, oos_trade_summary
from crypto_ai.phase7.registry import SymbolRegistry
from crypto_ai.phase7.segments import CausalDataGap
from crypto_ai.phase7.universe import ExpansionUniversePolicy, FrozenUniverse, SymbolDescriptor

RESEARCH_VIEWS = ("CORE", "EXPANDING")


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    name: str
    architecture: str
    feature_group: str
    horizon_minutes: int
    target_type: str
    explicit_symbol_id: bool = False
    symbol_balanced: bool = False


def phase7_experiment_specs(config: Phase7Config) -> tuple[ExperimentSpec, ...]:
    specs: list[ExperimentSpec] = []
    for horizon in config.targets.horizons_minutes:
        for target_type in config.targets.target_types:
            for architecture in config.models.architectures:
                specs.append(
                    ExperimentSpec(
                        name=f"architecture-{architecture}-A6-{horizon}m-{target_type}",
                        architecture=architecture,
                        feature_group="A6",
                        horizon_minutes=horizon,
                        target_type=target_type,
                        symbol_balanced=architecture in {"G0", "C0", "H0"},
                    )
                )
            if config.models.include_symbol_id_ablation:
                specs.append(
                    ExperimentSpec(
                        name=f"architecture-G0-symbol-id-A6-{horizon}m-{target_type}",
                        architecture="G0",
                        feature_group="A6",
                        horizon_minutes=horizon,
                        target_type=target_type,
                        explicit_symbol_id=True,
                        symbol_balanced=True,
                    )
                )
            if config.models.compare_symbol_balanced_weights:
                specs.append(
                    ExperimentSpec(
                        name=f"architecture-G0-unbalanced-A6-{horizon}m-{target_type}",
                        architecture="G0",
                        feature_group="A6",
                        horizon_minutes=horizon,
                        target_type=target_type,
                    )
                )
    for group in ("A0", "A1", "A2", "A3", "A4", "A5"):
        specs.append(
            ExperimentSpec(
                name=f"feature-ablation-G0-{group}-60m-raw",
                architecture="G0",
                feature_group=group,
                horizon_minutes=60,
                target_type="raw",
                symbol_balanced=True,
            )
        )
    for group in ("BASE", "BASE_PLUS_12H", "BASE_PLUS_1D", "BASE_PLUS_12H_1D"):
        specs.append(
            ExperimentSpec(
                name=f"htf-control-G0-{group}-60m-raw",
                architecture="G0",
                feature_group=group,
                horizon_minutes=60,
                target_type="raw",
                symbol_balanced=True,
            )
        )
    return tuple(specs)


def _load_gold_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    manifest = read_manifest(path)
    if manifest is None or manifest.get("classification") != "RETROSPECTIVE_MULTI_ASSET_RESEARCH":
        raise ValueError("A completed Phase 7 Gold manifest is required")
    if (
        manifest.get("prospective_holdout_status") != "LOCKED_UNUSED"
        or manifest.get("prospective_holdout_used") is not False
        or manifest.get("prospective_holdout_evaluation_authorized") is not False
        or manifest.get("july_2026_used") is not False
    ):
        raise ValueError("Phase 7 Gold lineage touched a forbidden prospective period")
    for record in manifest.get("partition_files", []):
        target = Path(record["path"])
        if not target.is_absolute():
            target = path.parent / target
        if not target.exists() or file_sha256(target) != record["sha256"]:
            raise ValueError(f"Phase 7 Gold checksum mismatch: {target}")
        record["path"] = str(target.resolve())
    return manifest


def _load_fold_rows(
    manifest: dict[str, Any],
    plan: FoldPlan,
    horizon_minutes: int,
) -> pa.Table:
    paths = [record["path"] for record in manifest["partition_files"]]
    dataset = ds.dataset(paths, format="parquet")
    condition = (
        (ds.field("feature_time") >= pa.scalar(plan.train_start))
        & (ds.field("feature_time") < pa.scalar(plan.test_end))
        & (ds.field("horizon_minutes") == horizon_minutes)
    )
    return dataset.to_table(filter=condition).sort_by(
        [("feature_time", "ascending"), ("symbol", "ascending")]
    )


def _finite(table: pa.Table, columns: tuple[str, ...], target: str) -> pa.Table:
    mask = np.ones(table.num_rows, dtype=bool)
    for name in columns + (target,):
        values = np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)
        mask &= np.isfinite(values)
    return table.filter(pa.array(mask))


def _prediction_target(spec: ExperimentSpec) -> str:
    return "raw_future_return" if spec.target_type == "raw" else "normalized_future_return"


def _to_raw_predictions(
    table: pa.Table,
    predictions: np.ndarray,
    *,
    target_type: str,
) -> np.ndarray:
    values = np.asarray(predictions, dtype=np.float64)
    if target_type == "raw":
        return values
    scale = np.asarray(
        table.column("ex_ante_volatility_scale").combine_chunks().to_pylist(),
        dtype=np.float64,
    )
    return values * scale


def _subset_covered(
    table: pa.Table, predicted: np.ndarray, covered: np.ndarray
) -> tuple[pa.Table, np.ndarray]:
    mask = np.asarray(covered, dtype=bool) & np.isfinite(predicted)
    return table.filter(pa.array(mask)), np.asarray(predicted, dtype=np.float64)[mask]


def _covered_observation_keys(
    table: pa.Table,
    covered: np.ndarray,
) -> dict[str, dict[str, Any]]:
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    times = table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    mask = np.asarray(covered, dtype=bool)
    result: dict[str, dict[str, Any]] = {}
    for symbol in sorted(str(value) for value in np.unique(symbols[mask])):
        rows = np.flatnonzero(mask & (symbols == symbol))
        digest = hashlib.sha256()
        for timestamp in times[rows]:
            digest.update(f"{symbol}|{int(timestamp)}\n".encode())
        result[symbol] = {"row_count": len(rows), "identity": digest.hexdigest()[:24]}
    return result


def _threshold_granularity(architecture: str) -> str:
    return {"C0": "cluster", "P0": "per_coin"}.get(architecture, "global")


def _conditional_metrics(
    table: pa.Table,
    predicted: np.ndarray,
    covered: np.ndarray,
) -> dict[str, Any]:
    actual = np.asarray(
        table.column("raw_future_return").combine_chunks().to_pylist(), dtype=np.float64
    )
    btc = np.asarray(table.column("btc_return_4h").combine_chunks().to_pylist(), dtype=np.float64)
    relative = np.asarray(
        table.column("relative_strength_vs_btc").combine_chunks().to_pylist(),
        dtype=np.float64,
    )
    valid = np.asarray(covered, dtype=bool) & np.isfinite(actual) & np.isfinite(predicted)
    groups = {
        "btc_up": valid & (btc > 0),
        "btc_down": valid & (btc < 0),
        "relative_strength_positive": valid & (relative > 0),
        "relative_strength_negative": valid & (relative < 0),
    }
    result: dict[str, Any] = {}
    for name, mask in groups.items():
        if np.count_nonzero(mask) >= 2:
            sample = table.filter(pa.array(mask))
            result[name] = evaluate_predictions(
                sample,
                np.asarray(predicted)[mask],
                np.ones(sample.num_rows, dtype=bool),
                target_column="raw_future_return",
            )["micro"]
    return result


def _excursion_summary(
    table: pa.Table,
    liquidity_tiers: dict[str, str],
) -> dict[str, Any]:
    symbols = table.column("symbol").combine_chunks().to_pylist()
    mfe = np.asarray(table.column("mfe_long").combine_chunks().to_pylist(), dtype=np.float64)
    mae = np.asarray(table.column("mae_long").combine_chunks().to_pylist(), dtype=np.float64)
    result: dict[str, Any] = {}
    for tier in sorted(set(liquidity_tiers.values())):
        rows = np.asarray([liquidity_tiers.get(str(symbol)) == tier for symbol in symbols])
        if np.any(rows):
            result[tier] = {
                "row_count": int(np.count_nonzero(rows)),
                "mean_mfe_long": float(np.mean(mfe[rows])),
                "mean_mae_long": float(np.mean(mae[rows])),
            }
    return result


def summarize_fold_completion(
    calendar_fold_ids: tuple[str, ...],
    eligible_fold_ids_by_symbol: dict[str, set[str]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep calendar, eligibility, completion, and skip counts semantically distinct."""

    completed_by_architecture: dict[str, set[str]] = {}
    completed_by_target: dict[str, set[str]] = {}
    skipped_reasons: dict[str, int] = {}
    for report in reports:
        spec_payload = report["spec"]
        if report["status"] == "COMPLETE":
            completed_by_architecture.setdefault(spec_payload["architecture"], set()).add(
                report["fold_id"]
            )
            target_key = f"{spec_payload['horizon_minutes']}m:{spec_payload['target_type']}"
            completed_by_target.setdefault(target_key, set()).add(report["fold_id"])
        else:
            reason = str(report.get("reason", "unspecified"))
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
    completed_folds = {item["fold_id"] for item in reports if item["status"] == "COMPLETE"}
    return {
        "calendar_fold_count": len(calendar_fold_ids),
        "eligible_fold_count_by_symbol": {
            key: len(value) for key, value in sorted(eligible_fold_ids_by_symbol.items())
        },
        "eligible_fold_count_by_architecture": {
            key: len(value) for key, value in sorted(completed_by_architecture.items())
        },
        "eligible_fold_count_by_target": {
            key: len(value) for key, value in sorted(completed_by_target.items())
        },
        "completed_fold_count": len(completed_folds),
        "skipped_fold_count": len(set(calendar_fold_ids) - completed_folds),
        "skip_reasons": skipped_reasons,
    }


def matched_architecture_comparisons(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare A6 G0/C0/P0/H0 only on identical covered TEST observations."""

    grouped: dict[tuple[str, str, int, str], dict[str, dict[str, Any]]] = {}
    for report in reports:
        if report.get("status") != "COMPLETE":
            continue
        spec = report["spec"]
        expected_name = (
            f"architecture-{spec['architecture']}-A6-"
            f"{spec['horizon_minutes']}m-{spec['target_type']}"
        )
        if spec["feature_group"] != "A6" or spec["name"] != expected_name:
            continue
        key = (
            report["research_view"],
            report["fold_id"],
            int(spec["horizon_minutes"]),
            str(spec["target_type"]),
        )
        grouped.setdefault(key, {})[spec["architecture"]] = report

    fields = ("mae", "rmse", "r2", "directional_accuracy", "pearson_ic", "spearman_ic")
    comparisons: list[dict[str, Any]] = []
    for key, by_architecture in sorted(grouped.items()):
        if set(by_architecture) != {"G0", "C0", "P0", "H0"}:
            continue
        common_symbols = set.intersection(
            *(set(report["test_coverage_keys_by_symbol"]) for report in by_architecture.values())
        )
        matched_rows = 0
        for symbol in sorted(common_symbols):
            identities = {
                report["test_coverage_keys_by_symbol"][symbol]["identity"]
                for report in by_architecture.values()
            }
            counts = {
                report["test_coverage_keys_by_symbol"][symbol]["row_count"]
                for report in by_architecture.values()
            }
            if len(identities) != 1 or len(counts) != 1:
                raise ValueError("architecture comparison coverage is not observation-matched")
            matched_rows += counts.pop()
        architecture_metrics: dict[str, Any] = {}
        for architecture, report in sorted(by_architecture.items()):
            per_symbol = report["test_metrics"]["per_symbol"]
            architecture_metrics[architecture] = {
                "matched_macro": {
                    field: (
                        float(
                            np.mean(
                                [
                                    per_symbol[symbol][field]
                                    for symbol in sorted(common_symbols)
                                    if per_symbol[symbol][field] is not None
                                ]
                            )
                        )
                        if any(per_symbol[symbol][field] is not None for symbol in common_symbols)
                        else None
                    )
                    for field in fields
                },
                "native_coverage": report["test_metrics"]["coverage"],
            }
        research_view, fold_id, horizon, target_type = key
        comparisons.append(
            {
                "research_view": research_view,
                "fold_id": fold_id,
                "horizon_minutes": horizon,
                "target_type": target_type,
                "matched_observation_rule": (
                    "intersection of identical (symbol, feature_time) TEST coverage across "
                    "G0/C0/P0/H0"
                ),
                "matched_symbols": sorted(common_symbols),
                "matched_symbol_count": len(common_symbols),
                "matched_row_count": matched_rows,
                "architectures": architecture_metrics,
            }
        )
    return comparisons


def _run_one(
    spec: ExperimentSpec,
    fold: MultiAssetFoldData,
    feature_columns: tuple[str, ...],
    config: Phase7Config,
    output_root: Path,
    checkpoint_identity: dict[str, Any],
    *,
    reporter: ProgressReporter | None = None,
    fold_position: int = 1,
    folds_total: int = 1,
) -> tuple[dict[str, Any], list[Path]]:
    experiment_started = time.monotonic()
    for segment_name, segment in (
        ("TRAIN", fold.train),
        ("VALIDATION", fold.validation),
        ("CAL_A", fold.calibration_a),
        ("CAL_B", fold.calibration_b),
    ):
        if "cross_sectional_context_scope" not in segment.column_names:
            raise ValueError(f"{segment_name} is missing fold-bound cross-sectional context")
        scopes = set(segment.column("cross_sectional_context_scope").to_pylist())
        if scopes != {"FOLD_ACTIVE_SYMBOLS"}:
            raise ValueError(f"{segment_name} contains non-fold cross-sectional context: {scopes}")
    target = _prediction_target(spec)
    train = _finite(fold.train, feature_columns, target)
    validation = _finite(fold.validation, feature_columns, target)
    calibration_a = _finite(fold.calibration_a, feature_columns, target)
    calibration_b = _finite(fold.calibration_b, feature_columns, target)
    if reporter is not None:
        reporter.training_started(
            fold_position=fold_position,
            folds_total=folds_total,
            spec=asdict(spec),
            eligible_coins=len(fold.eligibility_manifest["eligible_symbols"]),
            train_rows=train.num_rows,
            validation_rows=validation.num_rows,
            feature_count=len(feature_columns),
            train_start=fold.plan.train_start,
            train_end=fold.plan.train_end,
            validation_start=fold.plan.validation_start,
            validation_end=fold.plan.validation_end,
        )
    fit_context = (
        reporter.model_fit(
            fold_position=fold_position,
            folds_total=folds_total,
            spec=asdict(spec),
            feature_count=len(feature_columns),
            train_rows=train.num_rows,
            validation_rows=validation.num_rows,
        )
        if reporter is not None
        else nullcontext()
    )
    with fit_context:
        model = fit_architecture(
            spec.architecture,  # type: ignore[arg-type]
            train,
            validation,
            feature_columns=feature_columns,
            target_column=target,
            config=config.models,
            model_threads=config.resources.model_threads,
            cluster_mapping=fold.cluster_mapping,
            explicit_symbol_id=spec.explicit_symbol_id,
            symbol_balanced=spec.symbol_balanced,
            hybrid_calibration=validation if spec.architecture == "H0" else None,
            eligibility_calibration_a=calibration_a,
        )
    cal_a_raw, cal_a_covered = model.predict(calibration_a)
    cal_a_table, cal_a_predictions = _subset_covered(calibration_a, cal_a_raw, cal_a_covered)
    calibrator, calibration_report = fit_calibrator(
        cal_a_predictions,
        np.asarray(cal_a_table.column(target).to_pylist(), dtype=np.float64),
        config.calibration,
    )
    cal_b_model, cal_b_covered = model.predict(calibration_b)
    cal_b_table, cal_b_predictions = _subset_covered(calibration_b, cal_b_model, cal_b_covered)
    cal_b_raw = _to_raw_predictions(
        cal_b_table,
        calibrator.apply(cal_b_predictions),
        target_type=spec.target_type,
    )
    thresholds, threshold_report = select_cal_b_thresholds(
        cal_b_table,
        cal_b_raw,
        target_column="raw_future_return",
        liquidity_tiers=fold.liquidity_tiers,
        cluster_mapping=fold.cluster_mapping,
        granularity=_threshold_granularity(spec.architecture),  # type: ignore[arg-type]
        config=config.costs,
    )
    frozen_identity = stable_hash(
        {
            "model": model.metadata["model_identity"],
            "calibrator": calibrator.identity_hash,
            "thresholds": thresholds,
        }
    )
    test = _finite(fold.release_test(frozen_identity=frozen_identity), feature_columns, target)
    test_model, test_covered = model.predict(test)
    calibrated = np.full(test.num_rows, np.nan)
    calibrated[test_covered] = calibrator.apply(test_model[test_covered])
    predicted_raw = _to_raw_predictions(test, calibrated, target_type=spec.target_type)
    metrics = evaluate_predictions(
        test,
        predicted_raw,
        test_covered,
        target_column="raw_future_return",
        cluster_mapping=fold.cluster_mapping,
        age_bucket_mapping=fold.age_buckets,
        eligibility_reasons=model.metadata.get("per_symbol_eligibility"),
    )
    coverage_keys = _covered_observation_keys(test, test_covered)
    trades = build_oos_trades(
        test,
        predicted_raw,
        thresholds,
        target_column="raw_future_return",
        liquidity_tiers=fold.liquidity_tiers,
        cluster_mapping=fold.cluster_mapping,
        horizon_minutes=spec.horizon_minutes,
        config=config.costs,
    )
    if trades.num_rows:
        contributions = np.asarray(trades.column("net_return").to_pylist(), dtype=np.float64)
        trade_symbols = np.asarray(trades.column("symbol").to_pylist(), dtype=object)
        trade_times = trades.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
        concentration = {
            "asset": asset_concentration(trade_symbols, contributions),
            "time": time_concentration(trade_times, contributions),
        }
    else:
        concentration = {"asset": None, "time": None}
    report = {
        "status": "COMPLETE",
        "spec": asdict(spec),
        "fold_id": fold.plan.fold_id,
        "research_view": fold.research_view,
        "fold_membership_hash": fold.eligibility_manifest["fold_membership_hash"],
        "core_eligible_symbols": fold.eligibility_manifest["core_eligible_symbols"],
        "expansion_eligible_symbols": fold.eligibility_manifest["expansion_eligible_symbols"],
        "same_row_feature_columns": list(feature_columns),
        "segment_rows": {
            "train": train.num_rows,
            "validation": validation.num_rows,
            "calibration_a": calibration_a.num_rows,
            "calibration_b": calibration_b.num_rows,
            "test": test.num_rows,
        },
        "model": model.metadata,
        "calibration": calibration_report,
        "threshold_selection": threshold_report,
        "thresholds": asdict(thresholds),
        "test_metrics": metrics,
        "test_coverage_keys_by_symbol": coverage_keys,
        "conditional_test_metrics": _conditional_metrics(test, predicted_raw, test_covered),
        "economic": {
            "cost_assumption_classification": config.costs.assumption_classification,
            "trade_count": trades.num_rows,
            "no_trade": trades.num_rows == 0,
            "fixed_policy_cost_stress": fixed_policy_cost_stress(trades, config.costs),
            "adaptive_policy_cost_stress": adaptive_policy_cost_stress(
                test,
                predicted_raw,
                thresholds,
                target_column="raw_future_return",
                liquidity_tiers=fold.liquidity_tiers,
                cluster_mapping=fold.cluster_mapping,
                horizon_minutes=spec.horizon_minutes,
                config=config.costs,
            ),
            "concentration": concentration,
            "excursions_by_liquidity_tier": _excursion_summary(test, fold.liquidity_tiers),
        },
        "frozen_identity_before_test": frozen_identity,
        "checkpoint_identity": checkpoint_identity,
        "test_used_for_selection": False,
        **config.holdout_status_payload(),
    }
    report_path = atomic_json(output_root / "report.json", report)
    model_path = output_root / "model.joblib"
    save_model(model, model_path)
    if reporter is not None:
        reporter.fold_evaluation(
            report,
            trade_summary=oos_trade_summary(trades),
            elapsed_seconds=time.monotonic() - experiment_started,
            fold_position=fold_position,
            folds_total=folds_total,
        )
    return report, [model_path, report_path]


def run_phase7_training(
    config: Phase7Config,
    *,
    gold_manifest_path: Path,
    registry: SymbolRegistry,
    universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy,
    descriptors: list[SymbolDescriptor],
    checkpoint_store: CheckpointStore,
    run_root: Path,
    resume: bool,
    unusable_segments: tuple[CausalDataGap, ...] = (),
    reporter: ProgressReporter | None = None,
) -> dict[str, Any]:
    config.assert_cloud_execution_allowed()
    manifest = _load_gold_manifest(gold_manifest_path)
    groups = {name: tuple(values) for name, values in manifest["feature_groups"].items()}
    folds = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    specs = phase7_experiment_specs(config)
    reports: list[dict[str, Any]] = []
    eligible_fold_ids_by_symbol: dict[str, set[str]] = {}
    gold_manifest_checksum = file_sha256(gold_manifest_path.resolve())
    for fold_position, plan in enumerate(folds, start=1):
        horizons = sorted({spec.horizon_minutes for spec in specs})
        fold_tables = {horizon: _load_fold_rows(manifest, plan, horizon) for horizon in horizons}
        for research_view in RESEARCH_VIEWS:
            try:
                sliced = {
                    horizon: slice_multiasset_fold(
                        table,
                        plan,
                        registry=registry,
                        universe=universe,
                        expansion_policy=expansion_policy,
                        research_view=research_view,  # type: ignore[arg-type]
                        descriptors=descriptors,
                        universe_config=config.universe,
                        schedule=config.schedule,
                        holdout_start=config.prospective_holdout_start,
                        cluster_count=config.models.cluster_count,
                        seed=config.models.seed,
                        unusable_segments=unusable_segments,
                    )
                    for horizon, table in fold_tables.items()
                }
            except IneligibleFoldError as exc:
                # A genuine point-in-time eligibility failure: record every
                # experiment for this fold/view as INELIGIBLE and move on.
                # Anything else is a defect and must propagate (fail closed).
                for spec in specs:
                    stage = f"models/{research_view.lower()}/{plan.fold_id}/{spec.name}"
                    output = run_root / stage
                    report_path = output / "report.json"
                    checkpoint_identity = {
                        "experiment_id": spec.name,
                        "configuration_hash": config.configuration_hash,
                        "universe_definition_version": UNIVERSE_VERSION,
                        "research_view": research_view,
                        "core_universe_version": universe.version,
                        "core_universe_hash": universe.universe_hash,
                        "expansion_policy_version": expansion_policy.version,
                        "expansion_policy_hash": expansion_policy.policy_hash,
                        "fold_membership_hash": "UNAVAILABLE_SLICING_FAILED",
                        "registry_version": registry.version,
                        "registry_hash": registry.registry_hash,
                        "feature_version": FEATURE_VERSION,
                        "target_version": TARGET_VERSION,
                        "target_horizon_minutes": spec.horizon_minutes,
                        "target_type": spec.target_type,
                        "architecture": spec.architecture,
                        "fold_id": plan.fold_id,
                        "gold_dataset_id": manifest["dataset_id"],
                        "gold_manifest_sha256": gold_manifest_checksum,
                        "code_version": PHASE7_VERSION,
                    }
                    report = {
                        "status": "INELIGIBLE",
                        "spec": asdict(spec),
                        "fold_id": plan.fold_id,
                        "research_view": research_view,
                        "fold_membership_hash": "UNAVAILABLE_SLICING_FAILED",
                        "reason": str(exc),
                        "test_used_for_selection": False,
                        "checkpoint_identity": checkpoint_identity,
                        **config.holdout_status_payload(),
                    }
                    files = [atomic_json(report_path, report)]
                    checkpoint_store.complete(stage, files, checkpoint_identity)
                    reports.append(report)
                continue
            reference_fold = sliced[horizons[0]]
            if reporter is not None:
                reporter.fold_started(
                    fold_position=fold_position,
                    folds_total=len(folds),
                    research_view=research_view,
                    eligible_coins=len(reference_fold.eligibility_manifest["eligible_symbols"]),
                    plan=plan,
                )
            for symbol in reference_fold.eligibility_manifest["eligible_symbols"]:
                key = f"{research_view}:{symbol}"
                eligible_fold_ids_by_symbol.setdefault(key, set()).add(plan.fold_id)
            for spec_position, spec in enumerate(specs, start=1):
                stage = f"models/{research_view.lower()}/{plan.fold_id}/{spec.name}"
                output = run_root / stage
                report_path = output / "report.json"
                fold_data = sliced[spec.horizon_minutes]
                checkpoint_identity = {
                    "experiment_id": spec.name,
                    "configuration_hash": config.configuration_hash,
                    "universe_definition_version": UNIVERSE_VERSION,
                    "research_view": research_view,
                    "core_universe_version": universe.version,
                    "core_universe_hash": universe.universe_hash,
                    "expansion_policy_version": expansion_policy.version,
                    "expansion_policy_hash": expansion_policy.policy_hash,
                    "fold_membership_hash": fold_data.eligibility_manifest["fold_membership_hash"],
                    "registry_version": registry.version,
                    "registry_hash": registry.registry_hash,
                    "feature_version": FEATURE_VERSION,
                    "target_version": TARGET_VERSION,
                    "target_horizon_minutes": spec.horizon_minutes,
                    "target_type": spec.target_type,
                    "architecture": spec.architecture,
                    "fold_id": plan.fold_id,
                    "gold_dataset_id": manifest["dataset_id"],
                    "gold_manifest_sha256": gold_manifest_checksum,
                    "code_version": PHASE7_VERSION,
                }
                if resume and checkpoint_store.is_complete(
                    stage, expected_metadata=checkpoint_identity
                ):
                    reports.append(json.loads(report_path.read_text(encoding="utf-8")))
                    continue
                if resume and report_path.exists():
                    orphan_report = json.loads(report_path.read_text(encoding="utf-8"))
                    orphan_files = [report_path]
                    model_path = output / "model.joblib"
                    if orphan_report.get("status") == "COMPLETE" and model_path.exists():
                        orphan_model = load_model(model_path)
                        if (
                            orphan_model.metadata.get("model_identity")
                            != orphan_report.get("model", {}).get("model_identity")
                            or orphan_report.get("checkpoint_identity") != checkpoint_identity
                        ):
                            raise ValueError(
                                "Orphan model/report identity mismatch for "
                                f"{research_view} {plan.fold_id} {spec.name}"
                            )
                        orphan_files.append(model_path)
                    if orphan_report.get("status") == "INELIGIBLE" or len(orphan_files) == 2:
                        if orphan_report.get("checkpoint_identity") != checkpoint_identity:
                            raise ValueError(
                                "Orphan report identity mismatch for "
                                f"{research_view} {plan.fold_id} {spec.name}"
                            )
                        checkpoint_store.complete(stage, orphan_files, checkpoint_identity)
                        reports.append(orphan_report)
                        continue
                print(
                    f"[phase7:train] view {research_view} fold {fold_position}/{len(folds)} "
                    f"experiment {spec_position}/{len(specs)} {spec.name}",
                    flush=True,
                )
                try:
                    report, files = _run_one(
                        spec,
                        fold_data,
                        groups[spec.feature_group],
                        config,
                        output,
                        checkpoint_identity,
                        reporter=reporter,
                        fold_position=fold_position,
                        folds_total=len(folds),
                    )
                except IneligibleFoldError as exc:
                    report = {
                        "status": "INELIGIBLE",
                        "spec": asdict(spec),
                        "fold_id": plan.fold_id,
                        "research_view": research_view,
                        "fold_membership_hash": fold_data.eligibility_manifest[
                            "fold_membership_hash"
                        ],
                        "reason": str(exc),
                        "test_used_for_selection": False,
                        "checkpoint_identity": checkpoint_identity,
                        **config.holdout_status_payload(),
                    }
                    files = [atomic_json(report_path, report)]
                checkpoint_store.complete(stage, files, checkpoint_identity)
                reports.append(report)
        if reporter is not None:
            reporter.fold_completed(fold_position, len(folds), plan.fold_id)
    fold_completion = summarize_fold_completion(
        tuple(plan.fold_id for plan in folds),
        eligible_fold_ids_by_symbol,
        reports,
    )
    summary = {
        "status": "COMPLETE",
        "fold_count": len(folds),
        **fold_completion,
        "experiment_spec_count": len(specs),
        "research_views": list(RESEARCH_VIEWS),
        "matched_architecture_comparisons": matched_architecture_comparisons(reports),
        "completed_reports": sum(item["status"] == "COMPLETE" for item in reports),
        "ineligible_reports": sum(item["status"] == "INELIGIBLE" for item in reports),
        "reports": reports,
        "test_used_for_model_design": False,
        **config.holdout_status_payload(),
    }
    atomic_json(run_root / "training_summary.json", summary)
    if reporter is not None:
        reporter.training_completed(summary)
    return summary
