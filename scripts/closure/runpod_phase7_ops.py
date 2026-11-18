"""Operator kit outside the frozen source. Default is a non-executing plan.

Never imports a mutable checkout: execution requires the manifest-bound Git-free export.
Cloud creation, cloud start, acquisition and research-grid commands are deliberately absent.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SPEC = "architecture-G0-A6-60m-raw"
FOLD = "fold-000-a0e9a4f72689"
RUN = "phase7a-core20-primary-93f987736b1a79d26b773957"
VOLUME = "kz9axr9t9v"
DATASET = "gold-phase7-0cbf2910e8d96c9d19826598"
KIT = Path(__file__).resolve().parents[2]
DOC = KIT / "docs/runpod"
STAGES = (
    "bootstrap",
    "verify-transfer",
    "preflight",
    "prepare",
    "reload",
    "memory-probe",
    "restore-cache",
    "train",
    "resume",
    "collect",
)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() != timedelta(0):
        raise ValueError("UTC_REQUIRED")
    return result


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("POSITIVE_FINITE_VALUE_REQUIRED")
    return result


def expected():
    return read(DOC / "identity.expected.json")


def source_expectations():
    return read(DOC / "runpod_source_manifest.json")


def contract(path):
    c = read(path)
    if c.get("schema") != "crypto2_runpod_phase7_session_v1" or c.get("status") != "APPROVED":
        raise ValueError("OWNER_SESSION_APPROVAL_REQUIRED")
    if not c.get("owner") or c["owner"] == "OWNER_TO_CONFIRM_TOMORROW":
        raise ValueError("OWNER_REQUIRED")
    if utc(c["hard_stop_utc"]) <= datetime.now(UTC):
        raise ValueError("SESSION_EXPIRED")
    for name in ("max_session_usd", "compute_usd_per_hour", "all_in_usd_per_hour_upper_bound"):
        positive(c[name])
    positive(c["wallet_usd_at_start"])
    if c["all_in_usd_per_hour_upper_bound"] < c["compute_usd_per_hour"]:
        raise ValueError("ALL_IN_RATE_BELOW_COMPUTE")
    if not 0 <= float(c["identified_cumulative_usd_at_start"]) < 18:
        raise ValueError("HISTORICAL_CUMULATIVE_CAP")
    if c["max_session_usd"] + c["identified_cumulative_usd_at_start"] > 18:
        raise ValueError("SESSION_EXCEEDS_CUMULATIVE_CAP")
    if c["max_session_usd"] > c["wallet_usd_at_start"]:
        raise ValueError("INSUFFICIENT_WALLET")
    if utc(c["session_start_utc"]) > datetime.now(UTC):
        raise ValueError("SESSION_NOT_STARTED")
    if c["source_commit"] != source_expectations()["commit"] or c["identities"] != expected():
        raise ValueError("SESSION_SOURCE_IDENTITY_MISMATCH")
    if (c["volume_id"], c["region"], c["spec"], c["fold"], c["backend"], c["workers"]) != (
        VOLUME,
        "EU-SE-1",
        SPEC,
        FOLD,
        "cpu",
        1,
    ):
        raise ValueError("SESSION_SCOPE_MISMATCH")
    if c["approval"] != "LINUX_VERIFICATION_ONLY" or c["gpu_status"] != "GPU_NOT_QUALIFIED":
        raise ValueError("SEPARATE_STAGE_APPROVALS_REQUIRED")
    if not c["pod_id"].isalnum() or c["pod_id"] == "OWNER_TO_CONFIRM_TOMORROW":
        raise ValueError("LIVE_POD_ID_REQUIRED")
    if float(c["provider_container_disk_gb"]) < 150:
        raise ValueError("PROVIDER_LOCAL_DISK_QUOTA_BELOW_150GB")
    # Operating headroom is separate from the canonical hardware-capacity minimum.
    constrained = c.get("resource_profile") == "constrained_48gb"
    if c.get("resource_profile", "standard_smoke") not in {"standard_smoke", "constrained_48gb"}:
        raise ValueError("UNKNOWN_RESOURCE_PROFILE")
    if (
        constrained
        and c.get("constrained_memory_authorization") != "OWNER_AUTHORIZED_MEASURED_48GB_SMOKE"
    ):
        raise ValueError("CONSTRAINED_OWNER_AUTHORIZATION_REQUIRED")
    if (
        positive(c["minimum_free_ram_gib"]) < (8 if constrained else 32)
        or positive(c["minimum_free_disk_gib"]) < 25
    ):
        raise ValueError("OPERATING_HEADROOM_FLOOR_TOO_LOW")
    from runpod_wallet_policy_phase7 import policy

    policy(c)
    return c


def run(command, log=None, cwd=None, env=None):
    print("STAGE_COMMAND " + " ".join(map(str, command)), flush=True)
    if log is None:
        return subprocess.check_output(command, cwd=cwd, env=env, text=True)
    with Path(log).open("w") as stream:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            print(line, end="", flush=True)
            stream.write(line)
            stream.flush()
        code = process.wait()
    if code:
        raise RuntimeError(f"COMMAND_FAILED_{code}: {command[0]}")


def ancestor(path):
    while not path.exists():
        path = path.parent
    return path


def local_mount(path, provider_gb):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("REAL_LINUX_X86_64_REQUIRED")
    resolved = path.resolve()
    if resolved == Path("/") or resolved.is_relative_to(Path("/workspace")):
        raise ValueError("POD_LOCAL_SESSION_DIRECTORY_REQUIRED")
    probe = ancestor(resolved)
    mount = json.loads(
        run(
            [
                "findmnt",
                "--json",
                "--target",
                str(probe),
                "--output",
                "TARGET,SOURCE,FSTYPE,OPTIONS",
            ]
        )
    )["filesystems"][0]
    if mount["fstype"] not in {"overlay", "ext4", "xfs", "btrfs"}:
        raise ValueError("UNQUALIFIED_OR_NETWORK_FILESYSTEM")
    if "ro" in mount["options"].split(","):
        raise ValueError("LOCAL_FILESYSTEM_READ_ONLY")
    disk = shutil.disk_usage(probe)
    if min(disk.total, int(float(provider_gb) * 1e9)) < 150_000_000_000:
        raise ValueError("LOCAL_CAPACITY_OR_PROVIDER_QUOTA_INSUFFICIENT")
    return {
        "path": str(resolved),
        "mount": mount,
        "df_total_bytes": disk.total,
        "df_free_bytes": disk.free,
        "provider_container_disk_gb": provider_gb,
        "capacity_note": "df on overlay may report host capacity; provider quota also required",
    }


def context(args):
    c = contract(args.contract)
    if os.environ.get("RUNPOD_POD_ID") != c["pod_id"]:
        raise ValueError("MUST_EXECUTE_INSIDE_APPROVED_POD")
    source = Path(args.source_root).resolve()
    local = Path(args.local_root).resolve()
    inputs = Path(args.input_root).resolve()
    if inputs != Path("/workspace/phase7a-transfer"):
        raise ValueError("CANONICAL_INPUT_ROOT_REQUIRED")
    if not source.is_relative_to(local) or source == local or source.is_relative_to(inputs):
        raise ValueError("FROZEN_SOURCE_MUST_BE_IN_LOCAL_SESSION")
    mount = local_mount(local, c["provider_container_disk_gb"])
    if os.stat(ancestor(source)).st_dev != os.stat(ancestor(local)).st_dev:
        raise ValueError("SOURCE_ON_DIFFERENT_FILESYSTEM")
    frozen = read(source / "source-freeze.json")
    if (
        frozen.get("commit") != source_expectations()["commit"]
        or frozen.get("files_sha256") != source_expectations()["inventory_sha256"]
    ):
        raise ValueError("WRONG_FROZEN_EXPORT")
    if (
        hashlib.sha256(json.dumps(frozen["files"], sort_keys=True).encode()).hexdigest()
        != source_expectations()["inventory_sha256"]
    ):
        raise ValueError("SOURCE_INVENTORY_DIGEST_CHANGED")
    # Verify before importing any scientific code, including bootstrap.
    for rec in frozen["files"]:
        candidate = source / rec["path"]
        p = candidate.resolve()
        if (
            not p.is_relative_to(source)
            or candidate.is_symlink()
            or p.stat().st_size != rec["bytes"]
        ):
            raise ValueError("SOURCE_INVENTORY_INVALID")
        if sha(p) != rec["sha256"]:
            raise ValueError("SOURCE_HASH_MISMATCH")
    local.mkdir(parents=True, exist_ok=True)
    evidence = local / "evidence"
    evidence.mkdir(exist_ok=True)
    # This receipt is copied by the outside-Pod controller over SSH every 20 s.
    heartbeat = read(local / "control/stop-controller.json")
    if (heartbeat.get("status"), heartbeat.get("pod_id"), heartbeat.get("contract_sha256")) != (
        "ARMED",
        c["pod_id"],
        sha(args.contract),
    ) or not 0 <= (datetime.now(UTC) - utc(heartbeat["utc"])).total_seconds() <= 90:
        raise ValueError("FRESH_OUTSIDE_POD_STOP_CONTROLLER_REQUIRED")
    if heartbeat.get("stop_permission_verified") is not True:
        raise ValueError("STOP_PERMISSION_NOT_VERIFIED")
    write(evidence / "mount.json", mount)
    return c, source, local, inputs, evidence


def environment(c, source, local, inputs):
    inherited = sorted(k for k in os.environ if k.startswith("PHASE7_"))
    if inherited:
        raise ValueError("CLEAN_OPERATOR_ENVIRONMENT_REQUIRED: " + ",".join(inherited))
    from crypto_ai.phase7.runtime import cpu_availability

    cpus = cpu_availability()["effective_cpu_count"]
    threads = c.get(
        "model_threads",
        max(1, cpus - 1) if c.get("resource_profile") == "constrained_48gb" else cpus,
    )
    if not isinstance(threads, int) or not 1 <= threads <= cpus:
        raise ValueError("APPROVED_THREAD_BUDGET_EXCEEDS_EFFECTIVE_CPU")
    env = os.environ.copy()
    for name in ("VIRTUAL_ENV", "UV_WORKING_DIRECTORY"):
        env.pop(name, None)
    if (local / "operator-tools/bin/uv").is_file():
        env["PATH"] = str(local / "operator-tools/bin") + os.pathsep + env["PATH"]
    env.update(
        {
            "PYTHONPATH": str(source / "src") + os.pathsep + str(source),
            "UV_PROJECT": str(source),
            "UV_PROJECT_ENVIRONMENT": str(source / ".venv"),
            "PHASE7_LGBM_DEVICE": "cpu",
            "PHASE7_ALLOW_CLOUD_RESEARCH": "1",
            "PHASE7_DATA_ROOT": str(inputs / "crypto2-persistent/data"),
            "PHASE7_GOLD_ROOT": str(
                inputs / "crypto2-persistent/data/gold/phase7a_core20_primary_v1"
            ),
            "PHASE7_FEATURE_CONTEXT_SIDECAR": str(
                inputs / "feature_context_sidecar_v3/manifest.json"
            ),
            "PHASE7_ARTIFACT_ROOT": str(local / "stage-artifacts"),
            "PHASE7_CHECKPOINT_ROOT": str(local / "stage-checkpoints"),
            "PHASE7_CACHE_ROOT": str(local / "cache"),
            "PHASE7_MODEL_ROOT": str(local / "models"),
            "PHASE7_MODEL_HASH_REGISTRY": str(local / "model-hashes"),
            "PHASE7_REQUIRE_MODEL_REGISTRY": "1",
            "PHASE7_REPORT_ROOT": str(local / "reports"),
            "PHASE7_LOG_ROOT": str(local / "logs"),
            "PHASE7_TEMP_ROOT": str(local / "tmp"),
            "TMPDIR": str(local / "tmp"),
            "PHASE7_LEGACY_DATA_ROOT": "/home/nssharath123/crypto2.0/data",
            "PHASE7_LEGACY_GOLD_ROOT": (
                "/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1"
            ),
            "PHASE7_LEGACY_ARTIFACT_ROOT": "/home/nssharath123/crypto2.0/local_artifacts/phase7",
            "PHASE7_TOTAL_CPU_THREADS": str(cpus),
            "PHASE7_MODEL_PARALLELISM": "1",
            "PHASE7_LIGHTGBM_THREADS_PER_MODEL": str(threads),
            "PHASE7_RESOURCE_PROFILE": c.get("resource_profile", "standard_smoke"),
            "PHASE7_MIN_FREE_RAM_GIB": str(c["minimum_free_ram_gib"]),
            "PHASE7_MIN_FREE_DISK_GIB": str(c["minimum_free_disk_gib"]),
            "PHASE7_METRICS_EVERY": "25",
            "PHASE7_CACHE_MODE": "read_only",
            "PHASE7_GOLD_VALIDATION_REPORT": str(local / "evidence/gold-validation.json"),
        }
    )
    for name in (
        "stage-artifacts",
        "stage-checkpoints",
        "cache",
        "models",
        "model-hashes",
        "reports",
        "logs",
        "tmp",
    ):
        (local / name).mkdir(exist_ok=True)
    if c.get("resource_profile") == "constrained_48gb":
        env["PHASE7_MEMORY_GUARD_CONFIG"] = str(local / "control/memory-guard.json")
        env["PHASE7_MEMORY_QUALIFICATION_FILE"] = str(local / "evidence/memory-qualification.json")
    return env


def require_receipt(evidence, stage, c, contract_path):
    record = read(evidence / f"{stage}.json")
    if (record.get("status"), record.get("pod_id"), record.get("contract_sha256")) != (
        "PASS",
        c["pod_id"],
        sha(contract_path),
    ):
        raise ValueError(f"REQUIRED_STAGE_NOT_PASSED: {stage}")


def final_json(path):
    text = Path(path).read_text()
    for offset in range(len(text) - 1, -1, -1):
        if text[offset] != "{" or (offset and text[offset - 1] != "\n"):
            continue
        try:
            payload, length = json.JSONDecoder().raw_decode(text[offset:])
            if not text[offset + length :].strip():
                return payload
        except ValueError:
            pass
    raise ValueError("CANONICAL_FINAL_JSON_RESULT_MISSING")


def mirror_tree(src, dst, *, excluded_roots=()):
    """Add-only byte-equivalent copies. Never overwrite conflicting historical evidence."""
    for p in sorted(src.rglob("*")):
        if any(p == root or p.is_relative_to(root) for root in excluded_roots):
            continue
        if p.is_symlink():
            raise ValueError("EVIDENCE_OR_METADATA_SYMLINK_REFUSED")
        if not p.is_file():
            continue
        q = dst / p.relative_to(src)
        q.parent.mkdir(parents=True, exist_ok=True)
        if q.exists():
            if sha(p) != sha(q):
                raise ValueError("EXISTING_EVIDENCE_CONFLICT")
        else:
            # Snapshot once: live logs (memory guard timeline) may still grow while we copy, so the
            # copy is verified against the exact bytes read, not a later re-read of the source.
            data = p.read_bytes()
            with q.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copystat(p, q)
            if hashlib.sha256(data).hexdigest() != sha(q):
                raise ValueError("COPY_BACK_CHECKSUM_MISMATCH")


def mirror_linux_evidence(src, dst):
    """Retain gate results, excluding only the verifier's disposable pytest fixtures."""
    excluded = []
    for gate in src.iterdir():
        suffix = gate.name.removeprefix("software-gate-")
        if (
            gate.name.startswith("software-gate-")
            and len(suffix) == 32
            and all(c in "0123456789abcdef" for c in suffix)
        ):
            if gate.is_symlink() or not gate.is_dir():
                raise ValueError("EVIDENCE_OR_METADATA_SYMLINK_REFUSED")
            fixtures = gate / "tmp"
            if fixtures.is_symlink():
                raise ValueError("EVIDENCE_OR_METADATA_SYMLINK_REFUSED")
            if fixtures.is_dir():
                excluded.append(fixtures)
    mirror_tree(src, dst, excluded_roots=tuple(excluded))
    write(
        dst / "EXPORT_SCOPE.json",
        {
            "status": "PASS",
            "excluded_disposable_pytest_fixture_roots": [str(p.relative_to(src)) for p in excluded],
            "junit_gate_logs_and_verification_results": "RETAINED",
            "symlinks_outside_disposable_fixtures": "REFUSED",
        },
    )


