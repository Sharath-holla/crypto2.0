from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from crypto_ai.data.schema import candles_to_table
from crypto_ai.features import generate_baseline_features
from crypto_ai.labels import generate_forward_return_labels
from crypto_ai.research.config import FeatureConfig, LabelConfig
from tests.research_helpers import make_research_candles


def test_forward_label_uses_next_open_then_open_sixty_minutes_later() -> None:
    candles = make_research_candles(20)
    result = generate_forward_return_labels(
        candles_to_table(candles), interval="5m", config=LabelConfig()
    )

    assert result.valid_count == 7
    assert result.feature_time_us[0] == int(candles[1].open_time.timestamp() * 1_000_000)
    assert result.entry_time_us[0] == int(candles[1].open_time.timestamp() * 1_000_000)
    assert result.label_end_time_us[0] == int(candles[13].open_time.timestamp() * 1_000_000)
    assert result.entry_indices[0] == 1
    assert result.target_indices[0] == 13
    expected = float(candles[13].open / candles[1].open - 1)
    assert result.returns[0] == pytest.approx(expected)
    assert result.reason_counts == {"insufficient_future": 13, "gap_in_horizon": 0}


def test_label_generation_invalidates_horizons_crossing_a_gap() -> None:
    candles = make_research_candles(30, gap_index=8)
    result = generate_forward_return_labels(
        candles_to_table(candles), interval="5m", config=LabelConfig()
    )

    assert not result.valid_mask[0]
    assert result.reason_counts["gap_in_horizon"] > 0
    assert result.reason_counts["insufficient_future"] == 13


def test_label_output_is_deterministic_and_versioned() -> None:
    table = candles_to_table(make_research_candles(25))
    config = LabelConfig()
    first = generate_forward_return_labels(table, interval="5m", config=config)
    second = generate_forward_return_labels(table, interval="5m", config=config)

    np.testing.assert_array_equal(first.valid_mask, second.valid_mask)
    np.testing.assert_allclose(first.returns[first.valid_mask], second.returns[second.valid_mask])
    assert first.label_hash == second.label_hash == config.config_hash


def test_horizon_must_be_divisible_by_candle_interval() -> None:
    with pytest.raises(ValueError, match="not divisible"):
        LabelConfig(horizon_minutes=62).horizon_steps("5m")


def test_baseline_features_have_expected_warmup_and_formulas() -> None:
    candles = make_research_candles(100)
    config = FeatureConfig()
    result = generate_baseline_features(candles_to_table(candles), interval="5m", config=config)

    assert np.count_nonzero(result.warmup_mask) == 49
    assert result.valid_count == 51
    assert result.values["return_5m"][1] == pytest.approx(
        float(candles[1].close / candles[0].close - 1)
    )
    expected_ema20 = np.mean([float(candle.close) for candle in candles[:20]])
    assert result.values["ema20_distance"][19] == pytest.approx(
        float(candles[19].close) / expected_ema20 - 1
    )
    assert np.isfinite(result.values["rolling_volatility_1h"][12])
    assert 0 <= result.values["rsi14"][49] <= 100
    assert not np.any(result.unexpected_invalid_mask)


def test_features_do_not_read_future_rows() -> None:
    candles = make_research_candles(100)
    table = candles_to_table(candles)
    first = generate_baseline_features(table, interval="5m", config=FeatureConfig())
    mutated = list(candles)
    mutated[70] = replace(
        mutated[70],
        open=mutated[70].open * 2,
        high=mutated[70].high * 2,
        low=mutated[70].low * 2,
        close=mutated[70].close * 2,
    )
    second = generate_baseline_features(
        candles_to_table(mutated), interval="5m", config=FeatureConfig()
    )

    for name in FeatureConfig().columns:
        np.testing.assert_allclose(
            first.values[name][:70], second.values[name][:70], equal_nan=True
        )


def test_feature_warmup_restarts_after_a_gap() -> None:
    candles = make_research_candles(120, gap_index=60)
    result = generate_baseline_features(
        candles_to_table(candles), interval="5m", config=FeatureConfig()
    )

    gap_successor = 60
    assert result.contiguous_history[gap_successor] == 1
    assert result.warmup_mask[gap_successor]
    assert result.valid_mask[gap_successor + 49]


def test_official_feature_schema_rejects_future_or_unknown_columns() -> None:
    with pytest.raises(ValueError, match="approved leakage-reviewed"):
        FeatureConfig(columns=("future_return_60m",))
