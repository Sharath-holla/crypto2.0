"""Completion requires canonical evidence, not process exit or a fabricated result."""

from __future__ import annotations

import json
from pathlib import Path

from .adapter import read_json
from .config import CONFIG_HASH, GOLD_ID, RUN_ID


def completion_receipt(adapter, scope, log: Path):
    kind = scope["request"]["job_type"]
    if kind in {"CRYPTO_FOLD_TRAIN", "CRYPTO_SPEC_TRAIN"}:
        if kind == "CRYPTO_FOLD_TRAIN":
            path = adapter.paths.historical / RUN_ID / "training_summary.json"
        else:
            from crypto_ai.phase7.benchmark_one_spec import benchmark_plan

            config, _, _ = adapter._canonical()
            plan = benchmark_plan(
                config, scope["request"]["spec_id"], adapter.paths.runtime / "benchmarks"
            )
            path = Path(plan["run_root"]) / "benchmark_summary.json"
        evidence = read_json(path)
        if not evidence or (
            evidence.get("prospective_holdout_status") != "LOCKED_UNUSED"
            or evidence.get("prospective_holdout_used") is not False
            or evidence.get("prospective_holdout_evaluation_authorized") is not False
        ):
            raise ValueError("Canonical completion summary is absent or inconsistent")
        if kind == "CRYPTO_SPEC_TRAIN":
            if (
                evidence.get("status") != "BENCHMARK_ONLY"
                or evidence.get("benchmark_completed_reports") != 1
            ):
                raise ValueError("One-spec benchmark completion not proven")
        elif evidence.get("completed_reports") != 48:
            raise ValueError("Complete canonical Fold-1 evidence not proven")
        from crypto_ai.phase7.artifacts import CheckpointStore
        from crypto_ai.phase7.recovery import inspect_spec_artifacts
        from crypto_ai.phase7.runtime import RuntimePaths
        from crypto_ai.phase7.training import experiment_output_root

        from .jobs import digest

        trusted = read_json(adapter.paths.verification / "aiventra-expected-model-identities.json")
        if not trusted or digest(trusted) != scope.get("expected_models_hash"):
            raise ValueError("Independent completion identities are absent or changed")
        config, _, specs = adapter._canonical()
        selected = [
            spec
            for spec in specs
            if kind == "CRYPTO_FOLD_TRAIN" or spec.name == scope["request"]["spec_id"]
        ]
        runtime_paths = RuntimePaths.resolve(config.paths)
        root = path.parent
        store = CheckpointStore(
            root / "checkpoints" if kind == "CRYPTO_SPEC_TRAIN" else adapter.paths.checkpoints,
            root.name,
            runtime_paths.checkpoint_roots(),
            runtime_paths.legacy_checkpoint_roots(),
        )
        for spec in selected:
            expected = trusted.get("identities", {}).get(spec.name)
            if not expected or (
                expected.get("experiment_id") != spec.name
                or expected.get("fold_id") != scope["fold_id"]
                or expected.get("gold_dataset_id") != GOLD_ID
                or expected.get("configuration_hash") != CONFIG_HASH
                or expected.get("training_source_identity")
                != scope["identity"]["scientific_source_identity"]
            ):
                raise ValueError("Independent model identity does not bind this scientific scope")
            relative = Path("core") / scope["fold_id"] / spec.name
            proof = inspect_spec_artifacts(
                model_path=experiment_output_root(root, kind="model", config=config)
                / relative
                / "model.joblib",
                report_path=experiment_output_root(root, kind="report", config=config)
                / relative
                / "report.json",
                checkpoint_store=store,
                stage="models/" + relative.as_posix(),
                expected_identity=expected,
            )
            if proof["state"] != "COMPLETE":
                raise ValueError("Independent canonical model completion proof failed")
        return {"source": str(path), "verified_specs": len(selected), "qualified_model": None}
    with log.open("rb") as stream:
        stream.seek(max(0, log.stat().st_size - 256 * 1024))
        tail = stream.read(256 * 1024).decode("utf-8", errors="replace")
    candidates = []
    for line in tail.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get("status") in {"PASS", "PREPARATION_COMPLETE"}:
                candidates.append(value)
        except json.JSONDecodeError:
            pass
    if not candidates:
        raise ValueError("Expected canonical completion receipt is absent")
    evidence = candidates[-1]
    if (
        kind == "CRYPTO_RUNTIME_HEALTH"
        and evidence.get("identity", {}).get("configuration_hash") != CONFIG_HASH
    ):
        raise ValueError("Runtime completion identity mismatch")
    if kind == "CRYPTO_LINEAGE_VALIDATE" and evidence.get("dataset_id") != GOLD_ID:
        raise ValueError("Gold completion identity mismatch")
    if kind in {"CRYPTO_CACHE_PREPARE", "CRYPTO_CACHE_VALIDATE"} and (
        evidence.get("identity", {}).get("configuration_hash") != CONFIG_HASH
        or evidence.get("identity", {}).get("gold_dataset_id") != GOLD_ID
        or evidence.get("fold_id") != scope["fold_id"]
    ):
        raise ValueError("Prepared-cache completion identity mismatch")
    return evidence
