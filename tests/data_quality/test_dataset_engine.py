from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.models import ValidationStatus
from crypto_ai.data.quality.policy import QualityPolicy, load_quality_policy
from tests.factories import make_candle
from tests.quality_helpers import write_bronze_dataset


def _no_trade(candle):
    return replace(
        candle,
        base_volume=Decimal("0"),
        quote_volume=Decimal("0"),
        trade_count=0,
        taker_buy_base_volume=Decimal("0"),
        taker_buy_quote_volume=Decimal("0"),
    )


def _continuous_dataset(tmp_path: Path):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    return write_bronze_dataset(
        tmp_path,
        [
            (start, start + timedelta(minutes=10), [make_candle(0), make_candle(1)]),
            (
                start + timedelta(minutes=10),
                start + timedelta(minutes=20),
                [make_candle(2), make_candle(3)],
            ),
        ],
    )


def _codes(report, status: ValidationStatus | None = None) -> set[str]:
    return {check.check_name for check in report.checks if status is None or check.status is status}


def test_valid_cross_partition_dataset_passes_with_complete_summary(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)

    report = QualityEngine().validate_manifest(manifest_path)

    assert report.overall_status is ValidationStatus.PASS
    assert "cross_partition_continuity" in _codes(report, ValidationStatus.PASS)
    assert report.summary["observed_candles"] == 4
    assert report.summary["expected_candles"] == 4
    assert report.summary["missing_candles"] == 0
    assert report.report_id.startswith("quality-")
    assert report.dataset_version.startswith("dataset-")


def test_cross_partition_missing_candle_is_detected(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [
            (start, start + timedelta(minutes=10), [make_candle(0), make_candle(1)]),
            (
                start + timedelta(minutes=10),
                start + timedelta(minutes=20),
                [make_candle(3)],
            ),
        ],
    )

    report = QualityEngine().validate_manifest(manifest_path)

    assert report.overall_status is ValidationStatus.FAIL
    assert "cross_partition_gap" in _codes(report, ValidationStatus.FAIL)
    assert report.summary["missing_candles"] == 1


