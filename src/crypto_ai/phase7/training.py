from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.calibration import fit_calibrator
from crypto_ai.phase5.folds import FoldPlan, plan_folds
from crypto_ai.phase7.artifacts import (
    CheckpointStore,
    atomic_json,
    checkpoint_metadata_compatible,
)
from crypto_ai.phase7.backend import backend_metadata, resolve_lightgbm_backend
from crypto_ai.phase7.config import (
    FEATURE_VERSION,
    PHASE7_VERSION,
    TARGET_VERSION,
    UNIVERSE_VERSION,
    Phase7Config,
    stable_hash,
)
from crypto_ai.phase7.economics import (
    ThresholdSet,
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
from crypto_ai.phase7.models import (
    fit_architecture,
    load_model,
    prepare_architecture_inputs,
    save_model,
)
from crypto_ai.phase7.prepared_cache import (
    PREPROCESSING_VERSION,
    CachedPreparedData,
    PreparedCacheMissError,
    PreparedDataCache,
    PreparedTrainingSegments,
    prepared_cache_id,
)
from crypto_ai.phase7.progress import ProgressReporter, oos_trade_summary
from crypto_ai.phase7.registry import SymbolRegistry
from crypto_ai.phase7.resources import resource_admission
from crypto_ai.phase7.run_lease import owned_run
from crypto_ai.phase7.runtime import (
    ComputeBudget,
    RuntimePaths,
    cache_mode_from_environment,
    emit_event,
    git_commit,
    memory_snapshot,
)
from crypto_ai.phase7.segments import CausalDataGap
from crypto_ai.phase7.telemetry import instrument, telemetry
from crypto_ai.phase7.universe import (
    ExpansionUniversePolicy,
    FrozenUniverse,
    SymbolDescriptor,
    latest_descriptors,
    select_fold_active_universe,
)

RESEARCH_VIEWS = ("CORE", "EXPANDING")
SCIENTIFIC_SOURCE_IDENTITY_ALGORITHM = "phase7_scientific_source_manifest_v2"
TRAINING_SOURCE_IDENTITY_ALGORITHM = SCIENTIFIC_SOURCE_IDENTITY_ALGORITHM
TRAINING_CRITICAL_SOURCE_FILES = (
    "configs/data/binance.toml",
    "configs/data_quality/default.toml",
    "configs/phase7/research_core20_primary_v1.toml",
    "configs/phase7/research_v1.toml",
    "src/crypto_ai/data/ingestion/manifest.py",
    "src/crypto_ai/data/schema.py",
    "src/crypto_ai/data/storage/__init__.py",
    "src/crypto_ai/data/storage/parquet.py",
    "src/crypto_ai/domain/__init__.py",
    "src/crypto_ai/domain/candle.py",
    "src/crypto_ai/features/baseline.py",
    "src/crypto_ai/phase4/asof.py",
    "src/crypto_ai/phase4/features.py",
    "src/crypto_ai/phase4_1/features.py",
    "src/crypto_ai/phase5/calibration.py",
    "src/crypto_ai/phase5/config.py",
    "src/crypto_ai/phase5/folds.py",
    "src/crypto_ai/phase6/config.py",
    "src/crypto_ai/phase6/features.py",
    "src/crypto_ai/phase6/labels.py",
    "src/crypto_ai/phase7/artifacts.py",
    "src/crypto_ai/phase7/acquisition.py",
    "src/crypto_ai/phase7/backend.py",
    "src/crypto_ai/phase7/config.py",
    "src/crypto_ai/phase7/economics.py",
    "src/crypto_ai/phase7/features.py",
    "src/crypto_ai/phase7/folds.py",
    "src/crypto_ai/phase7/gold.py",
    "src/crypto_ai/phase7/gold_validation.py",
    "src/crypto_ai/phase7/metrics.py",
    "src/crypto_ai/phase7/models.py",
    "src/crypto_ai/phase7/pipeline.py",
    "src/crypto_ai/phase7/prepared_cache.py",
    "src/crypto_ai/phase7/quality.py",
    "src/crypto_ai/phase7/registry.py",
    "src/crypto_ai/phase7/segments.py",
    "src/crypto_ai/phase7/targets.py",
    "src/crypto_ai/phase7/training.py",
    "src/crypto_ai/phase7/universe.py",
    "src/crypto_ai/research/config.py",
    "src/crypto_ai/research/metrics.py",
    "scripts/run_phase7a_pipeline.py",
    "src/crypto_ai/phase7/phase7a.py",
    "src/crypto_ai/phase7/benchmark_one_spec.py",
    "src/crypto_ai/phase7/recovery.py",
    "src/crypto_ai/phase7/device_evidence.py",
)
EXECUTION_CONTEXT_SOURCE_FILES = (
    "src/crypto_ai/phase7/preflight.py",
    "src/crypto_ai/phase7/progress.py",
    "src/crypto_ai/phase7/runtime.py",
    "src/crypto_ai/phase7/lightning.py",
    "src/crypto_ai/phase7/run_lease.py",
    "src/crypto_ai/phase7/resources.py",
    "src/crypto_ai/phase7/telemetry.py",
    "src/crypto_ai/phase7/verify_linux.py",
    "src/crypto_ai/phase7/equivalence.py",
    "scripts/benchmark_phase7_backend.py",
    "scripts/benchmark_phase7_preparation.py",
    "scripts/manage_phase7_cache.py",
    "scripts/phase7_preflight.py",
    "scripts/run_phase7a_lightning.py",
    "scripts/validate_phase7_gold.py",
)


def _content_source_identity(
    algorithm: str,
    source_files: tuple[str, ...],
    repository_root: Path | None = None,
) -> dict[str, Any]:
    root = repository_root.resolve() if repository_root is not None else Path(__file__).parents[3]
    records: list[dict[str, str]] = []
    for relative_path in sorted(set(source_files)):
        normalized = Path(relative_path).as_posix()
        path = root / normalized
        if not path.is_file():
            raise RuntimeError(f"identity-critical source file is missing: {normalized}")
        # Git may check text out as CRLF on Windows and LF on Linux. Preserve
        # content identity across those equivalent checkouts; historical byte
        # freezes continue to use the exact committed bytes independently.
        content = path.read_bytes().replace(b"\r\n", b"\n")
        records.append({"path": normalized, "sha256": hashlib.sha256(content).hexdigest()})
    identity = {"algorithm": algorithm, "files": records}
    return {**identity, "manifest_sha256": stable_hash(identity, length=64)}


def scientific_source_identity(repository_root: Path | None = None) -> dict[str, Any]:
    """Return the authoritative content identity for scientific resume compatibility.

    The file list is deliberately independent of Git state and excludes logs,
    documentation, runtime paths, and machine metadata. Missing files fail closed.
    """

    return _content_source_identity(
        SCIENTIFIC_SOURCE_IDENTITY_ALGORITHM,
        TRAINING_CRITICAL_SOURCE_FILES,
        repository_root,
    )


def training_source_identity(repository_root: Path | None = None) -> dict[str, Any]:
    """Backward-compatible name for :func:`scientific_source_identity`."""

    return scientific_source_identity(repository_root)


def execution_source_identity(repository_root: Path | None = None) -> dict[str, Any]:
    """Identify operational code for audit, without making it a resume key."""

    return _content_source_identity(
        "phase7_execution_context_source_manifest_v1",
        EXECUTION_CONTEXT_SOURCE_FILES,
        repository_root,
    )


def training_stage_resume_identity(
    *, config: Phase7Config | None = None, gold_manifest_path: Path | None = None
) -> dict[str, Any]:
    """Bind stage-level reuse to the same scientific code/backend as model reuse."""

    identity = {
        "schema": "phase7_training_stage_resume_v2",
        "scientific_source_identity": training_source_identity(),
        "model_backend_semantics": resolve_lightgbm_backend().name,
    }
    if config is not None:
        identity["configuration_hash"] = config.configuration_hash
    if gold_manifest_path is not None:
        manifest = _load_gold_manifest(gold_manifest_path)
        identity["gold_dataset_id"] = manifest["dataset_id"]
        identity["gold_manifest_sha256"] = file_sha256(gold_manifest_path)
    return identity


def validate_training_stage_resume(
    metadata: dict[str, Any],
    *,
    config: Phase7Config | None = None,
    gold_manifest_path: Path | None = None,
) -> None:
    if metadata.get("scientific_resume_identity") != training_stage_resume_identity(
        config=config, gold_manifest_path=gold_manifest_path
    ):
        raise ValueError(
            "completed training-stage checkpoint has missing or incompatible scientific identity; "
            "per-model checkpoint review is required"
        )


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


def experiment_output_root(run_root: Path, *, kind: str, config: Phase7Config) -> Path:
    """Keep the legacy layout unless an explicit execution root is supplied."""

    if run_root.name.startswith("benchmark-only-"):
        return run_root / kind / "models"
    variable = "PHASE7_MODEL_ROOT" if kind == "model" else "PHASE7_REPORT_ROOT"
    if not os.environ.get(variable, "").strip():
        return run_root / "models"
    paths = RuntimePaths.resolve(config.paths)
    base = paths.model_root if kind == "model" else paths.report_root
    return base / run_root.name / "models"


@instrument("FOLD_LOAD", admit=True)
def _load_fold_rows(
    manifest: dict[str, Any],
    plan: FoldPlan,
    horizon_minutes: int,
    *,
    dataset: ds.Dataset | None = None,
) -> pa.Table:
    if dataset is None:
        paths = [record["path"] for record in manifest["partition_files"]]
        dataset = ds.dataset(paths, format="parquet", partitioning="hive")
    condition = (
        (ds.field("feature_time") >= pa.scalar(plan.train_start))
        & (ds.field("feature_time") < pa.scalar(plan.test_end))
        & (ds.field("horizon_minutes") == horizon_minutes)
    )
    # Gold is physically partitioned as symbol=<symbol>/year=<year>. Apply the
    # partition predicate as well as the exact timestamp predicate so PyArrow
    # can prune irrelevant files without changing logical row selection.
    # ``test_end`` is exclusive, hence a fold ending at midnight on January 1
    # does not require the new year's partition.
    if "year" in dataset.schema.names:
        end_year = (plan.test_end - timedelta(microseconds=1)).year
        condition = (
            (ds.field("year") >= plan.train_start.year) & (ds.field("year") <= end_year) & condition
        )
    return dataset.to_table(filter=condition).sort_by(
        [("feature_time", "ascending"), ("symbol", "ascending")]
    )


def _finite(table: pa.Table, columns: tuple[str, ...], target: str) -> pa.Table:
    names = columns + (target,)
    mask: pa.Array | pa.ChunkedArray = pc.is_finite(table.column(names[0]))
    for name in names[1:]:
        mask = pc.and_(mask, pc.is_finite(table.column(name)))
    valid = pc.fill_null(mask, False)
    return table if pc.all(valid).as_py() is True else table.filter(valid)


@instrument("PREPARE", admit=True)
def _prepare_training_segments(
    fold: MultiAssetFoldData,
    feature_columns: tuple[str, ...],
    target: str,
) -> PreparedTrainingSegments:
    for segment_name, segment in (
        ("TRAIN", fold.train),
        ("VALIDATION", fold.validation),
        ("CAL_A", fold.calibration_a),
        ("CAL_B", fold.calibration_b),
    ):
        if "cross_sectional_context_scope" not in segment.column_names:
            raise ValueError(f"{segment_name} is missing fold-bound cross-sectional context")
        scopes = set(pc.unique(segment.column("cross_sectional_context_scope")).to_pylist())
        if scopes != {"FOLD_ACTIVE_SYMBOLS"}:
            raise ValueError(f"{segment_name} contains non-fold cross-sectional context: {scopes}")
    train = _finite(fold.train, feature_columns, target)
    validation = _finite(fold.validation, feature_columns, target)
    calibration_a = _finite(fold.calibration_a, feature_columns, target)
    calibration_b = _finite(fold.calibration_b, feature_columns, target)
    return PreparedTrainingSegments(
        fold_id=fold.plan.fold_id,
        research_view=fold.research_view,
        feature_columns=feature_columns,
        target_column=target,
        train=train,
        validation=validation,
        calibration_a=calibration_a,
        calibration_b=calibration_b,
        model_inputs=prepare_architecture_inputs(
            train,
            validation,
            feature_columns=feature_columns,
            target_column=target,
            eligibility_calibration_a=calibration_a,
        ),
    )


def _prediction_target(spec: ExperimentSpec) -> str:
    return "raw_future_return" if spec.target_type == "raw" else "normalized_future_return"


def _reusable_model_key(
    fold_id: str,
    research_view: str,
    spec: ExperimentSpec,
    target: str,
    feature_columns: tuple[str, ...],
) -> tuple[Any, ...]:
    return (fold_id, research_view, spec.horizon_minutes, target, feature_columns)


def _is_reusable_g0(spec: ExperimentSpec) -> bool:
    return (
        spec.architecture == "G0"
        and not spec.explicit_symbol_id
        and spec.symbol_balanced
        and spec.feature_group == "A6"
    )


def causal_descriptor_identity(descriptors: list[SymbolDescriptor], train_end: Any) -> str:
    """Bind every field of exactly the descriptor records known at TRAIN end."""
    selected = latest_descriptors(descriptors, as_of=train_end)
    return stable_hash(
        {
            "train_end": train_end.isoformat(),
            "descriptors": {
                name: selected[name].model_dump(mode="json") for name in sorted(selected)
            },
        },
        length=64,
    )


def _prepared_cache_identity(
    *,
    config: Phase7Config,
    manifest: dict[str, Any],
    gold_manifest_sha256: str,
    source_identity: dict[str, Any],
    fold_id: str,
    research_view: str,
    fold_membership_hash: str,
    universe_hash: str,
    registry_hash: str,
    spec: ExperimentSpec,
    feature_columns: tuple[str, ...],
    descriptor_identity: str,
) -> dict[str, Any]:
    target = _prediction_target(spec)
    partition_identity = [
        {
            "sha256": item.get("sha256"),
            "row_count": item.get("row_count"),
        }
        for item in manifest.get("partition_files", [])
    ]
    lineage = manifest.get("lineage") if isinstance(manifest.get("lineage"), dict) else {}
    return {
        "gold_dataset_id": manifest["dataset_id"],
        "gold_manifest_sha256": gold_manifest_sha256,
        "gold_partition_manifest_sha256": stable_hash(partition_identity, length=64),
        "configuration_hash": config.configuration_hash,
        "gold_source_fingerprint": lineage.get("source_fingerprint"),
        "scientific_source_identity": source_identity["manifest_sha256"],
        "fold_id": fold_id,
        "research_view": research_view,
        "horizon_minutes": spec.horizon_minutes,
        "target_type": spec.target_type,
        "target_column": target,
        "feature_group": spec.feature_group,
        "feature_columns": list(feature_columns),
        "fold_membership_hash": fold_membership_hash,
        "universe_hash": universe_hash,
        "registry_hash": registry_hash,
        "causal_descriptor_identity": descriptor_identity,
        "purge": "actual_label_end_time_strictly_before_next_segment",
        "embargo_minutes": config.schedule.embargo_minutes,
        "preprocessing_version": PREPROCESSING_VERSION,
        "feature_version": FEATURE_VERSION,
        "target_version": TARGET_VERSION,
        "matrix_dtype": "float64",
        "matrix_code_identity": source_identity["manifest_sha256"],
        "symbol_encoding_contract": "deferred_sorted_train_symbols_one_hot_v1",
    }


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


def _frozen_test_identity_components(
    *, model_identity: str, calibrator_identity: str, thresholds: dict[str, Any]
) -> dict[str, Any]:
    return {
        "model": model_identity,
        "calibrator": calibrator_identity,
        "thresholds": thresholds,
    }


def _validate_complete_orphan_report(report: dict[str, Any], model: Any) -> None:
    """Fail closed unless a COMPLETE orphan is internally self-consistent."""

    try:
        model_identity = str(model.metadata["model_identity"])
        reported_model_identity = str(report["model"]["model_identity"])
        calibration = report["calibration"]["selected"]
        threshold_payload = report["thresholds"]
        calibrator_identity = report["calibrator_identity"]
        threshold_identity = report["threshold_identity"]
        frozen_identity = report["frozen_identity_before_test"]
        frozen_components = report["frozen_identity_components"]
    except (KeyError, TypeError) as exc:
        raise ValueError("COMPLETE orphan is missing frozen training artifacts") from exc
    if not isinstance(calibration, dict) or not isinstance(threshold_payload, dict):
        raise ValueError("COMPLETE orphan has malformed calibrator or threshold artifacts")
    try:
        canonical_thresholds = asdict(ThresholdSet(**threshold_payload))
    except (TypeError, ValueError) as exc:
        raise ValueError("COMPLETE orphan has malformed threshold artifacts") from exc
    expected_calibrator_identity = stable_hash(calibration)
    expected_threshold_identity = stable_hash(canonical_thresholds)
    expected_components = _frozen_test_identity_components(
        model_identity=model_identity,
        calibrator_identity=expected_calibrator_identity,
        thresholds=canonical_thresholds,
    )
    if (
        reported_model_identity != model_identity
        or calibrator_identity != expected_calibrator_identity
        or threshold_identity != expected_threshold_identity
        or frozen_components != expected_components
        or frozen_identity != stable_hash(expected_components)
    ):
        raise ValueError("COMPLETE orphan frozen training identity mismatch")


def _validate_model_file_binding(report: dict[str, Any], model_path: Path) -> None:
    """Verify independent report/model content binding before loading pickle."""
    digest = report.get("model_artifact_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or file_sha256(model_path) != digest:
        raise ValueError("model/report checksum binding is missing or mismatched")
    identity = dict(report)
    claimed = identity.pop("report_identity", None)
    if claimed != stable_hash(identity, length=64):
        raise ValueError("model report content identity mismatch")
    if "model_receipt_sha256" in report:
        from crypto_ai.phase7.recovery import validate_model_receipt

        validate_model_receipt(model_path, report)


def _restore_completed_g0(
    *,
    report_path: Path,
    model_path: Path,
    expected_checkpoint_identity: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    """Load a checkpoint-validated G0 so a resumed H0 never refits it."""

    if not report_path.is_file() or not model_path.is_file():
        raise FileNotFoundError("completed G0 checkpoint is missing its report or model artifact")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    reported_identity = report.get("checkpoint_identity")
    if not isinstance(reported_identity, dict) or not checkpoint_metadata_compatible(
        reported_identity, expected_checkpoint_identity
    ):
        raise ValueError("completed G0 checkpoint identity mismatch")
    _validate_model_file_binding(report, model_path)
    model = load_model(model_path)
    if model.metadata.get("scientific_input_identity") != reported_identity:
        raise ValueError("completed estimator scientific input identity mismatch")
    if model.metadata.get("publication") != report.get("publication"):
        raise ValueError("completed estimator publication identity mismatch")
    _validate_complete_orphan_report(report, model)
    if model.architecture != "G0":
        raise ValueError("completed reusable model is not G0")
    return report, model


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
    prepared_segments: PreparedTrainingSegments | None = None,
    reusable_models: dict[tuple[Any, ...], Any] | None = None,
    compute_budget: ComputeBudget | None = None,
    cache_id: str | None = None,
    execution_metadata: dict[str, Any] | None = None,
    model_path: Path | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    resource_admission("MODEL_FIT_START", additional_roots=(output_root, model_path or output_root))
    experiment_started = time.monotonic()
    target = _prediction_target(spec)
    prepared = prepared_segments or _prepare_training_segments(fold, feature_columns, target)
    if (
        prepared.fold_id != fold.plan.fold_id
        or prepared.research_view != fold.research_view
        or prepared.feature_columns != feature_columns
        or prepared.target_column != target
    ):
        raise ValueError("Prepared Phase 7 training segments do not match the experiment")
    train = prepared.train
    validation = prepared.validation
    calibration_a = prepared.calibration_a
    calibration_b = prepared.calibration_b
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
    reuse_key = _reusable_model_key(
        fold.plan.fold_id, fold.research_view, spec, target, feature_columns
    )
    reusable_global = (
        reusable_models.get(reuse_key)
        if reusable_models is not None and spec.architecture == "H0"
        else None
    )
    budget = compute_budget or ComputeBudget.resolve(config.resources)
    emit_event(
        "MODEL_START",
        fold_id=fold.plan.fold_id,
        spec=spec.name,
        **memory_snapshot(),
    )
    model_started = time.monotonic()
    telemetry(
        "MODEL_FIT_START",
        "START",
        started=model_started,
        matrix_shape=list(prepared.model_inputs.train_x.shape),
        matrix_bytes=prepared.model_inputs.train_x.nbytes
        + prepared.model_inputs.validation_x.nbytes,
        model_threads=budget.lightgbm_threads_per_model,
    )
    with fit_context:
        model = fit_architecture(
            spec.architecture,  # type: ignore[arg-type]
            train,
            validation,
            feature_columns=feature_columns,
            target_column=target,
            config=config.models,
            model_threads=budget.lightgbm_threads_per_model,
            estimator_workers=budget.model_parallelism,
            cluster_mapping=fold.cluster_mapping,
            explicit_symbol_id=spec.explicit_symbol_id,
            symbol_balanced=spec.symbol_balanced,
            hybrid_calibration=validation if spec.architecture == "H0" else None,
            eligibility_calibration_a=calibration_a,
            prepared_inputs=prepared.model_inputs,
            reusable_global=reusable_global,
        )
    model.metadata["scientific_input_identity"] = checkpoint_identity
    model.metadata["model_identity"] = stable_hash(
        {
            "structural_model_identity": model.metadata["model_identity"],
            "scientific_input_identity": checkpoint_identity,
        }
    )
    emit_event(
        "MODEL_DONE",
        fold_id=fold.plan.fold_id,
        spec=spec.name,
        elapsed_seconds=time.monotonic() - model_started,
        **memory_snapshot(),
    )
    telemetry("MODEL_FIT_END", "END", started=model_started)
    if reusable_models is not None and _is_reusable_g0(spec):
        reusable_models[reuse_key] = model
    emit_event("CAL_A_START", fold_id=fold.plan.fold_id, spec=spec.name)
    calibration_started = time.monotonic()
    telemetry("CALIBRATE", "START", started=calibration_started)
    cal_a_raw, cal_a_covered = model.predict(calibration_a)
    cal_a_table, cal_a_predictions = _subset_covered(calibration_a, cal_a_raw, cal_a_covered)
    calibrator, calibration_report = fit_calibrator(
        cal_a_predictions,
        np.asarray(cal_a_table.column(target).to_pylist(), dtype=np.float64),
        config.calibration,
    )
    emit_event("CAL_A_DONE", fold_id=fold.plan.fold_id, spec=spec.name)
    telemetry("CALIBRATE", "END", started=calibration_started)
    emit_event("CAL_B_START", fold_id=fold.plan.fold_id, spec=spec.name)
    threshold_started = time.monotonic()
    telemetry("THRESHOLD", "START", started=threshold_started)
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
    emit_event("CAL_B_DONE", fold_id=fold.plan.fold_id, spec=spec.name)
    telemetry("THRESHOLD", "END", started=threshold_started)
    threshold_payload = asdict(thresholds)
    frozen_components = _frozen_test_identity_components(
        model_identity=model.metadata["model_identity"],
        calibrator_identity=calibrator.identity_hash,
        thresholds=threshold_payload,
    )
    frozen_identity = stable_hash(frozen_components)
    emit_event("TEST_EVAL_START", fold_id=fold.plan.fold_id, spec=spec.name)
    test_started = time.monotonic()
    telemetry("TEST", "START", started=test_started)
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
        "thresholds": threshold_payload,
        "calibrator_identity": calibrator.identity_hash,
        "threshold_identity": stable_hash(threshold_payload),
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
        "frozen_identity_components": frozen_components,
        "checkpoint_identity": checkpoint_identity,
        "prepared_cache_id": cache_id,
        "execution_context": execution_metadata or {},
        "test_used_for_selection": False,
        "july_2026_used": False,
        **config.holdout_status_payload(),
    }
    emit_event("TEST_EVAL_DONE", fold_id=fold.plan.fold_id, spec=spec.name)
    telemetry("TEST", "END", started=test_started)
    model_path = model_path or output_root / "model.joblib"
    from crypto_ai.phase7.recovery import publish_model_receipt

    publication = {
        "run_identity": (execution_metadata or {}).get("run_identity", output_root.name),
        "mode": "benchmark"
        if checkpoint_identity.get("artifact_mode") == "BENCHMARK_ONLY"
        else "production",
        "fold_id": fold.plan.fold_id,
        "spec_id": spec.name,
        "state": "MODEL_REPORT_PUBLICATION_V1",
    }
    model.metadata["publication"] = publication
    report["publication"] = publication
    resource_admission("MODEL_PUBLISH", additional_roots=(model_path.parent, output_root))
    telemetry("MODEL_PUBLISH", "START")
    save_model(model, model_path)
    receipt_path = publish_model_receipt(model_path, checkpoint_identity, publication)
    telemetry("MODEL_PUBLISH", "END")
    report["model_artifact_sha256"] = file_sha256(model_path)
    report["model_receipt_sha256"] = file_sha256(receipt_path)
    report["artifact_mode"] = checkpoint_identity.get("artifact_mode", "PRODUCTION_RESEARCH")
    report["report_identity"] = stable_hash(report, length=64)
    resource_admission("REPORT_PUBLISH", additional_roots=(output_root,))
    telemetry("REPORT_PUBLISH", "START")
    report_path = atomic_json(output_root / "report.json", report)
    telemetry("REPORT_PUBLISH", "END")
    if reporter is not None:
        reporter.fold_evaluation(
            report,
            trade_summary=oos_trade_summary(trades),
            elapsed_seconds=time.monotonic() - experiment_started,
            fold_position=fold_position,
            folds_total=folds_total,
        )
    return report, [model_path, receipt_path, report_path]


def run_phase7_training(config: Phase7Config, **kwargs: Any) -> dict[str, Any]:
    """Every direct training call owns an isolated persistent filesystem lease."""
    config.assert_cloud_execution_allowed()
    root = kwargs["run_root"]
    mode = "benchmark" if kwargs.get("benchmark_spec_id") is not None else "production"
    store = kwargs["checkpoint_store"]
    if store.run_identity != root.name:
        raise ValueError("training lease/checkpoint run identity mismatch")
    if mode == "benchmark":
        from crypto_ai.phase7.benchmark_one_spec import benchmark_plan

        benchmark_plan(config, kwargs["benchmark_spec_id"], root.parent)
        first = plan_folds(
            config.data_start,
            config.research_cutoff,
            config.prospective_holdout_start,
            config.schedule,
        )[0]
        if (
            kwargs.get("benchmark_fold_id") != first.fold_id
            or store.root.resolve() != (root / "checkpoints").resolve()
        ):
            raise ValueError("benchmark requires isolated checkpoints and first canonical fold")
    elif kwargs.get("benchmark_fold_id") is not None:
        raise ValueError("benchmark fold selector requires exactly one canonical spec")
    with owned_run(root, root.name, training_source_identity(), mode=mode):
        return _run_phase7_training_owned(config, **kwargs)


def _run_phase7_training_owned(
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
    benchmark_spec_id: str | None = None,
    benchmark_fold_id: str | None = None,
) -> dict[str, Any]:
    config.assert_cloud_execution_allowed()
    source_identity = training_source_identity()
    manifest = _load_gold_manifest(gold_manifest_path)
    gold_paths = [record["path"] for record in manifest["partition_files"]]
    gold_dataset: ds.Dataset | None = None
    groups = {name: tuple(values) for name, values in manifest["feature_groups"].items()}
    folds = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    specs = phase7_experiment_specs(config)
    research_views = RESEARCH_VIEWS
    benchmark_only = benchmark_spec_id is not None
    if benchmark_only:
        from crypto_ai.phase7.benchmark_one_spec import benchmark_plan
        from crypto_ai.phase7.phase7a import select_one_spec

        benchmark_plan(config, benchmark_spec_id, run_root.parent)
        specs = (select_one_spec(config, benchmark_spec_id),)
        if benchmark_fold_id != folds[0].fold_id:
            raise ValueError("benchmark must select exactly the first canonical fold")
        if (
            not run_root.name.startswith("benchmark-only-")
            or checkpoint_store.root.resolve() != (run_root / "checkpoints").resolve()
            or checkpoint_store.run_identity != run_root.name
        ):
            raise ValueError("benchmark requires isolated BENCHMARK_ONLY artifacts/checkpoints")
        folds = (folds[0],)
        research_views = ("CORE",)
    elif benchmark_fold_id is not None:
        raise ValueError("benchmark fold selector requires exactly one canonical spec")
    reports: list[dict[str, Any]] = []
    eligible_fold_ids_by_symbol: dict[str, set[str]] = {}
    gold_manifest_checksum = file_sha256(gold_manifest_path.resolve())
    runtime_paths = RuntimePaths.resolve(config.paths)
    cache_mode = cache_mode_from_environment()
    durable_cache = PreparedDataCache(runtime_paths.cache_root, cache_mode)
    compute_budget = ComputeBudget.resolve(config.resources)
    selected_backend = resolve_lightgbm_backend()
    execution_metadata = {
        "run_identity": run_root.name,
        "git_commit": git_commit(),
        "configuration_hash": config.configuration_hash,
        "scientific_source_identity": source_identity,
        "execution_source_identity": execution_source_identity(),
        "gold_dataset_id": manifest["dataset_id"],
        "gold_manifest_sha256": gold_manifest_checksum,
        "backend": backend_metadata(selected_backend),
        "compute_budget": asdict(compute_budget),
        "runtime_paths": runtime_paths.payload(),
        "os": platform.platform(),
        "python": platform.python_version(),
    }
    emit_event("COMPUTE_BUDGET_RESOLVED", **asdict(compute_budget))
    for fold_position, plan in enumerate(folds, start=1):
        cached: dict[tuple[str, int, str, str], CachedPreparedData] = {}
        # Keep only the current horizon and prepared key. Durable entries remain
        # on disk; advancing a target/horizon releases prior Arrow/memmap payloads.
        sliced: dict[int, MultiAssetFoldData] = {}
        descriptor_identity = causal_descriptor_identity(descriptors, plan.train_end)

        def load_payload(
            view: str,
            spec: ExperimentSpec,
            *,
            cached: Any = cached,
            sliced: Any = sliced,
            plan: Any = plan,
            descriptor_identity: str = descriptor_identity,
        ) -> MultiAssetFoldData:
            nonlocal gold_dataset
            key = (view, spec.horizon_minutes, spec.target_type, spec.feature_group)
            if key in cached:
                return cached[key].fold
            cached.clear()
            if spec.horizon_minutes not in sliced:
                sliced.clear()
            if cache_mode != "disabled":
                membership = select_fold_active_universe(
                    registry,
                    descriptors,
                    fold_id=plan.fold_id,
                    train_end=plan.train_end,
                    core_universe=universe,
                    expansion_policy=expansion_policy,
                    config=config.universe,
                    research_view=view,
                    unusable_segments=unusable_segments,
                    required_start=plan.train_start,
                    required_end=plan.test_end,
                )
                identity = _prepared_cache_identity(
                    config=config,
                    manifest=manifest,
                    gold_manifest_sha256=gold_manifest_checksum,
                    source_identity=source_identity,
                    fold_id=plan.fold_id,
                    research_view=view,
                    fold_membership_hash=membership.membership_hash,
                    universe_hash=universe.universe_hash,
                    registry_hash=registry.registry_hash,
                    descriptor_identity=descriptor_identity,
                    spec=spec,
                    feature_columns=groups[spec.feature_group],
                )
                try:
                    bundle = durable_cache.load(identity, plan)
                except PreparedCacheMissError:
                    if cache_mode == "read_only":
                        raise
                else:
                    cached[key] = bundle
                    return bundle.fold
            if spec.horizon_minutes not in sliced:
                emit_event(
                    "FOLD_LOAD_START",
                    fold_id=plan.fold_id,
                    horizon=spec.horizon_minutes,
                    **memory_snapshot(),
                )
                if gold_dataset is None and gold_paths:
                    gold_dataset = ds.dataset(gold_paths, format="parquet", partitioning="hive")
                table = _load_fold_rows(
                    manifest,
                    plan,
                    spec.horizon_minutes,
                    **({"dataset": gold_dataset} if gold_dataset is not None else {}),
                )
                sliced[spec.horizon_minutes] = slice_multiasset_fold(
                    table,
                    plan,
                    registry=registry,
                    universe=universe,
                    expansion_policy=expansion_policy,
                    research_view=view,
                    descriptors=descriptors,
                    universe_config=config.universe,
                    schedule=config.schedule,
                    holdout_start=config.prospective_holdout_start,
                    cluster_count=config.models.cluster_count,
                    seed=config.models.seed,
                    unusable_segments=unusable_segments,
                )
                emit_event(
                    "FOLD_LOAD_DONE",
                    fold_id=plan.fold_id,
                    horizon=spec.horizon_minutes,
                    rows=table.num_rows,
                    **memory_snapshot(),
                )
            return sliced[spec.horizon_minutes]

        for research_view in research_views:
            cached.clear()
            sliced.clear()
            reusable_models = {}
            prepared_cache = cached_bundle = fold_data = None
            try:
                reference_fold = load_payload(research_view, specs[0])
            except IneligibleFoldError as exc:
                # A genuine point-in-time eligibility failure: record every
                # experiment for this fold/view as INELIGIBLE and move on.
                # Anything else is a defect and must propagate (fail closed).
                for spec in specs:
                    stage = f"models/{research_view.lower()}/{plan.fold_id}/{spec.name}"
                    output = (
                        experiment_output_root(run_root, kind="report", config=config)
                        / research_view.lower()
                        / plan.fold_id
                        / spec.name
                    )
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
                        "scientific_resume_identity_schema": (
                            "phase7_scientific_resume_identity_v2"
                        ),
                        "model_backend_semantics": selected_backend.name,
                        "training_source_identity": source_identity,
                        "causal_descriptor_identity": descriptor_identity,
                        **({"artifact_mode": "BENCHMARK_ONLY"} if benchmark_only else {}),
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
                        "prepared_cache_id": None,
                        "execution_context": execution_metadata,
                        **config.holdout_status_payload(),
                    }
                    if resume and checkpoint_store.is_complete(
                        stage, expected_metadata=checkpoint_identity
                    ):
                        previous = json.loads(report_path.read_text(encoding="utf-8"))
                        if previous.get("status") != "INELIGIBLE":
                            raise ValueError(
                                "slicing-ineligible checkpoint has an inconsistent report"
                            ) from exc
                        reports.append(previous)
                        continue
                    files = [atomic_json(report_path, report)]
                    checkpoint_store.complete(stage, files, checkpoint_identity)
                    reports.append(report)
                continue
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
            del reference_fold
            current_payload_key: tuple[Any, ...] | None = None
            prepared_cache_key: tuple[Any, ...] | None = None
            prepared_cache: PreparedTrainingSegments | None = None
            reusable_models: dict[tuple[Any, ...], Any] = {}
            unavailable_reusable_g0: set[tuple[Any, ...]] = set()
            for spec_position, spec in enumerate(specs, start=1):
                stage = f"models/{research_view.lower()}/{plan.fold_id}/{spec.name}"
                relative_stage = Path(research_view.lower()) / plan.fold_id / spec.name
                output = (
                    experiment_output_root(run_root, kind="report", config=config) / relative_stage
                )
                model_path = (
                    experiment_output_root(run_root, kind="model", config=config)
                    / relative_stage
                    / "model.joblib"
                )
                report_path = output / "report.json"
                durable_key = (
                    research_view,
                    spec.horizon_minutes,
                    spec.target_type,
                    spec.feature_group,
                )
                next_key = (
                    plan.fold_id,
                    research_view,
                    spec.horizon_minutes,
                    _prediction_target(spec),
                    groups[spec.feature_group],
                )
                if current_payload_key != next_key:
                    prepared_cache = None
                    cached_bundle = None
                    fold_data = None
                    reusable_models.clear()
                    unavailable_reusable_g0.clear()
                    current_payload_key = next_key
                fold_data = load_payload(research_view, spec)
                cached_bundle = cached.get(durable_key)
                feature_columns = groups[spec.feature_group]
                target = _prediction_target(spec)
                cache_identity = _prepared_cache_identity(
                    config=config,
                    manifest=manifest,
                    gold_manifest_sha256=gold_manifest_checksum,
                    source_identity=source_identity,
                    fold_id=plan.fold_id,
                    research_view=research_view,
                    fold_membership_hash=fold_data.eligibility_manifest["fold_membership_hash"],
                    universe_hash=universe.universe_hash,
                    registry_hash=registry.registry_hash,
                    descriptor_identity=descriptor_identity,
                    spec=spec,
                    feature_columns=feature_columns,
                )
                current_cache_id = (
                    "DISABLED"
                    if cache_mode == "disabled"
                    else (
                        cached_bundle.cache_id
                        if cached_bundle is not None
                        else prepared_cache_id(cache_identity)
                    )
                )
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
                    "scientific_resume_identity_schema": "phase7_scientific_resume_identity_v2",
                    "model_backend_semantics": selected_backend.name,
                    "training_source_identity": source_identity,
                    "causal_descriptor_identity": descriptor_identity,
                    "fold_context_identity": stable_hash(
                        {
                            "clusters": fold_data.cluster_mapping,
                            "tiers": fold_data.liquidity_tiers,
                            "age_buckets": fold_data.age_buckets,
                        },
                        length=64,
                    ),
                    **({"artifact_mode": "BENCHMARK_ONLY"} if benchmark_only else {}),
                }
                if resume and checkpoint_store.is_complete(
                    stage, expected_metadata=checkpoint_identity
                ):
                    completed_report = json.loads(report_path.read_text(encoding="utf-8"))
                    completed_status = completed_report.get("status")
                    if completed_status == "INELIGIBLE":
                        if _is_reusable_g0(spec):
                            unavailable_reusable_g0.add(
                                _reusable_model_key(
                                    plan.fold_id,
                                    research_view,
                                    spec,
                                    target,
                                    feature_columns,
                                )
                            )
                    elif completed_status != "COMPLETE":
                        raise ValueError(
                            f"completed checkpoint has unsupported report status: "
                            f"{completed_status!r}"
                        )
                    elif _is_reusable_g0(spec):
                        completed_report, completed_model = _restore_completed_g0(
                            report_path=report_path,
                            model_path=model_path,
                            expected_checkpoint_identity=checkpoint_identity,
                        )
                        reuse_key = _reusable_model_key(
                            plan.fold_id,
                            research_view,
                            spec,
                            target,
                            feature_columns,
                        )
                        reusable_models[reuse_key] = completed_model
                    reports.append(completed_report)
                    continue
                if model_path.exists() and not report_path.exists():
                    raise ValueError(
                        "MODEL_ONLY: preserve model; explicit operator decision required, no refit"
                    )
                if resume and report_path.exists():
                    orphan_report = json.loads(report_path.read_text(encoding="utf-8"))
                    orphan_files = [report_path]
                    orphan_model: Any | None = None
                    if orphan_report.get("status") == "COMPLETE":
                        from crypto_ai.phase7.recovery import (
                            inspect_spec_artifacts,
                            model_receipt_path,
                        )

                        artifact_state = inspect_spec_artifacts(
                            model_path=model_path,
                            report_path=report_path,
                            checkpoint_store=checkpoint_store,
                            stage=stage,
                            expected_identity=checkpoint_identity,
                        )
                        if artifact_state["state"] != "MODEL_REPORT":
                            raise ValueError(
                                f"orphan state {artifact_state['state']}: preserve and investigate"
                            )
                        orphan_identity = orphan_report.get("checkpoint_identity")
                        if not isinstance(
                            orphan_identity, dict
                        ) or not checkpoint_metadata_compatible(
                            orphan_identity, checkpoint_identity
                        ):
                            raise ValueError(
                                "Orphan model/report identity mismatch for "
                                f"{research_view} {plan.fold_id} {spec.name}"
                            )
                        if not model_path.exists():
                            raise FileNotFoundError(
                                "COMPLETE orphan report is missing its model artifact for "
                                f"{research_view} {plan.fold_id} {spec.name}"
                            )
                        _validate_model_file_binding(orphan_report, model_path)
                        orphan_model = load_model(model_path)
                        if orphan_model.metadata.get(
                            "scientific_input_identity"
                        ) != orphan_report.get("checkpoint_identity"):
                            raise ValueError("orphan estimator scientific input identity mismatch")
                        _validate_complete_orphan_report(orphan_report, orphan_model)
                        orphan_files.append(model_path)
                        orphan_files.append(model_receipt_path(model_path))
                    elif orphan_report.get("status") not in {"INELIGIBLE"}:
                        raise ValueError(
                            "Orphan report has non-reusable status for "
                            f"{research_view} {plan.fold_id} {spec.name}: "
                            f"{orphan_report.get('status')!r}"
                        )
                    if orphan_report.get("status") == "INELIGIBLE" or len(orphan_files) == 3:
                        orphan_identity = orphan_report.get("checkpoint_identity")
                        if not isinstance(
                            orphan_identity, dict
                        ) or not checkpoint_metadata_compatible(
                            orphan_identity, checkpoint_identity
                        ):
                            raise ValueError(
                                "Orphan report identity mismatch for "
                                f"{research_view} {plan.fold_id} {spec.name}"
                            )
                        checkpoint_store.complete(stage, orphan_files, checkpoint_identity)
                        if _is_reusable_g0(spec) and orphan_model is not None:
                            reuse_key = _reusable_model_key(
                                plan.fold_id,
                                research_view,
                                spec,
                                target,
                                feature_columns,
                            )
                            reusable_models[reuse_key] = orphan_model
                        elif _is_reusable_g0(spec) and orphan_report.get("status") == "INELIGIBLE":
                            unavailable_reusable_g0.add(
                                _reusable_model_key(
                                    plan.fold_id,
                                    research_view,
                                    spec,
                                    target,
                                    feature_columns,
                                )
                            )
                        reports.append(orphan_report)
                        continue
                required_g0_key = _reusable_model_key(
                    plan.fold_id,
                    research_view,
                    spec,
                    target,
                    feature_columns,
                )
                if spec.architecture == "H0" and required_g0_key in unavailable_reusable_g0:
                    report = {
                        "status": "INELIGIBLE",
                        "spec": asdict(spec),
                        "fold_id": plan.fold_id,
                        "research_view": research_view,
                        "fold_membership_hash": fold_data.eligibility_manifest[
                            "fold_membership_hash"
                        ],
                        "reason": "required reusable G0 base is INELIGIBLE",
                        "test_used_for_selection": False,
                        "checkpoint_identity": checkpoint_identity,
                        "prepared_cache_id": current_cache_id,
                        "execution_context": execution_metadata,
                        **config.holdout_status_payload(),
                    }
                    files = [atomic_json(report_path, report)]
                    checkpoint_store.complete(stage, files, checkpoint_identity)
                    reports.append(report)
                    continue
                print(
                    f"[phase7:train] view {research_view} fold {fold_position}/{len(folds)} "
                    f"experiment {spec_position}/{len(specs)} {spec.name}",
                    flush=True,
                )
                next_prepared_key = (
                    plan.fold_id,
                    research_view,
                    spec.horizon_minutes,
                    target,
                    feature_columns,
                )
                if cached_bundle is not None:
                    prepared_cache = cached_bundle.prepared
                    prepared_cache_key = next_prepared_key
                elif prepared_cache_key != next_prepared_key:
                    prep_started = time.monotonic()
                    prepared_cache = _prepare_training_segments(
                        fold_data,
                        feature_columns,
                        target,
                    )
                    prepared_cache_key = next_prepared_key
                    emit_event(
                        "MATRIX_PREPARATION_DONE",
                        fold_id=plan.fold_id,
                        research_view=research_view,
                        horizon=spec.horizon_minutes,
                        target=target,
                        elapsed_seconds=time.monotonic() - prep_started,
                        **memory_snapshot(),
                    )
                    cache_path = durable_cache.write(cache_identity, fold_data, prepared_cache)
                    if cache_path is not None:
                        cached_bundle = durable_cache.open_published(cache_identity, plan)
                        cached[durable_key] = cached_bundle
                        prepared_cache = cached_bundle.prepared
                if prepared_cache is None:
                    raise AssertionError("Phase 7 prepared-segment cache was not initialized")
                try:
                    report, files = _run_one(
                        spec,
                        fold_data,
                        feature_columns,
                        config,
                        output,
                        checkpoint_identity,
                        reporter=reporter,
                        fold_position=fold_position,
                        folds_total=len(folds),
                        prepared_segments=prepared_cache,
                        reusable_models=reusable_models,
                        compute_budget=compute_budget,
                        cache_id=current_cache_id,
                        execution_metadata=execution_metadata,
                        model_path=model_path,
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
                        "prepared_cache_id": current_cache_id,
                        "execution_context": execution_metadata,
                        **config.holdout_status_payload(),
                    }
                    files = [atomic_json(report_path, report)]
                    if _is_reusable_g0(spec):
                        unavailable_reusable_g0.add(required_g0_key)
                checkpoint_store.complete(stage, files, checkpoint_identity)
                emit_event("CHECKPOINT_SAVED", stage=stage)
                reports.append(report)
        cached.clear()
        sliced.clear()
        reusable_models.clear()
        prepared_cache = cached_bundle = fold_data = None
        if reporter is not None and not benchmark_only:
            reporter.fold_completed(fold_position, len(folds), plan.fold_id)
    if benchmark_only:
        summary = {
            "status": "BENCHMARK_ONLY",
            "artifact_mode": "BENCHMARK_ONLY",
            "canonical_fold_complete": False,
            "canonical_primary_run_complete": False,
            "fold_count": 0,
            "benchmark_fold_count": 1,
            "experiment_spec_count": 1,
            "research_views": ["CORE"],
            "reports": reports,
            "completed_reports": 0,
            "benchmark_completed_reports": sum(r["status"] == "COMPLETE" for r in reports),
            **config.holdout_status_payload(),
        }
        atomic_json(run_root / "benchmark_summary.json", summary)
        return summary
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
        "research_views": list(research_views),
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
