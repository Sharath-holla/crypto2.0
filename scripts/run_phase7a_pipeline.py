#!/usr/bin/env python3
"""Separate, fail-closed orchestration for Phase 7A CORE20 PRIMARY."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import ExitStack, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7 import pipeline, training
from crypto_ai.phase7.acquisition import plan_candle_download_request
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json, resource_snapshot
from crypto_ai.phase7.config import Phase7Config, load_phase7_config
from crypto_ai.phase7.discovery_checkpoint import DiscoverySymbolCheckpointStore
from crypto_ai.phase7.progress import ProgressReporter
from crypto_ai.phase7.registry import SymbolRegistry, read_registry, write_registry
from crypto_ai.phase7.segments import (
    AcquisitionOutcome,
    AcquisitionStatus,
    CandleFamilyAcquisition,
    CausalDataGap,
)
from crypto_ai.phase7.training import ExperimentSpec
from crypto_ai.phase7.universe import (
    read_expansion_policy,
    read_universe,
)

CONFIG_PATH = Path("configs/phase7/research_core20_primary_v1.toml")
SOURCE_CONFIG_PATH = Path("configs/phase7/research_v1.toml")
SOURCE_RUN_IDENTITY = "phase7-cc550337f1f4ee4654124bf6"
PHASE7A_SOURCE_FILE = "scripts/run_phase7a_pipeline.py"
STAGES = ("registry", "universe", "data", "gold", "train", "report")


class CanaryComplete(RuntimeError):
    pass


def validate_phase7a_config(config: Phase7Config, source: Phase7Config) -> None:
    actual = config.model_dump(mode="json")
    expected = source.model_dump(mode="json")
    if actual["name"] != "phase7a-core20-primary-v1":
        raise ValueError("Unexpected Phase 7A logical name")
    if Path(actual["paths"]["gold_root"]).as_posix() != "data/gold/phase7a_core20_primary_v1":
        raise ValueError("Unexpected Phase 7A Gold root")
    actual["name"] = expected["name"]
    actual["paths"]["gold_root"] = expected["paths"]["gold_root"]
    if actual != expected:
        raise ValueError(
            "Phase 7A config differs from canonical science outside its identity/Gold root"
        )
    if source.configuration_hash != "cc550337f1f4ee4654124bf6":
        raise ValueError("Canonical Phase 7 configuration identity changed")


def primary_specs(config: Phase7Config) -> tuple[ExperimentSpec, ...]:
    specs = tuple(
        spec for spec in training.phase7_experiment_specs(config) if spec.feature_group == "A6"
    )
    if len(specs) != 48:
        raise AssertionError("Phase 7A must derive exactly 48 primary A6 specifications")
    if any(spec.name.startswith(("feature-ablation-", "htf-control-")) for spec in specs):
        raise AssertionError("Deferred controls leaked into Phase 7A")
    return specs


def run_identity(config: Phase7Config) -> str:
    return f"phase7a-core20-primary-{config.configuration_hash}"


def _run_context(config: Phase7Config) -> tuple[str, Path, datetime]:
    identity = run_identity(config)
    root = config.paths.artifact_root.resolve() / identity
    path = root / "run.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("configuration_hash") != config.configuration_hash:
            raise ValueError("Phase 7A run/config identity mismatch")
        started_at = datetime.fromisoformat(payload["started_at"])
    else:
        started_at = datetime.now(UTC)
        atomic_json(
            path,
            {
                "run_identity": identity,
                "configuration_hash": config.configuration_hash,
                "phase": "7A",
                "profile": "CORE20_PRIMARY",
                "research_views": ["CORE"],
                "primary_spec_count": 48,
                "started_at": started_at.isoformat(),
                "resources": resource_snapshot(Path.cwd()),
                "research_cutoff": config.research_cutoff.isoformat(),
                **config.holdout_status_payload(),
            },
        )
    return identity, root, started_at.astimezone(UTC)


def _registry_stage(
    config: Phase7Config, source: Phase7Config, root: Path
) -> tuple[SymbolRegistry, list[Path]]:
    source_store = CheckpointStore(source.paths.checkpoint_root, SOURCE_RUN_IDENTITY)
    if not source_store.is_complete("registry"):
        raise RuntimeError("Canonical registry checkpoint is absent or invalid")
    source_path = (
        source.paths.artifact_root.resolve()
        / SOURCE_RUN_IDENTITY
        / "registry"
        / "symbol_registry.json"
    )
    registry = read_registry(source_path)
    destination = root / "registry"
    registry_path = write_registry(destination / "symbol_registry.json", registry)
    lineage = atomic_json(
        destination / "reuse_lineage.json",
        {
            "method": "immutable_checkpoint_verified_registry_reuse",
            "network_used": False,
            "source_run_identity": SOURCE_RUN_IDENTITY,
            "source_configuration_hash": source.configuration_hash,
            "source_registry": str(source_path.resolve()),
            "source_registry_sha256": file_sha256(source_path.resolve()),
            "registry_hash": registry.registry_hash,
        },
    )
    return registry, [registry_path, lineage]


def _reuse_discovery(
    source: Phase7Config,
    registry: SymbolRegistry,
    progress: object = None,
) -> CandleFamilyAcquisition:
    source_registry = read_registry(
        source.paths.artifact_root.resolve()
        / SOURCE_RUN_IDENTITY
        / "registry"
        / "symbol_registry.json"
    )
    if source_registry.registry_hash != registry.registry_hash:
        raise ValueError("Registry does not match canonical discovery lineage")
    store = DiscoverySymbolCheckpointStore(
        source, source_registry, run_identity=SOURCE_RUN_IDENTITY
    )
    end = source.research_cutoff
    start = source.universe.core_selection_cutoff - timedelta(
        days=source.universe.selection_lookback_days
    )
    candidates = tuple(
        record
        for record in source_registry.records
        if record.quote_asset == source.universe.quote_asset
        and record.contract_type == source.universe.contract_type
        and set(source.universe.required_intervals).issubset(record.available_intervals)
        and record.causal_available_from
        < end - timedelta(days=source.universe.minimum_history_days)
    )
    if len(candidates) != 507:
        raise RuntimeError(f"Canonical discovery candidate count is {len(candidates)}, not 507")
    outcomes: list[AcquisitionOutcome] = []
    for position, record in enumerate(candidates, start=1):
        request = plan_candle_download_request(record, interval="1d", start=start, end=end)
        if request is None:
            outcome = AcquisitionOutcome(
                symbol=record.symbol,
                interval="1d",
                status=AcquisitionStatus.LIFECYCLE_ABSENCE,
                reason="no causal source overlap with requested range",
            )
            hit = False
        else:
            outcome = store.load(
                record,
                interval="1d",
                request_start=request.start_utc,
                request_end=request.end_utc,
            )
            if outcome is None:
                raise RuntimeError(
                    f"No network-free canonical discovery checkpoint for {record.symbol}"
                )
            hit = True
        outcomes.append(outcome)
        if callable(progress):
            progress(
                position,
                len(candidates),
                record.symbol,
                "1d",
                outcome.status.value,
                hit,
            )
    return CandleFamilyAcquisition(tuple(outcomes))


def _training_patches(config: Phase7Config) -> ExitStack:
    original_specs = training.phase7_experiment_specs
    specs = tuple(spec for spec in original_specs(config) if spec.feature_group == "A6")
    if specs != primary_specs(config):
        raise AssertionError("Primary specification derivation is unstable")
    stack = ExitStack()
    stack.enter_context(patch.object(training, "RESEARCH_VIEWS", ("CORE",)))
    stack.enter_context(patch.object(training, "phase7_experiment_specs", lambda _: specs))
    source_files = training.TRAINING_CRITICAL_SOURCE_FILES
    if PHASE7A_SOURCE_FILE not in source_files:
        source_files = (*source_files, PHASE7A_SOURCE_FILE)
    stack.enter_context(patch.object(training, "TRAINING_CRITICAL_SOURCE_FILES", source_files))
    return stack


def _report_stage(config: Phase7Config, root: Path) -> tuple[dict[str, object], list[Path]]:
    original_atomic = pipeline.atomic_json

    def phase7a_atomic(path: Path, payload: dict[str, object], **kwargs: object) -> Path:
        if path.name == "phase7_report.json":
            payload = dict(payload)
            payload["status"] = "PHASE7A_CORE20_PRIMARY_COMPLETE"
            payload["research_views"] = ["CORE"]
            payload["primary_spec_count"] = 48
            payload["deferred_feature_ablation_count"] = 6
            payload["deferred_htf_control_count"] = 4
        return original_atomic(path, payload, **kwargs)

    with patch.object(pipeline, "atomic_json", phase7a_atomic):
        return pipeline._report_stage(config, root)


def run_stage(config: Phase7Config, stage: str, *, resume: bool, canary: bool) -> dict[str, object]:
    source = load_phase7_config(SOURCE_CONFIG_PATH)
    validate_phase7a_config(config, source)
    primary_specs(config)
    identity, root, observed_at = _run_context(config)
    reporter = ProgressReporter(
        config,
        run_identity=identity,
        run_started_at=observed_at,
        repository_root=Path.cwd(),
    )
    checkpoints = CheckpointStore(config.paths.checkpoint_root, identity)
    if resume and checkpoints.is_complete(stage):
        return {"status": "REUSED", "stage": stage, "run_identity": identity}
    missing = [name for name in STAGES[: STAGES.index(stage)] if not checkpoints.is_complete(name)]
    if missing:
        raise RuntimeError(f"Stage {stage} requires completed dependencies: {missing}")
    reporter.stage_started(stage, 1, 1)
    if stage == "registry":
        _, files = _registry_stage(config, source, root)
        metadata: dict[str, object] = {"network": "none_immutable_lineage_reuse"}
    elif stage == "universe":
        registry = read_registry(root / "registry" / "symbol_registry.json")
        original_selection = pipeline.select_fold_active_universe

        def core_selection(*args: object, **kwargs: object) -> object:
            kwargs["research_view"] = "CORE"
            return original_selection(*args, **kwargs)

        with (
            patch.object(
                pipeline,
                "acquire_discovery_daily",
                lambda _config, registry, progress=None, **_kwargs: _reuse_discovery(
                    source, registry, progress
                ),
            ),
            patch.object(pipeline, "select_fold_active_universe", core_selection),
        ):
            universe, policy, _, symbols, files = pipeline._universe_stage(
                config, root, registry, identity, resume, reporter
            )
        discovery_lineage = atomic_json(
            root / "universe" / "discovery_reuse_lineage.json",
            {
                "method": "network_free_immutable_per_symbol_checkpoint_reuse",
                "source_run_identity": SOURCE_RUN_IDENTITY,
                "source_configuration_hash": source.configuration_hash,
                "candidate_count": 507,
                "network_used": False,
            },
        )
        files.append(discovery_lineage)
        if len(symbols) != 20 or len(set(symbols)) != 20:
            raise RuntimeError("Phase 7A acquisition membership is not exactly Core20")
        metadata = {
            "core_universe_hash": universe.universe_hash,
            "expansion_policy_hash": policy.policy_hash,
            "acquisition_symbol_count": len(symbols),
            "research_views": ["CORE"],
            "discovery_reuse": SOURCE_RUN_IDENTITY,
        }
    elif stage == "data":
        registry = read_registry(root / "registry" / "symbol_registry.json")
        universe = read_universe(root / "universe" / "core_universe.json")
        policy = read_expansion_policy(root / "universe" / "expansion_policy.json")
        membership = json.loads(
            (root / "universe" / "fold_memberships.json").read_text(encoding="utf-8")
        )
        symbols = tuple(membership["acquisition_symbols"])
        if len(symbols) != 20:
            raise RuntimeError("Full-resolution acquisition escaped Core20")
        data, files = pipeline._data_stage(
            config, root, registry, universe, policy, symbols, reporter
        )
        metadata = {"symbol_count": 20, "research_universe_hash": data["research_universe_hash"]}
    elif stage == "gold":
        registry, universe, policy, data = pipeline._load_stage_state(root)
        gold, files = pipeline._gold_stage(config, root, registry, universe, policy, data, reporter)
        metadata = gold
    elif stage == "train":
        registry, universe, policy, data = pipeline._load_stage_state(root)
        gold = json.loads((root / "gold" / "result.json").read_text(encoding="utf-8"))
        descriptors = pipeline._fold_descriptors(config, registry, data)
        descriptor_path = atomic_json(
            root / "fold_descriptors.json",
            {"descriptors": [item.model_dump(mode="json") for item in descriptors]},
        )
        started = time.monotonic()
        with _training_patches(config):
            if canary:
                canary_started_path = root / "canary_started.json"
                if canary_started_path.exists():
                    canary_started = datetime.fromisoformat(
                        json.loads(canary_started_path.read_text(encoding="utf-8"))["started_at"]
                    )
                else:
                    canary_started = datetime.now(UTC)
                    atomic_json(
                        canary_started_path,
                        {
                            "status": "STARTED_NOT_COMPLETE",
                            "started_at": canary_started.isoformat(),
                            "train_stage_checkpoint_complete": False,
                            **config.holdout_status_payload(),
                        },
                    )
                original_completed = reporter.fold_completed

                def stop_after_fold(*args: object, **kwargs: object) -> None:
                    original_completed(*args, **kwargs)
                    raise CanaryComplete

                with (
                    patch.object(reporter, "fold_completed", stop_after_fold),
                    suppress(CanaryComplete),
                ):
                    training.run_phase7_training(
                        config,
                        gold_manifest_path=Path(gold["manifest"]),
                        registry=registry,
                        universe=universe,
                        expansion_policy=policy,
                        descriptors=descriptors,
                        unusable_segments=tuple(
                            CausalDataGap.model_validate(item)
                            for item in data.get("unusable_segments", [])
                        ),
                        checkpoint_store=checkpoints,
                        run_root=root,
                        resume=resume,
                        reporter=reporter,
                    )
                reports = list((root / "models" / "core").glob("*/*/report.json"))
                if len(reports) != 48:
                    raise RuntimeError(f"Fold 1 canary checkpoint count is {len(reports)}, not 48")
                canary_path = atomic_json(
                    root / "canary_summary.json",
                    {
                        "status": "CANARY_COMPLETE",
                        "folds_attempted": 1,
                        "fold_count": len(
                            plan_folds(
                                config.data_start,
                                config.research_cutoff,
                                config.prospective_holdout_start,
                                config.schedule,
                            )
                        ),
                        "fold_timings": [
                            {
                                "fold_id": reports[0].parents[1].name,
                                "wall_seconds": max(
                                    time.monotonic() - started,
                                    (datetime.now(UTC) - canary_started).total_seconds(),
                                ),
                            }
                        ],
                        "report_count": len(reports),
                        "training_checkpoint_complete": False,
                        **config.holdout_status_payload(),
                    },
                )
                reporter.emit(
                    "phase7a_fold1_canary_complete",
                    stage="training",
                    fields={
                        "status": "CANARY_COMPLETE",
                        "reports": 48,
                        "train_stage_checkpoint_complete": False,
                    },
                    human="PHASE 7A — FOLD 1 CANARY CHECKPOINTED; TRAIN STAGE REMAINS INCOMPLETE",
                )
                return {
                    "status": "CANARY_COMPLETE",
                    "run_identity": identity,
                    "summary": str(canary_path),
                }
            summary = training.run_phase7_training(
                config,
                gold_manifest_path=Path(gold["manifest"]),
                registry=registry,
                universe=universe,
                expansion_policy=policy,
                descriptors=descriptors,
                unusable_segments=tuple(
                    CausalDataGap.model_validate(item) for item in data.get("unusable_segments", [])
                ),
                checkpoint_store=checkpoints,
                run_root=root,
                resume=resume,
                reporter=reporter,
            )
        files = [descriptor_path, root / "training_summary.json"]
        files.extend(root.glob("models/**/*.joblib"))
        files.extend(root.glob("models/**/report.json"))
        metadata = {
            "fold_count": summary["fold_count"],
            "completed_reports": summary["completed_reports"],
            "ineligible_reports": summary["ineligible_reports"],
            "primary_spec_count": 48,
            "research_views": ["CORE"],
        }
    else:
        report, files = _report_stage(config, root)
        metadata = {"scorecard_rows": len(report["scorecard"]), "research_views": ["CORE"]}
    checkpoints.complete(stage, list(files), metadata)
    reporter.stage_completed(stage, 1, 1, metadata=metadata)
    if stage == "report":
        summary = json.loads((root / "training_summary.json").read_text(encoding="utf-8"))
        reporter.final_summary(report, summary, report_path=root / "phase7_report.json")
    return {"status": "COMPLETE", "stage": stage, "run_identity": identity}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args()
    if args.canary and args.stage != "train":
        raise ValueError("--canary is valid only for the train stage")
    config = load_phase7_config(args.config)
    config.assert_cloud_execution_allowed()
    result = run_stage(config, args.stage, resume=args.resume, canary=args.canary)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
