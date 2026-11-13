"""Cached-versus-uncached preparation qualification for the low-memory profile.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-low-memory-training).

Step 1 (inside the canonical prepare-only run): with ``PHASE7_UNCACHED_DIGEST_FILE`` set, the
training loop writes :func:`prepared_digest` of the freshly prepared, UNCACHED fold/matrices just
before the prepared cache is published. Observation only: nothing it computes feeds the run.

Step 2 (this module's CLI, a separate process): the published cache is re-opened with the
production read-only loader (checksums, schemas, alignment) and the same digest is recomputed.
A ``VALIDATED`` record is written only when every component is identical: row keys and order,
timestamps, symbols, targets, weights inputs, every feature column, float64 matrices, fold
boundaries/purge/embargo report, eligibility manifest and cache file hashes. The record binds the
current scientific/preparation source digests, Gold manifest and sidecar, so any later source or
data change invalidates it. Low-memory training admission requires this record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

DIGEST_ENV = "PHASE7_UNCACHED_DIGEST_FILE"
VALIDATION_ENV = "PHASE7_LOW_MEMORY_VALIDATION_FILE"
DIGEST_SCHEMA = "phase7_prepared_digest_v1"
VALIDATION_SCHEMA = "phase7_low_memory_validation_v1"
_CHUNK_ROWS = 262_144


def _hash_array(digest: Any, array: pa.Array) -> None:
    if pa.types.is_timestamp(array.type) or pa.types.is_date(array.type):
        array = array.cast(pa.int64())
    if (
        pa.types.is_floating(array.type)
        or pa.types.is_integer(array.type)
        or pa.types.is_boolean(array.type)
    ):
        values = array.to_numpy(zero_copy_only=False)
        digest.update(np.ascontiguousarray(values).tobytes())
        digest.update(
            np.ascontiguousarray(array.is_null().to_numpy(zero_copy_only=False)).tobytes()
        )
        return
    for value in array.to_pylist():
        digest.update(b"\x00N" if value is None else b"\x01" + str(value).encode("utf-8"))


def column_digest(column: pa.ChunkedArray | pa.Array) -> str:
    """Physical-layout independent digest of one column's logical values (NaN-bit exact)."""

    digest = hashlib.sha256()
    chunks = column.chunks if isinstance(column, pa.ChunkedArray) else [column]
    for chunk in chunks:
        for start in range(0, len(chunk), _CHUNK_ROWS):
            _hash_array(digest, chunk.slice(start, _CHUNK_ROWS))
    return digest.hexdigest()


def table_digest(table: pa.Table) -> dict[str, Any]:
    return {
        "rows": table.num_rows,
        "schema": table.schema.to_string(show_schema_metadata=False),
        "columns": {name: column_digest(table.column(name)) for name in table.column_names},
    }


def array_digest(array: np.ndarray) -> dict[str, Any]:
    values = np.asarray(array)
    digest = hashlib.sha256()
    if values.dtype == object:
        for value in values.reshape(-1):
            digest.update(str(value).encode("utf-8") + b"\x00")
    else:
        flat = values.reshape(values.shape[0], -1) if values.ndim > 1 else values
        for start in range(0, flat.shape[0], _CHUNK_ROWS):
            digest.update(np.ascontiguousarray(flat[start : start + _CHUNK_ROWS]).tobytes())
    return {"shape": list(values.shape), "dtype": str(values.dtype), "sha256": digest.hexdigest()}


