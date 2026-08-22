from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.context.config import stable_hash
from crypto_ai.context.models import CollectionResult, ObservationClass, TrainingEligibility
from crypto_ai.context.quality import validate_context_table
from crypto_ai.data.storage import file_sha256

_VOLATILE_DEDUP_FIELDS = frozenset({"availability_time", "ingested_at", "raw_payload_checksum"})


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def resolve_git_sha() -> str:
    configured = os.environ.get("GIT_SHA", "").strip()
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    return result.stdout.strip() or "UNKNOWN"


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row_payload(row: dict[str, object], *, exclude_volatile: bool) -> dict[str, object]:
    return {
        key: _json_value(value)
        for key, value in sorted(row.items())
        if not exclude_volatile or key not in _VOLATILE_DEDUP_FIELDS
    }


def _atomic_bytes(path: Path, content: bytes) -> Path:
    path = path.resolve()
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"Refusing to overwrite different context artifact: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _atomic_parquet(path: Path, table: pa.Table) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary, compression="zstd", write_statistics=True)
        checksum = file_sha256(temporary)
        if path.exists():
            if file_sha256(path) != checksum:
                raise FileExistsError(f"Refusing to overwrite different context dataset: {path}")
            return path
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


class ContextStore:
    """Immutable, manifest-addressed storage for small contextual datasets."""

    def __init__(
        self,
        root: Path,
        *,
        provider_id: str,
        dataset_name: str,
        key_columns: tuple[str, ...],
        time_column: str = "provider_timestamp",
        expected_step: timedelta | None = None,
    ) -> None:
        self.root = root.resolve()
        self.provider_id = provider_id
        self.dataset_name = dataset_name
        self.key_columns = key_columns
        self.time_column = time_column
        self.expected_step = expected_step

    @property
    def provider_root(self) -> Path:
        return self.root / self.provider_id

    @property
    def manifest_root(self) -> Path:
        return self.provider_root / "manifests" / self.dataset_name

    def _valid_manifest(self, path: Path) -> dict[str, Any] | None:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("provider") != self.provider_id
                or manifest.get("dataset_name") != self.dataset_name
            ):
                return None
            identity_payload = dict(manifest)
            claimed_identity = identity_payload.pop("manifest_identity", None)
            if claimed_identity != stable_hash(identity_payload):
                return None
            dataset_path = Path(manifest["dataset_path"])
            raw_path = Path(manifest["raw_path"])
            if not dataset_path.is_file() or not raw_path.is_file():
                return None
            if file_sha256(dataset_path) != manifest.get("dataset_sha256"):
                return None
            if file_sha256(raw_path) != manifest.get("raw_payload_sha256"):
                return None
            return manifest
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def latest_manifest(self) -> tuple[Path, dict[str, Any]] | None:
        if not self.manifest_root.exists():
            return None
        valid: list[tuple[datetime, Path, dict[str, Any]]] = []
        for path in self.manifest_root.glob("*.json"):
            manifest = self._valid_manifest(path)
            if manifest is None:
                continue
            try:
                created = datetime.fromisoformat(str(manifest["ingested_at"]))
            except ValueError:
                continue
            valid.append((created, path, manifest))
        if not valid:
            return None
        _, path, manifest = max(valid, key=lambda item: (item[0], item[1].name))
        return path, manifest

    def load_latest(self) -> tuple[pa.Table, Path, dict[str, Any]] | None:
        latest = self.latest_manifest()
        if latest is None:
            return None
        path, manifest = latest
        table = pq.ParquetFile(Path(manifest["dataset_path"])).read()
        validate_context_table(
            table,
            key_columns=self.key_columns,
            time_column=self.time_column,
            expected_step=self.expected_step,
        )
        return table, path, manifest

    def persist(
        self,
        *,
        raw_payload: Any,
        table: pa.Table,
        ingested_at: datetime,
        source_endpoint: str,
        source_version: str,
        schema_version: str,
        observation_class: ObservationClass,
        eligibility: TrainingEligibility,
        eligibility_reason: str,
        config_hash: str,
        requested_start: datetime | None = None,
        requested_end: datetime | None = None,
        symbol: str | None = None,
        period: str | None = None,
        input_duplicate_count: int = 0,
        coverage_limitation: str | None = None,
        availability_policy: str | None = None,
    ) -> CollectionResult:
        captured = ingested_at.astimezone(UTC)
        quality = validate_context_table(
            table,
            key_columns=self.key_columns,
            time_column=self.time_column,
            expected_step=self.expected_step,
        )
        existing = self.load_latest()
        existing_rows: dict[tuple[object, ...], dict[str, object]] = {}
        existing_result: CollectionResult | None = None
        if existing is not None:
            old_table, old_manifest_path, old_manifest = existing
            if old_table.schema != table.schema:
                raise ValueError("Context schema changed without a new dataset namespace")
            for row in old_table.to_pylist():
                existing_rows[tuple(row[name] for name in self.key_columns)] = row
            existing_result = CollectionResult(
                dataset_version=str(old_manifest["dataset_version"]),
                dataset_path=Path(old_manifest["dataset_path"]),
                manifest_path=old_manifest_path,
                raw_path=Path(old_manifest["raw_path"]),
                row_count=int(old_manifest["row_count"]),
                duplicate_count=int(old_manifest.get("duplicate_count", 0)),
                reused=True,
            )

        overlap_duplicates = 0
        novel_rows = 0
        for row in table.to_pylist():
            key = tuple(row[name] for name in self.key_columns)
            previous = existing_rows.get(key)
            if previous is not None:
                if _row_payload(previous, exclude_volatile=True) != _row_payload(
                    row, exclude_volatile=True
                ):
                    raise ValueError(f"Conflicting context observation for key {key!r}")
                overlap_duplicates += 1
                continue
            existing_rows[key] = row
            novel_rows += 1
        if existing_result is not None and novel_rows == 0:
            return existing_result

        merged_rows = [existing_rows[key] for key in sorted(existing_rows)]
        merged = pa.Table.from_pylist(merged_rows, schema=table.schema)
        merged_quality = validate_context_table(
            merged,
            key_columns=self.key_columns,
            time_column=self.time_column,
            expected_step=self.expected_step,
        )
        semantic_rows = [_row_payload(row, exclude_volatile=True) for row in merged_rows]
        dataset_version = stable_hash(
            {
                "provider": self.provider_id,
                "dataset_name": self.dataset_name,
                "schema_version": schema_version,
                "rows": semantic_rows,
            },
            length=24,
        )
        raw_content = canonical_json_bytes(raw_payload)
        raw_checksum = hashlib.sha256(raw_content).hexdigest()
        raw_path = _atomic_bytes(self.provider_root / "raw" / f"{raw_checksum}.json", raw_content)
        dataset_path = _atomic_parquet(
            self.provider_root / self.dataset_name / "normalized" / f"{dataset_version}.parquet",
            merged,
        )
        manifest: dict[str, Any] = {
            "manifest_version": "context_manifest_v1",
            "provider": self.provider_id,
            "dataset_name": self.dataset_name,
            "dataset_version": dataset_version,
            "schema_version": schema_version,
            "observation_class": observation_class.value,
            "source_endpoint": source_endpoint,
            "source_version": source_version,
            "symbol": symbol,
            "period": period,
            "requested_start": requested_start.astimezone(UTC).isoformat()
            if requested_start
            else None,
            "requested_end": requested_end.astimezone(UTC).isoformat() if requested_end else None,
            "actual_start": merged_quality.first_timestamp,
            "actual_end": merged_quality.last_timestamp,
            "row_count": merged.num_rows,
            "new_row_count": novel_rows,
            "duplicate_count": input_duplicate_count + overlap_duplicates,
            "missing_timestamp_count": merged_quality.missing_timestamp_count,
            "missing_timestamps": list(merged_quality.missing_timestamps),
            "missing_timestamps_truncated": merged_quality.missing_timestamps_truncated,
            "quality_status": merged_quality.status,
            "raw_path": str(raw_path),
            "raw_payload_sha256": raw_checksum,
            "dataset_path": str(dataset_path),
            "dataset_sha256": file_sha256(dataset_path),
            "ingested_at": captured.isoformat(),
            "git_sha": resolve_git_sha(),
            "config_hash": config_hash,
            "training_eligibility": eligibility.value,
            "training_eligible": eligibility.training_eligible,
            "eligibility_reason": eligibility_reason,
            "availability_policy": availability_policy,
            "coverage_limitation": coverage_limitation,
            "previous_dataset_version": (
                existing_result.dataset_version if existing_result is not None else None
            ),
            "input_quality": {
                "row_count": quality.row_count,
                "first_timestamp": quality.first_timestamp,
                "last_timestamp": quality.last_timestamp,
            },
        }
        manifest["manifest_identity"] = stable_hash(manifest)
        manifest_path = _atomic_bytes(
            self.manifest_root / f"{dataset_version}.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        return CollectionResult(
            dataset_version=dataset_version,
            dataset_path=dataset_path,
            manifest_path=manifest_path,
            raw_path=raw_path,
            row_count=merged.num_rows,
            duplicate_count=input_duplicate_count + overlap_duplicates,
            reused=False,
        )