def test_cross_partition_exact_and_conflicting_duplicates_are_distinguished(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    repeated = make_candle(1)
    exact_manifest, _ = write_bronze_dataset(
        tmp_path / "exact",
        [
            (start, start + timedelta(minutes=10), [make_candle(0), repeated]),
            (
                start + timedelta(minutes=10),
                start + timedelta(minutes=20),
                [repeated, make_candle(2), make_candle(3)],
            ),
        ],
    )
    conflict = replace(repeated, high=repeated.high + Decimal("1"))
    conflict_manifest, _ = write_bronze_dataset(
        tmp_path / "conflict",
        [
            (start, start + timedelta(minutes=10), [make_candle(0), repeated]),
            (
                start + timedelta(minutes=10),
                start + timedelta(minutes=20),
                [conflict, make_candle(2), make_candle(3)],
            ),
        ],
    )

    exact = QualityEngine().validate_manifest(exact_manifest)
    conflicting = QualityEngine().validate_manifest(conflict_manifest)

    assert "cross_partition_exact_duplicate" in _codes(exact, ValidationStatus.FAIL)
    assert "cross_partition_conflicting_duplicate" in _codes(conflicting, ValidationStatus.FAIL)


def test_out_of_order_manifest_partitions_are_detected(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    manifest["partitions"] = list(reversed(manifest["partitions"]))
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert "out_of_order_partitions" in _codes(report, ValidationStatus.FAIL)


def test_manifest_partition_and_total_row_count_mismatches_fail(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    manifest["partitions"][0]["row_count"] = 99
    manifest["row_count"] = 99
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert {"manifest_row_count", "manifest_total_row_count"} <= _codes(
        report, ValidationStatus.FAIL
    )


def test_manifest_timestamp_range_mismatch_fails(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    manifest["start"] = (datetime(2026, 8, 1, tzinfo=UTC) - timedelta(minutes=5)).isoformat()
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert "manifest_timestamp_range" in _codes(report, ValidationStatus.FAIL)


def test_empty_requested_partition_remains_a_hard_failure(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    empty = manifest["partitions"][0]
    empty.update(
        {
            "status": "empty",
            "row_count": 0,
            "file": None,
            "sha256": None,
            "quality": {"is_valid": False},
        }
    )
    manifest["file_locations"] = [
        record["file"] for record in manifest["partitions"] if record.get("file")
    ]
    manifest["row_count"] = sum(record["row_count"] for record in manifest["partitions"])
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert report.overall_status is ValidationStatus.FAIL
    assert "empty_partition" in _codes(report, ValidationStatus.FAIL)


def test_missing_manifest_referenced_file_fails(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    missing = "klines/market=usdm/symbol=BTCUSDT/interval=5m/date=2026-08-01/missing.parquet"
    manifest["partitions"][0]["file"] = missing
    manifest["file_locations"][0] = missing
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert "missing_referenced_file" in _codes(report, ValidationStatus.FAIL)
    assert report.summary["missing_file_count"] == 1


def test_unreadable_parquet_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.parquet"
    path.write_bytes(b"not parquet")

    report = QualityEngine().validate_file(
        path,
        symbol="BTCUSDT",
        interval="5m",
        source="binance_usdm_futures_rest",
        market="usdm",
    )

    assert report.overall_status is ValidationStatus.FAIL
    assert "unreadable_parquet" in _codes(report, ValidationStatus.FAIL)


def test_checksum_mismatch_is_detected_without_repair(tmp_path: Path) -> None:
    manifest_path, files = _continuous_dataset(tmp_path)
    original = files[0].read_bytes()
    manifest = read_manifest(manifest_path)
    assert manifest is not None
    manifest["partitions"][0]["sha256"] = "0" * 64
    write_manifest(manifest_path, manifest)

    report = QualityEngine().validate_manifest(manifest_path)

    assert "manifest_checksum" in _codes(report, ValidationStatus.FAIL)
    assert files[0].read_bytes() == original


def test_machine_readable_report_is_deterministic_and_versioned(tmp_path: Path) -> None:
    manifest_path, _ = _continuous_dataset(tmp_path)
    engine = QualityEngine()
    first = engine.validate_manifest(manifest_path)
    second = engine.validate_manifest(manifest_path)

    first_path = engine.write_report(first, tmp_path / "quality")
    second_path = engine.write_report(second, tmp_path / "quality")
    payload = json.loads(second_path.read_text(encoding="utf-8"))

    assert first.report_id == second.report_id
    assert first_path == second_path
    assert payload["report_schema_version"] == "1.0.0"
    assert payload["validator_version"] == "1.2.0"
    assert payload["overall_status"] == "PASS"
    assert payload["source_files"]
    assert payload["checks"]

    legacy = replace(first, validator_version="1.1.0", report_id="")
    legacy_path = engine.write_report(legacy, tmp_path / "quality")
    assert legacy.report_id != first.report_id
    assert legacy_path != first_path
    assert legacy_path.exists() and first_path.exists()


def test_overall_warn_and_fail_statuses_are_deterministic(tmp_path: Path) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    candles = []
    for index in range(30):
        price = Decimal("100000") if index == 20 else Decimal("65000")
        candle = make_candle(index)
        candles.append(
            replace(
                candle,
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price,
            )
        )
    warn_manifest, _ = write_bronze_dataset(
        tmp_path / "warn",
        [(start, start + timedelta(minutes=150), candles)],
    )
    fail_manifest, _ = write_bronze_dataset(
        tmp_path / "fail",
        [
            (
                start,
                start + timedelta(minutes=5),
                [replace(make_candle(), high=Decimal("1"))],
            )
        ],
    )

    warn = QualityEngine().validate_manifest(warn_manifest)
    fail = QualityEngine().validate_manifest(fail_manifest)

    assert warn.overall_status is ValidationStatus.WARN
    assert fail.overall_status is ValidationStatus.FAIL


def test_quality_policy_file_is_typed_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "quality.toml"
    path.write_text(
        "[quality]\nallowed_missing_percentage = 1.5\n"
        "zero_volume_warning_percentage = 1.0\n"
        "zero_volume_failure_percentage = 10.0\n"
        "zero_volume_percentage_min_observations = 25\n",
        encoding="utf-8",
    )

    policy = load_quality_policy(path)

    assert isinstance(policy, QualityPolicy)
    assert policy.allowed_missing_percentage == 1.5
    assert policy.zero_volume_percentage_min_observations == 25


def test_one_row_daily_no_trade_manifest_warns_instead_of_failing(tmp_path: Path) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candle = _no_trade(make_candle(start=start, interval_minutes=24 * 60))
    manifest_path, files = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(days=1), [candle])],
        interval="1d",
    )
    before = files[0].read_bytes()

    report = QualityEngine().validate_manifest(manifest_path)

    assert report.overall_status is ValidationStatus.WARN
    assert "zero_volume_prevalence" in _codes(report, ValidationStatus.WARN)
    assert "zero_base_volume_with_activity" not in _codes(report, ValidationStatus.FAIL)
    assert report.summary["observed_candles"] == 1
    assert report.summary["zero_volume_count"] == 1
    assert report.summary["zero_volume_percentage"] == 100.0
    assert files[0].read_bytes() == before


def test_manifest_share_uses_complete_daily_history_denominator(tmp_path: Path) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    partitions = []
    for index in range(120):
        opened = start + timedelta(days=index)
        candle = make_candle(index, start=start, interval_minutes=24 * 60)
        if index == 60:
            candle = _no_trade(candle)
        partitions.append((opened, opened + timedelta(days=1), [candle]))
    manifest_path, _ = write_bronze_dataset(tmp_path, partitions, interval="1d")

    report = QualityEngine().validate_manifest(manifest_path)

    prevalence = next(
        check for check in report.checks if check.check_name == "zero_volume_prevalence"
    )
    assert report.overall_status is ValidationStatus.WARN
    assert prevalence.status is ValidationStatus.WARN
    assert prevalence.observed_value["total_observations"] == 120
    assert prevalence.observed_value["zero_volume_percentage"] == pytest.approx(100 / 120)
    assert report.summary["consecutive_zero_volume_runs"] == [1]


def test_complete_valid_no_trade_manifest_is_liquidity_warning(tmp_path: Path) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = [_no_trade(make_candle(index, start=start)) for index in range(100)]
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=500), candles)],
    )

    report = QualityEngine().validate_manifest(manifest_path)

    prevalence = next(
        check for check in report.checks if check.check_name == "zero_volume_prevalence"
    )
    assert report.overall_status is ValidationStatus.WARN
    assert prevalence.status is ValidationStatus.WARN
    assert prevalence.observed_value["hard_failure_enabled"] is False
    assert prevalence.expected_value["failure_threshold_effect"] == (
        "deprecated_liquidity_metadata_only"
    )
    assert report.summary["zero_volume_count"] == 100
    assert report.summary["zero_volume_percentage"] == 100.0
    assert report.summary["consecutive_zero_volume_runs"] == [100]


