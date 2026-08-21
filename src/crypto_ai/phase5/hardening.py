from __future__ import annotations

import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase4.market_data import MarketDataKind, read_market_dataset
from crypto_ai.phase4_1.config import load_backtest_v2_1_config
from crypto_ai.phase4_1.gold import read_gold_v2_1
from crypto_ai.phase5.calibration import fit_calibrator
from crypto_ai.phase5.config import HardeningConfig
from crypto_ai.phase5.engine import (
    _artifact_files_valid,
    _block_bootstrap_predictive,
    _candidate_columns,
    _concat,
    _economic_bootstrap,
    _feature_schema,
    _floats,
    _group_trade_metrics,
    _hash,
    _matrix,
    _opportunity_table,
    _prediction_year_metrics,
    _target,
    _times,
    _top_positive_group_share,
)
from crypto_ai.phase5.execution import (
    ADAPTIVE_POLICY_COST_STRESS,
    FIXED_POLICY_COST_STRESS,
    economic_metrics,
    prepare_execution_arrays,
    reprice_fixed_policy_trades,
    simulate_trades,
    trade_identity_hash,
)
from crypto_ai.phase5.folds import FoldPlan, slice_hardened_fold
from crypto_ai.phase5.policy import select_threshold
from crypto_ai.research.config import DatasetBuildConfig
from crypto_ai.research.gold import TARGET_COLUMN, _load_silver
from crypto_ai.research.metrics import prediction_buckets, regression_metrics
from crypto_ai.research.models import load_model

HARDENING_VERSION = "1.1.0"
RESULT_VERSION = "walkforward_v1_1"


def _fold_plan(payload: dict[str, Any]) -> FoldPlan:
    return FoldPlan(
        **{
            key: datetime.fromisoformat(value) if key.endswith(("start", "end")) else value
            for key, value in payload.items()
        }
    )


def _prediction_table(segment: pa.Table, raw: np.ndarray, calibrated: np.ndarray) -> pa.Table:
    return pa.table(
        {
            "feature_time": segment.column("feature_time"),
            "label_end_time": segment.column("label_end_time"),
            TARGET_COLUMN: segment.column(TARGET_COLUMN),
            "raw_prediction": pa.array(raw, type=pa.float64()),
            "calibrated_prediction": pa.array(calibrated, type=pa.float64()),
        }
    )


def _source_fold_directory(source_run: Path, candidate: str, fold_id: str) -> Path:
    return source_run / "candidates" / candidate / "folds" / fold_id


def _validate_source_fold(directory: Path) -> dict[str, Any]:
    manifest = read_manifest(directory / "fold_manifest.json")
    if manifest is None:
        raise FileNotFoundError(f"missing historical fold manifest: {directory}")
    if not _artifact_files_valid(directory, manifest, str(manifest.get("identity", ""))):
        raise ValueError(f"historical fold artifact failed immutable checksum audit: {directory}")
    return manifest


def _load_hardened_fold(directory: Path, multipliers: tuple[float, ...]) -> dict[str, Any]:
    manifest = read_manifest(directory / "fold_manifest.json")
    backtest = read_manifest(directory / "backtest.json")
    calibration = read_manifest(directory / "calibrator.json")
    threshold = read_manifest(directory / "threshold.json")
    if any(item is None for item in (manifest, backtest, calibration, threshold)):
        raise ValueError(f"incomplete hardened fold: {directory}")
    return {
        "manifest": manifest,
        "backtest": backtest,
        "calibration": calibration,
        "threshold": threshold,
        "predictions": pq.read_table(directory / "test_predictions.parquet"),
        "fixed_trades": {
            str(value): pq.read_table(directory / f"fixed_policy_trades_{value:g}x.parquet")
            for value in multipliers
        },
        "adaptive_trades": {
            str(value): pq.read_table(directory / f"adaptive_policy_trades_{value:g}x.parquet")
            for value in multipliers
        },
    }