def transfer(source, local, inputs, evidence):
    from crypto_ai.phase7.artifacts import CheckpointStore
    from crypto_ai.phase7.config import load_phase7_config, stable_hash
    from crypto_ai.phase7.gold_validation import locate_gold_manifest, validate_phase7_gold
    from crypto_ai.phase7.identity_summary import identity_summary
    from crypto_ai.phase7.phase7a import pipeline_dispatcher
    from crypto_ai.phase7.runtime import RuntimePaths
    from crypto_ai.phase7.training import causal_descriptor_identity

    definition = read(DOC / "transfer.expected.json")
    records = definition["records"]
    if len(records) != 2777 or sum(x["bytes"] for x in records) != 10998003736:
        raise ValueError("TRANSFER_DEFINITION_CHANGED")
    critical = 0
    for rec in records:
        p = (inputs / rec["path"]).resolve()
        if not p.is_relative_to(inputs) or p.stat().st_size != rec["bytes"]:
            raise ValueError(f"MISSING_OR_WRONG_SIZE: {rec['path']}")
        # Retain trusted large-file provenance; don't add a blanket Parquet scan.
        if p.suffix in {".json", ".txt"} or p.name == "SIDECAR_COMPLETE":
            if sha(p) != rec["sha256"]:
                raise ValueError(f"CRITICAL_MANIFEST_HASH_MISMATCH: {rec['path']}")
            critical += 1
    mirror_tree(inputs / "crypto2-persistent/phase7/artifacts", local / "stage-artifacts")
    mirror_tree(inputs / "crypto2-persistent/phase7/checkpoints", local / "stage-checkpoints")
    config = load_phase7_config(source / "configs/phase7/research_core20_primary_v1.toml")
    runtime = RuntimePaths.resolve(config.paths)
    store = CheckpointStore(
        runtime.checkpoint_root, RUN, runtime.checkpoint_roots(), runtime.legacy_checkpoint_roots()
    )
    refs = []
    for stage in ("registry", "universe", "data", "gold"):
        # Canonical checks include every referenced hash; never replace with size-only PASS.
        if not store.is_complete(stage):
            raise ValueError(f"CHECKPOINT_NOT_VALID: {stage}")
        checkpoint = read(runtime.checkpoint_root / RUN / f"{stage}.json")
        refs.append({"stage": stage, "checkpoint_hash": checkpoint["checkpoint_hash"]})
    gold = locate_gold_manifest(runtime.gold_root)
    ids = identity_summary(gold, inputs / "feature_context_sidecar_v3/manifest.json")
    if ids != expected():
        raise ValueError("SIX_IDENTITIES_DIFFER")
    write(evidence / "identity.json", ids)
    validation = validate_phase7_gold(runtime.gold_root)
    write(evidence / "gold-validation.json", validation)
    if validation["status"] != "PASS":
        raise ValueError("GOLD_VALIDATION_FAILED")
    dispatcher = pipeline_dispatcher()
    registry, universe, policy, data = dispatcher.pipeline._load_stage_state(
        runtime.artifact_root / RUN
    )
    descriptors = dispatcher.pipeline._fold_descriptors(config, registry, data, fold_ids=(FOLD,))
    from crypto_ai.phase5.folds import plan_folds

    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    write(
        evidence / "descriptor-equivalence.json",
        {
            "status": "PASS",
            "method": "canonical relocated checkpoint bytes and canonical descriptor builder",
            "descriptor_identity": causal_descriptor_identity(descriptors, plan.train_end),
            "registry_hash": registry.registry_hash,
            "universe_hash": universe.universe_hash,
            "descriptor_count": len(descriptors),
            "configuration_hash": config.configuration_hash,
            "data_manifest_sha256": sha(runtime.artifact_root / RUN / "data/data_manifest.json"),
            "internal_data_hash": stable_hash(data, length=64),
        },
    )
    return {
        "files": len(records),
        "bytes": sum(x["bytes"] for x in records),
        "critical_files_hashed": critical,
        "checkpoint_references": refs,
        "discovery": "manifest-only; forensic extras excluded",
        "partition_hashes": "canonical checkpoint and Gold gates executed",
    }


