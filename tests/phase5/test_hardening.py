from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.phase5.config import load_hardening_config
from crypto_ai.phase5.hardening import (
    RESULT_VERSION,
    _qualification,
    compare_hardened_candidates,
)
from crypto_ai.phase5.verification import _timestamp_holdout_count


def _inconclusive_aggregate() -> dict[str, object]:
    metric = {
        "trade_count": 5,
        "expectancy": -0.001,
        "maximum_drawdown": -0.01,
    }
    return {
        "fixed_policy_cost_stress": {"1.0": metric, "1.5": metric},
        "fold_count": 17,
        "reliable_fold_count": 0,
        "folds": [{"base_expectancy": -0.001}],
        "top_fold_positive_pnl_share": None,
        "top_year_positive_pnl_share": None,
        "top_regime_positive_pnl_share": None,
    }


def test_repository_hardening_configs_freeze_v1_1_and_holdout() -> None:
    primary = load_hardening_config(Path("configs/walkforward/btc_primary_v1_1.toml"))
    derivatives = load_hardening_config(Path("configs/walkforward/btc_derivatives_v1_1.toml"))
    assert primary.protocol_version == "1.1.0"
    assert derivatives.protocol_version == primary.protocol_version
    assert primary.walkforward.candidates == ("L0", "L5")
    assert derivatives.walkforward.candidates == ("D0", "D2")
    assert primary.walkforward.prospective_holdout_start == datetime(2026, 8, 1, tzinfo=UTC)


def test_qualification_fail_coexists_with_inconclusive_evidence() -> None:
    config = load_hardening_config(Path("configs/walkforward/btc_primary_v1_1.toml"))
    result = _qualification(_inconclusive_aggregate(), config)
    assert result["qualification_status"] == "FAIL"
    assert result["evidence_status"] == "INCONCLUSIVE"
    assert result["qualified"] is False
    assert result["gates"]["minimum_total_trades"] is False


def test_hardened_comparison_returns_no_qualified_model(tmp_path: Path) -> None:
    primary_path = tmp_path / "primary.json"
    derivatives_path = tmp_path / "derivatives.json"

    def candidate() -> dict[str, object]:
        return {
            "qualification": {
                "qualification_status": "FAIL",
                "evidence_status": "INCONCLUSIVE",
                "qualified": False,
            }
        }

    common = {
        "status": "complete",
        "result_version": RESULT_VERSION,
        "prospective_holdout_start": "2026-08-01T00:00:00+00:00",
        "max_feature_time_used": "2026-07-31T23:55:00+00:00",
        "prospective_holdout_used": False,
        "candidate_comparison": {"evidence_status": "INCONCLUSIVE"},
    }
    write_manifest(
        primary_path,
        common
        | {
            "run_id": "primary",
            "candidates": {"L0": candidate(), "L5": candidate()},
        },
    )
    write_manifest(
        derivatives_path,
        common
        | {
            "run_id": "derivatives",
            "candidates": {"D0": candidate(), "D2": candidate()},
        },
    )
    result = compare_hardened_candidates(primary_path, derivatives_path)
    assert result["champion_decision"] == "NO QUALIFIED MODEL"
    assert result["prospective_holdout_used"] is False


def test_artifact_timestamp_scan_detects_holdout_rows(tmp_path: Path) -> None:
    holdout = datetime(2026, 8, 1, tzinfo=UTC)
    path = tmp_path / "timestamps.parquet"
    pq.write_table(
        pa.table(
            {
                "feature_time": pa.array(
                    [datetime(2026, 7, 31, 23, 55, tzinfo=UTC), holdout],
                    type=pa.timestamp("us", tz="UTC"),
                )
            }
        ),
        path,
    )
    count, maximum = _timestamp_holdout_count(path, holdout)
    assert count == 1
    assert maximum == holdout.isoformat()
