from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.phase5.config import load_walk_forward_config
from crypto_ai.phase5.engine import (
    _artifact_files_valid,
    compare_walk_forward_candidates,
    walk_forward_plan,
)
from crypto_ai.phase5.folds import plan_folds, slice_fold


def _plan_fixture(tmp_path: Path, family: str) -> Path:
    """Minimal synthetic planning input, never an estimate of missing market history."""
    root = tmp_path / family
    root.mkdir()
    version = f"synthetic-plan-{family}"
    start = datetime(2019, 9 if family == "primary" else 12, 1, tzinfo=UTC)
    table = pa.table(
        {
            "feature_time": pa.array(
                [start, datetime(2026, 5, 31, 23, 55, tzinfo=UTC)],
                type=pa.timestamp("us", tz="UTC"),
            )
        }
    ).replace_schema_metadata({b"dataset_version": version.encode()})
    path = root / "synthetic.parquet"
    pq.write_table(table, path)
    manifest_path = root / "manifest.json"
    write_manifest(
        manifest_path,
        {
            "file": path.name,
            "sha256": file_sha256(path),
            "dataset_version": version,
            "dataset_family": "core_long_history" if family == "primary" else "derivatives_overlap",
        },
    )
    return manifest_path


def test_plans_freeze_lineage_and_use_different_family_periods(tmp_path: Path) -> None:
    primary_config = load_walk_forward_config(Path("configs/walkforward/btc_primary_v1.toml"))
    derivatives_config = load_walk_forward_config(
        Path("configs/walkforward/btc_derivatives_v1.toml")
    )
    primary_config = primary_config.model_copy(
        update={"dataset_manifest": _plan_fixture(tmp_path, "primary")}
    )
    derivatives_config = derivatives_config.model_copy(
        update={"dataset_manifest": _plan_fixture(tmp_path, "derivatives")}
    )
    primary = walk_forward_plan(primary_config)
    derivatives = walk_forward_plan(derivatives_config)
    assert primary["fold_count"] == 17
    assert derivatives["fold_count"] == 16
    assert primary["dataset_version"] == "synthetic-plan-primary"
    assert derivatives["dataset_version"] == "synthetic-plan-derivatives"
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


@pytest.mark.parametrize(
    "mutation",
    ["hash", "lineage", "missing-sha", "missing-version", "missing-time", "missing-file"],
)
def test_plan_rejects_invalid_lineage_before_planning(tmp_path: Path, mutation: str) -> None:
    import json

    manifest_path = _plan_fixture(tmp_path, "primary")
    manifest = json.loads(manifest_path.read_text())
    path = manifest_path.parent / manifest["file"]
    if mutation == "hash":
        manifest["sha256"] = "0" * 64
    elif mutation == "lineage":
        manifest["dataset_version"] = "wrong-lineage"
    elif mutation in {"missing-sha", "missing-version"}:
        manifest.pop("sha256" if mutation == "missing-sha" else "dataset_version")
    elif mutation == "missing-time":
        table = pq.ParquetFile(path).read().rename_columns(["wrong_time"])
        pq.write_table(table, path)
        manifest["sha256"] = file_sha256(path)
    else:
        manifest["file"] = "absent.parquet"
    write_manifest(manifest_path, manifest)
    config = load_walk_forward_config(Path("configs/walkforward/btc_primary_v1.toml"))
    config = config.model_copy(update={"dataset_manifest": manifest_path})
    with pytest.raises((ValueError, KeyError)):
        walk_forward_plan(config)


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