def _harden_fold(
    *,
    gold: pa.Table,
    plan: FoldPlan,
    candidate: str,
    columns: tuple[str, ...],
    config: HardeningConfig,
    source_run: Path,
    run_directory: Path,
    funding: pa.Table | None,
    execution_1m: pa.Table | None,
    resume: bool,
) -> dict[str, Any]:
    walkforward = config.walkforward
    source_directory = _source_fold_directory(source_run, candidate, plan.fold_id)
    source_manifest = _validate_source_fold(source_directory)
    source_model = source_directory / "model.joblib"
    source_model_sha256 = file_sha256(source_model)
    identity = _hash(
        {
            "protocol": HARDENING_VERSION,
            "configuration": config.configuration_hash,
            "source_fold_identity": source_manifest["identity"],
            "source_model_sha256": source_model_sha256,
            "candidate": candidate,
            "fold": plan.to_dict(),
        }
    )
    final = run_directory / "candidates" / candidate / "folds" / plan.fold_id
    existing = read_manifest(final / "fold_manifest.json")
    if resume and existing is not None and _artifact_files_valid(final, existing, identity):
        return _load_hardened_fold(final, walkforward.cost_multipliers)
    if final.exists():
        raise FileExistsError(f"refusing to overwrite hardened fold artifact: {final}")
    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        fold = slice_hardened_fold(
            gold,
            plan,
            walkforward.schedule,
            walkforward.prospective_holdout_start,
        )
        bundle = load_model(source_model)
        if tuple(bundle.feature_columns) != columns:
            raise ValueError("historical model feature schema differs from frozen candidate schema")
        calibration_a_raw = bundle.predict(_matrix(fold.calibration_a, columns), columns)
        calibrator, calibration_diagnostics = fit_calibrator(
            calibration_a_raw,
            _target(fold.calibration_a),
            walkforward.calibration,
        )
        calibration_a_calibrated = calibrator.apply(calibration_a_raw)
        calibration_b_raw = bundle.predict(_matrix(fold.calibration_b, columns), columns)
        calibration_b_calibrated = calibrator.apply(calibration_b_raw)
        backtest_config = load_backtest_v2_1_config(walkforward.backtest_config)
        policy, threshold_diagnostics = select_threshold(
            calibration_b_calibrated,
            _target(fold.calibration_b),
            _times(fold.calibration_b, "feature_time"),
            walkforward.threshold,
            cost_bps=backtest_config.non_funding_round_trip_bps,
            horizon_minutes=backtest_config.horizon_minutes,
        )
        threshold_diagnostics["selection_source"] = "calibration_b_only"
        frozen_identity = _hash(
            {
                "source_model_sha256": source_model_sha256,
                "calibrator": calibrator.identity_hash,
                "policy": policy.identity_hash,
            }
        )
        test = fold.release_test(frozen_identity=frozen_identity)
        historical_test = pq.read_table(source_directory / "test_predictions.parquet")
        if not np.array_equal(
            _times(test, "feature_time"), _times(historical_test, "feature_time")
        ):
            raise ValueError("hardened TEST rows differ from historical frozen TEST rows")
        test_raw = _floats(historical_test, "raw_prediction")
        test_calibrated = calibrator.apply(test_raw)
        predictions = _opportunity_table(
            test,
            test_raw,
            test_calibrated,
            candidate=candidate,
            family=walkforward.family,
            fold_id=plan.fold_id,
            calibrator_method=calibrator.method,
            threshold_bps=policy.threshold_bps,
            feature_schema_hash=_feature_schema(columns)["sha256"],
        ).append_column(
            "hardening_protocol_version",
            pa.array([HARDENING_VERSION] * test.num_rows),
        )
        prepared_execution = prepare_execution_arrays(
            predictions,
            execution_1m,
            backtest_config,
        )
        base_trades, base_metrics = simulate_trades(
            predictions,
            policy,
            backtest_config,
            funding=funding,
            execution_1m=execution_1m,
            cost_multiplier=1.0,
            stress_type=ADAPTIVE_POLICY_COST_STRESS,
            prepared_execution=prepared_execution,
        )
        fixed_trades: dict[str, pa.Table] = {}
        fixed_metrics: dict[str, dict[str, Any]] = {}
        adaptive_trades: dict[str, pa.Table] = {}
        adaptive_metrics: dict[str, dict[str, Any]] = {}
        for multiplier in walkforward.cost_multipliers:
            key = str(multiplier)
            fixed, fixed_result = reprice_fixed_policy_trades(
                base_trades,
                backtest_config,
                cost_multiplier=multiplier,
            )
            fixed_result["opportunity_count"] = predictions.num_rows
            fixed_result["no_trade_count"] = predictions.num_rows - fixed.num_rows
            if multiplier == 1.0:
                adaptive, adaptive_result = base_trades, base_metrics
            else:
                adaptive, adaptive_result = simulate_trades(
                    predictions,
                    policy,
                    backtest_config,
                    funding=funding,
                    execution_1m=execution_1m,
                    cost_multiplier=multiplier,
                    stress_type=ADAPTIVE_POLICY_COST_STRESS,
                    prepared_execution=prepared_execution,
                )
            fixed_trades[key], fixed_metrics[key] = fixed, fixed_result
            adaptive_trades[key], adaptive_metrics[key] = adaptive, adaptive_result
            pq.write_table(
                fixed,
                temporary / f"fixed_policy_trades_{multiplier:g}x.parquet",
                compression="zstd",
            )
            pq.write_table(
                adaptive,
                temporary / f"adaptive_policy_trades_{multiplier:g}x.parquet",
                compression="zstd",
            )
        fixed_hashes = {item["trade_identity_hash"] for item in fixed_metrics.values()}
        if len(fixed_hashes) != 1:
            raise AssertionError("fixed-policy stress changed the frozen trade list")
        pq.write_table(
            _prediction_table(
                fold.calibration_a,
                calibration_a_raw,
                calibration_a_calibrated,
            ),
            temporary / "calibration_a_predictions.parquet",
            compression="zstd",
        )
        pq.write_table(
            _prediction_table(
                fold.calibration_b,
                calibration_b_raw,
                calibration_b_calibrated,
            ),
            temporary / "calibration_b_predictions.parquet",
            compression="zstd",
        )
        pq.write_table(predictions, temporary / "test_predictions.parquet", compression="zstd")
        calibration_output = {
            "frozen_before_test": True,
            "fit_source": "CALIBRATION_A_ONLY",
            "calibration_a_range": fold.report["segments"]["calibration_a"]["range"],
            "calibration_b_range": fold.report["segments"]["calibration_b"]["range"],
            "calibration_a_rows": fold.calibration_a.num_rows,
            "calibration_b_rows": fold.calibration_b.num_rows,
            "purged_rows": fold.report["segments"]["calibration_a"]["purged"],
            "embargo_rows": fold.report["segments"]["calibration_b"]["embargoed"],
            "calibration_method": calibrator.method,
            "slope": calibrator.slope,
            "intercept": calibrator.intercept,
            "candidate_thresholds": list(walkforward.threshold.grid_bps),
            "selected_threshold": policy.threshold_bps,
            "threshold_trade_count": policy.calibration_trade_count,
            "calibrator": calibrator.to_dict(),
            "diagnostics": calibration_diagnostics,
        }
        write_manifest(temporary / "calibrator.json", calibration_output)
        write_manifest(
            temporary / "threshold.json",
            {
                "frozen_before_test": True,
                "selection_source": "CALIBRATION_B_ONLY",
                "policy": policy.to_dict(),
                "diagnostics": threshold_diagnostics,
            },
        )
        max_feature_time = max(
            segment.column("feature_time")[-1].as_py()
            for segment in (
                fold.train,
                fold.validation,
                fold.calibration_a,
                fold.calibration_b,
                test,
            )
        )
        if max_feature_time >= walkforward.prospective_holdout_start:
            raise AssertionError("prospective holdout contamination detected")
        backtest = {
            "fold_id": plan.fold_id,
            "candidate": candidate,
            "result_version": RESULT_VERSION,
            "model_retrained": False,
            "source_model_sha256": source_model_sha256,
            "calibration_a_predictive": regression_metrics(
                _target(fold.calibration_a), calibration_a_calibrated
            ),
            "calibration_b_predictive": regression_metrics(
                _target(fold.calibration_b), calibration_b_calibrated
            ),
            "test_predictive_raw": regression_metrics(_target(test), test_raw),
            "test_predictive_calibrated": regression_metrics(_target(test), test_calibrated),
            "test_reliability_curve": prediction_buckets(
                _target(test),
                test_calibrated,
                bucket_count=walkforward.calibration.reliability_buckets,
            ),
            "fixed_policy_cost_stress": fixed_metrics,
            "adaptive_policy_cost_stress": adaptive_metrics,
            "fixed_policy_trade_invariant": {
                "satisfied": True,
                "trade_identity_hash": next(iter(fixed_hashes)),
            },
            "purging_and_embargo": fold.report,
            "test_access": {
                "released_after_frozen_identity": frozen_identity,
                "early_stopping_used_test": False,
                "calibrator_fit_used_test": False,
                "calibration_method_selection_used_test": False,
                "threshold_selection_used_test": False,
                "calibration_b_influenced_calibrator_fit": False,
            },
            "prospective_holdout_start": walkforward.prospective_holdout_start.isoformat(),
            "max_feature_time_used": max_feature_time.isoformat(),
            "prospective_holdout_used": False,
        }
        write_manifest(temporary / "backtest.json", backtest)
        file_names = [
            "calibration_a_predictions.parquet",
            "calibration_b_predictions.parquet",
            "test_predictions.parquet",
            "calibrator.json",
            "threshold.json",
            "backtest.json",
            *[f"fixed_policy_trades_{value:g}x.parquet" for value in walkforward.cost_multipliers],
            *[
                f"adaptive_policy_trades_{value:g}x.parquet"
                for value in walkforward.cost_multipliers
            ],
        ]
        manifest = {
            "status": "complete",
            "identity": identity,
            "frozen_identity": frozen_identity,
            "candidate": candidate,
            "fold": plan.to_dict(),
            "feature_schema": _feature_schema(columns),
            "source_fold_manifest": str((source_directory / "fold_manifest.json").resolve()),
            "source_model": str(source_model.resolve()),
            "source_model_sha256": source_model_sha256,
            "model_retrained": False,
            "files": {name: file_sha256(temporary / name) for name in file_names},
            "created_at": datetime.now(UTC).isoformat(),
            "prospective_holdout_start": walkforward.prospective_holdout_start.isoformat(),
            "max_feature_time_used": max_feature_time.isoformat(),
            "prospective_holdout_used": False,
            "version": HARDENING_VERSION,
            "result_version": RESULT_VERSION,
        }
        write_manifest(temporary / "fold_manifest.json", manifest)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _load_hardened_fold(final, walkforward.cost_multipliers)