def _stable(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def prepared_digest(fold: Any, prepared: Any) -> dict[str, Any]:
    inputs = prepared.model_inputs
    return {
        "schema": DIGEST_SCHEMA,
        "fold_id": fold.plan.fold_id,
        "plan": fold.plan.to_dict(),
        "research_view": fold.research_view,
        "fold_report": _stable(fold.report),
        "eligibility_manifest": _stable(fold.eligibility_manifest),
        "cluster_mapping": _stable(fold.cluster_mapping),
        "liquidity_tiers": _stable(fold.liquidity_tiers),
        "feature_columns": list(prepared.feature_columns),
        "target_column": prepared.target_column,
        "tables": {
            "train": table_digest(prepared.train),
            "validation": table_digest(prepared.validation),
            "calibration_a": table_digest(prepared.calibration_a),
            "calibration_b": table_digest(prepared.calibration_b),
            "test": table_digest(fold._test),
        },
        "arrays": {
            name: array_digest(getattr(inputs, name))
            for name in (
                "train_x",
                "validation_x",
                "train_y",
                "validation_y",
                "train_symbols",
                "validation_symbols",
                "calibration_symbols",
            )
        },
    }


def write_uncached_digest(fold: Any, prepared: Any, cache_id: str) -> None:
    """Called by the training loop before cache publication when DIGEST_ENV is set."""

    target = os.environ.get(DIGEST_ENV, "").strip()
    if not target:
        return
    payload = {**prepared_digest(fold, prepared), "cache_id": cache_id, "source": "UNCACHED"}
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _differences(left: Any, right: Any, prefix: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        found: list[str] = []
        for key in sorted(set(left) | set(right)):
            found.extend(_differences(left.get(key), right.get(key), f"{prefix}/{key}"))
        return found
    return [] if left == right else [prefix or "/"]


def current_source_digests() -> dict[str, str]:
    from crypto_ai.phase7.preparation_identity import preparation_source_identity
    from crypto_ai.phase7.training import training_source_identity

    return {
        "scientific_source_digest": training_source_identity()["manifest_sha256"],
        "preparation_digest": preparation_source_identity()["manifest_sha256"],
    }


def qualify(
    *,
    uncached_digest_path: Path,
    cache_root: Path,
    gold_manifest: Path,
    sidecar: Path,
    config_path: Path,
    resource_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from crypto_ai.data.storage import file_sha256
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.identity_summary import identity_summary
    from crypto_ai.phase7.prepared_cache import PreparedDataCache

    uncached = json.loads(uncached_digest_path.read_text(encoding="utf-8"))
    if uncached.get("schema") != DIGEST_SCHEMA or uncached.get("source") != "UNCACHED":
        raise ValueError("uncached digest file is not a prepare-run digest")
    cache_id = str(uncached["cache_id"])
    entry = cache_root / cache_id
    manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
    config = load_phase7_config(config_path)
    plans = {
        plan.fold_id: plan
        for plan in plan_folds(
            config.data_start,
            config.research_cutoff,
            config.prospective_holdout_start,
            config.schedule,
        )
    }
    plan = plans[uncached["fold_id"]]
    bundle = PreparedDataCache(cache_root, "read_only").load(manifest["identity"], plan)
    cached = {**prepared_digest(bundle.fold, bundle.prepared), "cache_id": bundle.cache_id}
    comparable_uncached = {key: value for key, value in uncached.items() if key != "source"}
    differences = _differences(comparable_uncached, cached)
    identities = identity_summary(gold_manifest, sidecar)
    record = {
        "schema": VALIDATION_SCHEMA,
        "status": "VALIDATED" if not differences else "FAILED",
        "memory_profile": "low_memory",
        "comparison": "UNCACHED_PREPARATION_VS_READ_ONLY_RELOAD",
        "differences": differences,
        "fold_id": uncached["fold_id"],
        "cache_id": cache_id,
        "cache_manifest_sha256": file_sha256(entry / "manifest.json"),
        "cache_files": manifest["files"],
        "uncached_digest_sha256": file_sha256(uncached_digest_path),
        "tables_compared": sorted(uncached["tables"]),
        "arrays_compared": sorted(uncached["arrays"]),
        "row_counts": {name: item["rows"] for name, item in uncached["tables"].items()},
        **current_source_digests(),
        "identities": identities,
        "resource_evidence": resource_evidence or {},
        "holdout": config.holdout_status_payload(),
    }
    return record


def require_validation(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Admission helper: the named record must be VALIDATED for the CURRENT source."""

    env = os.environ if environ is None else environ
    value = env.get(VALIDATION_ENV, "").strip()
    if not value:
        raise ValueError(
            "LOW_MEMORY_VALIDATION_REQUIRED: training under the low-memory profile needs a "
            f"VALIDATED cached-vs-uncached record named by {VALIDATION_ENV}"
        )
    from crypto_ai.data.storage import file_sha256

    path = Path(value)
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != VALIDATION_SCHEMA or record.get("status") != "VALIDATED":
        raise ValueError("LOW_MEMORY_VALIDATION_REQUIRED: record is not VALIDATED")
    if record.get("differences"):
        raise ValueError("LOW_MEMORY_VALIDATION_REQUIRED: record lists differences")
    current = current_source_digests()
    for key, expected in current.items():
        if record.get(key) != expected:
            raise ValueError(f"LOW_MEMORY_VALIDATION_STALE: {key} changed since validation")
    return {"path": str(path.resolve()), "sha256": file_sha256(path), "record": record}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uncached-digest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--gold-manifest", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase7/research_core20_primary_v1.toml")
    )
    parser.add_argument("--resource-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = (
        json.loads(args.resource_evidence.read_text(encoding="utf-8"))
        if args.resource_evidence
        else None
    )
    record = qualify(
        uncached_digest_path=args.uncached_digest,
        cache_root=args.cache_root,
        gold_manifest=args.gold_manifest,
        sidecar=args.sidecar,
        config_path=args.config,
        resource_evidence=evidence,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": record["status"], "differences": record["differences"]}))
    return 0 if record["status"] == "VALIDATED" else 3


if __name__ == "__main__":
    sys.exit(main())
