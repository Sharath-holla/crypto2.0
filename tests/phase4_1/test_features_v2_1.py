from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from crypto_ai.data.schema import candles_to_table
from crypto_ai.phase4_1.features import (
    CORE_GROUPS_V2_1,
    FEATURE_GROUPS_V2_1,
    MINIMUM_HISTORY_ROWS,
    generate_features_v2_1,
)
from tests.research_helpers import make_research_candles


def test_v2_1_has_precise_taker_semantics_and_expected_size() -> None:
    result = generate_features_v2_1(candles_to_table(make_research_candles(4_500)), interval="5m")

    assert result.columns == tuple(
        name for group in CORE_GROUPS_V2_1 for name in FEATURE_GROUPS_V2_1[group]
    )
    assert len(result.columns) == 52
    assert "pressure" not in result.groups
    assert result.diagnostics["taker_flow_semantics"] == (
        "candle-level aggressive/taker flow; not order-book depth"
    )
    valid_index = int(np.flatnonzero(result.valid_mask)[0])
    assert result.values["taker_buy_base_share"][valid_index] == pytest.approx(0.5)
    assert result.values["taker_sell_base_share"][valid_index] == pytest.approx(0.5)
    assert result.values["taker_flow_imbalance_base"][valid_index] == pytest.approx(0.0)


def test_v2_1_regime_is_future_perturbation_safe() -> None:
    candles = make_research_candles(4_500)
    first = generate_features_v2_1(candles_to_table(candles), interval="5m")
    mutated = list(candles)
    for index in range(3_500, len(mutated)):
        mutated[index] = replace(
            mutated[index],
            open=mutated[index].open * 2,
            high=mutated[index].high * 2,
            low=mutated[index].low * 2,
            close=mutated[index].close * 2,
        )
    second = generate_features_v2_1(candles_to_table(mutated), interval="5m")

    for name in FEATURE_GROUPS_V2_1["regime"]:
        np.testing.assert_allclose(
            first.values[name][:3_500], second.values[name][:3_500], equal_nan=True
        )


def test_v2_1_resets_valid_history_after_a_gap() -> None:
    result = generate_features_v2_1(
        candles_to_table(make_research_candles(5_000, gap_index=2_500)), interval="5m"
    )

    assert not np.any(result.valid_mask[2_500 : 2_500 + MINIMUM_HISTORY_ROWS - 1])
    assert np.any(result.valid_mask[2_500 + MINIMUM_HISTORY_ROWS :])


def test_v2_1_rejects_impossible_taker_values() -> None:
    candles = make_research_candles(2_500)
    candles[100] = replace(
        candles[100],
        taker_buy_quote_volume=candles[100].quote_volume + Decimal("0.1"),
    )

    with pytest.raises(ValueError, match="cannot exceed"):
        generate_features_v2_1(candles_to_table(candles), interval="5m")


def test_v2_1_zero_volume_is_safe_and_reported() -> None:
    candles = make_research_candles(2_500)
    candles[100] = replace(
        candles[100],
        base_volume=Decimal("0"),
        quote_volume=Decimal("0"),
        trade_count=0,
        taker_buy_base_volume=Decimal("0"),
        taker_buy_quote_volume=Decimal("0"),
    )

    result = generate_features_v2_1(candles_to_table(candles), interval="5m")

    assert result.diagnostics["zero_base_volume_rows"] == 1
    assert result.diagnostics["zero_quote_volume_rows"] == 1
    assert result.diagnostics["zero_trade_count_rows"] == 1
    assert not result.valid_mask[100]
