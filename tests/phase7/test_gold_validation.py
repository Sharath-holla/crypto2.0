from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.config import FEATURE_VERSION, MARKET_CONTEXT_VERSION, TARGET_VERSION
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.gold_validation import (
    GoldValidationError,
    GoldValidationExpectations,
    HoldoutViolationError,
    native_feature_columns,
    validate_phase7_gold,
)


def _gold_fixture(root: Path, *, start: datetime) -> GoldValidationExpectations:
    dataset_id = "gold-fixture"
    dataset_root = root / dataset_id
    partition = dataset_root / "dataset" / "symbol=BTCUSDT" / f"year={start.year}" / "part.parquet"
    partition.parent.mkdir(parents=True)
    rows = 8
    feature_times = [start + timedelta(minutes=5 * index) for index in range(rows)]
    horizons = [15, 30, 60, 120] * 2
    data: dict[str, object] = {
        "symbol": ["BTCUSDT"] * rows,
        "feature_time": pa.array(feature_times, type=pa.timestamp("us", tz="UTC")),
        "entry_time": pa.array(
            [value + timedelta(minutes=5) for value in feature_times],
            type=pa.timestamp("us", tz="UTC"),
        ),
        "label_end_time": pa.array(
            [
                value + timedelta(minutes=5 + horizon)
                for value, horizon in zip(feature_times, horizons, strict=True)
            ],
            type=pa.timestamp("us", tz="UTC"),
        ),
        "horizon_minutes": horizons,
        "raw_future_return": np.linspace(-0.1, 0.1, rows),
        "normalized_future_return": np.linspace(-1.0, 1.0, rows),
        "ex_ante_volatility_scale": np.ones(rows),
        "mfe_long": np.full(rows, 0.02),
        "mae_long": np.full(rows, 0.01),
        "mfe_short": np.full(rows, 0.01),
        "mae_short": np.full(rows, 0.02),
        "feature_version": [FEATURE_VERSION] * rows,
        "market_context_version": [MARKET_CONTEXT_VERSION] * rows,
        "target_version": [TARGET_VERSION] * rows,
        "cross_sectional_context_scope": ["ACQUISITION_UNION_PREVIEW"] * rows,
    }
    for index, name in enumerate(native_feature_columns()):
        data[name] = np.full(rows, index + 0.5, dtype=np.float64)
    pq.write_table(pa.table(data), partition)
    feature_columns = native_feature_columns()
    manifest = {
        "dataset_id": dataset_id,
        "classification": "RETROSPECTIVE_MULTI_ASSET_RESEARCH",
        "rows": rows,
        "feature_version": FEATURE_VERSION,
        "target_version": TARGET_VERSION,
        "feature_columns": list(feature_columns),
        "feature_groups": {
            name: list(values) for name, values in feature_ablation_sets(feature_columns).items()
        },
        "partitioned_by": ["symbol", "year"],
        "universe_version": "fixture-universe-v1",
        "universe_hash": "fixture-universe-hash",
        "registry_version": "fixture-registry-v1",
        "registry_hash": "fixture-registry-hash",
        "research_cutoff": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
        "prospective_holdout_start": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
        "lineage": {"source_fingerprint": "fixture-source"},
        "partition_files": [
            {
                "path": partition.relative_to(dataset_root).as_posix(),
                "sha256": file_sha256(partition),
            }
        ],
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
        "july_2026_used": False,
    }
    (dataset_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return GoldValidationExpectations(
        dataset_id=dataset_id,
        partitions=1,
        rows=rows,
        symbols=frozenset({"BTCUSDT"}),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
        holdout_start=datetime(2026, 8, 1, tzinfo=UTC),
        total_files=2,
    )


def test_gold_validation_checks_exact_identity_schema_and_rows(tmp_path: Path) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    report = validate_phase7_gold(tmp_path, expectations=expectations)
    assert report["status"] == "PASS"
    assert report["rows"] == 8
    assert report["native_feature_count"] == 54
    assert report["holdout_status"] == "LOCKED_UNUSED"


def test_gold_validation_rejects_august_even_when_manifest_flags_are_locked(
    tmp_path: Path,
) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2026, 8, 1, tzinfo=UTC))
    with pytest.raises(HoldoutViolationError, match="HOLDOUT_VIOLATION"):
        validate_phase7_gold(tmp_path, expectations=expectations)


def test_gold_validation_fails_closed_on_expected_count_mismatch(tmp_path: Path) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    changed = GoldValidationExpectations(
        dataset_id=expectations.dataset_id,
        partitions=1,
        rows=9,
        symbols=expectations.symbols,
        total_files=2,
    )
    with pytest.raises(GoldValidationError, match="row count mismatch"):
        validate_phase7_gold(tmp_path, expectations=changed)


@pytest.mark.parametrize("field", ["prospective_holdout_used", "july_2026_used"])
def test_gold_validation_rejects_missing_holdout_metadata(tmp_path: Path, field: str) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    path = tmp_path / expectations.dataset_id / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop(field)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HoldoutViolationError):
        validate_phase7_gold(tmp_path, expectations=expectations)


def test_gold_validation_rejects_feature_order_and_unverified_hash_report(tmp_path: Path) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    report = validate_phase7_gold(tmp_path, expectations=expectations, verify_hashes=False)
    assert report["status"] == "INCOMPLETE_HASH_VERIFICATION"
    assert report["partition_hashes_verified"] is False
    path = tmp_path / expectations.dataset_id / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["feature_columns"][0:2] = reversed(manifest["feature_columns"][0:2])
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(GoldValidationError, match="order"):
        validate_phase7_gold(tmp_path, expectations=expectations)


def test_gold_validation_detects_partition_hash_corruption(tmp_path: Path) -> None:
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    partition = next(tmp_path.rglob("*.parquet"))
    with partition.open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(GoldValidationError, match="checksum mismatch"):
        validate_phase7_gold(tmp_path, expectations=expectations)
