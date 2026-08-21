from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.models import ValidationStatus
from crypto_ai.data.quality.policy import QualityPolicy
from crypto_ai.data.quality.promotion import SilverPromoter
from crypto_ai.data.storage import file_sha256, read_candle_parquet
from tests.factories import make_candle
from tests.quality_helpers import write_bronze_dataset


def _one_partition(tmp_path: Path, candles):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    return write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=5 * len(candles)), candles)],
    )


def test_passing_bronze_promotes_with_lineage_and_preserves_bronze(tmp_path: Path) -> None:
    manifest_path, bronze_files = _one_partition(
        tmp_path,
        [make_candle(index) for index in range(4)],
    )
    bronze_hashes = [file_sha256(path) for path in bronze_files]
    report = QualityEngine().validate_manifest(manifest_path)

    result = SilverPromoter().promote(
        manifest_path,
        report,
        silver_root=tmp_path / "silver",
        quarantine_root=tmp_path / "quarantine",
    )

    assert result.promoted
    assert result.promotion_manifest is not None and result.promotion_manifest.exists()
    assert len(result.output_files) == 1
    silver = result.output_files[0]
    assert read_candle_parquet(silver).num_rows == 4
    metadata = {
        key.decode(): value.decode()
        for key, value in (pq.ParquetFile(silver).schema_arrow.metadata or {}).items()
    }
    assert metadata["source_dataset_version"] == report.dataset_version
    assert metadata["validation_report_id"] == report.report_id
    assert metadata["silver_dataset_version"] == result.silver_dataset_version
    assert [file_sha256(path) for path in bronze_files] == bronze_hashes


def test_repeated_promotion_is_idempotent(tmp_path: Path) -> None:
    manifest_path, _ = _one_partition(tmp_path, [make_candle(0), make_candle(1)])
    report = QualityEngine().validate_manifest(manifest_path)
    promoter = SilverPromoter()
    arguments = {
        "silver_root": tmp_path / "silver",
        "quarantine_root": tmp_path / "quarantine",
    }

    first = promoter.promote(manifest_path, report, **arguments)
    first_hashes = [file_sha256(path) for path in first.output_files]
    second = promoter.promote(manifest_path, report, **arguments)

    assert second.promoted
    assert first.silver_dataset_version == second.silver_dataset_version
    assert first.promotion_manifest == second.promotion_manifest
    assert first.output_files == second.output_files
    assert [file_sha256(path) for path in second.output_files] == first_hashes


def test_failed_bronze_is_quarantined_by_reference_and_not_promoted(tmp_path: Path) -> None:
    invalid = replace(make_candle(), high=Decimal("1"))
    manifest_path, bronze_files = _one_partition(tmp_path, [invalid])
    before = file_sha256(bronze_files[0])
    report = QualityEngine().validate_manifest(manifest_path)

    result = SilverPromoter().promote(
        manifest_path,
        report,
        silver_root=tmp_path / "silver",
        quarantine_root=tmp_path / "quarantine",
    )

    assert report.overall_status is ValidationStatus.FAIL
    assert not result.promoted
    assert result.quarantine_record is not None and result.quarantine_record.exists()
    assert not list((tmp_path / "silver").rglob("*.parquet"))
    assert file_sha256(bronze_files[0]) == before


def test_allowed_exact_duplicate_is_reported_then_removed_in_silver(tmp_path: Path) -> None:
    candle = make_candle()
    start = candle.open_time
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=5), [candle, candle])],
    )
    policy = QualityPolicy(allowed_duplicate_count=1)
    report = QualityEngine(policy).validate_manifest(manifest_path)

    result = SilverPromoter(policy).promote(
        manifest_path,
        report,
        silver_root=tmp_path / "silver",
        quarantine_root=tmp_path / "quarantine",
    )

    assert report.overall_status is ValidationStatus.WARN
    assert result.promoted
    assert result.exact_duplicates_removed == 1
    assert read_candle_parquet(result.output_files[0]).num_rows == 1


def test_warning_is_rejected_when_policy_disallows_warn_promotion(tmp_path: Path) -> None:
    candle = make_candle()
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(candle.open_time, candle.open_time + timedelta(minutes=5), [candle, candle])],
    )
    policy = QualityPolicy(allowed_duplicate_count=1, allow_warnings_for_silver=False)
    report = QualityEngine(policy).validate_manifest(manifest_path)

    result = SilverPromoter(policy).promote(
        manifest_path,
        report,
        silver_root=tmp_path / "silver",
        quarantine_root=tmp_path / "quarantine",
    )

    assert report.overall_status is ValidationStatus.WARN
    assert not result.promoted
    assert result.quarantine_record is not None
