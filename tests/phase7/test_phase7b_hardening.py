"""Added by Claude (2026-11-02, Phase 3): hardening helpers, console table, abort and gating."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7 import hardening as h
from crypto_ai.phase7.training_metrics import (
    FitMetricObserver,
    TrainingMetricScope,
    display_metrics,
)


def test_defaults_match_the_shipped_toml_and_reject_unknown_keys(tmp_path: Path) -> None:
    shipped = Path(__file__).resolve().parents[2] / "configs" / "phase7" / "hardening_v1.toml"
    assert h.load_hardening_config(shipped) == h.HardeningConfig()
    bad = tmp_path / "bad.toml"
    bad.write_text("[hardening]\nnot_a_key = 1\n")
    with pytest.raises(ValueError, match="unknown hardening config keys"):
        h.load_hardening_config(bad)


def test_fixed_threshold_precision_recall() -> None:
    actual = np.array([0.001, -0.001, 0.001, 0.0, 0.002])
    predicted = np.array([0.001, 0.001, -0.001, 0.001, 0.002])
    scores = h.fixed_threshold_precision_recall(actual, predicted, 5.0)
    assert scores["signals"] == 5 and scores["real_moves"] == 4
    assert scores["true_positives"] == 2  # rows 0 and 4
    assert scores["precision"] == pytest.approx(2 / 5)
    assert scores["recall"] == pytest.approx(2 / 4)
    assert h.fixed_threshold_precision_recall(np.zeros(3), np.zeros(3), 5.0)["precision"] is None


def test_display_metrics_now_include_precision_and_recall() -> None:
    names = [
        name for name, _value, _flag in display_metrics(np.ones(4) * 0.001, np.ones(4) * 0.001)
    ]
    assert names == ["mae", "rmse", "directional_accuracy", "fixed_precision", "fixed_recall"]


def test_trend_flag() -> None:
    assert h.trend_flag(None, 1.0) == "= flat"
    assert h.trend_flag(1.0, 0.9) == "↓ better"
    assert h.trend_flag(1.0, 1.1) == "↑ worse"
    assert h.trend_flag(1.0, 1.0005) == "= flat"


def test_observer_prints_a_readable_line_and_aborts_after_n_worse_checks(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        "crypto_ai.phase7.training_metrics.current_config",
        lambda: h.HardeningConfig(abort_after_worse_checks=2),
    )
    scope = TrainingMetricScope(tmp_path, {"fold_id": "f1", "spec_id": "s1"}, period=1)
    observer = FitMetricObserver(scope, "global")
    observer.zero_baseline_rmse = 0.01

    def env(iteration: int, rmse: float) -> SimpleNamespace:
        return SimpleNamespace(
            iteration=iteration,
            begin_iteration=0,
            end_iteration=10,
            evaluation_result_list=[
                ("train", "rmse", 0.009, False),
                ("validation", "rmse", rmse, False),
                ("validation", "directional_accuracy", 0.5, True),
            ],
        )

    observer(env(0, 0.02))  # worse than the 0.01 zero baseline: streak 1
    out = capsys.readouterr().out
    assert "[fit f1/s1/global] round    1/10" in out and "fixed-threshold, validation only" in out
    with pytest.raises(h.FitAbortedError):
        observer(env(1, 0.03))  # streak 2 -> abort
    assert "FIT_ABORTED" in capsys.readouterr().out


def test_observer_streak_resets_when_validation_recovers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "crypto_ai.phase7.training_metrics.current_config",
        lambda: h.HardeningConfig(abort_after_worse_checks=2),
    )
    observer = FitMetricObserver(TrainingMetricScope(tmp_path, {}, period=1), "global")
    observer.zero_baseline_rmse = 0.01

    def step(iteration: int, rmse: float) -> None:
        observer(
            SimpleNamespace(
                iteration=iteration,
                begin_iteration=0,
                end_iteration=10,
                evaluation_result_list=[("validation", "rmse", rmse, False)],
            )
        )

    step(0, 0.02)
    step(1, 0.005)  # better than baseline: streak resets
    step(2, 0.02)  # only one bad check again, no abort
    assert observer.worse_streak == 1


def test_baselines_score_the_same_validation_rows() -> None:
    rng = np.random.default_rng(1)
    train_x = rng.normal(size=(400, 3))
    train_y = train_x[:, 0] * 0.01
    val_x = rng.normal(size=(100, 3))
    val_y = val_x[:, 0] * 0.01
    perfect = val_y.copy()
    covered = np.ones(100, dtype=bool)
    covered[:10] = False
    result = h.score_baselines(train_x, train_y, val_x, val_y, perfect, covered)
    assert result["validation_rows_scored"] == 90
    assert result["lightgbm"]["rmse"] == pytest.approx(0.0, abs=1e-12)
    assert result["lightgbm_beats_zero"] and result["lightgbm_beats_ridge"] in (True, False)
    assert result["ridge"]["rmse"] < result["zero_return"]["rmse"]


def test_decision_metrics_per_side() -> None:
    result = h.decision_metrics(
        ["A", "A", "A", "A"],
        np.array([0.01, -0.01, 0.0001, 0.01]),
        np.array([0.01, 0.01, 0.01, 0.0]),
        threshold_bps_by_symbol={"A": 5.0},
        cost_bps_by_symbol={"A": 10.0},
    )
    assert result["long"]["signals"] == 3 and result["long"]["true_positives"] == 1
    assert result["long"]["false_negatives"] == 1  # row 3: profitable but no signal
    assert result["short"]["signals"] == 0
    assert result["no_trade_signals"] == 1
    assert result["long"]["precision"] == pytest.approx(1 / 3)


def test_no_trade_when_threshold_is_none() -> None:
    result = h.decision_metrics(
        ["A"],
        np.array([0.05]),
        np.array([0.05]),
        threshold_bps_by_symbol={"A": None},
        cost_bps_by_symbol={"A": 10.0},
    )
    assert result["long"]["signals"] == 0 and result["no_trade_signals"] == 1


def _trades(net: list[float]) -> pa.Table:
    return pa.table(
        {
            "net_return": net,
            "exit_time": pa.array(list(range(len(net))), type=pa.int64()),
            "liquidity_tier": ["HIGH_LIQUIDITY"] * len(net),
        }
    )


def test_trading_metrics_values_and_funding_is_not_modelled() -> None:
    tiers = {"HIGH_LIQUIDITY": {"fee_bps": 8.0, "spread_bps": 1.0, "slippage_bps": 2.0}}
    result = h.trading_metrics(_trades([0.01, -0.005, 0.02, -0.01]), tiers)
    assert result["profit_factor"] == pytest.approx(0.03 / 0.015)
    assert result["max_drawdown"] == pytest.approx(0.01)
    assert result["win_rate"] == 0.5 and result["net_return_sum"] == pytest.approx(0.015)
    assert result["fees_return_sum"] == pytest.approx(4 * 8.0 / 10_000)
    assert result["funding"] == "NOT_MODELLED"
    assert h.trading_metrics(_trades([]), tiers)["profit_factor"] is None


def test_stop_file_and_pilot_and_fold_gate(tmp_path: Path) -> None:
    cfg = h.HardeningConfig()
    assert not h.stop_requested(tmp_path, cfg)
    (tmp_path / cfg.stop_file_name).write_text("")
    assert h.stop_requested(tmp_path, cfg)
    specs = [
        SimpleNamespace(horizon_minutes=15, target_type="raw"),
        SimpleNamespace(horizon_minutes=60, target_type="raw"),
        SimpleNamespace(horizon_minutes=60, target_type="vol"),
    ]
    assert h.apply_pilot_filter(specs, cfg) == tuple(specs)
    pilot = h.HardeningConfig(pilot_horizon_minutes=60, pilot_target_type="raw")
    assert h.apply_pilot_filter(specs, pilot) == (specs[1],)
    with pytest.raises(ValueError):
        h.apply_pilot_filter(
            specs, h.HardeningConfig(pilot_horizon_minutes=5, pilot_target_type="x")
        )
    bad = [{"status": "COMPLETE", "phase7b": {"baselines": {"lightgbm_beats_zero": False}}}]
    good = bad + [{"status": "COMPLETE", "phase7b": {"baselines": {"lightgbm_beats_zero": True}}}]
    gated = h.HardeningConfig(fold_gate_folds=3)
    assert h.fold_gate_failed(bad, 1, gated) and not h.fold_gate_failed(good, 1, gated)
    assert not h.fold_gate_failed(bad, 4, gated) and not h.fold_gate_failed(bad, 1, cfg)


def test_results_table_appends_one_row_per_fold_and_spec(tmp_path: Path) -> None:
    report = {
        "fold_id": "fold-001",
        "spec": {"name": "g0-60-raw", "horizon_minutes": 60, "target_type": "raw"},
        "segment_rows": {"train": 10, "test": 5},
        "calibration": {"selected": {"method": "identity"}, "selection_source": "x"},
        "test_used_for_selection": False,
        "phase7b": {
            "baselines": {"lightgbm_skill_vs_zero": 0.02, "lightgbm_beats_zero": True},
            "decision": {"long": {"precision": 0.5}, "short": {}, "no_trade_signals": 3},
            "trading": {"trades": 4, "net_return_sum": 0.01, "funding": "NOT_MODELLED"},
        },
    }
    h.append_result_row(tmp_path, h.results_row_from_report(report))
    h.append_result_row(tmp_path, h.results_row_from_report(report))
    rows = h.read_results_table(tmp_path / h.RESULTS_FILENAME)
    assert len(rows) == 2 and rows[0]["spec"] == "g0-60-raw" and rows[0]["trades"] == "4"
    assert rows[0]["funding"] == "NOT_MODELLED" and rows[0]["long_precision"] == "0.5"


def test_ranking_is_descriptive_and_success_is_not_independent_evidence() -> None:
    # CHANGED BY CLAUDE (2026-11-06, IA-01/IA-02): the old test asserted Bonferroni p-values and a
    # "significant" flag computed from validation rows. Those claims were invalid and were removed.
    rows = []
    for fold in range(12):
        rows.append(
            {
                "fold_id": f"f{fold}",
                "spec": "good",
                "lightgbm_skill_vs_zero": 0.05 + 0.001 * fold,
                "beats_zero": "True",
                "net_return_sum": "0.01",
            }
        )
        rows.append(
            {
                "fold_id": f"f{fold}",
                "spec": "noise",
                "lightgbm_skill_vs_zero": (-1) ** fold * 0.01,
                "beats_zero": str(fold % 2 == 0),
                "net_return_sum": "-0.01" if fold % 2 else "0.01",
            }
        )
    ranking = h.descriptive_ranking(rows)
    assert ranking["specs_tried"] == 2 and ranking["spec_fold_pairs_tried"] == 24
    assert ranking["ranking_kind"] == "DESCRIPTIVE_RANKING"
    assert ranking["metric_class"] == "DEVELOPMENT_METRIC"
    assert ranking["inference_status"] == "NOT_INDEPENDENT"
    assert ranking["p_values"] == "NOT_APPLICABLE"
    best = ranking["ranking"][0]
    assert best["spec"] == "good" and best["worst_fold_skill"] > 0
    assert not any(key.startswith("p_") or "significant" in key for key in best)
    assert h.rank_specs_with_correction(rows)["inference_status"] == "NOT_INDEPENDENT"
    success = h.evaluate_success(rows)
    assert success["specs"]["good"]["descriptive_criteria_met"]
    assert not success["specs"]["noise"]["descriptive_criteria_met"]
    assert success["status"] == "DESCRIPTIVE_ONLY"
    assert success["qualifies_as_independent_evidence"] is False


def test_duplicate_fold_rows_cannot_satisfy_success_or_ranking() -> None:
    # IA-02 reproduction: ten copies of one fold used to pass "10 folds" with significant=true.
    row = {
        "fold_id": "f0",
        "spec": "lucky",
        "lightgbm_skill_vs_zero": 0.5,
        "beats_zero": "True",
        "net_return_sum": "0.01",
    }
    with pytest.raises(ValueError, match="DUPLICATE_RESULT"):
        h.evaluate_success([dict(row) for _ in range(10)])
    with pytest.raises(ValueError, match="DUPLICATE_RESULT"):
        h.descriptive_ranking([dict(row) for _ in range(10)])


def test_silver_check_warns_but_rebuild_fails_clearly(tmp_path: Path) -> None:
    assert h.silver_status(tmp_path)["status"] == "ABSENT"
    with pytest.raises(h.SilverMissingError, match="Gold rebuild needs Silver"):
        h.require_silver(tmp_path, "Gold rebuild")
    silver = tmp_path / "phase7" / "silver" / "binance"
    silver.mkdir(parents=True)
    (silver / "m.json").write_text("{}")
    (silver / "p.parquet").write_bytes(b"x")
    assert h.silver_status(tmp_path)["status"] == "PRESENT"
    h.require_silver(tmp_path, "Gold rebuild")