def cache_reload(source, local, inputs, evidence):
    import numpy as np
    import pyarrow.compute as pc

    from crypto_ai.phase5.folds import calibration_split_time, plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.gold_validation import locate_gold_manifest, production_a6_model_columns
    from crypto_ai.phase7.models import symbol_balanced_weights
    from crypto_ai.phase7.phase7a import pipeline_dispatcher, select_one_spec
    from crypto_ai.phase7.prepared_cache import PreparedDataCache, prepared_cache_id
    from crypto_ai.phase7.runtime import RuntimePaths
    from crypto_ai.phase7.training import _prepared_cache_identity, causal_descriptor_identity
    from crypto_ai.phase7.universe import select_fold_active_universe

    config = load_phase7_config(source / "configs/phase7/research_core20_primary_v1.toml")
    paths = RuntimePaths.resolve(config.paths)
    dispatcher = pipeline_dispatcher()
    registry, universe, policy, data = dispatcher.pipeline._load_stage_state(
        paths.artifact_root / RUN
    )
    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    descriptors = dispatcher.pipeline._fold_descriptors(config, registry, data, fold_ids=(FOLD,))
    gaps = tuple(
        dispatcher.CausalDataGap.model_validate(x) for x in data.get("unusable_segments", [])
    )
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
    gold_path = locate_gold_manifest(paths.gold_root)
    manifest = read(gold_path)  # Identity derivation only; canonical input gate already passed.
    columns = tuple(manifest["feature_groups"]["A6"])
    if columns != tuple(production_a6_model_columns()) or len(columns) != 109:
        raise ValueError("A6_ORDER_DRIFT")
    identity = _prepared_cache_identity(
        config=config,
        manifest=manifest,
        gold_manifest_sha256=sha(gold_path),
        source_identity={},
        fold_id=plan.fold_id,
        research_view="CORE",
        fold_membership_hash=membership.membership_hash,
        universe_hash=universe.universe_hash,
        registry_hash=registry.registry_hash,
        spec=select_one_spec(config, SPEC),
        feature_columns=columns,
        descriptor_identity=causal_descriptor_identity(descriptors, plan.train_end),
    )
    cache = PreparedDataCache(paths.cache_root, "read_only")
    path = cache.cache_path(identity)
    cache_manifest = path / "manifest.json"
    before = sha(cache_manifest)
    summaries = []
    for _ in range(2):
        bundle = cache.load(identity, plan)  # Full canonical hash/matrix/finite/alignment gate.
        tables = {
            "train": bundle.prepared.train,
            "validation": bundle.prepared.validation,
            "calibration_a": bundle.prepared.calibration_a,
            "calibration_b": bundle.prepared.calibration_b,
        }
        split = calibration_split_time(plan)
        boundaries = {
            "train": (plan.train_start, plan.train_end),
            "validation": (plan.validation_start, plan.validation_end),
            "calibration_a": (plan.calibration_start, split),
            "calibration_b": (split, plan.calibration_end),
        }
        segments = {}
        for name, table in tables.items():
            if table["feature_time"].null_count or table["label_end_time"].null_count:
                raise ValueError("CACHE_NULL_TIMESTAMP")
            if set(pc.unique(table["horizon_minutes"]).to_pylist()) != {60}:
                raise ValueError("CACHE_HORIZON_MISMATCH")
            times = pc.min_max(table["feature_time"]).as_py()
            lower, upper = boundaries[name]
            ends = pc.min_max(table["label_end_time"]).as_py()
            if (
                times["min"] is None
                or times["min"] < lower
                or times["max"] >= upper
                or ends["max"] >= upper
                or times["max"] >= config.research_cutoff
            ):
                raise ValueError("CACHE_FORBIDDEN_PERIOD")
            segments[name] = {
                "rows": table.num_rows,
                "feature_time": times,
                "symbols": sorted(pc.unique(table["symbol"]).to_pylist()),
            }
        # TEST is inspected structurally only. No outcomes/predictions/metrics are released.
        test_times = pc.min_max(bundle.fold._test["feature_time"]).as_py()
        test_ends = pc.min_max(bundle.fold._test["label_end_time"]).as_py()
        if (
            test_times["min"] is None
            or test_times["min"] < plan.test_start
            or test_times["max"] >= plan.test_end
            or test_times["max"] >= config.research_cutoff
            or test_ends["max"] >= config.research_cutoff
        ):
            raise ValueError("CACHE_TEST_FORBIDDEN_PERIOD")
        weights = symbol_balanced_weights(bundle.prepared.model_inputs.train_symbols)
        if not np.all(np.isfinite(weights)) or not np.all(weights > 0):
            raise ValueError("WEIGHTS_INVALID")
        from crypto_ai.phase7.fit_boundary import assert_fit_matrices, assert_fit_segments

        mi = bundle.prepared.model_inputs
        assert_fit_matrices(mi.train_x, mi.train_y, mi.validation_x, mi.validation_y, weights)
        fit_boundary = assert_fit_segments(
            bundle.prepared.train,
            bundle.prepared.validation,
            model_inputs=mi,
            feature_columns=columns,
            target_column=identity["target_column"],
            validation_start_us=int(plan.validation_start.timestamp() * 1_000_000),
        )
        summaries.append(
            {
                "cache_id": bundle.cache_id,
                "segments": segments,
                "test_structure": {"rows": bundle.fold._test.num_rows, "feature_time": test_times},
                "weights_sha256": hashlib.sha256(weights.tobytes()).hexdigest(),
                "weights_rows": len(weights),
                "weights_sum": float(weights.sum()),
                "fit_boundary": fit_boundary,
                "manifest_sha256": sha(cache_manifest),
            }
        )
        del bundle, tables, weights, mi, table
        gc.collect()
    if summaries[0] != summaries[1] or before != sha(cache_manifest):
        raise ValueError("READ_ONLY_RELOAD_DIFFERS")
    if prepared_cache_id(identity) != summaries[0]["cache_id"]:
        raise ValueError("CACHE_ID_DRIFT")
    return {
        "cache_identity": identity,
        "loads": summaries,
        "equivalence": "EXACT_SAME_HASHED_PAYLOAD",
        "marker": "CACHE_COMPLETE",
        "mode": "read_only",
        "test_metrics_accessed": False,
        "qualification_scope": (
            "canonical alignment plus independently rederived identity; "
            "not a new Gold recomputation"
        ),
    }


