from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.config import FeatureConfig, TargetConfig
from crypto_ai.phase7.features import (
    generate_multiasset_features,
    validate_multiasset_primary_key,
)
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry
from crypto_ai.phase7.metrics import evaluate_predictions
from crypto_ai.phase7.targets import generate_multiasset_targets


def _config() -> FeatureConfig:
    return FeatureConfig(
        correlation_window_rows=24,
        liquidity_window_rows=24,
        volatility_window_rows=24,
        daily_volatility_rows=24,
        seven_day_volatility_rows=48,
        include_12h=False,
        include_1d=False,
        include_derivatives=False,
    )


def _column(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _times(table: pa.Table) -> np.ndarray:
    return table.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()


def _symbols(table: pa.Table) -> np.ndarray:
    return np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)


def _compare_before(
    left: pa.Table, right: pa.Table, cutoff_us: int, columns: tuple[str, ...]
) -> None:
    left_rows = _times(left) < cutoff_us
    right_rows = _times(right) < cutoff_us
    assert left.column("symbol").to_pylist() == right.column("symbol").to_pylist()
    assert np.array_equal(left_rows, right_rows)
    for name in columns:
        assert np.allclose(
            _column(left, name)[left_rows],
            _column(right, name)[right_rows],
            equal_nan=True,
        )


def test_future_price_perturbation_does_not_change_past_features() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    split = int(np.unique(times)[100])
    baseline = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=_config()
    )
    rows = candles.to_pylist()
    for index, row in enumerate(rows):
        if symbols[index] == "SOLUSDT" and times[index] >= split:
            for name in ("open", "high", "low", "close"):
                row[name] = float(row[name]) * 2.0
    changed = generate_multiasset_features(
        pa.Table.from_pylist(rows), registry=synthetic_registry(), config=_config()
    )
    _compare_before(
        baseline.table,
        changed.table,
        split,
        ("return_5m", "daily_volatility", "relative_strength_vs_btc"),
    )


def test_future_anchor_prices_do_not_change_past_btc_or_eth_context() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    split = int(np.unique(times)[100])
    baseline = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=_config()
    )
    rows = candles.to_pylist()
    for index, row in enumerate(rows):
        if symbols[index] in {"BTCUSDT", "ETHUSDT"} and times[index] >= split:
            for name in ("open", "high", "low", "close"):
                row[name] = float(row[name]) * 1.5
    changed = generate_multiasset_features(
        pa.Table.from_pylist(rows), registry=synthetic_registry(), config=_config()
    )
    _compare_before(
        baseline.table,
        changed.table,
        split,
        ("btc_return_1h", "eth_return_1h", "btc_correlation", "eth_correlation"),
    )


def test_future_symbol_rows_do_not_change_past_market_breadth() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    split = int(np.unique(times)[100])
    baseline_rows = np.flatnonzero(symbols != "XRPUSDT")
    future_xrp = np.flatnonzero((symbols == "XRPUSDT") & (times >= split))
    baseline_table = candles.take(pa.array(baseline_rows, type=pa.int64()))
    changed_table = candles.take(
        pa.array(np.concatenate((baseline_rows, future_xrp)), type=pa.int64())
    )
    baseline = generate_multiasset_features(
        baseline_table, registry=synthetic_registry(), config=_config()
    ).table
    changed = generate_multiasset_features(
        changed_table, registry=synthetic_registry(), config=_config()
    ).table
    changed_symbols = _symbols(changed)
    changed_times = _times(changed)
    changed = changed.filter(pa.array(~((changed_symbols == "XRPUSDT") & (changed_times >= split))))
    _compare_before(
        baseline,
        changed,
        split,
        ("market_member_count", "market_mean_return", "market_pct_positive"),
    )


def test_feature_state_resets_after_a_reported_gap() -> None:
    candles = synthetic_candles(rows_per_symbol=100)
    symbols = np.asarray(candles.column("symbol").to_pylist(), dtype=object)
    symbol_rows = np.flatnonzero(symbols == "BTCUSDT")
    removed = int(symbol_rows[60])
    kept = np.delete(np.arange(candles.num_rows), removed)
    features = generate_multiasset_features(
        candles.take(pa.array(kept, type=pa.int64())),
        registry=synthetic_registry(),
        config=_config(),
    ).table
    btc = np.flatnonzero(_symbols(features) == "BTCUSDT")
    original_time = candles.column("open_time")[removed + 1].as_py() + timedelta(minutes=5)
    row = np.flatnonzero(
        (_symbols(features) == "BTCUSDT")
        & (_times(features) == int(original_time.timestamp() * 1_000_000))
    )[0]
    assert np.isnan(_column(features, "return_5m")[row])
    assert np.count_nonzero(np.isnan(_column(features, "return_5m")[btc])) >= 2


@pytest.mark.parametrize(("prefix", "config_field"), [("12h", "include_12h"), ("1d", "include_1d")])
def test_higher_timeframe_join_never_uses_future_availability(
    prefix: str, config_field: str
) -> None:
    candles = synthetic_candles(rows_per_symbol=100)
    first = candles.column("open_time")[0].as_py()
    context = pa.table(
        {
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "availability_time": [first + timedelta(hours=1), first + timedelta(hours=2)],
            f"htf_{prefix}_return": [1.0, 99.0],
        }
    )
    features = generate_multiasset_features(
        candles,
        registry=synthetic_registry(),
        config=_config().model_copy(update={config_field: True}),
        higher_timeframe_context=context,
    ).table
    btc = _symbols(features) == "BTCUSDT"
    times = _times(features)
    before_second = btc & (times < int((first + timedelta(hours=2)).timestamp() * 1_000_000))
    values = _column(features, f"htf_{prefix}_return")[before_second]
    assert np.all(values[np.isfinite(values)] == 1.0)


def test_normalized_target_uses_feature_time_scale_and_round_trips() -> None:
    candles = synthetic_candles(rows_per_symbol=180)
    features = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=_config()
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=TargetConfig(),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    ).table
    raw = _column(targets, "raw_future_return")
    normalized = _column(targets, "normalized_future_return")
    scale = _column(targets, "ex_ante_volatility_scale")
    valid = np.isfinite(normalized) & np.isfinite(scale)
    assert np.count_nonzero(valid)
    assert np.allclose(normalized[valid] * scale[valid], raw[valid])


def test_duplicate_multiasset_primary_key_is_rejected() -> None:
    features = generate_multiasset_features(
        synthetic_candles(rows_per_symbol=80),
        registry=synthetic_registry(),
        config=_config(),
    ).table
    duplicate = pa.concat_tables([features, features.slice(0, 1)])
    with pytest.raises(ValueError, match="duplicate multi-asset primary key"):
        validate_multiasset_primary_key(duplicate)


def test_macro_metrics_equal_weight_symbols_instead_of_rows() -> None:
    table = pa.table(
        {
            "symbol": ["A"] * 100 + ["B"],
            "feature_time": pa.array(list(range(101)), type=pa.timestamp("us", tz="UTC")),
            "target": [0.0] * 100 + [10.0],
        }
    )
    report = evaluate_predictions(
        table,
        np.zeros(101),
        np.ones(101, dtype=bool),
        target_column="target",
    )
    assert report["micro"]["mae"] == pytest.approx(10 / 101)
    assert report["macro"]["mae"] == pytest.approx(5.0)
