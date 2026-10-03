"""Isolated canonical one-spec planning; --execute requires separate owner authorization."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7.artifacts import CheckpointStore
from crypto_ai.phase7.config import load_phase7_config, stable_hash
from crypto_ai.phase7.gold_validation import locate_gold_manifest, validate_phase7_gold
from crypto_ai.phase7.phase7a import (
    CONFIG_PATH,
    enumerate_specs,
    pipeline_dispatcher,
    select_one_spec,
)
from crypto_ai.phase7.runtime import RuntimePaths
from crypto_ai.phase7.training import run_phase7_training


def benchmark_plan(config: Any, spec_id: str, output_root: Path) -> dict[str, Any]:
    if config.configuration_hash != "93f987736b1a79d26b773957":
        raise ValueError("benchmark requires the unchanged canonical Phase 7A configuration")
    spec = select_one_spec(config, spec_id)
    fold = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    runtime = RuntimePaths.resolve(config.paths)
    root = output_root.resolve()
    canonical = runtime.artifact_root / f"phase7a-core20-primary-{config.configuration_hash}"
    protected = (
        canonical,
        runtime.gold_root,
        runtime.cache_root,
        runtime.checkpoint_root,
        runtime.model_root / canonical.name,
        runtime.report_root / canonical.name,
    )
    if any(
        root == p.resolve() or root.is_relative_to(p.resolve()) or p.resolve().is_relative_to(root)
        for p in protected
    ):
        raise ValueError("benchmark output overlaps protected production/input roots")
    identity = "benchmark-only-" + stable_hash(
        {"config": config.configuration_hash, "spec": spec_id, "fold": fold.fold_id}
    )
    return {
        "status": "BENCHMARK_ONLY",
        "spec": asdict(spec),
        "spec_count": 1,
        "fold_id": fold.fold_id,
        "fold_count": 1,
        "canonical_fold_complete": False,
        "canonical_primary_run_complete": False,
        "run_root": str(root / identity),
        "configuration_hash": config.configuration_hash,
        **config.holdout_status_payload(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--spec-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--enumerate", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Future owner-authorized real-data run; default only prints a plan.",
    )
    args = parser.parse_args()
    config = load_phase7_config(args.config)
    dispatcher = pipeline_dispatcher()
    dispatcher.validate_phase7a_config(config, load_phase7_config(dispatcher.SOURCE_CONFIG_PATH))
    if args.enumerate:
        if args.execute or args.spec_id:
            parser.error("enumeration cannot execute/select a spec")
        result = enumerate_specs(config)
    else:
        if not args.spec_id or args.output_root is None:
            parser.error("--spec-id and isolated --output-root are required")
        result = benchmark_plan(config, args.spec_id, args.output_root)
        if args.execute:
            config.assert_cloud_execution_allowed()
            runtime = RuntimePaths.resolve(config.paths)
            root = runtime.artifact_root / dispatcher.run_identity(config)
            store = CheckpointStore(
                runtime.checkpoint_root,
                root.name,
                runtime.checkpoint_roots(),
                runtime.legacy_checkpoint_roots(),
            )
            for stage in ("registry", "universe", "data", "gold"):
                if not store.is_complete(stage):
                    raise RuntimeError(f"benchmark requires verified existing {stage} checkpoint")
            validate_phase7_gold(runtime.gold_root)
            import os

            from crypto_ai.phase7.preflight import build_preflight_report

            validation_path = os.environ.get("PHASE7_GOLD_VALIDATION_REPORT")
            preflight = build_preflight_report(
                args.config,
                gold_validation_report=(Path(validation_path) if validation_path else None),
            )
            if preflight["status"] != "PASS":
                raise RuntimeError(
                    "benchmark preflight failed: " + str(preflight["blocking_errors"])
                )
            registry, universe, policy, data = dispatcher.pipeline._load_stage_state(root)
            run_root = Path(result["run_root"])
            result = run_phase7_training(
                config,
                gold_manifest_path=locate_gold_manifest(runtime.gold_root),
                registry=registry,
                universe=universe,
                expansion_policy=policy,
                descriptors=dispatcher.pipeline._fold_descriptors(config, registry, data),
                unusable_segments=tuple(
                    dispatcher.CausalDataGap.model_validate(item)
                    for item in data.get("unusable_segments", [])
                ),
                checkpoint_store=CheckpointStore(run_root / "checkpoints", run_root.name),
                run_root=run_root,
                resume=True,
                benchmark_spec_id=args.spec_id,
                benchmark_fold_id=result["fold_id"],
            )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