def stage_approval(args, c, mode):
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.run_contract import approval_binding, validate_owner_approval

    if not args.approval:
        raise ValueError("SEPARATE_PREPARE_OR_TRAIN_APPROVAL_REQUIRED")
    config = load_phase7_config(
        Path(args.source_root) / "configs/phase7/research_core20_primary_v1.toml"
    )
    result = validate_owner_approval(
        Path(args.approval), expected=approval_binding(config, SPEC, FOLD), mode=mode
    )
    if (
        result["cost_currency"] != "USD"
        or result["cost_ceiling"] != c["max_session_usd"]
        or utc(result["stop_deadline_utc"]) != utc(c["hard_stop_utc"])
    ):
        raise ValueError("STAGE_AND_SESSION_COST_CONTRACT_DIFFER")


def partial_for_restart(args, c):
    from crypto_ai.phase7.preemption import verify_partial

    if not args.checkpoint or not args.approval:
        raise ValueError("FRESH_RESUME_ONE_CPU_SMOKE_APPROVAL_REQUIRED")
    value = read(args.approval)
    if value.get("status") != "APPROVED" or value.get("mode") != "train":
        raise ValueError("FRESH_RESUME_ONE_CPU_SMOKE_APPROVAL_REQUIRED")
    previous = verify_partial(Path(args.checkpoint))
    if (value.get("operation"), value.get("logical_run_id"), value.get("checkpoint_sha256")) != (
        "RESUME_ONE_CPU_SMOKE_RESTART_FROM_ZERO",
        previous["logical_run_id"],
        previous["checkpoint_sha256"],
    ):
        raise ValueError("FRESH_RESUME_ONE_CPU_SMOKE_APPROVAL_REQUIRED")
    if previous["binding"]["scientific_ids"] != expected() or previous["pod_id"] == c["pod_id"]:
        raise ValueError("RESUME_IDENTITY_MISMATCH_OR_OLD_POD_REUSED")
    if c.get("previous_pod_id") != previous["pod_id"]:
        raise ValueError("SESSION_PREVIOUS_POD_BINDING_REQUIRED")
    if c.get("model_threads") != previous["binding"]["model_threads"]:
        raise ValueError("RESUME_THREAD_BUDGET_MUST_MATCH")
    return previous


