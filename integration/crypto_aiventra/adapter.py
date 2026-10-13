"""Bounded metadata observations. Never scans market rows, fits, or unlocks TEST."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psutil

from .config import CONFIG_HASH, GOLD_ID, RUN_ID, CryptoPaths, git

MAX_DOCUMENT = 256 * 1024
METRICS = (
    "mae",
    "rmse",
    "r2",
    "directional_accuracy",
    "pearson_ic",
    "spearman_ic",
    "coverage",
    "cross_sectional_ic",
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact(item)
            for key, item in value.items()
            if not any(
                word in key.lower() for word in ("password", "token", "secret", "credential")
            )
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(api[_-]?key|password|secret|authorization)\s*[:=]\s*[^\n,;]+",
            r"\1=[REDACTED]",
            value,
        )
        value = re.sub(
            r"\b(?:sk-|gsk_|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{16,}", "[REDACTED]", value
        )
        for name, secret in os.environ.items():
            if (
                any(word in name.upper() for word in ("PASSWORD", "TOKEN", "SECRET", "API_KEY"))
                and len(secret) >= 12
            ):
                value = value.replace(secret, "[REDACTED]")
    return value


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size > MAX_DOCUMENT:
        raise ValueError("Metadata is aliased or exceeds the bounded document limit")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Metadata must be a JSON object")
    return result


class Crypto2Adapter:
    def __init__(self, paths: CryptoPaths | None = None):
        self.paths = paths or CryptoPaths.from_environment()

    def get_project_identity(self):
        from crypto_ai.phase5.folds import plan_folds
        from crypto_ai.phase7.config import load_phase7_config
        from crypto_ai.phase7.phase7a import primary_specs
        from crypto_ai.phase7.training import scientific_source_identity

        config = load_phase7_config(
            self.paths.repo / "configs/phase7/research_core20_primary_v1.toml"
        )
        if config.configuration_hash != CONFIG_HASH:
            raise ValueError("Canonical Crypto configuration changed; integration is blocked")
        folds = plan_folds(
            config.data_start,
            config.research_cutoff,
            config.prospective_holdout_start,
            config.schedule,
        )
        demo = os.environ.get("CRYPTO_DEMO_FIXTURE_STATE") == "1"
        if demo and not self.paths.runtime.is_relative_to(
            self.paths.repo / "aiventra/data/pytest-temp"
        ):
            raise ValueError("Demo mode requires an explicitly isolated browser fixture root")
        return {
            "name": "Crypto 2.0",
            "phase": "7A",
            "profile": "CORE20_PRIMARY",
            "mode": "DEMO_FIXTURE_STATE" if demo else "REAL_CRYPTO_STATE",
            "role": "SCIENTIFIC_ENGINE",
            "control_plane": "AIVENTRA_OS",
            "run_identity": RUN_ID,
            "configuration_hash": config.configuration_hash,
            "branch": git(self.paths.repo, "branch", "--show-current"),
            "git_commit": git(self.paths.repo, "rev-parse", "HEAD"),
            "scientific_source_identity": scientific_source_identity(self.paths.repo),
            "operation_source_identity": hashlib.sha256(
                b"".join(
                    str(path.relative_to(self.paths.repo)).encode()
                    + hashlib.sha256(path.read_bytes()).digest()
                    for path in sorted(
                        [
                            *(self.paths.repo / "integration/crypto_aiventra").glob("*.py"),
                            self.paths.repo / "aiventra/apps/api/company_os/crypto_control.py",
                            self.paths.repo
                            / "aiventra/apps/api/company_os/routes/crypto_operations.py",
                        ]
                    )
                )
            ).hexdigest(),
            "folds_expected": len(folds),
            "specs_expected": len(primary_specs(config)),
            "features": 109,
            "physical_columns": 130,
            "research_view": "CORE",
            "feature_group": "A6",
            "research_cutoff": config.research_cutoff.isoformat(),
            "july_2026_used": False,
            **config.holdout_status_payload(),
            "scientific_execution_authorized": False,
        }

    def _canonical(self):
        from crypto_ai.phase5.folds import plan_folds
        from crypto_ai.phase7.config import load_phase7_config
        from crypto_ai.phase7.phase7a import primary_specs

        config = load_phase7_config(
            self.paths.repo / "configs/phase7/research_core20_primary_v1.toml"
        )
        if config.configuration_hash != CONFIG_HASH:
            raise ValueError("Canonical configuration drift")
        return (
            config,
            plan_folds(
                config.data_start,
                config.research_cutoff,
                config.prospective_holdout_start,
                config.schedule,
            ),
            primary_specs(config),
        )

    def get_dataset_status(self):
        root = self.paths.gold
        path = root / "manifest.json"
        if not path.is_file():
            path = root / GOLD_ID / "manifest.json"
        result = {
            "dataset_id": GOLD_ID,
            "status": "AWAITING_EVIDENCE",
            "partitions_expected": 138,
            "rows_expected": 50_352_548,
            "production_features": 109,
            "physical_columns": 130,
            "protected": True,
            "market_rows_read": False,
            "byte_validation": "NOT_RUN",
        }
        try:
            manifest = read_json(path)
            if manifest is not None:
                if (
                    manifest.get("dataset_id") != GOLD_ID
                    or manifest.get("prospective_holdout_used") is not False
                    or manifest.get("prospective_holdout_evaluation_authorized") is not False
                    or manifest.get("prospective_holdout_status") != "LOCKED_UNUSED"
                ):
                    raise ValueError("Gold identity/holdout metadata mismatch")
                result.update(
                    status="MANIFEST_PRESENT_NOT_BYTE_VALIDATED",
                    manifest_path=str(path),
                    partitions_declared=len(manifest.get("partition_files", [])),
                    rows_declared=manifest.get("rows", manifest.get("row_count")),
                )
        except (OSError, ValueError, TypeError):
            result.update(status="CORRUPT_OR_INCONSISTENT", error="Gold metadata is not trusted")
        return result

    def get_lineage_status(self):
        # A dated handoff is not live proof of restored lineage or current data hashes.
        root = self.paths.historical / RUN_ID
        result = {
            "status": "AWAITING_EVIDENCE",
            "registry_hash": None,
            "universe_hash": None,
            "fold_descriptor_identity": None,
            "silver_manifests_verified": None,
            "silver_partitions_verified": None,
            "derivative_bindings_verified": None,
            "full_lineage_closure": "NOT_VERIFIED",
            "protected": True,
        }
        for filename, field, key in (
            ("registry/symbol_registry.json", "registry_hash", "registry_hash"),
            ("universe/core_universe.json", "universe_hash", "universe_hash"),
        ):
            try:
                evidence = read_json(root / filename)
                if evidence:
                    result[field] = evidence.get(key)
                    result["status"] = "PARTIAL_METADATA_NOT_VALIDATED"
            except (OSError, ValueError):
                result["status"] = "CORRUPT_EVIDENCE"
        return result

    def _report_path(self, fold_id: str, spec_id: str) -> Path:
        return self.paths.reports / RUN_ID / "models/core" / fold_id / spec_id / "report.json"

    def get_model_results(self, fold_id: str | None = None):
        config, folds, specs = self._canonical()
        fold_id = fold_id or folds[0].fold_id
        if fold_id not in {fold.fold_id for fold in folds}:
            raise ValueError("Unknown canonical fold")
        records = []
        current_source = None
        for position, spec in enumerate(specs, 1):
            row = {
                "position": position,
                "spec_id": spec.name,
                **asdict(spec),
                "fold_id": fold_id,
                "seed": config.models.seed,
                "status": "AWAITING_EVIDENCE",
                "metrics": None,
                "best_iteration": None,
                "duration_seconds": None,
                "model_size_bytes": None,
                "artifact_integrity": "NOT_VERIFIED",
            }
            try:
                path = self._report_path(fold_id, spec.name)
                report = read_json(path)
                if report:
                    if current_source is None:
                        from crypto_ai.phase7.training import scientific_source_identity

                        current_source = scientific_source_identity(self.paths.repo)
                    identity = report.get("checkpoint_identity", {})
                    if (
                        identity.get("configuration_hash") != CONFIG_HASH
                        or identity.get("gold_dataset_id") != GOLD_ID
                        or identity.get("fold_id") != fold_id
                        or identity.get("experiment_id") != spec.name
                        or identity.get("training_source_identity") != current_source
                        or report.get("prospective_holdout_used") is not False
                        or report.get("prospective_holdout_evaluation_authorized") is not False
                        or report.get("prospective_holdout_status") != "LOCKED_UNUSED"
                        or report.get("july_2026_used") is not False
                    ):
                        raise ValueError("Report identity mismatch")
                    status = report.get("status")
                    if status not in {"COMPLETE", "INELIGIBLE"}:
                        raise ValueError("Report is not a completed canonical outcome")
                    # Reported metrics are not model/checkpoint qualification.
                    metrics = report.get("test_metrics", {})
                    row.update(
                        status="REPORTED_" + status,
                        metrics=redact(metrics),
                        best_iteration=report.get("model", {}).get("best_iteration"),
                        source_path=str(path),
                        report_sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                    )
            except (OSError, ValueError, TypeError):
                row.update(
                    status="CORRUPT_OR_INCONSISTENT",
                    error="Report evidence failed metadata validation",
                )
            records.append(row)
        return records

    def get_fold_status(self):
        _, folds, _ = self._canonical()
        records = []
        for fold in folds:
            reports = self.get_model_results(fold.fold_id)
            reported = sum(row["status"] == "REPORTED_COMPLETE" for row in reports)
            failed = sum(row["status"] == "CORRUPT_OR_INCONSISTENT" for row in reports)
            evidence_present = any(row["status"] != "AWAITING_EVIDENCE" for row in reports)
            records.append(
                {
                    **fold.to_dict(),
                    "display_fold": fold.index + 1,
                    "status": "BLOCKED"
                    if failed
                    else "STARTED_NOT_COMPLETE"
                    if evidence_present
                    else "AWAITING_EVIDENCE",
                    "specs_expected": 48,
                    "reports_reported_complete": reported,
                    "models_verified_complete": None,
                    "reports_verified_complete": None,
                    "prepared_cache_state": "NOT_VERIFIED",
                    "start_time": None,
                    "completion_time": None,
                    "errors": failed,
                    "qualification": "NOT_EVALUATED",
                }
            )
        return records

    def get_preparation_status(self):
        entries = []
        if self.paths.cache.is_dir():
            for entry in sorted(self.paths.cache.iterdir())[:256]:
                if not re.fullmatch(r"[a-f0-9]{64}", entry.name):
                    continue
                row = {"cache_id": entry.name, "status": "INCOMPLETE_OR_CORRUPT", "protected": True}
                try:
                    payload = read_json(entry / "manifest.json")
                    if payload and payload.get("cache_id") == entry.name:
                        identity = payload.get("identity", {})
                        if (
                            identity.get("configuration_hash") == CONFIG_HASH
                            and identity.get("gold_dataset_id") == GOLD_ID
                        ):
                            row.update(
                                status="PUBLISHED_NOT_VALIDATED",
                                identity=redact(identity),
                                arrays=payload.get("arrays"),
                                tables=payload.get("tables"),
                            )
                except (OSError, ValueError, TypeError):
                    pass
                entries.append(row)
        return {
            "status": "PUBLISHED_NOT_VALIDATED" if entries else "AWAITING_EVIDENCE",
            "entries": entries,
            "stage": None,
            "elapsed_seconds": None,
            "progress_percent": None,
            "stage_order": [
                "Loading Gold",
                "Slicing fold",
                "Preparing segments",
                "Architecture inputs",
                "Publishing cache",
                "Cache validation",
            ],
        }

    def get_training_status(self):
        try:
            progress = read_json(self.paths.logs / RUN_ID / "progress.json")
            if progress is None:
                progress = read_json(self.paths.historical / RUN_ID / "progress.json")
        except (OSError, ValueError):
            return {"status": "CORRUPT_EVIDENCE", "progress": None}
        if progress and progress.get("run_identity") != RUN_ID:
            return {"status": "INCONSISTENT", "progress": None}
        return {
            "status": "PROGRESS_EVIDENCE_PRESENT" if progress else "AWAITING_EVIDENCE",
            "progress": redact(progress),
            "actual_device": None,
            "boosting_iteration": None,
            "best_iteration": None,
            "specs_expected": 48,
        }

    def get_resource_usage(self):
        vm = psutil.virtual_memory()
        disk_path = self.paths.persistent
        while not disk_path.exists():
            disk_path = disk_path.parent
        disk = shutil.disk_usage(disk_path)
        return {
            "observed_at": time.time(),
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "cpu_sample_seconds": 0.1,
            "ram_total_bytes": vm.total,
            "ram_available_bytes": vm.available,
            "process_rss_bytes": psutil.Process().memory_info().rss,
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
            "adapter_pid": os.getpid(),
            "gpu": "NOT_PROBED",
            "gpu_required": False,
            "worker_pid": None,
        }

    def get_holdout_status(self):
        identity = self.get_project_identity()
        return {
            key: identity[key]
            for key in (
                "prospective_holdout_status",
                "prospective_holdout_used",
                "prospective_holdout_evaluation_authorized",
                "prospective_holdout_start",
                "july_2026_used",
            )
        }

    def artifact_roots(self):
        return {
            name: getattr(self.paths, name)
            for name in (
                "cache",
                "models",
                "reports",
                "logs",
                "checkpoints",
                "verification",
                "historical",
            )
        }

    def artifact_path(self, category: str, relative: str) -> Path:
        roots = self.artifact_roots()
        if category not in roots or not relative or len(relative) > 600:
            raise ValueError("Unknown artifact category/path")
        value = Path(relative)
        if (
            value.is_absolute()
            or ".." in value.parts
            or any(part.startswith(".") for part in value.parts)
        ):
            raise ValueError("Unsafe artifact path")
        if re.search(
            r"(?i)(2026[-_/]0[78]|august|july|holdout|secret|credential|id_rsa)", relative
        ):
            raise ValueError("Protected or private artifact path")
        root = roots[category].resolve()
        target = (root / value).resolve()
        if not target.is_relative_to(root) or any(
            (root / Path(*value.parts[:i])).is_symlink() for i in range(1, len(value.parts) + 1)
        ):
            raise ValueError("Artifact path escaped approved root or is aliased")
        if any(
            target.is_relative_to(protected) for protected in (self.paths.gold, self.paths.data)
        ):
            raise ValueError("Market data is not an artifact-browser target")
        return target

    def get_artifacts(self, category: str = "reports", relative: str = "."):
        # Do not recursively crawl a scientific disk; one bounded directory page only.
        root = self.artifact_roots().get(category)
        if root is None:
            raise ValueError("Unknown artifact category")
        if root.is_symlink() or any(
            root.resolve().is_relative_to(item.resolve())
            for item in (self.paths.gold, self.paths.data)
        ):
            raise ValueError("Market data or aliased roots cannot be browsed")
        directory = root if relative == "." else self.artifact_path(category, relative)
        if not directory.is_dir():
            return {"status": "AWAITING_EVIDENCE", "entries": []}
        entries = []
        for path in sorted(directory.iterdir())[:200]:
            child = path.relative_to(root).as_posix()
            try:
                self.artifact_path(category, child)
            except ValueError:
                continue
            entries.append(
                {
                    "name": path.name,
                    "relative_path": child,
                    "directory": path.is_dir(),
                    "bytes": None if path.is_dir() else path.stat().st_size,
                    "protected": True,
                }
            )
        return {"status": "READ_ONLY", "entries": entries}

    def get_logs(self, category: str, relative: str, *, tail: bool = False):
        path = self.artifact_path(category, relative)
        if path.suffix.lower() not in {".json", ".md", ".csv", ".txt", ".log"}:
            raise ValueError("Only bounded text metadata may be inspected")
        if tail:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 64 * 1024))
                text = stream.read(64 * 1024).decode("utf-8", errors="replace")
        else:
            if path.stat().st_size > MAX_DOCUMENT:
                raise ValueError("Artifact exceeds document limit; use log tail")
            text = path.read_text(encoding="utf-8")
        return {
            "content": redact(text),
            "read_only": True,
            "truncated": tail and path.stat().st_size > 64 * 1024,
        }

    def snapshot(self):
        return {
            "identity": self.get_project_identity(),
            "dataset": self.get_dataset_status(),
            "lineage": self.get_lineage_status(),
            "folds": self.get_fold_status(),
            "models": self.get_model_results(),
            "preparation": self.get_preparation_status(),
            "training": self.get_training_status(),
            "resources": self.get_resource_usage(),
            "holdout": self.get_holdout_status(),
            "observed_at": time.time(),
        }
