"""Stage immutable smoke inputs locally; preserve hierarchy, hashes and historical checkpoints.

This performs no network transfer, cloud work, data repair, cache build, or model fit.
A copied historical checkpoint may still fail its original checksum contract. Report
that failure explicitly; never rewrite the checkpoint to make it pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import CheckpointStore
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.runtime import RuntimePaths

RUN = "phase7a-core20-primary-93f987736b1a79d26b773957"
STAGES = ("registry", "universe", "data", "gold")


def copy_verified(source: Path, destination: Path) -> dict:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"not a regular input: {source}")
    before = source.stat()
    digest = file_sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if file_sha256(destination) != digest:
            raise FileExistsError(f"different staged bytes: {destination}")
    else:
        # Copy bytes, never hard-link immutable recovered source to a writable stage.
        shutil.copyfile(source, destination)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or file_sha256(
        destination
    ) != digest:
        raise ValueError(f"copy changed input or destination bytes: {source}")
    return {"path": destination.as_posix(), "bytes": after.st_size, "sha256": digest}


def descriptor_transfer_paths(source: Path) -> set[str]:
    """Mirror Fold-0 TRAIN-only 1d descriptor inputs, including manifest lineage.

    The loader verifies the end-date partition before applying its half-open row
    predicate, so include that partition too. No future row enters descriptors.
    """
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.registry import read_registry

    config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    start = plan.train_end - timedelta(days=config.universe.selection_lookback_days)
    run_root = source / "phase7/artifacts" / RUN
    registry = read_registry(run_root / "registry/symbol_registry.json").by_symbol()
    data = json.loads((run_root / "data/data_manifest.json").read_text())
    selected: set[str] = set()

    def resolve(value: str) -> Path:
        prefix = "/home/nssharath123/crypto2.0/data/"
        if not value.startswith(prefix):
            raise ValueError("unsupported descriptor lineage root")
        path = (source / "data" / value[len(prefix) :]).resolve()
        if not path.is_relative_to(source / "data"):
            raise ValueError("descriptor lineage escape")
        return path

    def include(path: Path) -> None:
        selected.add(path.relative_to(source).as_posix())

    for symbol, value in data["candle_silver_manifests"]["1d"].items():
        record = registry[symbol]
        if record.causal_available_from >= plan.train_end or (
            record.available_until is not None and record.available_until <= start
        ):
            continue
        manifest_path = resolve(value)
        include(manifest_path)
        manifest = json.loads(manifest_path.read_text())
        bronze_path = resolve(manifest["source_manifest"])
        include(bronze_path)
        bronze = json.loads(bronze_path.read_text())
        lo = max(start, datetime.fromisoformat(bronze["start"].replace("Z", "+00:00")))
        hi = min(plan.train_end, datetime.fromisoformat(bronze["end"].replace("Z", "+00:00")))
        children = [manifest_path]
        if manifest.get("manifest_kind") == "phase7_causal_segment_group":
            children = [resolve(item["silver_manifest"]) for item in manifest["segments"]]
        for child in children:
            include(child)
            for item in json.loads(child.read_text()).get("output_files", []):
                path = child.parent.parent / item["file"]
                match = re.search(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)", item["file"])
                if match is None:
                    raise ValueError("descriptor partition has no canonical date")
                if lo.date() <= datetime.fromisoformat(match[1]).date() <= hi.date():
                    if file_sha256(path) != item["sha256"]:
                        raise ValueError("descriptor source partition checksum mismatch")
                    include(path)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-persistent", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--push-list", type=Path, default=Path("docs/reviews/evidence_closure/runpod_push_list.txt")
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_persistent.resolve()
    destination = args.destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("staging must be separate from immutable source")
    relative_paths = args.push_list.read_text().splitlines()
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("duplicate transfer path")
    for name in relative_paths:
        path = Path(name)
        if path.is_absolute() or any(
            p.startswith(".") or p == ".." or p.endswith(".partial") for p in path.parts
        ):
            raise ValueError("noncanonical or forensic transfer path")
    original_count = len(relative_paths)
    descriptor_paths = descriptor_transfer_paths(source)
    supplements = sorted(descriptor_paths - set(relative_paths))
    relative_paths += supplements
    relative_paths += [f"phase7/checkpoints/{RUN}/{stage}.json" for stage in STAGES]
    records = []
    for index, name in enumerate(relative_paths):
        row = copy_verified(source / name, destination / "crypto2-persistent" / name)
        row["path"] = str(Path(row["path"]).relative_to(destination))
        records.append(row)
        if index % 100 == 0:
            print(f"verified persistent inputs {index + 1}/{len(relative_paths)}", flush=True)
    sidecar_manifest = json.loads(args.sidecar.read_text())
    sidecar_paths = ["manifest.json", "SIDECAR_COMPLETE"] + [
        part["path"] for part in sidecar_manifest["partitions"]
    ]
    for name in sidecar_paths:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or any(p.startswith(".") for p in path.parts):
            raise ValueError("unsafe sidecar path")
        row = copy_verified(
            args.sidecar.parent / name, destination / "feature_context_sidecar_v3" / name
        )
        row["path"] = str(Path(row["path"]).relative_to(destination))
        records.append(row)
    persistent = destination / "crypto2-persistent"
    env = {
        "PHASE7_DATA_ROOT": str(persistent / "data"),
        "PHASE7_GOLD_ROOT": str(persistent / "data/gold/phase7a_core20_primary_v1"),
        "PHASE7_ARTIFACT_ROOT": str(persistent / "phase7/artifacts"),
        "PHASE7_CHECKPOINT_ROOT": str(persistent / "phase7/checkpoints"),
        "PHASE7_LEGACY_DATA_ROOT": "/home/nssharath123/crypto2.0/data",
        "PHASE7_LEGACY_GOLD_ROOT": (
            "/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1"
        ),
        "PHASE7_LEGACY_ARTIFACT_ROOT": "/home/nssharath123/crypto2.0/local_artifacts/phase7",
    }
    prior = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    failures = []
    try:
        config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
        runtime = RuntimePaths.resolve(config.paths)
        store = CheckpointStore(
            runtime.checkpoint_root,
            RUN,
            runtime.checkpoint_roots(),
            runtime.legacy_checkpoint_roots(),
        )
        stages = {stage: store.is_complete(stage) for stage in STAGES}
        for stage in STAGES:
            payload = json.loads(store.checkpoint_path(stage).read_text())
            for item in payload["files"]:
                resolved = store._resolve_file_record(stage, item)
                actual = file_sha256(resolved) if resolved.is_file() else None
                if actual != item["sha256"]:
                    failures.append(
                        {
                            "stage": stage,
                            "source_path": item.get("path"),
                            "resolved_path": str(resolved),
                            "expected_sha256": item["sha256"],
                            "actual_sha256": actual,
                        }
                    )
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    report = {
        "schema": "phase7_smoke_transfer_staging_v1",
        "copy_status": "PASS",
        "files": records,
        "file_count": len(records),
        "bytes": sum(r["bytes"] for r in records),
        "push_list_files": original_count,
        "descriptor_supplement_files": len(supplements),
        "descriptor_supplement_paths": supplements,
        "checkpoint_status": stages,
        "checkpoint_hash_failures": failures,
        "remapping_environment": env,
        "operating_system": os.uname().sysname,
        "linux_validation": "NOT_RUN",
        "remote_transfer": "NOT_RUN_NO_AUTHORIZED_ENDPOINT",
        "source_bytes_changed": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"files", "checkpoint_hash_failures", "remapping_environment"}
            },
            indent=2,
        )
    )
    print(f"historical checkpoint checksum failures: {len(failures)}", flush=True)
    return 0 if all(stages.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