def persist_cache_if_capacity(local, qualified, c):
    from crypto_ai.phase7.preemption import copy_qualified_cache

    cache_id = qualified["loads"][0]["cache_id"]
    if not c.get("retain_qualified_cache", True):
        return {
            "status": "CONDITIONAL",
            "retained": False,
            "restart_mode": "MODEL_RESUME_WITH_CACHE_REPREPARATION",
        }
    # FUSE df may expose backing-pool capacity. Respect the provisioned 50 GB quota too.
    used = int(subprocess.check_output(["du", "-sb", "/workspace"], text=True).split()[0])
    available = max(0, min(shutil.disk_usage("/workspace").free, 50_000_000_000 - used))
    try:
        result = copy_qualified_cache(
            local / "cache" / cache_id,
            Path("/workspace/phase7a-cache") / cache_id,
            cache_id,
            available_bytes=available,
        )
        return {
            "status": "PASS",
            "retained": True,
            "cache_id": cache_id,
            "bytes": result.get("bytes"),
            "path": result["path"],
            "quota_free_bytes_before": available,
        }
    except OSError as exc:
        return {
            "status": "CONDITIONAL",
            "retained": False,
            "error_type": type(exc).__name__,
            "restart_mode": "MODEL_RESUME_WITH_CACHE_REPREPARATION",
        }


def configure_preemption(args, c, local, qualified, env, previous=None):
    from crypto_ai.phase7.config import stable_hash
    from crypto_ai.phase7.preemption import copy_verified_tree

    cache_id = qualified["loads"][0]["cache_id"]
    logical = "phase7-" + stable_hash(
        {"identities": expected(), "cache": cache_id, "spec": SPEC, "fold": FOLD}, length=24
    )
    if previous and previous["logical_run_id"] != logical:
        raise ValueError("RESUME_LOGICAL_RUN_ID_MISMATCH")
    if previous and previous["binding"]["cache_manifest_sha256"] != sha(
        local / "cache" / cache_id / "manifest.json"
    ):
        raise ValueError("RESUME_CACHE_PAYLOAD_MISMATCH")
    session = c["pod_id"] + "-" + sha(args.contract)[:12]
    persistent = Path("/workspace/phase7a-evidence/training-checkpoints") / logical
    # Tiny protocol probe before fitting; no large cache copy during a wallet emergency.
    probe = local / "control" / ("publication-probe-" + session)
    probe.mkdir(parents=True, exist_ok=True)
    write(probe / "probe.json", {"logical_run_id": logical, "session": session})
    copy_verified_tree(
        probe, persistent / "publication-probes" / session, reserve_bytes=50 * 1024**2
    )
    configuration = {
        "schema": "phase7_preemption_config_v1",
        "logical_run_id": logical,
        "execution_session_id": session,
        "pod_id": c["pod_id"],
        "interval_rounds": 25,
        "expected_scientific_ids": expected(),
        "expected_cache_id": cache_id,
        "local_root": str(local / "partial-checkpoints" / logical),
        "persistent_root": str(persistent),
        "request_path": str(local / "control/CHECKPOINT_REQUEST.json"),
        "receipt_path": str(local / "control/checkpoint-receipt.json"),
        "restart_checkpoint": None if previous is None else previous["checkpoint_path"],
        "resume_from_partial": False,
    }
    retention = (
        read(local / "evidence/cache-retention.json")
        if (local / "evidence/cache-retention.json").is_file()
        else {}
    )
    configuration["cache_retained"] = retention.get("retained", False)
    write(local / "control/preemption.json", configuration)
    env["PHASE7_PREEMPTION_CONFIG"] = str(local / "control/preemption.json")
    return {
        "logical_run_id": logical,
        "execution_session_id": session,
        "mid_fit_resume": "NOT_QUALIFIED",
        "restart_from_round": 0,
    }


def start_memory_guard(c, source, local, args):
    if c.get("resource_profile") != "constrained_48gb":
        return
    import atexit
    import time

    cfg = {
        "stage": args.stage,
        "local_root": str(local),
        "contract_sha256": sha(args.contract),
        "heartbeat": str(local / "control/memory-guard-heartbeat.json"),
        "timeline": str(local / "evidence/memory_timeline.jsonl"),
        "emergency_evidence": str(
            Path("/workspace/phase7a-evidence")
            / c["pod_id"]
            / "memory-guard"
            / (args.stage + "-" + str(os.getpid()) + ".json")
        ),
    }
    path = local / "control/memory-guard.json"
    write(path, cfg)
    guard = subprocess.Popen(
        [
            str(source / ".venv/bin/python"),
            "-m",
            "crypto_ai.phase7.memory_profile",
            "--config",
            str(path),
            "--pid",
            str(os.getpid()),
        ],
        cwd=source,
        env=os.environ.copy()
        | {"PYTHONPATH": str(source / "src"), "PHASE7_RESOURCE_PROFILE": "constrained_48gb"},
    )
    atexit.register(guard.terminate)
    # A cold container right after uv sync can need well over 5 s for the guard's first imports.
    for _ in range(300):
        if guard.poll() is not None:
            raise MemoryError("MEMORY_GUARD_DID_NOT_START")
        if Path(cfg["heartbeat"]).exists():
            beat = read(cfg["heartbeat"])
            if (
                beat.get("target_pid") == os.getpid()
                and beat.get("contract_sha256") == cfg["contract_sha256"]
            ):
                return
        time.sleep(0.1)
    guard.terminate()
    raise MemoryError("MEMORY_GUARD_HEARTBEAT_TIMEOUT")


