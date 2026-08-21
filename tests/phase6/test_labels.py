from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.data.schema import candles_to_table
from crypto_ai.labels import generate_forward_return_labels
from crypto_ai.phase6.config import LABEL_RESEARCH_VERSION
from crypto_ai.phase6.labels import (
    BARRIER_AMBIGUOUS,
    BARRIER_SL,
    BARRIER_TP,
    HORIZON_STEPS,
    generate_research_labels,
)
from crypto_ai.research.config import LabelConfig
from tests.research_helpers import make_research_candles


def test_label_v1_remains_unchanged_and_v2_is_separate() -> None:
    table = candles_to_table(make_research_candles(100))
    original = generate_forward_return_labels(table, interval="5m", config=LabelConfig())

    assert original.label_hash == LabelConfig().config_hash
    assert LABEL_RESEARCH_VERSION.startswith("label_v2_research")
    assert LabelConfig().version != LABEL_RESEARCH_VERSION


def test_multi_horizon_entry_and_label_end_timing() -> None:
    candles = candles_to_table(make_research_candles(100))
    result = generate_research_labels(candles, atr_pct=np.full(100, 0.001))
    opens = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()

    assert result.entry_time_us[0] == result.feature_time_us[0] == opens[1]
    for horizon, steps in HORIZON_STEPS.items():
        name = f"forward_return_{horizon}"
        assert result.label_end_time_us[name][0] == opens[1 + steps]
        expected = float(
            candles.column("open")[1 + steps].as_py() / candles.column("open")[1].as_py()
            - Decimal(1)
        )
        assert result.values[name][0] == pytest.approx(expected)


def test_gap_crossing_invalidates_every_affected_horizon() -> None:
    candles = candles_to_table(make_research_candles(100, gap_index=10))
    result = generate_research_labels(candles, atr_pct=np.full(candles.num_rows, 0.001))

    assert not result.valid["forward_return_15m"][8]
    assert result.reason_counts["15m"]["gap_crossing_invalidated"] > 0


def test_mfe_and_mae_are_correct_and_not_features() -> None:
    candles = make_research_candles(30)
    table = candles_to_table(candles)
    result = generate_research_labels(table, atr_pct=np.full(30, 0.001))
    entry = float(candles[1].open)
    expected_mfe = max(float(item.high) for item in candles[1:4]) / entry - 1.0
    expected_mae = 1.0 - min(float(item.low) for item in candles[1:4]) / entry

    assert result.values["mfe_long_15m"][0] == expected_mfe
    assert result.values["mae_long_15m"][0] == expected_mae
    assert all("mfe" not in name and "mae" not in name for name in ("feature_time",))


def test_same_coarse_bar_tp_and_sl_is_ambiguous_without_1m() -> None:
    candles = make_research_candles(100)
    entry = candles[1].open
    candles[1] = replace(
        candles[1],
        high=entry * Decimal("1.01"),
        low=entry * Decimal("0.99"),
    )
    result = generate_research_labels(
        candles_to_table(candles), atr_pct=np.full(100, 0.001), minute_candles=None
    )

    assert result.values["tp_before_sl_symmetric_1_0_atr_1h"][0] == BARRIER_AMBIGUOUS
    assert result.barrier_resolution["tp_before_sl_symmetric_1_0_atr_1h"]["ambiguous"] > 0


@pytest.mark.parametrize(
    "high_multiple,low_multiple,expected",
    [("1.002", "0.9995", BARRIER_TP), ("1.0005", "0.998", BARRIER_SL)],
)
def test_single_barrier_ordering_is_classified_safely(
    high_multiple: str, low_multiple: str, expected: int
) -> None:
    candles = make_research_candles(100)
    entry = candles[1].open
    candles[1] = replace(
        candles[1],
        high=entry * Decimal(high_multiple),
        low=entry * Decimal(low_multiple),
    )
    result = generate_research_labels(
        candles_to_table(candles), atr_pct=np.full(100, 0.001), minute_candles=None
    )

    assert result.values["tp_before_sl_symmetric_1_0_atr_1h"][0] == expected


def test_excursion_labels_never_cross_terminal_data() -> None:
    candles = candles_to_table(
        make_research_candles(60, start=datetime(2026, 6, 30, 19, tzinfo=UTC))
    )
    result = generate_research_labels(candles, atr_pct=np.full(60, 0.001))

    assert not result.valid["forward_return_4h"][-1]
    assert result.label_end_time_us["forward_return_4h"][-1] == -1
