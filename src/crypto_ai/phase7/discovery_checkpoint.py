from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai import __version__
from crypto_ai.data.ingestion.manifest import read_manifest
from crypto_ai.data.quality.models import (
    QUALITY_REPORT_SCHEMA_VERSION,
    QUALITY_VALIDATOR_VERSION,
)
from crypto_ai.data.quality.policy import load_quality_policy
from crypto_ai.data.quality.promotion import SILVER_TRANSFORMATION_VERSION
from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.artifacts import atomic_json
from crypto_ai.phase7.config import (
    PHASE7_VERSION,
    SCIENTIFIC_BASELINE_ID,
    Phase7Config,
    stable_hash,
)
from crypto_ai.phase7.registry import SymbolRecord, SymbolRegistry
from crypto_ai.phase7.segments import (
    AcquisitionOutcome,
    AcquisitionStatus,
    CausalDataGap,
)

logger = logging.getLogger(__name__)

DISCOVERY_CHECKPOINT_SCHEMA_VERSION = "phase7_discovery_symbol_checkpoint_v1"
DISCOVERY_ACQUISITION_CONTRACT_VERSION = "phase7_discovery_acquisition_v1"
ARCHIVE_REST_RECONCILIATION_POLICY_VERSION = "archive_rest_reconciliation_v1"
ARCHIVE_MISSING_RECONCILIATION_POLICY_VERSION = "archive_missing_official_rest_exact_rows_v1"
CAUSAL_SEGMENT_POLICY_VERSION = "causal_segment_quarantine_v1"
DATA_QUALITY_EXCLUSION_POLICY_VERSION = "discovery_data_quality_exclusion_v1"


@dataclass(frozen=True, slots=True)
class _Evidence:
    files: tuple[dict[str, str], ...]
    identity: dict[str, Any]
    accepted_start: str
    accepted_end: str


def _read(path: Path) -> dict[str, Any]:
    payload = read_manifest(path)
    if payload is None:
        raise FileNotFoundError(path)
    return payload