def memory_probe(source, local, inputs, evidence, c, contract_path):
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.hardening import current_config
    from crypto_ai.phase7.memory_profile import checkpoint, fit_fingerprint, probe_scope
    from crypto_ai.phase7.models import fit_architecture, symbol_balanced_weights
    from crypto_ai.phase7.phase7a import select_one_spec
    from crypto_ai.phase7.prepared_cache import PreparedDataCache
    from crypto_ai.phase7.training import try_build_validation_context
    from crypto_ai.phase7.training_metrics import training_metric_scope

    qualified = cache_reload(source, local, inputs, evidence)
    config = load_phase7_config(source / "configs/phase7/research_core20_primary_v1.toml")
    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    cache = PreparedDataCache(local / "cache", "read_only")
    bundle = cache.load(qualified["cache_identity"], plan)
    prepared = bundle.prepared
    spec = select_one_spec(config, SPEC)
    mi = prepared.model_inputs
    cpus = __import__(
        "crypto_ai.phase7.runtime", fromlist=["effective_cpu_count"]
    ).effective_cpu_count()
    threads = c.get("model_threads", max(1, cpus - 1))
    weights = symbol_balanced_weights(mi.train_symbols) if spec.symbol_balanced else None
    fingerprint = fit_fingerprint(
        config.models, threads, mi.train_x, mi.train_y, mi.validation_x, mi.validation_y, weights
    )
    diagnostics, _ = try_build_validation_context(
        prepared.validation,
        target_type=spec.target_type,
        normalization_floor=config.targets.normalization_floor,
        config=current_config(),
    )
    gc.collect()
    checkpoint("MEMORY_QUALIFICATION_START")
    short = config.models.model_copy(update={"n_estimators": 5})
    with (
        probe_scope(),
        training_metric_scope(
            evidence / "memory-probe-metrics",
            diagnostics=diagnostics,
            purpose="MEMORY_QUALIFICATION_ONLY",
            round_limit=5,
        ),
    ):
        model = fit_architecture(
            "G0",
            prepared.train,
            prepared.validation,
            feature_columns=prepared.feature_columns,
            target_column=prepared.target_column,
            config=short,
            model_threads=threads,
            estimator_workers=1,
            cluster_mapping=bundle.fold.cluster_mapping,
            explicit_symbol_id=spec.explicit_symbol_id,
            symbol_balanced=spec.symbol_balanced,
            eligibility_calibration_a=prepared.calibration_a,
            prepared_inputs=mi,
        )
    checkpoint("MEMORY_QUALIFICATION_END")
    records = [
        json.loads(line) for line in (evidence / "memory_timeline.jsonl").read_text().splitlines()
    ]
    # Include the entire stage, reload/validation and native construction, not only its ending RSS.
    records = [
        r
        for r in records
        if r["stage"] == "memory-probe" or r["stage"].startswith("MEMORY_QUALIFICATION")
    ]
    peak = max(r["cgroup_memory_current_bytes"] for r in records)
    ratio = max(r["cgroup_ratio"] for r in records)
    remaining = min(r["ram_available_bytes"] for r in records)
    if ratio >= 0.82 or remaining < 10 * 1024**3:
        raise MemoryError(
            "48GB_HOST_INSUFFICIENT: probe requires <82% cgroup use and >=10 GiB effective headroom"
        )
    cache_manifest = cache.cache_path(qualified["cache_identity"]) / "manifest.json"
    proof = {
        "status": "PASS",
        "purpose": "MEMORY_QUALIFICATION_ONLY",
        "canonical_result": False,
        "resource_profile": "constrained_48gb",
        "contract_sha256": sha(contract_path),
        "cache_manifest": str(cache_manifest),
        "cache_manifest_sha256": sha(cache_manifest),
        "cache_id": bundle.cache_id,
        "fit_fingerprint": fingerprint,
        "probe_rounds": 5,
        "observed_rounds": model.estimators["global"].booster_.current_iteration(),
        "peak_cgroup_bytes": peak,
        "peak_cgroup_ratio": ratio,
        "minimum_effective_headroom_bytes": remaining,
        "peak_process_tree_rss_bytes": max(
            r.get("process_tree_rss_bytes", r["process_rss_bytes"]) for r in records
        ),
        "peak_measurement": "SAMPLED_250MS_PLUS_STAGE_BOUNDARIES; NOT_A_500_ROUND_BOUND",
        "test_metrics_accessed": False,
        "scientific_ids": expected(),
    }
    write(evidence / "memory-qualification.json", proof)
    del model, bundle, prepared, mi, weights, diagnostics
    gc.collect()
    checkpoint("AFTER_PROBE_OBJECT_RELEASE")
    return proof


