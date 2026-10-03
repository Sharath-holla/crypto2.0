"""Read-only artifact classification and explicit, lease-protected reconciliation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json, checkpoint_metadata_compatible
from crypto_ai.phase7.config import stable_hash
from crypto_ai.phase7.run_lease import owned_run

REQUIRED_INPUT_IDENTITY = {
    "experiment_id",
    "fold_id",
    "gold_dataset_id",
    "gold_manifest_sha256",
    "model_backend_semantics",
    "training_source_identity",
    "configuration_hash",
}


def model_receipt_path(model_path: Path) -> Path:
    return model_path.with_name("model_receipt.json")


def publish_model_receipt(model_path: Path, identity: dict[str, Any], publication: dict[str, Any]):
    payload = {
        "publication_state": "MODEL_PUBLISHED",
        "publication": publication,
        "checkpoint_identity": identity,
        "model_artifact_sha256": file_sha256(model_path),
    }
    payload["receipt_identity"] = stable_hash(payload, length=64)
    return atomic_json(model_receipt_path(model_path), payload)


def validate_model_receipt(model_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    path = model_receipt_path(model_path)
    if file_sha256(path) != report.get("model_receipt_sha256"):
        raise ValueError("model receipt checksum mismatch")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_identity", None)
    if claimed != stable_hash(unsigned, length=64):
        raise ValueError("model receipt content identity mismatch")
    if (
        receipt.get("model_artifact_sha256") != file_sha256(model_path)
        or receipt.get("checkpoint_identity") != report.get("checkpoint_identity")
        or receipt.get("publication") != report.get("publication")
    ):
        raise ValueError("model receipt/report/scientific identity mismatch")
    return receipt


def inspect_spec_artifacts(
    *,
    model_path: Path,
    report_path: Path,
    checkpoint_store: CheckpointStore,
    stage: str,
    expected_identity: dict[str, Any],
) -> dict[str, Any]:
    """Never fit, read Gold, invent metrics or deserialize an unbound model."""
    from crypto_ai.phase7.models import load_model
    from crypto_ai.phase7.training import (
        _validate_complete_orphan_report,
        _validate_model_file_binding,
    )

    checkpoint = checkpoint_store.checkpoint_path(stage)
    receipt_path = model_receipt_path(model_path)
    inventory = {
        "model": model_path.is_file(),
        "report": report_path.is_file(),
        "receipt": receipt_path.is_file(),
        "checkpoint": checkpoint.is_file(),
    }

    def result(state: str, action: str, reason: str = ""):
        return {
            "state": state,
            "recommended_action": action,
            "reason": reason,
            "inventory": inventory,
            "run_identity": checkpoint_store.run_identity,
            "stage": stage,
            "scanned_at": datetime.now(UTC).isoformat(),
        }

    if not REQUIRED_INPUT_IDENTITY.issubset(expected_identity):
        return result(
            "INCONSISTENT", "REQUIRE_TRUSTED_EXPECTED_IDENTITY", "missing identity fields"
        )
    if any(path.is_symlink() for path in (model_path, report_path, receipt_path, checkpoint)):
        return result("INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "aliased publication artifact")
    if not any(inventory.values()):
        return result("NONE", "NORMAL_AUTHORIZED_EXECUTION_ONLY")
    if inventory["model"] and not inventory["report"] and not inventory["checkpoint"]:
        if inventory["receipt"]:
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                unsigned = dict(receipt)
                claimed = unsigned.pop("receipt_identity", None)
                if claimed != stable_hash(unsigned, length=64) or receipt.get(
                    "model_artifact_sha256"
                ) != file_sha256(model_path):
                    return result(
                        "CORRUPT", "PRESERVE_AND_INVESTIGATE", "invalid model receipt/hash"
                    )
                if (
                    receipt.get("checkpoint_identity") != expected_identity
                    or receipt.get("publication", {}).get("run_identity")
                    != checkpoint_store.run_identity
                ):
                    return result(
                        "INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "wrong model identity"
                    )
            except Exception:
                return result("CORRUPT", "PRESERVE_AND_INVESTIGATE", "unreadable model receipt")
        return result(
            "MODEL_ONLY",
            "PRESERVE_OPERATOR_DECISION_REQUIRED",
            "no report/metrics; never reconstruct from missing evidence",
        )
    if not inventory["model"] or not inventory["report"]:
        return result("INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "incomplete artifact inventory")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        publication = report.get("publication", {})
        expected_mode = (
            "benchmark"
            if expected_identity.get("artifact_mode") == "BENCHMARK_ONLY"
            else "production"
        )
        if (
            report.get("status") != "COMPLETE"
            or not isinstance(report.get("checkpoint_identity"), dict)
            or not checkpoint_metadata_compatible(report["checkpoint_identity"], expected_identity)
            or report.get("spec", {}).get("name") != expected_identity["experiment_id"]
            or report.get("fold_id") != expected_identity["fold_id"]
            or report.get("publication", {}).get("run_identity") != checkpoint_store.run_identity
            or publication.get("mode") != expected_mode
            or publication.get("fold_id") != expected_identity["fold_id"]
            or publication.get("spec_id") != expected_identity["experiment_id"]
            or publication.get("state") != "MODEL_REPORT_PUBLICATION_V1"
            or report.get("test_used_for_selection") is not False
            or report.get("prospective_holdout_status") != "LOCKED_UNUSED"
            or report.get("prospective_holdout_used") is not False
            or report.get("prospective_holdout_evaluation_authorized") is not False
            or report.get("july_2026_used") is not False
        ):
            return result("INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "report identity mismatch")
        _validate_model_file_binding(report, model_path)
        validate_model_receipt(model_path, report)
        model = load_model(model_path)
        if model.metadata.get("scientific_input_identity") != report[
            "checkpoint_identity"
        ] or model.metadata.get("publication") != report.get("publication"):
            return result("INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "estimator identity mismatch")
        _validate_complete_orphan_report(report, model)
        if (
            model.metadata.get("compute_backend") != expected_identity["model_backend_semantics"]
            or model.architecture != report["spec"]["architecture"]
            or not all(
                isinstance(report.get(key), dict) and report[key]
                for key in ("test_metrics", "economic", "segment_rows")
            )
        ):
            return result(
                "INCONSISTENT",
                "PRESERVE_AND_INVESTIGATE",
                "completion evidence missing or backend mismatch",
            )
    except Exception:
        return result("CORRUPT", "PRESERVE_AND_INVESTIGATE", "invalid bound model/report evidence")
    if not inventory["checkpoint"]:
        return result("MODEL_REPORT", "EXPLICIT_CHECKPOINT_RECONCILIATION_AVAILABLE")
    try:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        if (
            payload.get("run_identity") != checkpoint_store.run_identity
            or payload.get("stage") != stage
            or not checkpoint_metadata_compatible(payload.get("metadata", {}), expected_identity)
        ):
            return result(
                "INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "checkpoint identity mismatch"
            )
        files = {checkpoint_store._resolve_file_record(stage, item) for item in payload["files"]}
        if files != {model_path.resolve(), report_path.resolve(), receipt_path.resolve()}:
            return result(
                "INCONSISTENT", "PRESERVE_AND_INVESTIGATE", "checkpoint inventory mismatch"
            )
        if not checkpoint_store.is_complete(stage, expected_metadata=expected_identity):
            return result("CORRUPT", "PRESERVE_AND_INVESTIGATE", "checkpoint integrity failure")
    except Exception:
        return result("CORRUPT", "PRESERVE_AND_INVESTIGATE", "unreadable checkpoint")
    return result("COMPLETE", "REUSE_VERIFIED_CHECKPOINT")


def reconcile_spec_checkpoint(*, run_root: Path, mode: str, **arguments: Any) -> dict[str, Any]:
    from crypto_ai.phase7.training import training_source_identity

    expected = arguments["expected_identity"]
    store = arguments["checkpoint_store"]
    if expected.get("training_source_identity") != training_source_identity():
        raise ValueError("reconciliation requires current reviewed scientific source identity")
    with owned_run(run_root, store.run_identity, expected["training_source_identity"], mode=mode):
        state = inspect_spec_artifacts(**arguments)
        if state["state"] == "COMPLETE":
            return state
        if state["state"] != "MODEL_REPORT":
            raise ValueError(f"cannot reconcile artifact state {state['state']}: {state['reason']}")
        model = arguments["model_path"]
        store.complete(
            arguments["stage"],
            [model, arguments["report_path"], model_receipt_path(model)],
            expected,
        )
        return inspect_spec_artifacts(**arguments)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument(
        "--expected-identity",
        type=Path,
        required=True,
        help="Independently trusted identity; never infer it from the orphan.",
    )
    parser.add_argument("--mode", choices=("production", "benchmark"), required=True)
    parser.add_argument("--reconcile-checkpoint", action="store_true")
    args = parser.parse_args()
    expected = json.loads(args.expected_identity.read_text(encoding="utf-8"))
    from crypto_ai.phase7.config import PathConfig
    from crypto_ai.phase7.runtime import RuntimePaths

    runtime = RuntimePaths.resolve(PathConfig())
    store = CheckpointStore(
        args.checkpoint_root,
        args.run_root.resolve().name,
        logical_roots=runtime.checkpoint_roots(),
        legacy_roots=runtime.legacy_checkpoint_roots(),
    )
    arguments = {
        "model_path": args.model,
        "report_path": args.report,
        "checkpoint_store": store,
        "stage": args.stage,
        "expected_identity": expected,
    }
    result = (
        reconcile_spec_checkpoint(run_root=args.run_root, mode=args.mode, **arguments)
        if args.reconcile_checkpoint
        else inspect_spec_artifacts(**arguments)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["state"] in {"CORRUPT", "INCONSISTENT"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
