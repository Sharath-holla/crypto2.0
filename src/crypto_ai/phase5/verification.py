from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.execution import (
    ADAPTIVE_POLICY_COST_STRESS,
    FIXED_POLICY_COST_STRESS,
    trade_identity_hash,
)
from crypto_ai.phase5.hardening import RESULT_VERSION

_FIXED_MULTIPLIERS = (1.0, 1.25, 1.5, 2.0)


def _failure(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _checksum_manifest(directory: Path, manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for name, expected in manifest.get("files", {}).items():
        path = directory / name
        if not path.exists():
            failures.append(f"missing:{path}")
        elif file_sha256(path) != expected:
            failures.append(f"checksum:{path}")
    return failures


def _timestamp_holdout_count(path: Path, holdout: datetime) -> tuple[int, str | None]:
    schema = pq.ParquetFile(path).schema_arrow
    names = [
        name for name in ("feature_time", "entry_time", "label_end_time") if name in schema.names
    ]
    if not names:
        return 0, None
    table = pq.read_table(path, columns=names)
    holdout_us = int(holdout.timestamp() * 1_000_000)
    count = 0
    maximum: int | None = None
    for name in names:
        values = table.column(name).combine_chunks().cast(pa.int64()).to_numpy()
        if len(values):
            count += int(np.count_nonzero(values >= holdout_us))
            value = int(np.max(values))
            maximum = value if maximum is None else max(maximum, value)
    return (
        count,
        None
        if maximum is None
        else datetime.fromtimestamp(maximum / 1_000_000, tz=holdout.tzinfo).isoformat(),
    )


def _fixed_identity(table: pa.Table) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    return tuple(
        table.column(name).to_pylist()
        for name in ("trade_id", "entry_time", "exit_time", "direction")
    )


def _verify_fold(
    directory: Path,
    *,
    holdout: datetime,
    candidate: str,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    manifest = read_manifest(directory / "fold_manifest.json")
    backtest = read_manifest(directory / "backtest.json")
    calibration = read_manifest(directory / "calibrator.json")
    threshold = read_manifest(directory / "threshold.json")
    if any(item is None for item in (manifest, backtest, calibration, threshold)):
        return {}, [f"incomplete-fold:{directory}"]
    failures.extend(_checksum_manifest(directory, manifest))
    _failure(failures, manifest.get("model_retrained") is False, f"retrained:{directory}")
    _failure(
        failures,
        manifest.get("prospective_holdout_used") is False,
        f"holdout-flag:{directory}",
    )
    source_model = Path(manifest["source_model"])
    _failure(failures, source_model.exists(), f"source-model-missing:{source_model}")
    if source_model.exists():
        _failure(
            failures,
            file_sha256(source_model) == manifest["source_model_sha256"],
            f"source-model-hash:{source_model}",
        )
    source_fold_manifest = Path(manifest["source_fold_manifest"])
    source = read_manifest(source_fold_manifest)
    _failure(failures, source is not None, f"source-fold-missing:{source_fold_manifest}")
    if source is not None:
        failures.extend(_checksum_manifest(source_fold_manifest.parent, source))
        _failure(
            failures,
            source.get("feature_schema") == manifest.get("feature_schema"),
            f"feature-schema:{directory}",
        )
    cal_a_start, cal_a_end = map(datetime.fromisoformat, calibration["calibration_a_range"])
    cal_b_start, cal_b_end = map(datetime.fromisoformat, calibration["calibration_b_range"])
    test_start = datetime.fromisoformat(manifest["fold"]["test_start"])
    _failure(failures, cal_a_start < cal_a_end <= cal_b_start, f"cal-order-a:{directory}")
    _failure(failures, cal_b_start < cal_b_end <= test_start, f"cal-order-b:{directory}")
    _failure(failures, calibration["purged_rows"] > 0, f"cal-purge:{directory}")
    _failure(failures, calibration["embargo_rows"] > 0, f"cal-embargo:{directory}")
    _failure(
        failures,
        calibration.get("fit_source") == "CALIBRATION_A_ONLY",
        f"cal-owner:{directory}",
    )
    _failure(
        failures,
        threshold.get("selection_source") == "CALIBRATION_B_ONLY",
        f"threshold-owner:{directory}",
    )
    access = backtest["test_access"]
    for name in (
        "early_stopping_used_test",
        "calibrator_fit_used_test",
        "calibration_method_selection_used_test",
        "threshold_selection_used_test",
        "calibration_b_influenced_calibrator_fit",
    ):
        _failure(failures, access.get(name) is False, f"test-isolation:{name}:{directory}")
    fixed_identity = None
    fixed_hashes: list[str] = []
    fixed_counts: list[int] = []
    fixed_nets: list[float] = []
    for multiplier in _FIXED_MULTIPLIERS:
        key = str(multiplier)
        path = directory / f"fixed_policy_trades_{multiplier:g}x.parquet"
        table = pq.read_table(path)
        identity = _fixed_identity(table)
        fixed_identity = identity if fixed_identity is None else fixed_identity
        _failure(failures, identity == fixed_identity, f"fixed-identity:{key}:{directory}")
        actual_hash = trade_identity_hash(table)
        metrics = backtest["fixed_policy_cost_stress"][key]
        _failure(
            failures,
            metrics.get("stress_type") == FIXED_POLICY_COST_STRESS,
            f"fixed-label:{key}:{directory}",
        )
        _failure(
            failures,
            metrics.get("trade_identity_hash") == actual_hash,
            f"fixed-hash:{key}:{directory}",
        )
        fixed_hashes.append(actual_hash)
        fixed_counts.append(table.num_rows)
        fixed_nets.append(float(metrics["total_net_return"]))
    _failure(failures, len(set(fixed_hashes)) == 1, f"fixed-hash-invariant:{directory}")
    _failure(failures, len(set(fixed_counts)) == 1, f"fixed-count-invariant:{directory}")
    _failure(
        failures,
        all(left >= right - 1e-15 for left, right in zip(fixed_nets, fixed_nets[1:], strict=False)),
        f"fixed-monotonicity:{directory}",
    )
    for multiplier in _FIXED_MULTIPLIERS:
        metrics = backtest["adaptive_policy_cost_stress"][str(multiplier)]
        _failure(
            failures,
            metrics.get("stress_type") == ADAPTIVE_POLICY_COST_STRESS,
            f"adaptive-label:{multiplier}:{directory}",
        )
    holdout_rows = 0
    max_timestamps: list[str] = []
    for path in directory.glob("*.parquet"):
        count, maximum = _timestamp_holdout_count(path, holdout)
        holdout_rows += count
        if maximum is not None:
            max_timestamps.append(maximum)
    _failure(failures, holdout_rows == 0, f"holdout-rows:{holdout_rows}:{directory}")
    base = backtest["fixed_policy_cost_stress"]["1.0"]
    _failure(
        failures,
        "statistically_reliable" in base and "reliability_reason" in base,
        f"reliability-fields:{directory}",
    )
    return (
        {
            "candidate": candidate,
            "fold_id": manifest["fold"]["fold_id"],
            "fixed_trade_hash": fixed_hashes[0],
            "fixed_trade_count": fixed_counts[0],
            "fixed_net_results": dict(zip(map(str, _FIXED_MULTIPLIERS), fixed_nets, strict=True)),
            "holdout_rows": holdout_rows,
            "max_timestamp": max(max_timestamps) if max_timestamps else None,
            "failure_count": len(failures),
        },
        failures,
    )


def verify_hardened_runs(
    primary_summary_path: Path,
    derivatives_summary_path: Path,
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    """Independently audit immutable Phase 5.1 artifacts and their v1 lineage."""

    failures: list[str] = []
    summaries = [
        read_manifest(primary_summary_path.resolve()),
        read_manifest(derivatives_summary_path.resolve()),
    ]
    if any(summary is None for summary in summaries):
        raise FileNotFoundError("both hardened summaries are required")
    candidates: dict[str, Any] = {}
    fold_details: list[dict[str, Any]] = []
    source_manifests: set[Path] = set()
    holdout_rows = 0
    max_timestamps: list[str] = []
    qualification_rules_changed = False
    feature_schemas_changed = False
    label_changed = False
    hyperparameters_changed = False
    dataset_lineage: dict[str, Any] = {}
    for summary in summaries:
        _failure(
            failures,
            summary.get("result_version") == RESULT_VERSION,
            f"result-version:{summary.get('run_id')}",
        )
        _failure(
            failures,
            summary.get("models_retrained") is False,
            f"retrained-run:{summary.get('run_id')}",
        )
        holdout = datetime.fromisoformat(summary["prospective_holdout_start"])
        run_directory = primary_summary_path.resolve().parent
        if summary["family"] == "derivatives":
            run_directory = derivatives_summary_path.resolve().parent
        source_summary = read_manifest(Path(summary["source_summary"]))
        _failure(
            failures,
            source_summary is not None,
            f"source-summary-missing:{summary['run_id']}",
        )
        walkforward_configuration = summary["identity"]["configuration"]["walkforward"]
        gold_manifest = read_manifest(Path(walkforward_configuration["dataset_manifest"]))
        _failure(
            failures,
            gold_manifest is not None,
            f"gold-manifest-missing:{summary['run_id']}",
        )
        if source_summary is not None:
            qualification_rules_changed |= (
                source_summary["identity"]["configuration"]["qualification"]
                != walkforward_configuration["qualification"]
            )
            hyperparameters_changed |= (
                file_sha256(Path(walkforward_configuration["experiment_config"]))
                != source_summary["identity"]["model_config_sha256"]
            )
        if gold_manifest is not None:
            _failure(
                failures,
                gold_manifest.get("sha256") == summary["identity"]["dataset_sha256"],
                f"gold-lineage:{summary['run_id']}",
            )
            label_changed |= (
                gold_manifest.get("label_version") != "1.0.0"
                or gold_manifest.get("target_column") != "future_return_60m"
            )
            dataset_lineage[summary["family"]] = {
                "dataset_version": gold_manifest.get("dataset_version"),
                "dataset_sha256": gold_manifest.get("sha256"),
                "feature_version": gold_manifest.get("feature_version"),
                "label_version": gold_manifest.get("label_version"),
                "target_column": gold_manifest.get("target_column"),
            }
        expected_folds = int(summary["outer_walk_forward_design"]["fold_count"])
        for candidate, candidate_result in summary["candidates"].items():
            directory = run_directory / "candidates" / candidate / "folds"
            fold_directories = sorted(path for path in directory.iterdir() if path.is_dir())
            _failure(
                failures,
                len(fold_directories) == expected_folds,
                f"fold-count:{candidate}:{len(fold_directories)}:{expected_folds}",
            )
            candidate_details = []
            for fold_directory in fold_directories:
                detail, fold_failures = _verify_fold(
                    fold_directory,
                    holdout=holdout,
                    candidate=candidate,
                )
                failures.extend(fold_failures)
                if detail:
                    candidate_details.append(detail)
                    fold_details.append(detail)
                    holdout_rows += detail["holdout_rows"]
                    if detail["max_timestamp"] is not None:
                        max_timestamps.append(detail["max_timestamp"])
                manifest = read_manifest(fold_directory / "fold_manifest.json")
                if manifest is not None:
                    source_manifests.add(Path(manifest["source_fold_manifest"]))
                    source = read_manifest(Path(manifest["source_fold_manifest"]))
                    if source is not None:
                        feature_schemas_changed |= source.get("feature_schema") != manifest.get(
                            "feature_schema"
                        )
            pooled = pq.read_table(
                run_directory / "oos_predictions.parquet",
                filters=[("candidate", "=", candidate)],
                columns=["feature_time"],
            )
            times = pooled.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
            duplicate_count = len(times) - len(np.unique(times))
            _failure(failures, duplicate_count == 0, f"duplicate-oos:{candidate}")
            qualification = candidate_result.get("qualification", {})
            _failure(
                failures,
                qualification.get("qualification_status") in {"PASS", "FAIL"},
                f"qualification-status:{candidate}",
            )
            _failure(
                failures,
                qualification.get("evidence_status")
                in {"NEGATIVE", "INCONCLUSIVE", "WEAK_POSITIVE", "PROMISING_UNVALIDATED"},
                f"evidence-status:{candidate}",
            )
            candidates[candidate] = {
                "expected_folds": expected_folds,
                "completed_folds": len(fold_directories),
                "missing_folds": max(0, expected_folds - len(fold_directories)),
                "invalid_folds": sum(
                    detail.get("failure_count", 0) > 0 for detail in candidate_details
                ),
                "duplicate_oos_timestamps": duplicate_count,
                "qualification_status": qualification.get("qualification_status"),
                "evidence_status": qualification.get("evidence_status"),
            }
        artifact_manifest = read_manifest(run_directory / "artifact_manifest.json")
        if artifact_manifest is None:
            failures.append(f"root-manifest-missing:{run_directory}")
        else:
            failures.extend(_checksum_manifest(run_directory, artifact_manifest))
        for path in run_directory.glob("*.parquet"):
            count, maximum = _timestamp_holdout_count(path, holdout)
            holdout_rows += count
            if maximum is not None:
                max_timestamps.append(maximum)
        source_qualification = summary["outer_walk_forward_design"]
        _failure(
            failures,
            source_qualification.get("prospective_holdout_used") is False,
            f"source-holdout:{summary['run_id']}",
        )
    _failure(failures, not qualification_rules_changed, "qualification-rules-changed")
    _failure(failures, not feature_schemas_changed, "feature-schemas-changed")
    _failure(failures, not label_changed, "label-changed")
    _failure(failures, not hyperparameters_changed, "hyperparameters-changed")
    result = {
        "status": "PASS" if not failures else "FAIL",
        "result_version": RESULT_VERSION,
        "verified_at": datetime.now().astimezone().isoformat(),
        "candidates": candidates,
        "hardened_fold_count": len(fold_details),
        "source_fold_manifest_count": len(source_manifests),
        "models_retrained": False,
        "qualification_rules_changed": qualification_rules_changed,
        "feature_schemas_changed": feature_schemas_changed,
        "label_changed": label_changed,
        "hyperparameters_changed": hyperparameters_changed,
        "dataset_lineage": dataset_lineage,
        "prospective_holdout_rows": holdout_rows,
        "max_artifact_timestamp": max(max_timestamps) if max_timestamps else None,
        "checksum_or_invariant_failures": len(failures),
        "failures": failures,
    }
    if output is not None:
        write_manifest(output.resolve(), result)
    return result