def execute(args):
    c, source, local, inputs, evidence = context(args)
    args.authorized_stop_path = local / "control/STOP_REQUEST.json"
    args.authorized_evidence_path = evidence
    if args.authorized_stop_path.exists():
        raise ValueError("PENDING_STOP_REQUEST; DO_NOT_CONTINUE")
    py = source / ".venv/bin/python"
    if args.stage == "bootstrap":
        if any(k.startswith("PHASE7_") for k in os.environ):
            raise ValueError("CLEAN_OPERATOR_ENVIRONMENT_REQUIRED")
        bootstrap_env = os.environ.copy()
        for name in ("VIRTUAL_ENV", "UV_WORKING_DIRECTORY"):
            bootstrap_env.pop(name, None)
        bootstrap_env.update(
            {
                "PYTHONPATH": str(source / "src") + os.pathsep + str(source),
                "UV_PROJECT": str(source),
                "UV_PROJECT_ENVIRONMENT": str(source / ".venv"),
                "PHASE7_RESOURCE_PROFILE": c.get("resource_profile", "standard_smoke"),
            }
        )
        run(["apt-get", "update"], evidence / "apt-update.log")
        run(
            [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "libgomp1",
                "ca-certificates",
                "curl",
                "python3-venv",
            ],
            evidence / "apt-install.log",
        )
        if not shutil.which("uv"):
            # Fixed tool version; package dependencies still come exclusively from uv.lock.
            tools_root = local / "operator-tools"
            run(["python3", "-m", "venv", str(tools_root)], evidence / "uv-tool-venv.log")
            run(
                [str(tools_root / "bin/python"), "-m", "pip", "install", "uv==0.13.7"],
                evidence / "uv-install.log",
            )
            bootstrap_env["PATH"] = str(tools_root / "bin") + os.pathsep + bootstrap_env["PATH"]
        run(
            ["uv", "sync", "--locked", "--extra", "dev", "--python", "3.12"],
            evidence / "uv-sync.log",
            cwd=source,
            env=bootstrap_env,
        )
        run(
            [str(py), str(Path(__file__).resolve()), "versions"],
            evidence / "versions.json",
            cwd=source,
            env=bootstrap_env,
        )
        start_memory_guard(c, source, local, args)
        # Cheap real cgroup admission before the Gold validator or Linux suite.
        probe_code = (
            "import json,sys; from pathlib import Path; "
            "from crypto_ai.phase7.runtime import system_snapshot; "
            "from crypto_ai.phase7.run_contract import smoke_resource_errors; "
            "s=system_snapshot(Path(sys.argv[1])); e=smoke_resource_errors(s); "
            "print(json.dumps({'snapshot':s,'errors':e})); sys.exit(2 if e else 0)"
        )
        run(
            [str(py), "-c", probe_code, str(local)],
            evidence / "bootstrap-resources.json",
            cwd=source,
            env=bootstrap_env,
        )
        detail = {"uname": platform.uname()._asdict(), "mount": read(evidence / "mount.json")}
    else:
        if Path(sys.prefix).resolve() != (source / ".venv").resolve():
            raise ValueError("RUN_WITH_FROZEN_EXPORT_VENV_PYTHON")
        sys.path[:0] = [str(source / "src"), str(source)]
        env = environment(c, source, local, inputs)
        os.environ.update({k: v for k, v in env.items() if k.startswith("PHASE7_")})
        from crypto_ai.phase7.run_contract import validate_environment

        validate_environment(os.environ)
        start_memory_guard(c, source, local, args)
        require_receipt(evidence, "bootstrap", c, args.contract)
        if args.stage == "verify-transfer":
            from crypto_ai.phase7.resources import resource_admission

            resource_admission("OPERATOR_TRANSFER_VALIDATION", additional_roots=(local,))
            detail = transfer(source, local, inputs, evidence)
        elif args.stage == "preflight":
            require_receipt(evidence, "verify-transfer", c, args.contract)
            run(
                [
                    "bash",
                    str(source / "scripts/closure/verify_linux_external.sh"),
                    str(local / "linux-fs"),
                ],
                evidence / "linux-gate.log",
                cwd=source,
                env=env,
            )
            # The canonical shell intentionally unsets PHASE7_ in its child only.
            from crypto_ai.phase7.filesystem_probe import qualify_filesystem
            from crypto_ai.phase7.resources import resource_admission
            from crypto_ai.phase7.run_contract import smoke_resource_errors
            from crypto_ai.phase7.runtime import system_snapshot

            fs = qualify_filesystem(local / "filesystem-qualification")
            if fs["status"] != "PASS":
                raise ValueError("FILESYSTEM_QUALIFICATION_FAILED")
            probe = Path(fs["path"])
            if probe.parent != local / "filesystem-qualification" or not probe.name.startswith(
                "phase7-filesystem-probe-"
            ):
                raise ValueError("PROBE_CLEANUP_SCOPE_REFUSED")
            shutil.rmtree(probe)  # Only this newly created isolated probe, never input/cache data.
            fs["cleanup"] = "PASS" if not probe.exists() else "FAIL"
            write(evidence / "filesystem.json", fs)
            snapshot = system_snapshot(local)
            errors = smoke_resource_errors(snapshot)
            write(evidence / "resources.json", {"snapshot": snapshot, "errors": errors})
            if errors:
                raise ValueError("RESOURCE_ADMISSION_FAILED: " + ";".join(errors))
            resource_admission("OPERATOR_PREFLIGHT", additional_roots=(local,))
            from crypto_ai.phase7.gold_validation import locate_gold_manifest

            gold = locate_gold_manifest(Path(env["PHASE7_GOLD_ROOT"]))
            run(
                [
                    str(py),
                    "-m",
                    "crypto_ai.phase7.resource_estimate",
                    "--manifest",
                    str(gold),
                    "--path",
                    str(local / "cache"),
                    "--fold-index",
                    "0",
                    "--horizon-minutes",
                    "60",
                    "--config",
                    str(source / "configs/phase7/research_core20_primary_v1.toml"),
                    "--json",
                ],
                evidence / "resource-estimate.json",
                cwd=source,
                env=env,
            )
            detail = {
                "linux_gate": "PASS",
                "filesystem": "PASS",
                "resources": "PASS",
                "next": "STOP_AND_REPORT; separate PREPARE ONE CACHE approval required",
            }
        elif args.stage == "memory-probe":
            require_receipt(evidence, "reload", c, args.contract)
            stage_approval(args, c, "train")
            if c.get("resource_profile") != "constrained_48gb":
                raise ValueError("MEMORY_PROBE_REQUIRES_CONSTRAINED_PROFILE")
            detail = memory_probe(source, local, inputs, evidence, c, args.contract)
        elif args.stage == "restore-cache":
            from crypto_ai.phase7.preemption import copy_qualified_cache

            require_receipt(evidence, "preflight", c, args.contract)
            stage_approval(args, c, "train")
            previous = partial_for_restart(args, c)
            cache_id = previous["binding"]["prepared_cache_id"]
            source_cache = Path("/workspace/phase7a-cache") / cache_id
            if not source_cache.is_dir():
                raise ValueError(
                    "MODEL_RESUME_WITH_CACHE_REPREPARATION: separate PREPARE approval required"
                )
            if sha(source_cache / "manifest.json") != previous["binding"]["cache_manifest_sha256"]:
                raise ValueError("RESUME_CACHE_PAYLOAD_MISMATCH")
            copy_qualified_cache(source_cache, local / "cache" / cache_id, cache_id)
            qualified = cache_reload(source, local, inputs, evidence)
            write(
                evidence / "cache-retention.json",
                {
                    "status": "PASS",
                    "retained": True,
                    "cache_id": cache_id,
                    "restored_from": str(source_cache),
                },
            )
            write(
                evidence / "reload.json",
                {
                    "status": "PASS",
                    "pod_id": c["pod_id"],
                    "contract_sha256": sha(args.contract),
                    **qualified,
                },
            )
            detail = {
                "cache_restored": True,
                "cache_id": cache_id,
                "next": "RESUME_ONE_CPU_SMOKE_OWNER_APPROVAL",
            }
        elif args.stage in {"prepare", "train", "resume"}:
            require_receipt(evidence, "preflight", c, args.contract)
            stage_approval(args, c, "train" if args.stage == "resume" else args.stage)
            preemption_metadata = {}
            if args.stage in {"train", "resume"}:
                require_receipt(evidence, "reload", c, args.contract)
                if c.get("resource_profile") == "constrained_48gb":
                    require_receipt(evidence, "memory-probe", c, args.contract)
                # Revalidate exact cache again before fitting; fail instead of rebuilding.
                qualified = cache_reload(source, local, inputs, evidence)
                previous = partial_for_restart(args, c) if args.stage == "resume" else None
                preemption_metadata = configure_preemption(args, c, local, qualified, env, previous)
            env["PHASE7_CACHE_MODE"] = "auto" if args.stage == "prepare" else "read_only"
            env["PHASE7_OWNER_APPROVAL_FILE"] = str(Path(args.approval).resolve())
            command = [
                str(py),
                "-m",
                "crypto_ai.phase7.benchmark_one_spec",
                "--config",
                str(source / "configs/phase7/research_core20_primary_v1.toml"),
                "--spec-id",
                SPEC,
                "--output-root",
                str(local / "benchmarks/smoke"),
                "--execute",
            ]
            if args.stage == "prepare":
                command.append("--prepare-only")
            run(command, evidence / f"{args.stage}.log", cwd=source, env=env)
            result = final_json(evidence / f"{args.stage}.log")
            if result.get("status") == "PREEMPTED_RESTART_REQUIRED":
                write(evidence / f"{args.stage}-result.json", result)
                collect(local, source, c, args.contract)
                write(
                    local / "control/SESSION_PAUSED.json",
                    {"reason": "PREEMPTED_RESTART_REQUIRED", "receipt": result["receipt"]},
                )
                print(json.dumps(result, indent=2))
                return
            if args.stage == "prepare":
                if result.get("status") != "PREPARED_ONLY" or result.get("models_fitted") != 0:
                    raise ValueError("PREPARE_RESULT_NOT_QUALIFIED")
            elif (
                result.get("status") != "BENCHMARK_ONLY"
                or result.get("benchmark_completed_reports") != 1
                or len(result.get("reports", [])) != 1
            ):
                raise ValueError("ONE_SMOKE_NOT_COMPLETED")
            write(evidence / f"{args.stage}-result.json", result)
            detail = {
                "spec": SPEC,
                "fold": FOLD,
                "backend": "cpu",
                "workers": 1,
                "next": "STOP_AND_REPORT",
                "approval_sha256": sha(args.approval),
                **preemption_metadata,
            }
        elif args.stage == "reload":
            require_receipt(evidence, "prepare", c, args.contract)
            stage_approval(args, c, "prepare")
            detail = cache_reload(source, local, inputs, evidence)
            retention = persist_cache_if_capacity(local, detail, c)
            write(evidence / "cache-retention.json", retention)
            detail["cache_retention"] = retention
        else:
            detail = {"collection_only": True}
    receipt = {
        "status": "PASS",
        "stage": args.stage,
        "resource_profile": c.get("resource_profile", "standard_smoke"),
        "pod_id": c["pod_id"],
        "contract_sha256": sha(args.contract),
        "utc": datetime.now(UTC).isoformat(),
        **detail,
    }
    write(evidence / f"{args.stage}.json", receipt)
    collect(local, source, c, args.contract)
    if args.stage in {"train", "resume"}:
        write(
            local / "control/SESSION_COMPLETE.json",
            {
                "reason": "ONE_SMOKE_COMPLETE_EVIDENCE_EXPORTED",
                "utc": datetime.now(UTC).isoformat(),
            },
        )
    print(json.dumps(receipt, indent=2, default=str))


