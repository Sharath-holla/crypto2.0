"""Independent review regressions for context."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pytest

from crypto_ai.phase7.config import FeatureConfig
from crypto_ai.phase7.features import (
    MARKET_CONTEXT_COLUMNS,
    bind_fold_cross_sectional_context,
    build_fold_context_table,
    generate_multiasset_features,
)
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry
from crypto_ai.phase7.targets import generate_multiasset_targets
from tests.phase7.test_pre_lightning_finalization import canonical

OUTPUTS = (
    "trailing_liquidity_percentile",
    "trailing_volatility_percentile",
    "trade_intensity_percentile",
    *MARKET_CONTEXT_COLUMNS,
)


@pytest.fixture
def future_gap():
    config = canonical()
    start = datetime(2021, 1, 1, tzinfo=UTC)
    gap = start + timedelta(minutes=900)
    candles = synthetic_candles(rows_per_symbol=260, start=start)
    candles = candles.filter(
        pc.invert(
            pc.and_(
                pc.equal(candles["symbol"], "SOLUSDT"),
                pc.equal(candles["open_time"], pa.scalar(gap)),
            )
        )
    )
    features = generate_multiasset_features(
        candles,
        registry=synthetic_registry(),
        config=FeatureConfig(
            correlation_window_rows=12,
            liquidity_window_rows=12,
            volatility_window_rows=12,
            daily_volatility_rows=12,
            seven_day_volatility_rows=24,
            include_12h=False,
            include_1d=False,
        ),
    ).table
    targets = generate_multiasset_targets(
        candles,
        features,
        config=config.targets,
        research_cutoff=config.research_cutoff,
    ).table
    gold = features.join(targets, keys=["symbol", "feature_time"], join_type="inner")
    return gap, features, gold


def at(table, when, symbol):
    return table.filter(
        pc.and_(
            pc.equal(table["feature_time"], pa.scalar(when)),
            pc.equal(table["symbol"], symbol),
        )
    )


def test_real_gap_short_label_survives_and_all_eleven_context_fields_are_causal(future_gap):
    gap, features, gold = future_gap
    when = gap - timedelta(minutes=40)
    h15 = gold.filter(pc.equal(gold["horizon_minutes"], 15))
    h60 = gold.filter(pc.equal(gold["horizon_minutes"], 60))
    assert at(h15, when, "SOLUSDT").num_rows == 1
    assert at(h60, when, "SOLUSDT").num_rows == 0
    expected = build_fold_context_table(features)
    for symbol in ("BTCUSDT", "ETHUSDT", "XRPUSDT"):
        reference = at(expected, when, symbol)
        first = at(bind_fold_cross_sectional_context(h15, context_source=gold), when, symbol)
        second = at(bind_fold_cross_sectional_context(h60, context_source=gold), when, symbol)
        for name in OUTPUTS:
            np.testing.assert_allclose(
                second[name].to_numpy(),
                reference[name].to_numpy(),
                rtol=1e-12,
                atol=1e-15,
                equal_nan=True,
            )
            np.testing.assert_array_equal(first[name].to_numpy(), second[name].to_numpy())


def test_all_labels_missing_is_not_accepted_as_observable_context(future_gap):
    gap, features, gold = future_gap
    when = gap - timedelta(minutes=20)
    assert at(features, when, "SOLUSDT").num_rows == 1
    assert at(gold, when, "SOLUSDT").num_rows == 0
    # A surviving coin still has a 60m label, so this is a model-facing defect.
    assert at(gold.filter(pc.equal(gold["horizon_minutes"], 60)), when, "BTCUSDT").num_rows == 1
    reference = at(build_fold_context_table(features), when, "BTCUSDT")
    unchecked = at(build_fold_context_table(gold), when, "BTCUSDT")
    assert reference["market_member_count"][0].as_py() == 4
    assert unchecked["market_member_count"][0].as_py() == 3
    with pytest.raises(ValueError, match="M01_CONTEXT_SOURCE_INCOMPLETE"):
        build_fold_context_table(gold, verify_observable_coverage=True)


def test_complete_observable_union_is_checked_then_compacted(future_gap):
    gap, features, gold = future_gap
    # Earlier timestamps have observable rows in the union even when 60m labels vanish.
    early = gold.filter(pc.less(gold["feature_time"], pa.scalar(gap - timedelta(minutes=20))))
    compact = build_fold_context_table(early, verify_observable_coverage=True)
    assert compact.num_rows * 2 < early.num_rows
    when = gap - timedelta(minutes=40)
    for name in OUTPUTS:
        np.testing.assert_allclose(
            at(compact, when, "ETHUSDT")[name].to_numpy(),
            at(build_fold_context_table(features), when, "ETHUSDT")[name].to_numpy(),
            rtol=1e-12,
            atol=1e-15,
            equal_nan=True,
        )
