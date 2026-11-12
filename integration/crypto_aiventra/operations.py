"""Trusted wrappers calling canonical science; no numerical reimplementation."""

from __future__ import annotations

import argparse
import json

from .adapter import Crypto2Adapter
from .config import RUN_ID, require_branch


def prepare_cache(adapter: Crypto2Adapter, spec_id: str, *, validate_only: bool = False):
    from crypto_ai.data.storage import file_sha256
    from crypto_ai.phase7 import training
    from crypto_ai.phase7.artifacts import CheckpointStore
    from crypto_ai.phase7.gold_validation import locate_gold_manifest
    from crypto_ai.phase7.phase7a import pipeline_dispatcher, select_one_spec
    from crypto_ai.phase7.prepared_cache import PreparedCacheMissError, PreparedDataCache
    from crypto_ai.phase7.run_lease import owned_run
    from crypto_ai.phase7.runtime import RuntimePaths
    from crypto_ai.phase7.segments import CausalDataGap
    from crypto_ai.phase7.universe import select_fold_active_universe

    config, folds, _ = adapter._canonical()
    config.assert_cloud_execution_allowed()
    runtime = RuntimePaths.resolve(config.paths)
    store = CheckpointStore(
        runtime.checkpoint_root,
        RUN_ID,
        runtime.checkpoint_roots(),
        runtime.legacy_checkpoint_roots(),
    )
    for stage in ("registry", "universe", "data", "gold"):
        if not store.is_complete(stage):
            raise ValueError(f"Canonical {stage} checkpoint is not valid; no recomputation")
    dispatcher = pipeline_dispatcher()
    root = runtime.artifact_root / RUN_ID
    source = training.scientific_source_identity()
    with owned_run(root, RUN_ID, source, mode="production"):
        registry, universe, policy, data = dispatcher.pipeline._load_stage_state(root)
        descriptors = dispatcher.pipeline._fold_descriptors(config, registry, data)
        gaps = tuple(
            CausalDataGap.model_validate(item) for item in data.get("unusable_segments", [])
        )
        spec, plan = select_one_spec(config, spec_id), folds[0]
        manifest_path = locate_gold_manifest(runtime.gold_root)
        manifest = training._load_gold_manifest(manifest_path)
        columns = tuple(manifest["feature_groups"]["A6"])
        membership = select_fold_active_universe(
            registry,
            descriptors,
            fold_id=plan.fold_id,
            train_end=plan.train_end,
            core_universe=universe,
            expansion_policy=policy,
            config=config.universe,
            research_view="CORE",
            unusable_segments=gaps,
            required_start=plan.train_start,
            required_end=plan.test_end,
        )
        identity = training._prepared_cache_identity(
            config=config,
            manifest=manifest,
            gold_manifest_sha256=file_sha256(manifest_path),
            source_identity=source,
            fold_id=plan.fold_id,
            research_view="CORE",
            fold_membership_hash=membership.membership_hash,
            universe_hash=universe.universe_hash,
            registry_hash=registry.registry_hash,
            spec=spec,
            feature_columns=columns,
            descriptor_identity=training.causal_descriptor_identity(descriptors, plan.train_end),
        )
        cache = PreparedDataCache(runtime.cache_root, "read_only" if validate_only else "auto")
        try:
            loaded = cache.load(identity, plan)
        except PreparedCacheMissError:
            if validate_only:
                raise
            rows = training._load_fold_rows(manifest, plan, spec.horizon_minutes)
            fold = training.slice_multiasset_fold(
                rows,
                plan,
                registry=registry,
                universe=universe,
                expansion_policy=policy,
                research_view="CORE",
                descriptors=descriptors,
                universe_config=config.universe,
                schedule=config.schedule,
                holdout_start=config.prospective_holdout_start,
                cluster_count=config.models.cluster_count,
                seed=config.models.seed,
                unusable_segments=gaps,
            )
            prepared = training._prepare_training_segments(
                fold, columns, training._prediction_target(spec)
            )
            cache.write(identity, fold, prepared)
            loaded = cache.open_published(identity, plan)
        return {
            "status": "PREPARATION_COMPLETE",
            "cache_id": loaded.cache_id,
            "fold_id": plan.fold_id,
            "identity": identity,
            "model_fit": False,
            "test_evaluated": False,
        }


def run(operation: str, spec_id: str):
    adapter = Crypto2Adapter()
    require_branch(adapter.paths.repo)
    if operation == "CRYPTO_RUNTIME_HEALTH":
        return {
            "status": "PASS",
            "identity": adapter.get_project_identity(),
            "resources": adapter.get_resource_usage(),
        }
    if operation == "CRYPTO_RECOVERY_INSPECT":
        from crypto_ai.phase7.run_lease import owner_liveness

        from .adapter import read_json

        lease = read_json(adapter.paths.historical / RUN_ID / ".phase7-run-lease.json")
        return {
            "status": "PASS",
            "lease": lease,
            "liveness": owner_liveness(lease) if lease else "NO_RETAINED_OWNER",
            "training": adapter.get_training_status(),
            "automatic_resume": False,
        }
    if operation == "CRYPTO_REPORT_GENERATE":
        return {"status": "PASS", "snapshot": adapter.snapshot(), "qualification": "NOT_EVALUATED"}
    if operation in {"CRYPTO_CACHE_PREPARE", "CRYPTO_CACHE_VALIDATE"}:
        return prepare_cache(adapter, spec_id, validate_only=operation == "CRYPTO_CACHE_VALIDATE")
    if operation == "CRYPTO_LINEAGE_VALIDATE":
        from crypto_ai.phase7.gold_validation import validate_phase7_gold

        return {
            **validate_phase7_gold(adapter.paths.gold),
            "validation_scope": "GOLD_ONLY_CANONICAL_VALIDATOR",
            "full_lineage_closure": "NOT_VERIFIED",
        }
    raise PermissionError("This operation has no approved canonical execution wrapper")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--spec-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.operation, args.spec_id), sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