def _trade_concentration(trades: pa.Table) -> dict[str, Any]:
    if trades.num_rows == 0:
        return {
            "trade_count": 0,
            "largest_trade_contribution": None,
            "top_5_trade_contribution": None,
            "top_10_percent_trade_contribution": None,
            "largest_positive_trade": None,
            "largest_negative_trade": None,
            "top_positive_trades": {"positive_pnl_total": 0.0},
        }
    values = _floats(trades, "net_return")
    descending = np.sort(values)[::-1]
    total = float(np.sum(values))

    def contribution(count: int) -> dict[str, Any]:
        value = float(np.sum(descending[:count]))
        return {
            "net_return": value,
            "share_of_total_net_return": None if total <= 0 else value / total,
            "share_reliable": total > 0,
        }

    positive = np.sort(values[values > 0])[::-1]
    positive_total = float(np.sum(positive))
    return {
        "trade_count": len(values),
        "total_net_return": total,
        "largest_trade_contribution": contribution(1),
        "top_5_trade_contribution": contribution(min(5, len(values))),
        "top_10_percent_trade_contribution": contribution(max(1, int(np.ceil(len(values) * 0.10)))),
        "largest_positive_trade": float(np.max(positive)) if len(positive) else None,
        "largest_negative_trade": (
            float(np.min(values[values < 0])) if np.any(values < 0) else None
        ),
        "top_positive_trades": {
            "positive_pnl_total": positive_total,
            "largest_positive_share": (
                None if positive_total == 0 else float(positive[0] / positive_total)
            ),
            "top_5_positive_share": (
                None if positive_total == 0 else float(np.sum(positive[:5]) / positive_total)
            ),
        },
    }