def collect(local, source, c, contract_path):
    # Unique snapshot per stage; never mirror immutable inputs or delete remote evidence.
    target = (
        Path("/workspace/phase7a-evidence")
        / c["pod_id"]
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ"))
    )
    target.mkdir(parents=True, exist_ok=False)
    for name in (
        "evidence",
        "logs",
        "models",
        "model-hashes",
        "reports",
        "benchmarks",
        "stage-checkpoints",
    ):
        src = local / name
        if src.is_dir():
            mirror_tree(src, target / name)
    for name in (".linux-closure-logs", ".pytest-linux-verification"):
        if (source / name).is_dir():
            copier = mirror_linux_evidence if name == ".pytest-linux-verification" else mirror_tree
            copier(source / name, target / "linux" / name)
    shutil.copy2(contract_path, target / "session-contract.json")
    write(
        target / "EXPORT_COMPLETE.json",
        {
            "status": "PASS",
            "pod_id": c["pod_id"],
            "volume_id": VOLUME,
            "copied_files": len([p for p in target.rglob("*") if p.is_file()]),
            "cache_policy": (
                "large local prepared cache not included; "
                "copy separately only if approved and space permits"
            ),
        },
    )
    print("EVIDENCE_EXPORTED " + str(target), flush=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=(*STAGES, "versions"))
    p.add_argument(
        "--execute",
        action="store_true",
        help="Requires fresh approvals and external stop heartbeat",
    )
    p.add_argument("--contract", default=os.getenv("CRYPTO2_SESSION_CONTRACT"))
    p.add_argument("--approval", help="Separate canonical prepare/train owner record")
    p.add_argument(
        "--checkpoint", help="Verified persistent partial checkpoint; restart only, no init_model"
    )
    p.add_argument(
        "--source-root", default=os.getenv("CRYPTO2_SOURCE_ROOT", "/crypto2-session/source")
    )
    p.add_argument("--local-root", default=os.getenv("CRYPTO2_LOCAL_ROOT", "/crypto2-session"))
    p.add_argument("--input-root", default="/workspace/phase7a-transfer")
    return p


def main():
    args = parser().parse_args()
    if args.stage == "versions":
        print(
            json.dumps(
                {
                    "python": sys.version,
                    "packages": {
                        name: importlib.metadata.version(name)
                        for name in ("numpy", "pyarrow", "lightgbm", "psutil", "pytest", "ruff")
                    },
                    "uv": subprocess.check_output(["uv", "--version"], text=True).strip(),
                },
                indent=2,
            )
        )
        return 0
    print("STAGE " + args.stage, flush=True)
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_ONLY",
                    "stage": args.stage,
                    "source_commit": source_expectations()["commit"],
                    "spec": SPEC,
                    "fold": FOLD,
                    "backend": "cpu",
                    "workers": 1,
                    "compute_started": False,
                    "cache_built": False,
                    "models_fitted": 0,
                    "requires": (
                        "fresh session approval + outside-Pod stop control; "
                        "prepare/train separately approved"
                    ),
                },
                indent=2,
            )
        )
        return 0
    try:
        execute(args)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "stage": args.stage,
                    "error": str(exc),
                    "next": "STOP; collect evidence; external controller must stop compute",
                }
            ),
            file=sys.stderr,
        )
        # Signal via a strictly local control file, never a provider credential.
        if hasattr(args, "authorized_stop_path"):
            write(args.authorized_stop_path, {"reason": "STAGE_FAILURE", "stage": args.stage})
            write(
                args.authorized_evidence_path / f"{args.stage}.json",
                {
                    "status": "FAIL",
                    "stage": args.stage,
                    "error": str(exc),
                    "utc": datetime.now(UTC).isoformat(),
                },
            )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
