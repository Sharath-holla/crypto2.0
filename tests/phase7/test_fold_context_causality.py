"""M-01: fold cross-sectional context must not depend on one horizon's label availability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.features import (
    CROSS_SECTIONAL_SOURCE_COLUMNS,
    FOLD_CONTEXT_VERSION,
    MARKET_CONTEXT_COLUMNS,
    bind_fold_cross_sectional_context,
    build_fold_context_table,
)

START = datetime(2022, 1, 1, tzinfo=UTC)
SYMBOLS = ("AAAUSDT", "BBBUSDT", "CCCUSDT")
CONTEXT_OUTPUTS = (
    "trailing_liquidity_percentile",
    "trailing_volatility_percentile",
    "trade_intensity_percentile",
    *MARKET_CONTEXT_COLUMNS,
    "market_membership_hash",
)


def _rows(horizon: int, missing: set[tuple[str, int]]) -> pa.Table:
    """Synthetic Gold-like rows for one horizon; ``missing`` simulates absent labels."""
    records: list[dict[str, object]] = []
    for step in range(6):
        for index, symbol in enumerate(SYMBOLS):
            if (symbol, step) in missing:
                continue
            records.append(
                {
                    "symbol": symbol,
                    "feature_time": START + timedelta(minutes=5 * step),
                    "horizon_minutes": horizon,
                    "return_5m": 0.001 * (index + 1) * (-1) ** step,
                    "realized_volatility_1h": 0.01 * (index + 1) + 0.001 * step,
                    "taker_flow_imbalance": 0.1 * (index - 1),
                    CROSS_SECTIONAL_SOURCE_COLUMNS[0]: 100.0 * (index + 1) + step,
                    CROSS_SECTIONAL_SOURCE_COLUMNS[1]: 0.5 * (3 - index),
                    CROSS_SECTIONAL_SOURCE_COLUMNS[2]: 10.0 + index * 2 - step,
                }
            )
    table = pa.Table.from_pylist(records)
    placeholder = pa.array([np.nan] * table.num_rows)
    for name in CONTEXT_OUTPUTS:
        table = table.append_column(
            name, pa.array([""] * table.num_rows) if name == "market_membership_hash" else placeholder
        )
    return table


# CCC loses its 60m label for the last two timestamps (e.g. a data gap just after
# them); its 15m label survives one step longer. Features exist for every symbol.
H15 = _rows(15, {("CCCUSDT", 5)})
H60 = _rows(60, {("CCCUSDT", 4), ("CCCUSDT", 5)})


def _by_key(table: pa.Table, column: str) -> dict[tuple[str, datetime], object]:
    return {
        (symbol, when): value
        for symbol, when, value in zip(
            table.column("symbol").to_pylist(),
            table.column("feature_time").to_pylist(),
            table.column(column).to_pylist(),
            strict=True,
        )
    }


def test_legacy_single_horizon_binding_leaks_label_availability() -> None:
    """Documents the defect: without an all-horizon source, context varies by horizon."""
    legacy15 = _by_key(bind_fold_cross_sectional_context(H15), "market_member_count")
    legacy60 = _by_key(bind_fold_cross_sectional_context(H60), "market_member_count")
    step4 = START + timedelta(minutes=20)
    assert legacy15[("AAAUSDT", step4)] == 3.0
    assert legacy60[("AAAUSDT", step4)] == 2.0  # shrunk by horizon-60 label availability


def test_all_horizon_context_is_identical_across_horizons() -> None:
    source = pa.concat_tables([H15, H60])
    bound15 = bind_fold_cross_sectional_context(H15, context_source=source)
    bound60 = bind_fold_cross_sectional_context(H60, context_source=source)
    for column in CONTEXT_OUTPUTS:
        first = _by_key(bound15, column)
        second = _by_key(bound60, column)
        for key in first.keys() & second.keys():
            left, right = first[key], second[key]
            assert (left == right) or (left != left and right != right), (column, key)
    step4 = START + timedelta(minutes=20)
    assert _by_key(bound60, "market_member_count")[("AAAUSDT", step4)] == 3.0
    assert set(bound60.column("cross_sectional_context_scope").to_pylist()) == {
        "FOLD_ACTIVE_SYMBOLS"
    }


def test_context_is_unchanged_by_removing_a_horizons_labels() -> None:
    """Dropping rows from one horizon's labels cannot change another horizon's context."""
    baseline_source = pa.concat_tables([H15, H60])
    thinned_60 = _rows(60, {("CCCUSDT", 4), ("CCCUSDT", 5), ("BBBUSDT", 5)})
    thinned_source = pa.concat_tables([H15, thinned_60])
    before = bind_fold_cross_sectional_context(H15, context_source=baseline_source)
    after = bind_fold_cross_sectional_context(H15, context_source=thinned_source)
    for column in CONTEXT_OUTPUTS:
        for left, right in zip(
            before.column(column).to_pylist(), after.column(column).to_pylist(), strict=True
        ):
            assert left == right or (left != left and right != right), column


def test_context_at_a_timestamp_ignores_later_rows() -> None:
    """Appending future timestamps leaves context at earlier timestamps untouched."""
    full = pa.concat_tables([H15, H60])
    early_keep = [
        (when < START + timedelta(minutes=15)) for when in full.column("feature_time").to_pylist()
    ]
    early = full.filter(pa.array(early_keep))
    context_full = build_fold_context_table(full)
    context_early = build_fold_context_table(early)
    cutoff = START + timedelta(minutes=15)
    full_rows = {
        (s, t): i
        for i, (s, t) in enumerate(
            zip(
                context_full.column("symbol").to_pylist(),
                context_full.column("feature_time").to_pylist(),
                strict=True,
            )
        )
        if t < cutoff
    }
    for i, key in enumerate(
        zip(
            context_early.column("symbol").to_pylist(),
            context_early.column("feature_time").to_pylist(),
            strict=True,
        )
    ):
        j = full_rows[key]
        for column in CONTEXT_OUTPUTS:
            a = context_early.column(column)[i].as_py()
            b = context_full.column(column)[j].as_py()
            assert a == b or (a != a and b != b)


def test_duplicate_rows_that_disagree_are_rejected() -> None:
    corrupted = _rows(60, set())
    values = corrupted.column("return_5m").to_pylist()
    values[0] += 1.0
    corrupted = corrupted.set_column(
        corrupted.schema.get_field_index("return_5m"), "return_5m", pa.array(values)
    )
    with pytest.raises(ValueError, match="disagrees across duplicate"):
        build_fold_context_table(pa.concat_tables([H15, corrupted]))


def test_context_must_cover_every_modelled_row() -> None:
    narrow_source = _rows(15, {("CCCUSDT", step) for step in range(6)})
    with pytest.raises(ValueError, match="does not cover every model row"):
        bind_fold_cross_sectional_context(H15, context_source=narrow_source)


def test_context_version_is_declared_for_cache_identity() -> None:
    assert FOLD_CONTEXT_VERSION == "fold_context_v3_label_independent"