def _path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Artifact path is missing")
    return Path(value).resolve()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _file_record(role: str, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {"role": role, "path": str(resolved), "sha256": file_sha256(resolved)}


def _unique_file_records(records: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    by_path: dict[str, dict[str, str]] = {}
    for record in records:
        prior = by_path.get(record["path"])
        if prior is not None and prior["sha256"] != record["sha256"]:
            raise ValueError(f"Conflicting evidence fingerprint: {record['path']}")
        by_path[record["path"]] = record
    return tuple(sorted(by_path.values(), key=lambda item: (item["path"], item["role"])))


class DiscoverySymbolCheckpointStore:
    """Run-scoped completed-discovery evidence with a network-free resume path."""

    def __init__(
        self,
        config: Phase7Config,
        registry: SymbolRegistry,
        *,
        run_identity: str,
    ) -> None:
        self.config = config
        self.registry = registry
        self.run_identity = run_identity
        data_root = config.paths.data_root.resolve() / "phase7"
        self.bronze_root = data_root / "bronze" / "binance"
        self.quality_root = data_root / "quality"
        self.silver_root = data_root / "silver" / "binance"
        self.root = (
            config.paths.checkpoint_root.resolve()
            / run_identity
            / "discovery"
            / DISCOVERY_ACQUISITION_CONTRACT_VERSION
            / PHASE7_VERSION
        )
        self._candidate_index: dict[tuple[str, str], list[Path]] | None = None
        self._contract = {
            "phase7_version": PHASE7_VERSION,
            "scientific_baseline": SCIENTIFIC_BASELINE_ID,
            "configuration_hash": config.configuration_hash,
            "run_identity": run_identity,
            "acquisition_contract_version": DISCOVERY_ACQUISITION_CONTRACT_VERSION,
            "ingestion_version": __version__,
            "candle_schema_version": CANDLE_SCHEMA_VERSION,
            "validator_version": QUALITY_VALIDATOR_VERSION,
            "quality_report_schema_version": QUALITY_REPORT_SCHEMA_VERSION,
            "quality_policy_hash": stable_hash(
                load_quality_policy(config.quality_config).model_dump(mode="json")
            ),
            "silver_transformation_version": SILVER_TRANSFORMATION_VERSION,
            "archive_rest_reconciliation_policy": (ARCHIVE_REST_RECONCILIATION_POLICY_VERSION),
            "archive_missing_reconciliation_policy": (
                ARCHIVE_MISSING_RECONCILIATION_POLICY_VERSION
            ),
            "causal_segment_policy": CAUSAL_SEGMENT_POLICY_VERSION,
            "data_quality_exclusion_policy": DATA_QUALITY_EXCLUSION_POLICY_VERSION,
        }

    def checkpoint_path(self, symbol: str, interval: str) -> Path:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("Discovery checkpoint symbol is invalid")
        if not interval or "/" in interval or "\\" in interval:
            raise ValueError("Discovery checkpoint interval is invalid")
        return self.root / normalized / f"{interval}.completed.json"

    def _expected_identity(
        self,
        record: SymbolRecord,
        interval: str,
        request_start: datetime,
        request_end: datetime,
    ) -> dict[str, Any]:
        return {
            **self._contract,
            "symbol": record.symbol,
            "interval": interval,
            "requested_range": {
                "start": _iso(request_start),
                "end_exclusive": _iso(request_end),
            },
            "registry_version": self.registry.version,
            "registry_hash": self.registry.registry_hash,
            "registry_record_hash": stable_hash(record.model_dump(mode="json")),
        }

    def load(
        self,
        record: SymbolRecord,
        *,
        interval: str,
        request_start: datetime,
        request_end: datetime,
    ) -> AcquisitionOutcome | None:
        path = self.checkpoint_path(record.symbol, interval)
        if not path.is_file():
            return None
        started = time.perf_counter()
        try:
            payload = _read(path)
            claimed = payload.get("checkpoint_hash")
            hashed = dict(payload)
            hashed.pop("checkpoint_hash", None)
            if claimed != stable_hash(hashed):
                raise ValueError("completion checkpoint hash mismatch")
            if (
                payload.get("schema_version") != DISCOVERY_CHECKPOINT_SCHEMA_VERSION
                or payload.get("status") != "COMPLETE"
                or payload.get("identity")
                != self._expected_identity(record, interval, request_start, request_end)
            ):
                raise ValueError("completion checkpoint identity mismatch")
            for item in payload.get("evidence_files", []):
                evidence_path = _path(item.get("path"))
                if file_sha256(evidence_path) != item.get("sha256"):
                    raise ValueError(f"evidence fingerprint mismatch: {evidence_path}")
            outcome = AcquisitionOutcome.model_validate(payload.get("outcome"))
            evidence = self._validate_outcome_evidence(
                outcome,
                record=record,
                interval=interval,
                request_start=request_start,
                request_end=request_end,
                deep=False,
            )
            if stable_hash(evidence.identity) != payload.get("artifact_identity"):
                raise ValueError("completion artifact identity mismatch")
        except (
            FileNotFoundError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(
                "Discovery symbol completion checkpoint rejected",
                extra={
                    "event": "discovery_symbol_checkpoint_invalid",
                    "symbol": record.symbol,
                    "interval": interval,
                    "checkpoint": str(path),
                    "reason": str(exc),
                },
            )
            return None
        logger.info(
            "Discovery symbol completion checkpoint verified",
            extra={
                "event": "discovery_symbol_checkpoint_hit",
                "symbol": record.symbol,
                "interval": interval,
                "checkpoint": str(path),
                "elapsed_seconds": time.perf_counter() - started,
                "binance_network_calls": 0,
                "validator_traversals": 0,
                "quality_reports_created": 0,
                "silver_promotions": 0,
            },
        )
        return outcome

    def complete(
        self,
        record: SymbolRecord,
        outcome: AcquisitionOutcome,
        *,
        interval: str,
        request_start: datetime,
        request_end: datetime,
        backfilled: bool = False,
        deep: bool = False,
    ) -> Path:
        existing = self.load(
            record,
            interval=interval,
            request_start=request_start,
            request_end=request_end,
        )
        path = self.checkpoint_path(record.symbol, interval)
        if existing is not None:
            return path
        evidence = self._validate_outcome_evidence(
            outcome,
            record=record,
            interval=interval,
            request_start=request_start,
            request_end=request_end,
            deep=deep,
        )
        payload: dict[str, Any] = {
            "schema_version": DISCOVERY_CHECKPOINT_SCHEMA_VERSION,
            "status": "COMPLETE",
            "completed_at": datetime.now(UTC).isoformat(),
            "backfilled_from_existing_evidence": backfilled,
            "identity": self._expected_identity(record, interval, request_start, request_end),
            "accepted_range": {
                "start": evidence.accepted_start,
                "end_exclusive": evidence.accepted_end,
            },
            "artifact_identity": stable_hash(evidence.identity),
            "artifact_identity_payload": evidence.identity,
            "evidence_files": list(evidence.files),
            "outcome": outcome.model_dump(mode="json"),
        }
        payload["checkpoint_hash"] = stable_hash(payload)
        atomic_json(path, payload)
        logger.info(
            "Discovery symbol completion checkpoint created",
            extra={
                "event": (
                    "discovery_symbol_checkpoint_backfilled"
                    if backfilled
                    else "discovery_symbol_checkpoint_created"
                ),
                "symbol": record.symbol,
                "interval": interval,
                "checkpoint": str(path),
                "artifact_identity": payload["artifact_identity"],
                "binance_network_calls": 0 if backfilled else None,
            },
        )
        return path

    def backfill(
        self,
        record: SymbolRecord,
        *,
        interval: str,
        request_start: datetime,
        request_end: datetime,
    ) -> AcquisitionOutcome | None:
        candidates = self._candidates().get((record.symbol, interval), [])
        proven: list[tuple[AcquisitionOutcome, _Evidence]] = []
        for candidate in candidates:
            try:
                payload = _read(candidate)
                if payload.get("manifest_kind") == "phase7_causal_segment_group":
                    outcome = AcquisitionOutcome(
                        symbol=record.symbol,
                        interval=interval,
                        status=AcquisitionStatus.QUALITY_REJECTED_SEGMENT,
                        silver_manifest=str(candidate.resolve()),
                        reason=(
                            "official-source reconciliation could not prove a usable "
                            "historical interval"
                        ),
                        gaps=tuple(
                            CausalDataGap.model_validate(item)
                            for item in payload.get("unusable_segments", [])
                        ),
                    )
                else:
                    outcome = AcquisitionOutcome(
                        symbol=record.symbol,
                        interval=interval,
                        status=AcquisitionStatus.VALID,
                        silver_manifest=str(candidate.resolve()),
                    )
                evidence = self._validate_outcome_evidence(
                    outcome,
                    record=record,
                    interval=interval,
                    request_start=request_start,
                    request_end=request_end,
                    deep=True,
                )
                proven.append((outcome, evidence))
            except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
                continue
        if not proven:
            logger.info(
                "No unambiguous completed discovery evidence was available",
                extra={
                    "event": "discovery_symbol_backfill_unavailable",
                    "symbol": record.symbol,
                    "interval": interval,
                    "candidate_count": len(candidates),
                },
            )
            return None
        identities = {stable_hash(item[1].identity) for item in proven}
        if len(identities) != 1:
            logger.warning(
                "Ambiguous completed discovery evidence was refused",
                extra={
                    "event": "discovery_symbol_backfill_ambiguous",
                    "symbol": record.symbol,
                    "interval": interval,
                    "proven_candidate_count": len(proven),
                    "artifact_identity_count": len(identities),
                },
            )
            return None
        outcome = sorted(proven, key=lambda item: str(item[0].silver_manifest))[0][0]
        self.complete(
            record,
            outcome,
            interval=interval,
            request_start=request_start,
            request_end=request_end,
            backfilled=True,
            deep=True,
        )
        return self.load(
            record,
            interval=interval,
            request_start=request_start,
            request_end=request_end,
        )

    def _candidates(self) -> dict[tuple[str, str], list[Path]]:
        if self._candidate_index is not None:
            return self._candidate_index
        index: dict[tuple[str, str], list[Path]] = {}
        for path in sorted((self.silver_root / "manifests").glob("*.json")):
            try:
                payload = _read(path)
                if payload.get("manifest_kind") == "phase7_causal_segment_group":
                    symbol = str(payload["symbol"]).upper()
                    interval = str(payload["interval"])
                else:
                    source = _read(_path(payload.get("source_manifest")))
                    if str(source.get("run_id", "")).startswith("segmented-"):
                        continue
                    symbol = str(source["symbol"]).upper()
                    interval = str(source["interval"])
            except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
                continue
            index.setdefault((symbol, interval), []).append(path.resolve())
        self._candidate_index = index
        return index

    def _validate_outcome_evidence(
        self,
        outcome: AcquisitionOutcome,
        *,
        record: SymbolRecord,
        interval: str,
        request_start: datetime,
        request_end: datetime,
        deep: bool,
    ) -> _Evidence:
        if outcome.symbol != record.symbol or outcome.interval != interval:
            raise ValueError("Outcome symbol/interval mismatch")
        if outcome.status is AcquisitionStatus.SYMBOL_EXCLUDED_DATA_QUALITY:
            return self._validate_exclusion(
                outcome,
                record=record,
                interval=interval,
                request_start=request_start,
                request_end=request_end,
            )
        if outcome.status not in {
            AcquisitionStatus.VALID,
            AcquisitionStatus.QUALITY_REJECTED_SEGMENT,
        }:
            raise ValueError("Only accepted discovery outcomes can be checkpointed")
        silver_path = _path(outcome.silver_manifest)
        silver = _read(silver_path)
        if silver.get("manifest_kind") == "phase7_causal_segment_group":
            return self._validate_segment_group(
                outcome,
                silver_path,
                silver,
                record=record,
                interval=interval,
                request_start=request_start,
                request_end=request_end,
                deep=deep,
            )
        if outcome.status is not AcquisitionStatus.VALID:
            raise ValueError("Segmented outcome requires a causal segment-group manifest")
        return self._validate_ordinary(
            silver_path,
            silver,
            record=record,
            interval=interval,
            request_start=request_start,
            request_end=request_end,
            deep=deep,
        )

    def _validate_exclusion(
        self,
        outcome: AcquisitionOutcome,
        *,
        record: SymbolRecord,
        interval: str,
        request_start: datetime,
        request_end: datetime,
    ) -> _Evidence:
        path = _path(outcome.exclusion_evidence)
        payload = _read(path)
        expected_range = {
            "start": _iso(request_start),
            "end_exclusive": _iso(request_end),
        }
        if (
            payload.get("schema_version") != DATA_QUALITY_EXCLUSION_POLICY_VERSION
            or payload.get("status") != AcquisitionStatus.SYMBOL_EXCLUDED_DATA_QUALITY.value
            or str(payload.get("symbol", "")).upper() != record.symbol
            or payload.get("market") != "usdm"
            or payload.get("interval") != interval
            or payload.get("configuration_hash") != self.config.configuration_hash
            or payload.get("run_identity") != self.run_identity
            or payload.get("scientific_baseline") != SCIENTIFIC_BASELINE_ID
            or payload.get("requested_range") != expected_range
            or not payload.get("failed_checks")
            or not payload.get("reconciliation_mechanisms_attempted")
            or not payload.get("final_exclusion_reason")
            or payload.get("raw_sources_mutated") is not False
            or payload.get("fabricated_rows") is not False
        ):
            raise ValueError("Data-quality exclusion identity is incompatible")
        evidence_files = payload.get("evidence_files", [])
        if not evidence_files:
            raise ValueError("Data-quality exclusion lacks immutable evidence")
        files = [_file_record("exclusion_evidence", path)]
        for item in evidence_files:
            evidence_path = _path(item.get("path"))
            if file_sha256(evidence_path) != item.get("sha256"):
                raise ValueError(f"Exclusion evidence fingerprint mismatch: {evidence_path}")
            files.append(_file_record(str(item.get("role", "evidence")), evidence_path))
        identity = {
            "exclusion_evidence_sha256": file_sha256(path),
            "evidence_files": evidence_files,
            "failed_checks": payload.get("failed_checks"),
            "affected_timestamps": payload.get("affected_timestamps"),
            "final_exclusion_reason": payload.get("final_exclusion_reason"),
        }
        return _Evidence(
            _unique_file_records(files),
            identity,
            expected_range["start"],
            expected_range["end_exclusive"],
        )

    def _validate_ordinary(
        self,
        silver_path: Path,
        silver: dict[str, Any],
        *,
        record: SymbolRecord,
        interval: str,
        request_start: datetime,
        request_end: datetime,
        deep: bool,
    ) -> _Evidence:
        source_path = _path(silver.get("source_manifest"))
        source = _read(source_path)
        report_id = str(silver.get("validation_report_id", ""))
        report_path = (self.quality_root / f"{report_id}.json").resolve()
        report = _read(report_path)
        if (
            str(source.get("symbol", "")).upper() != record.symbol
            or source.get("interval") != interval
            or not str(source.get("source", "")).startswith("binance")
            or source.get("market") != "usdm"
            or source.get("status") not in {"completed", "completed_with_quality_errors"}
            or source.get("schema_version") != CANDLE_SCHEMA_VERSION
            or source.get("ingestion_version") != __version__
        ):
            raise ValueError("Bronze source identity is incompatible")
        accepted_start = str(source.get("start", ""))
        accepted_end = str(source.get("end", ""))
        parsed_start = datetime.fromisoformat(accepted_start.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(accepted_end.replace("Z", "+00:00"))
        if not (
            request_start.astimezone(UTC)
            <= parsed_start.astimezone(UTC)
            < parsed_end.astimezone(UTC)
            <= request_end.astimezone(UTC)
        ):
            raise ValueError("Accepted Bronze bounds are outside the frozen request")
        if (
            report.get("report_id") != report_id
            or report.get("overall_status") not in {"PASS", "WARN"}
            or report.get("validator_version") != QUALITY_VALIDATOR_VERSION
            or report.get("report_schema_version") != QUALITY_REPORT_SCHEMA_VERSION
            or _path(report.get("source_manifest")) != source_path
            or report.get("dataset_version") != silver.get("source_dataset_version")
            or report.get("range", {}).get("start") != accepted_start
            or report.get("range", {}).get("end") != accepted_end
            or stable_hash(report.get("policy")) != self._contract["quality_policy_hash"]
            or any(item.get("status") == "FAIL" for item in report.get("checks", []))
        ):
            raise ValueError("Quality evidence is incompatible or not successful")
        if (
            silver.get("quality_status") not in {"PASS", "WARN"}
            or silver.get("validation_version") != QUALITY_VALIDATOR_VERSION
            or silver.get("transformation") != SILVER_TRANSFORMATION_VERSION
        ):
            raise ValueError("Silver identity is incompatible")

        partitions = {
            str(item.get("file")): item
            for item in source.get("partitions", [])
            if isinstance(item, dict) and item.get("file")
        }
        source_identity: list[dict[str, Any]] = []
        for item in report.get("source_files", []):
            relative = str(item.get("relative_path", ""))
            partition = partitions.get(relative)
            if (
                item.get("status") != "readable"
                or partition is None
                or partition.get("status") != "complete"
                or partition.get("sha256") != item.get("sha256")
                or partition.get("row_count") != item.get("row_count")
            ):
                raise ValueError("Bronze partition/report lineage mismatch")
            data_path = self.bronze_root / relative
            self._verify_data_file(data_path, str(item.get("sha256")), deep=deep)
            source_identity.append(
                {
                    "relative_path": relative,
                    "sha256": item.get("sha256"),
                    "row_count": item.get("row_count"),
                }
            )

        output_identity: list[dict[str, Any]] = []
        for item in silver.get("output_files", []):
            relative = str(item.get("file", ""))
            output_path = self.silver_root / relative
            self._verify_data_file(output_path, str(item.get("sha256")), deep=deep)
            if item.get("source_sha256") not in {entry["sha256"] for entry in source_identity}:
                raise ValueError("Silver output lacks accepted Bronze lineage")
            output_identity.append(
                {
                    "file": relative,
                    "sha256": item.get("sha256"),
                    "source_sha256": item.get("source_sha256"),
                    "row_count": item.get("row_count"),
                }
            )
        if not source_identity or not output_identity:
            raise ValueError("Accepted discovery evidence cannot be empty")
        files = _unique_file_records(
            [
                _file_record("bronze_manifest", source_path),
                _file_record("quality_report", report_path),
                _file_record("silver_manifest", silver_path),
            ]
        )
        identity = {
            "bronze_manifest": next(item for item in files if item["path"] == str(source_path)),
            "bronze_run_id": source.get("run_id"),
            "bronze_dataset_version": report.get("dataset_version"),
            "bronze_source_files": stable_hash(source_identity),
            "quality_report_id": report_id,
            "quality_report_sha256": file_sha256(report_path),
            "silver_dataset_version": silver.get("silver_dataset_version"),
            "silver_manifest_sha256": file_sha256(silver_path),
            "silver_outputs": stable_hash(output_identity),
            "quality_status": silver.get("quality_status"),
        }
        return _Evidence(files, identity, accepted_start, accepted_end)

    def _validate_segment_group(
        self,
        outcome: AcquisitionOutcome,
        group_path: Path,
        group: dict[str, Any],
        *,
        record: SymbolRecord,
        interval: str,
        request_start: datetime,
        request_end: datetime,
        deep: bool,
    ) -> _Evidence:
        if (
            outcome.status is not AcquisitionStatus.QUALITY_REJECTED_SEGMENT
            or group.get("quality_status") != "SEGMENTED_VALID"
            or str(group.get("symbol", "")).upper() != record.symbol
            or group.get("interval") != interval
            or group.get("segment_identity", {}).get("segmenter_version")
            != CAUSAL_SEGMENT_POLICY_VERSION
            or group.get("raw_sources_mutated") is not False
            or group.get("corrupt_rows_promoted") is not False
        ):
            raise ValueError("Causal segment-group identity is incompatible")
        source_path = _path(group.get("source_manifest"))
        source = _read(source_path)
        if file_sha256(source_path) != group.get("source_manifest_sha256"):
            raise ValueError("Causal group source fingerprint mismatch")
        accepted_start = str(source.get("start", ""))
        accepted_end = str(source.get("end", ""))
        parsed_start = datetime.fromisoformat(accepted_start.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(accepted_end.replace("Z", "+00:00"))
        if not (
            request_start.astimezone(UTC)
            <= parsed_start.astimezone(UTC)
            < parsed_end.astimezone(UTC)
            <= request_end.astimezone(UTC)
        ):
            raise ValueError("Segment source bounds are outside the frozen request")
        gaps = tuple(
            CausalDataGap.model_validate(item) for item in group.get("unusable_segments", [])
        )
        if not gaps or gaps != outcome.gaps:
            raise ValueError("Segmented outcome/gap evidence mismatch")
        files = [
            _file_record("bronze_manifest", source_path),
            _file_record("segment_group_manifest", group_path),
        ]
        segment_identities: list[dict[str, Any]] = []
        for item in group.get("segments", []):
            bronze_path = _path(item.get("bronze_manifest"))
            child_path = _path(item.get("silver_manifest"))
            if file_sha256(bronze_path) != item.get("bronze_manifest_sha256") or file_sha256(
                child_path
            ) != item.get("silver_manifest_sha256"):
                raise ValueError("Causal child manifest fingerprint mismatch")
            child = _read(child_path)
            evidence = self._validate_ordinary(
                child_path,
                child,
                record=record,
                interval=interval,
                request_start=parsed_start,
                request_end=parsed_end,
                deep=deep,
            )
            files.extend(evidence.files)
            segment_identities.append(evidence.identity)
        for gap in gaps:
            for role, value, expected in (
                ("failed_quality_report", gap.quality_report, gap.quality_report_sha256),
                ("quarantine", gap.quarantine, gap.quarantine_sha256),
                ("rest_manifest", gap.rest_manifest, gap.rest_manifest_sha256),
                ("comparison_report", gap.comparison_report, gap.comparison_report_sha256),
            ):
                evidence_path = Path(value).resolve()
                if file_sha256(evidence_path) != expected:
                    raise ValueError(f"Causal gap evidence fingerprint mismatch: {evidence_path}")
                files.append(_file_record(role, evidence_path))
        identity = {
            "segment_group_sha256": file_sha256(group_path),
            "source_manifest_sha256": file_sha256(source_path),
            "segments": segment_identities,
            "gaps": [gap.model_dump(mode="json") for gap in gaps],
        }
        return _Evidence(_unique_file_records(files), identity, accepted_start, accepted_end)

    @staticmethod
    def _verify_data_file(path: Path, expected_sha256: str, *, deep: bool) -> None:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        if deep and file_sha256(resolved) != expected_sha256:
            raise ValueError(f"Immutable data fingerprint mismatch: {resolved}")