def test_1000why_shape_is_valid_liquidity_warning(tmp_path: Path) -> None:
    start = datetime(2024, 11, 25, tzinfo=UTC)
    candles = [make_candle(index, start=start, interval_minutes=24 * 60) for index in range(583)]
    candles[-105:] = [_no_trade(candle) for candle in candles[-105:]]
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(days=583), candles)],
        interval="1d",
    )

    report = QualityEngine().validate_manifest(manifest_path)

    assert report.overall_status is ValidationStatus.WARN
    assert "zero_volume_prevalence" in _codes(report, ValidationStatus.WARN)
    assert "zero_volume_prevalence" not in _codes(report, ValidationStatus.FAIL)
    assert report.summary["observed_candles"] == 583
    assert report.summary["zero_volume_count"] == 105
    assert report.summary["zero_volume_percentage"] == pytest.approx(105 / 583 * 100)
    assert report.summary["consecutive_zero_volume_runs"] == [105]


def test_manifest_zero_share_warning_is_independent_of_physical_boundaries(
    tmp_path: Path,
) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = [make_candle(index, start=start) for index in range(100)]
    candles[47:53] = [_no_trade(candle) for candle in candles[47:53]]
    first_boundary = start + timedelta(minutes=49 * 5)
    second_boundary = start + timedelta(minutes=51 * 5)
    end = start + timedelta(minutes=100 * 5)
    whole_manifest, _ = write_bronze_dataset(
        tmp_path / "whole",
        [(start, end, candles)],
    )
    split_manifest, _ = write_bronze_dataset(
        tmp_path / "split",
        [
            (start, first_boundary, candles[:49]),
            (first_boundary, second_boundary, candles[49:51]),
            (second_boundary, end, candles[51:]),
        ],
    )

    whole = QualityEngine().validate_manifest(whole_manifest)
    split = QualityEngine().validate_manifest(split_manifest)

    assert whole.overall_status is split.overall_status is ValidationStatus.WARN
    assert "zero_volume_prevalence" in _codes(whole, ValidationStatus.WARN)
    assert "zero_volume_prevalence" in _codes(split, ValidationStatus.WARN)
    assert whole.summary["zero_volume_percentage"] == 6.0
    assert split.summary["zero_volume_percentage"] == 6.0
    assert whole.summary["consecutive_zero_volume_runs"] == [6]
    assert split.summary["consecutive_zero_volume_runs"] == [6]
