"""Added by Claude (2026-11-02, finding M-01): context must not depend on future label VALUES.

Perturbing every label beyond a fold's TRAIN end (values and label end times) must leave the
computed fold-context features unchanged, and must also leave the context at every timestamp
before that edge unchanged when the later rows are removed altogether.
"""

from __future__ import annotations

from datetime import timedelta

import pyarrow as pa
import pytest

from crypto_ai.phase7.features import bind_fold_cross_sectional_context, build_fold_context_table
from tests.phase7.test_fold_context_causality import (
    CONTEXT_OUTPUTS,
    H15,
    H60,
    START,
)

TRAIN_END = START + timedelta(minutes=15)


def _with_labels(table: pa.Table, *, shift: float, shift_after_edge_only: bool) -> pa.Table:
    times = table.column("feature_time").to_pylist()
    values = [
        0.001 * index + (shift if (not shift_after_edge_only or when >= TRAIN_END) else 0.0)
        for index, when in enumerate(times)
    ]
    ends = [
        when + timedelta(minutes=60 + (7 if (shift and when >= TRAIN_END) else 0)) for when in times
    ]
    table = table.append_column("raw_future_return", pa.array(values))
    return table.append_column("label_end_time", pa.array(ends))


def _same(left: pa.Table, right: pa.Table, column: str) -> bool:
    a, b = left.column(column).to_pylist(), right.column(column).to_pylist()
    return all(x == y or (x != x and y != y) for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("source_table", [H15, H60])
def test_perturbing_labels_after_train_end_leaves_context_unchanged(source_table) -> None:
    baseline = _with_labels(source_table, shift=0.0, shift_after_edge_only=True)
    perturbed = _with_labels(source_table, shift=5.0, shift_after_edge_only=True)
    context_a = build_fold_context_table(baseline)
    context_b = build_fold_context_table(perturbed)
    for column in CONTEXT_OUTPUTS:
        assert _same(context_a, context_b, column), column
    bound_a = bind_fold_cross_sectional_context(baseline, context_source=baseline)
    bound_b = bind_fold_cross_sectional_context(perturbed, context_source=perturbed)
    for column in CONTEXT_OUTPUTS:
        assert _same(bound_a, bound_b, column), column


def test_context_before_the_edge_ignores_all_rows_after_it() -> None:
    full = _with_labels(pa.concat_tables([H15, H60]), shift=5.0, shift_after_edge_only=True)
    keep = pa.array([when < TRAIN_END for when in full.column("feature_time").to_pylist()])
    before_only = full.filter(keep)
    context_full = build_fold_context_table(full)
    context_before = build_fold_context_table(before_only)
    early = context_full.filter(
        pa.array([when < TRAIN_END for when in context_full.column("feature_time").to_pylist()])
    )
    assert early.num_rows == context_before.num_rows
    order = ["symbol", "feature_time"]
    early = early.sort_by([(name, "ascending") for name in order])
    context_before = context_before.sort_by([(name, "ascending") for name in order])
    for column in CONTEXT_OUTPUTS:
        assert _same(early, context_before, column), column