def _positive_fold_share(records: list[dict[str, Any]]) -> float | None:
    values = np.asarray(
        [
            record["backtest"]["fixed_policy_cost_stress"]["1.0"]["total_net_return"]
            for record in records
        ]
    )
    positive = np.clip(values, 0, None)
    return None if np.sum(positive) == 0 else float(np.max(positive) / np.sum(positive))


def _qualification(aggregate: dict[str, Any], config: HardeningConfig) -> dict[str, Any]:
    rules = config.walkforward.qualification
    base = aggregate["fixed_policy_cost_stress"]["1.0"]
    stress = aggregate["fixed_policy_cost_stress"][str(rules.required_cost_multiplier)]
    fold_expectancy = [
        fold["base_expectancy"]
        for fold in aggregate["folds"]
        if fold["base_expectancy"] is not None
    ]
    median_expectancy = float(np.median(fold_expectancy)) if fold_expectancy else None
    gates = {
        "minimum_test_folds": aggregate["fold_count"] >= rules.minimum_test_folds,
        "minimum_total_trades": base["trade_count"] >= rules.minimum_total_trades,
        "minimum_reliable_folds": aggregate["reliable_fold_count"] >= rules.minimum_reliable_folds,
        "positive_median_fold_expectancy": median_expectancy is not None and median_expectancy > 0,
        "positive_pooled_base_expectancy": base["expectancy"] is not None
        and base["expectancy"] > 0,
        "maximum_drawdown": abs(base["maximum_drawdown"]) <= rules.maximum_drawdown,
        "positive_required_fixed_cost_stress": stress["expectancy"] is not None
        and stress["expectancy"] > 0,
        "fold_concentration": aggregate["top_fold_positive_pnl_share"] is not None
        and aggregate["top_fold_positive_pnl_share"] <= rules.maximum_top_fold_pnl_share,
        "year_concentration": aggregate["top_year_positive_pnl_share"] is not None
        and aggregate["top_year_positive_pnl_share"] <= rules.maximum_top_year_pnl_share,
        "regime_concentration": aggregate["top_regime_positive_pnl_share"] is not None
        and aggregate["top_regime_positive_pnl_share"] <= rules.maximum_top_regime_pnl_share,
    }
    qualification_status = "PASS" if all(gates.values()) else "FAIL"
    insufficient = not gates["minimum_total_trades"] or not gates["minimum_reliable_folds"]
    if qualification_status == "PASS":
        evidence_status = "PROMISING_UNVALIDATED"
    elif insufficient:
        evidence_status = "INCONCLUSIVE"
    elif (base["expectancy"] or 0.0) <= 0 and (stress["expectancy"] or 0.0) <= 0:
        evidence_status = "NEGATIVE"
    elif (base["expectancy"] or 0.0) > 0:
        evidence_status = "WEAK_POSITIVE"
    else:
        evidence_status = "INCONCLUSIVE"
    failed = [name for name, passed in gates.items() if not passed]
    return {
        "qualification_status": qualification_status,
        "evidence_status": evidence_status,
        "qualified": qualification_status == "PASS",
        "reason": "failed gates: " + ", ".join(failed),
        "gates": gates,
        "median_fold_expectancy": median_expectancy,
    }


