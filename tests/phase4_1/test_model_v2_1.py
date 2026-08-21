from __future__ import annotations

import numpy as np

from crypto_ai.phase4_1.model import (
    _block_bootstrap,
    derivatives_ablation_sets,
    long_history_ablation_sets,
)


def test_long_history_ablations_are_nested_and_predeclared() -> None:
    ablations = long_history_ablation_sets()

    assert list(ablations) == ["L0", "L1", "L2", "L3", "L4", "L5"]
    assert len(ablations["L0"]) == 13
    assert set(ablations["L2"]) > set(ablations["L1"])
    assert set(ablations["L3"]) > set(ablations["L2"])
    assert set(ablations["L4"]) > set(ablations["L3"])
    assert "taker_buy_base_share" in ablations["L4"]
    assert "bull_regime" in ablations["L5"]
    assert "sideways_regime" not in ablations["L5"]


def test_derivatives_ablations_do_not_require_short_oi_history() -> None:
    without_oi = derivatives_ablation_sets(include_open_interest=False)
    with_oi = derivatives_ablation_sets(include_open_interest=True)

    assert list(without_oi) == ["D0", "D1", "D2"]
    assert list(with_oi) == ["D0", "D1", "D2", "D3"]
    assert "funding_rate" not in without_oi["D0"]
    assert "funding_rate" in without_oi["D1"]
    assert "mark_index_basis" in without_oi["D2"]
    assert "open_interest_change_1h" in with_oi["D3"]


def test_block_bootstrap_is_seeded_and_reports_uncertainty() -> None:
    actual = np.sin(np.arange(2_000) / 10.0) * 0.001
    predicted = actual * 0.2 + np.cos(np.arange(2_000) / 17.0) * 0.0001

    first = _block_bootstrap(actual, predicted, seed=42, samples=20, block_rows=24)
    second = _block_bootstrap(actual, predicted, seed=42, samples=20, block_rows=24)

    assert first == second
    interval = first["intervals_95pct"]["pearson_ic"]
    assert interval["lower"] <= interval["median"] <= interval["upper"]
