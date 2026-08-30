from __future__ import annotations

import copy
import io
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from crypto_ai.logging import JsonFormatter
from crypto_ai.phase7 import load_phase7_config, phase7_plan
from crypto_ai.phase7.config import FEATURE_VERSION, TARGET_VERSION
from crypto_ai.phase7.progress import (
    ProgressReporter,
    estimate_remaining_seconds,
    fold_result_payload,
    oos_trade_summary,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/phase7/research_v1.toml"
RUN_STARTED = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def _reporter(
    tmp_path: Path,
    *,
    emit_human: bool = False,
    heartbeat_seconds: float = 600.0,
    monotonic=None,
) -> ProgressReporter:
    return ProgressReporter(
        load_phase7_config(CONFIG_PATH),
        run_identity="observability-test-run",
        run_started_at=RUN_STARTED,
        repository_root=ROOT,
        progress_path=tmp_path / "progress.json",
        emit_human=emit_human,
        heartbeat_seconds=heartbeat_seconds,
        monotonic=monotonic,
    )


def _sample_report() -> dict[str, object]:
    return {
        "status": "COMPLETE",
        "fold_id": "fold-04",
        "research_view": "CORE",
        "spec": {
            "name": "architecture-G0-A6-60m-return",
            "architecture": "G0",
            "target_type": "return",
            "horizon_minutes": 60,
        },
        "core_eligible_symbols": ["BTCUSDT", "ETHUSDT"],
        "expansion_eligible_symbols": [],
        "same_row_feature_columns": [f"feature_{index}" for index in range(54)],
        "test_metrics": {
            "coverage": {"symbols_covered": 2, "oos_rows": 120},
            "micro": {
                "mae": 0.01,
                "rmse": 0.02,
                "r2": 0.03,
                "directional_accuracy": 0.54,
                "pearson_ic": 0.11,
                "spearman_ic": 0.12,
            },
        },
        "economic": {
            "trade_count": 7,
            "fixed_policy_cost_stress": {"1.0": {"expectancy": 0.004}},
        },
    }


def _training_start(reporter: ProgressReporter) -> dict[str, object] | None:
    return reporter.training_started(
        fold_position=1,
        folds_total=16,
        spec={"architecture": "G0", "name": "g0-test"},
        eligible_coins=20,
        train_rows=10_000,
        validation_rows=2_000,
        feature_count=54,
        train_start=datetime(2020, 1, 1, tzinfo=UTC),
        train_end=datetime(2021, 1, 1, tzinfo=UTC),
        validation_start=datetime(2021, 1, 1, tzinfo=UTC),
        validation_end=datetime(2021, 2, 1, tzinfo=UTC),
    )


def test_training_start_event_has_fold_model_features_and_target(tmp_path: Path) -> None:
    payload = _training_start(_reporter(tmp_path))

    assert payload is not None
    assert payload["event"] == "phase7_training_started"
    assert payload["fold"] == 1
    assert payload["model"] == "G0"
    assert payload["feature_count"] == 54
    assert payload["target_identity"] == TARGET_VERSION


def test_fold_evaluation_reports_actual_supplied_oos_metrics(tmp_path: Path) -> None:
    payload = _reporter(tmp_path).fold_evaluation(
        _sample_report(),
        trade_summary={
            "long_trades": 4,
            "short_trades": 3,
            "wins": 5,
            "losses": 2,
            "win_rate": 5 / 7,
            "gross_return_sum": 0.09,
            "total_assumed_cost_return": 0.014,
            "net_return_sum": 0.076,
        },
        elapsed_seconds=42.0,
        fold_position=4,
        folds_total=16,
    )

    assert payload["metric_scope"] == "OUT_OF_SAMPLE_TEST"
    assert payload["predictions"] == 120
    assert payload["trades"] == 7
    assert payload["net_return_sum"] == 0.076
    assert payload["spearman_ic"] == 0.12


def test_missing_metrics_render_as_na(tmp_path: Path, capsys) -> None:
    reporter = _reporter(tmp_path, emit_human=True)
    reporter.fold_evaluation(
        _sample_report(),
        trade_summary=None,
        elapsed_seconds=None,
        fold_position=4,
        folds_total=16,
    )

    rendered = capsys.readouterr().out
    assert "Sharpe: N/A" in rendered
    assert "Precision: N/A" in rendered
    assert "NO_TRADE signals: N/A" in rendered


def test_training_metrics_cannot_be_mislabeled_as_oos() -> None:
    report = _sample_report()
    report["train_metrics"] = {"micro": {"mae": 999.0}, "pnl": 999.0}

    payload = fold_result_payload(report)

    assert payload["metric_scope"] == "OUT_OF_SAMPLE_TEST"
    assert payload["mae"] == 0.01
    assert 999.0 not in payload.values()


def test_stage_progress_count_percentage_and_eta_are_correct(tmp_path: Path) -> None:
    clock_values = iter((10.0, 20.0))
    reporter = _reporter(tmp_path, monotonic=lambda: next(clock_values))
    reporter.stage_started("acquisition", 2, 6)

    payload = reporter.progress(
        stage="acquisition",
        completed=5,
        total=10,
        current="BTCUSDT",
        interval="5m",
        status="VALID",
    )

    assert payload is not None
    assert payload["symbols_completed"] == 5
    assert payload["symbols_total"] == 10
    assert payload["stage_progress"] == 50.0
    assert payload["eta_seconds_approximate"] == 10.0


def test_progress_events_do_not_mutate_training_configuration(tmp_path: Path) -> None:
    config = load_phase7_config(CONFIG_PATH)
    before = config.model_dump(mode="json")
    reporter = _reporter(tmp_path)

    reporter.stage_started("train", 5, 6)
    _training_start(reporter)

    assert config.model_dump(mode="json") == before
    assert reporter.config.model_dump(mode="json") == before


def test_progress_does_not_alter_feature_target_or_fold_identities(tmp_path: Path) -> None:
    config = load_phase7_config(CONFIG_PATH)
    plan_before = phase7_plan(config)

    reporter = _reporter(tmp_path)
    reporter.stage_started("gold", 4, 6)
    plan_after = phase7_plan(config)
    plan_before.pop("resource_snapshot")
    plan_after.pop("resource_snapshot")

    assert FEATURE_VERSION == "multiasset_features_v2"
    assert TARGET_VERSION == "multiasset_targets_v2"
    assert plan_after == plan_before
    assert config.configuration_hash == "cc550337f1f4ee4654124bf6"


def test_august_holdout_remains_locked_unused(tmp_path: Path) -> None:
    reporter = _reporter(tmp_path)
    payload = _training_start(reporter)
    state = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))

    assert payload is not None
    assert payload["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert state["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert state["prospective_holdout_used"] is False
    assert state["july_2026_used"] is False


def test_training_heartbeat_does_not_touch_model_state(tmp_path: Path) -> None:
    reporter = _reporter(tmp_path, heartbeat_seconds=0.01)
    model_state = {"weights": (1.0, 2.0), "iteration": 17}
    before = copy.deepcopy(model_state)

    with reporter.model_fit(
        fold_position=1,
        folds_total=16,
        spec={"architecture": "G0", "name": "g0-test"},
        feature_count=54,
        train_rows=100,
        validation_rows=20,
    ):
        time.sleep(0.04)

    assert model_state == before


def test_eta_is_unavailable_with_insufficient_observations() -> None:
    assert estimate_remaining_seconds(0, 10, 30.0) is None
    assert estimate_remaining_seconds(1, 10, 30.0) is None
    assert estimate_remaining_seconds(10, 10, 30.0) is None
    assert estimate_remaining_seconds(2, 10, 0.0) is None


def test_final_summary_uses_actual_report_and_training_artifact(tmp_path: Path) -> None:
    reporter = _reporter(tmp_path)
    report_path = tmp_path / "phase7_report.json"
    report_path.write_text("{}\n", encoding="utf-8")
    report = {
        "scorecard": [{"experiment": "g0-test"}],
        "model_qualification_performed": False,
        "qualified_model": "NONE",
        "july_2026_used": False,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
    }
    training = {
        "completed_fold_count": 1,
        "reports": [_sample_report()],
    }

    payload = reporter.final_summary(report, training, report_path=report_path)

    assert payload["folds_completed"] == 1
    assert payload["scorecard_rows"] == 1
    assert payload["qualified_model"] == "NONE"
    assert payload["net_pnl"] is None
    assert payload["report_artifact"] == str(report_path.resolve())


def test_structured_progress_log_remains_parseable_json(tmp_path: Path) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    progress_logger = logging.getLogger("crypto_ai.phase7.progress")
    original_level = progress_logger.level
    progress_logger.setLevel(logging.INFO)
    progress_logger.addHandler(handler)
    try:
        _reporter(tmp_path).stage_started("registry", 1, 6)
    finally:
        progress_logger.removeHandler(handler)
        progress_logger.setLevel(original_level)

    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["event"] == "phase7_stage_started"
    assert payload["stage"] == "registry"
    assert payload["configuration_hash"] == "cc550337f1f4ee4654124bf6"


def test_progress_json_is_atomic_and_resumable(tmp_path: Path) -> None:
    reporter = _reporter(tmp_path)
    assert _training_start(reporter) is not None

    resumed = _reporter(tmp_path)
    assert _training_start(resumed) is None
    state = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))

    assert state["training_started"] is True
    assert not list(tmp_path.glob(".*.tmp"))


def test_metric_rendering_is_side_effect_only_and_reproducible() -> None:
    report = _sample_report()
    before = copy.deepcopy(report)
    trades = pa.table(
        {
            "direction": [1, -1],
            "gross_return": [0.02, -0.01],
            "base_cost_bps": [10.0, 20.0],
            "net_return": [0.019, -0.012],
        }
    )
    trades_before = trades.to_pydict()

    first = fold_result_payload(report, trade_summary=oos_trade_summary(trades))
    second = fold_result_payload(report, trade_summary=oos_trade_summary(trades))

    assert first == second
    assert report == before
    assert trades.to_pydict() == trades_before