def _aggregate_candidate(
    candidate: str,
    records: list[dict[str, Any]],
    config: HardeningConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    walkforward = config.walkforward
    predictions = _concat([record["predictions"] for record in records])
    times = _times(predictions, "feature_time")
    if len(times) != len(np.unique(times)):
        raise ValueError(f"{candidate} has duplicate hardened OOS rows")
    actual = _floats(predictions, TARGET_COLUMN)
    predicted = _floats(predictions, "calibrated_prediction")
    fixed: dict[str, Any] = {}
    adaptive: dict[str, Any] = {}
    fixed_tables: dict[str, pa.Table] = {}
    adaptive_tables: dict[str, pa.Table] = {}
    for multiplier in walkforward.cost_multipliers:
        key = str(multiplier)
        fixed_table = _concat([record["fixed_trades"][key] for record in records])
        adaptive_table = _concat([record["adaptive_trades"][key] for record in records])
        fixed_tables[key], adaptive_tables[key] = fixed_table, adaptive_table
        fixed[key] = economic_metrics(
            fixed_table,
            opportunity_count=predictions.num_rows,
            minimum_reliable_trade_count=walkforward.qualification.minimum_total_trades,
        ) | {
            "stress_type": FIXED_POLICY_COST_STRESS,
            "cost_multiplier": multiplier,
            "trade_identity_hash": trade_identity_hash(fixed_table),
        }
        adaptive[key] = economic_metrics(
            adaptive_table,
            opportunity_count=predictions.num_rows,
            minimum_reliable_trade_count=walkforward.qualification.minimum_total_trades,
        ) | {
            "stress_type": ADAPTIVE_POLICY_COST_STRESS,
            "cost_multiplier": multiplier,
            "trade_identity_hash": trade_identity_hash(adaptive_table),
        }
    fixed_hashes = {value["trade_identity_hash"] for value in fixed.values()}
    if len(fixed_hashes) != 1:
        raise AssertionError("pooled fixed-policy trade identity changed across costs")
    base_trades = fixed_tables["1.0"]
    grouped = _group_trade_metrics(base_trades)
    fold_rows: list[dict[str, Any]] = []
    for record in records:
        backtest = record["backtest"]
        base = backtest["fixed_policy_cost_stress"]["1.0"]
        predictive = backtest["test_predictive_calibrated"]
        fold_rows.append(
            {
                "candidate": candidate,
                "fold_id": backtest["fold_id"],
                "pearson_ic": predictive["pearson_ic"],
                "directional_accuracy": predictive["directional_accuracy"],
                "trade_count": base["trade_count"],
                "base_expectancy": base["expectancy"],
                "base_net_return": base["total_net_return"],
                "statistically_reliable": base["statistically_reliable"],
                "reliability_reason": base["reliability_reason"],
            }
        )
    aggregate = {
        "candidate": candidate,
        "fold_count": len(records),
        "reliable_fold_count": sum(row["statistically_reliable"] for row in fold_rows),
        "zero_trade_fold_count": sum(row["trade_count"] == 0 for row in fold_rows),
        "predictive": regression_metrics(actual, predicted),
        "predictive_by_year": _prediction_year_metrics(predictions),
        "predictive_bootstrap": _block_bootstrap_predictive(
            actual,
            predicted,
            samples=walkforward.bootstrap.samples,
            block_rows=walkforward.bootstrap.block_rows,
            confidence=walkforward.bootstrap.confidence,
            seed=walkforward.seed,
        ),
        "fixed_policy_cost_stress": fixed,
        "adaptive_policy_cost_stress": adaptive,
        "fixed_policy_trade_invariant": {
            "satisfied": True,
            "trade_identity_hash": next(iter(fixed_hashes)),
        },
        "economic_bootstrap": _economic_bootstrap(
            base_trades,
            samples=walkforward.bootstrap.samples,
            confidence=walkforward.bootstrap.confidence,
            seed=walkforward.seed,
        ),
        "folds": fold_rows,
        "calibration_history": [record["calibration"] for record in records],
        "threshold_history": [record["threshold"]["policy"] for record in records],
        "trade_concentration": _trade_concentration(base_trades),
        "diagnostics": grouped,
        "top_fold_positive_pnl_share": _positive_fold_share(records),
        "top_year_positive_pnl_share": _top_positive_group_share(grouped["year"]),
        "top_regime_positive_pnl_share": _top_positive_group_share(grouped["regime"]),
    }
    aggregate["qualification"] = _qualification(aggregate, config)
    aggregate["_predictions"] = predictions
    aggregate["_fixed_trades"] = fixed_tables
    aggregate["_adaptive_trades"] = adaptive_tables
    return aggregate, fold_rows


def _strip_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def _load_inputs(
    config: HardeningConfig,
) -> tuple[pa.Table | None, pa.Table | None, str | None, str | None]:
    walkforward = config.walkforward
    funding = None
    funding_version = None
    if walkforward.funding_manifest is not None:
        funding, metadata = read_market_dataset(
            walkforward.funding_manifest, MarketDataKind.FUNDING
        )
        funding_version = metadata["dataset_version"]
    execution = None
    execution_version = None
    if walkforward.execution_1m_silver_manifest is not None:
        execution, metadata, _ = _load_silver(
            DatasetBuildConfig(
                silver_manifest=walkforward.execution_1m_silver_manifest,
                symbol="BTCUSDT",
                interval="1m",
            )
        )
        execution_version = metadata["silver_dataset_version"]
    return funding, execution, funding_version, execution_version


def run_hardened_walk_forward(
    config: HardeningConfig,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """Re-run Phase 5 post-processing from immutable v1 models and TEST predictions."""

    if config.protocol_version != HARDENING_VERSION:
        raise ValueError("unsupported hardening protocol version")
    walkforward = config.walkforward
    source_summary_path = config.source_summary.resolve()
    source_summary = read_manifest(source_summary_path)
    if source_summary is None or source_summary.get("status") != "complete":
        raise ValueError("a complete historical Phase 5 summary is required")
    if source_summary.get("version") != "1.0.0":
        raise ValueError("Phase 5.1 hardening requires an immutable v1.0.0 source run")
    if source_summary.get("family") != walkforward.family:
        raise ValueError("source summary family differs from hardening configuration")
    if tuple(source_summary["candidates"]) != walkforward.candidates:
        raise ValueError("source candidates differ from frozen hardening candidates")
    if source_summary.get("prospective_holdout_used"):
        raise ValueError("historical source reports prospective holdout contamination")
    if (
        source_summary["prospective_holdout_start"]
        != walkforward.prospective_holdout_start.isoformat()
    ):
        raise ValueError("prospective holdout boundary cannot change during hardening")
    gold, gold_manifest = read_gold_v2_1(walkforward.dataset_manifest)
    if gold_manifest["sha256"] != source_summary["identity"]["dataset_sha256"]:
        raise ValueError("Gold lineage differs from historical Phase 5 source")
    holdout_us = int(walkforward.prospective_holdout_start.timestamp() * 1_000_000)
    development_mask = _times(gold, "feature_time") < holdout_us
    gold = gold.filter(pa.array(development_mask))
    if gold.num_rows == 0 or np.any(_times(gold, "feature_time") >= holdout_us):
        raise AssertionError("development Gold violates the prospective holdout lock")
    identity = {
        "version": HARDENING_VERSION,
        "result_version": RESULT_VERSION,
        "configuration": config.model_dump(mode="json"),
        "source_summary_sha256": file_sha256(source_summary_path),
        "dataset_sha256": gold_manifest["sha256"],
        "models_retrained": False,
    }
    run_id = f"wf-hardened-{walkforward.name}-{_hash(identity)}"
    run_directory = config.artifact_root.resolve() / run_id
    summary_path = run_directory / "walkforward_hardened_summary.json"
    existing = read_manifest(summary_path)
    if resume and existing is not None:
        if existing.get("identity_hash") != _hash(identity):
            raise ValueError("completed hardened run identity differs")
        return existing
    if summary_path.exists():
        raise FileExistsError(f"refusing to overwrite hardened run: {run_directory}")
    plans = tuple(_fold_plan(item) for item in source_summary["walk_forward_design"]["folds"])
    funding, execution, funding_version, execution_version = _load_inputs(config)
    source_run = source_summary_path.parent
    schemas = _candidate_columns(walkforward)
    candidate_records = {candidate: [] for candidate in walkforward.candidates}
    for plan in plans:
        for candidate, columns in schemas.items():
            candidate_records[candidate].append(
                _harden_fold(
                    gold=gold,
                    plan=plan,
                    candidate=candidate,
                    columns=columns,
                    config=config,
                    source_run=source_run,
                    run_directory=run_directory,
                    funding=funding,
                    execution_1m=execution,
                    resume=resume,
                )
            )
    aggregates: dict[str, dict[str, Any]] = {}
    fold_rows: list[dict[str, Any]] = []
    all_predictions: list[pa.Table] = []
    all_fixed_base: list[pa.Table] = []
    all_adaptive_base: list[pa.Table] = []
    for candidate in walkforward.candidates:
        aggregate, rows = _aggregate_candidate(candidate, candidate_records[candidate], config)
        aggregates[candidate] = aggregate
        fold_rows.extend(rows)
        all_predictions.append(aggregate["_predictions"])
        all_fixed_base.append(aggregate["_fixed_trades"]["1.0"])
        all_adaptive_base.append(aggregate["_adaptive_trades"]["1.0"])
    left, right = (aggregates[name] for name in walkforward.candidates)
    comparison = {
        "left": walkforward.candidates[0],
        "right": walkforward.candidates[1],
        "matched_test_feature_times": np.array_equal(
            _times(left["_predictions"], "feature_time"),
            _times(right["_predictions"], "feature_time"),
        ),
        "pearson_ic_delta_right_minus_left": right["predictive"]["pearson_ic"]
        - left["predictive"]["pearson_ic"],
        "base_expectancy_delta_right_minus_left": (
            (right["fixed_policy_cost_stress"]["1.0"]["expectancy"] or 0.0)
            - (left["fixed_policy_cost_stress"]["1.0"]["expectancy"] or 0.0)
        ),
        "evidence_status": "INCONCLUSIVE",
    }
    qualified = [
        name
        for name, aggregate in aggregates.items()
        if aggregate["qualification"]["qualification_status"] == "PASS"
    ]
    champion = (
        max(
            qualified,
            key=lambda name: aggregates[name]["fixed_policy_cost_stress"]["1.0"]["expectancy"],
        )
        if qualified
        else None
    )
    max_feature_time = max(
        datetime.fromisoformat(record["manifest"]["max_feature_time_used"])
        for records in candidate_records.values()
        for record in records
    )
    if max_feature_time >= walkforward.prospective_holdout_start:
        raise AssertionError("hardened run used the prospective holdout")
    run_directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "oos_predictions": "oos_predictions.parquet",
        "fixed_policy_base_trades": "fixed_policy_base_trades.parquet",
        "adaptive_policy_base_trades": "adaptive_policy_base_trades.parquet",
        "fold_metrics": "fold_metrics.parquet",
    }
    pq.write_table(
        _concat(all_predictions), run_directory / outputs["oos_predictions"], compression="zstd"
    )
    pq.write_table(
        _concat(all_fixed_base),
        run_directory / outputs["fixed_policy_base_trades"],
        compression="zstd",
    )
    pq.write_table(
        _concat(all_adaptive_base),
        run_directory / outputs["adaptive_policy_base_trades"],
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(fold_rows),
        run_directory / outputs["fold_metrics"],
        compression="zstd",
    )
    summary = {
        "run_id": run_id,
        "status": "complete",
        "phase": "5 Hardening",
        "result_version": RESULT_VERSION,
        "result_type": "RETROSPECTIVE WALK-FORWARD OOS HARDENING",
        "created_at": datetime.now(UTC).isoformat(),
        "identity_hash": _hash(identity),
        "identity": identity,
        "family": walkforward.family,
        "source_run_id": source_summary["run_id"],
        "source_summary": str(source_summary_path),
        "models_retrained": False,
        "reuse": {
            "frozen_model_artifacts": True,
            "saved_test_raw_predictions": True,
            "calibration_predictions_recomputed_from_frozen_models": True,
        },
        "funding_dataset_version": funding_version,
        "execution_1m_dataset_version": execution_version,
        "prospective_holdout_start": walkforward.prospective_holdout_start.isoformat(),
        "max_feature_time_used": max_feature_time.isoformat(),
        "prospective_holdout_used": False,
        "outer_walk_forward_design": source_summary["walk_forward_design"],
        "calibration_protocol": {
            "calibration_a": "chronological first half; fit/select calibrator only",
            "calibration_b": "chronological second half; threshold selection only",
            "purge": "actual label_end_time before Cal-B start",
            "embargo_minutes": walkforward.schedule.embargo_minutes,
        },
        "cost_stress_primary": FIXED_POLICY_COST_STRESS,
        "cost_stress_secondary": ADAPTIVE_POLICY_COST_STRESS,
        "candidates": {
            candidate: _strip_runtime(aggregates[candidate]) for candidate in walkforward.candidates
        },
        "candidate_comparison": comparison,
        "champion_decision": (
            f"{champion} RESEARCH CHAMPION" if champion else "NO QUALIFIED MODEL"
        ),
        "machine_readable_outputs": outputs,
        "version": HARDENING_VERSION,
    }
    write_manifest(summary_path, summary)
    artifact_manifest = {
        "status": "complete",
        "run_id": run_id,
        "result_version": RESULT_VERSION,
        "files": {
            **{name: file_sha256(run_directory / name) for name in outputs.values()},
            summary_path.name: file_sha256(summary_path),
        },
        "prospective_holdout_used": False,
    }
    write_manifest(run_directory / "artifact_manifest.json", artifact_manifest)
    return summary


def compare_hardened_candidates(
    primary_summary_path: Path,
    derivatives_summary_path: Path,
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    primary = read_manifest(primary_summary_path.resolve())
    derivatives = read_manifest(derivatives_summary_path.resolve())
    if primary is None or derivatives is None:
        raise FileNotFoundError("both hardened summaries are required")
    if (
        primary.get("result_version") != RESULT_VERSION
        or derivatives.get("result_version") != RESULT_VERSION
    ):
        raise ValueError("candidate comparison requires walkforward_v1_1 results")
    if primary.get("prospective_holdout_used") or derivatives.get("prospective_holdout_used"):
        raise ValueError("prospective holdout contamination detected")
    candidates = {**primary["candidates"], **derivatives["candidates"]}
    qualified = [
        name
        for name, value in candidates.items()
        if value["qualification"]["qualification_status"] == "PASS"
    ]
    result = {
        "status": "complete",
        "result_version": RESULT_VERSION,
        "prospective_holdout_start": primary["prospective_holdout_start"],
        "max_feature_time_used": max(
            primary["max_feature_time_used"], derivatives["max_feature_time_used"]
        ),
        "prospective_holdout_used": False,
        "primary_run_id": primary["run_id"],
        "derivatives_run_id": derivatives["run_id"],
        "candidate_status": {name: value["qualification"] for name, value in candidates.items()},
        "L0_vs_L5": primary["candidate_comparison"],
        "D0_vs_D2": derivatives["candidate_comparison"],
        "champion_decision": "NO QUALIFIED MODEL" if not qualified else qualified[0],
    }
    if output is not None:
        write_manifest(output.resolve(), result)
    return result
