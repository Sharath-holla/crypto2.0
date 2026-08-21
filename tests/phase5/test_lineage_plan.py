from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.config import load_walk_forward_config
from crypto_ai.phase5.engine import (
    _artifact_files_valid,
    compare_walk_forward_candidates,
    walk_forward_plan,
)
from crypto_ai.phase5.folds import plan_folds, slice_fold


def test_real_plans_freeze_lineage_and_use_different_family_periods() -> None:
    primary_config = load_walk_forward_config(Path("configs/walkforward/btc_primary_v1.toml"))
    derivatives_config = load_walk_forward_config(
        Path("configs/walkforward/btc_derivatives_v1.toml")
    )
    primary = walk_forward_plan(primary_config)
    derivatives = walk_forward_plan(derivatives_config)
    assert primary["fold_count"] == 17
    assert derivatives["fold_count"] == 16
    assert primary["folds"][0]["train_start"] != derivatives["folds"][0]["train_start"]
    assert primary["candidate_feature_schemas"]["L0"]["feature_count"] == 13
    assert primary["candidate_feature_schemas"]["L5"]["feature_count"] == 46
    assert (
        derivatives["candidate_feature_schemas"]["D0"]["columns"]
        == primary["candidate_feature_schemas"]["L5"]["columns"]
    )
    assert derivatives["candidate_feature_schemas"]["D2"]["feature_count"] == 55
    assert not primary["prospective_holdout_used"]
    assert not derivatives["prospective_holdout_used"]
    assert all(
        datetime.fromisoformat(item["test_end"]) <= primary_config.prospective_holdout_start
        for item in primary["folds"]
    )


def test_resume_validation_requires_identity_and_checksums(tmp_path: Path) -> None:
    artifact = tmp_path / "value.txt"
    artifact.write_text("immutable", encoding="utf-8")
    manifest = {
        "status": "complete",
        "identity": "expected",
        "files": {"value.txt": file_sha256(artifact)},
    }
    assert _artifact_files_valid(tmp_path, manifest, "expected")
    assert not _artifact_files_valid(tmp_path, manifest, "different")
    artifact.write_text("tampered", encoding="utf-8")
    assert not _artifact_files_valid(tmp_path, manifest, "expected")


def test_sixty_minute_embargo_removes_exactly_twelve_five_minute_rows() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    config = load_walk_forward_config(Path("configs/walkforward/btc_primary_v1.toml"))
    schedule = config.schedule.model_copy(
        update={
            "train_months": 1,
            "validation_months": 1,
            "calibration_months": 1,
            "test_months": 1,
            "step_months": 1,
            "minimum_rows_per_segment": 1,
        }
    )
    plan = plan_folds(
        start,
        datetime(2020, 6, 1, tzinfo=UTC),
        datetime(2021, 1, 1, tzinfo=UTC),
        schedule,
    )[0]
    feature = [start + timedelta(minutes=5 * index) for index in range(31 * 24 * 12 * 4)]
    table = pa.table(
        {
            "feature_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [value + timedelta(minutes=60) for value in feature],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "future_return_60m": [0.0] * len(feature),
        }
    )
    fold = slice_fold(table, plan, schedule, datetime(2021, 1, 1, tzinfo=UTC))
    assert fold.report["segments"]["validation"]["embargoed"] == 12
    assert fold.report["segments"]["calibration"]["embargoed"] == 12
    assert fold.report["segments"]["test"]["embargoed"] == 12


def test_derivatives_value_is_inconclusive_without_evidence_on_both_sides(
    tmp_path: Path,
) -> None:
    def candidate(trades: int, reliable_folds: int) -> dict[str, object]:
        return {
            "economic": {"1.0": {"trade_count": trades, "expectancy": 0.001}},
            "reliable_fold_count": reliable_folds,
            "qualification": {"qualified": False, "status": "INCONCLUSIVE"},
        }

    primary_path = tmp_path / "primary.json"
    derivatives_path = tmp_path / "derivatives.json"
    common = {
        "status": "complete",
        "prospective_holdout_used": False,
        "prospective_holdout_start": "2026-08-01T00:00:00+00:00",
    }
    write_manifest(
        primary_path,
        common
        | {
            "family": "primary",
            "run_id": "primary",
            "candidates": {"L0": candidate(0, 0), "L5": candidate(0, 0)},
            "candidate_comparison": {},
        },
    )
    write_manifest(
        derivatives_path,
        common
        | {
            "family": "derivatives",
            "run_id": "derivatives",
            "candidates": {"D0": candidate(72, 1), "D2": candidate(207, 2)},
            "candidate_comparison": {"D2_value_classification": "VALUE ADDED"},
            "identity": {
                "configuration": {
                    "qualification": {
                        "minimum_total_trades": 100,
                        "minimum_reliable_folds": 3,
                    }
                }
            },
        },
    )
    result = compare_walk_forward_candidates(primary_path, derivatives_path)
    assert result["D0_vs_D2"]["D2_value_classification"] == "INCONCLUSIVE"
    assert result["champion_decision"] == "NO QUALIFIED MODEL"
