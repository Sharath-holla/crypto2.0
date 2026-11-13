# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
"""RUNTIME-ONLY candidate optimizations (benchmark harness). Repository files are not modified.
Each patch must return tables with identical values/order to the production function."""

from datetime import timedelta

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds


def _contiguous_or_filter(table, mask_np):
    mask_np = np.asarray(mask_np, dtype=bool)
    idx = np.flatnonzero(mask_np)
    if len(idx) == len(mask_np):
        return table
    if len(idx) == 0:
        return table.slice(0, 0)
    if idx[-1] - idx[0] + 1 == len(idx):
        return table.slice(int(idx[0]), len(idx))
    return table.filter(pa.array(mask_np))


def apply(group_size=16):
    import crypto_ai.phase5.folds as F5
    import crypto_ai.phase7.folds as F7
    import crypto_ai.phase7.training as T

    def _range(table, start, end):
        v = F5._times(table, "feature_time")
        s, e = int(start.timestamp() * 1e6), int(end.timestamp() * 1e6)
        return _contiguous_or_filter(table, (v >= s) & (v < e))

    def _prepare_previous(table, next_start):
        before = table.num_rows
        b = int(next_start.timestamp() * 1e6)
        kept = _contiguous_or_filter(table, F5._times(table, "label_end_time") < b)
        return kept, before - kept.num_rows

    def _embargo(table, start, minutes):
        if minutes == 0:
            return table, 0
        before = table.num_rows
        e = int(start.timestamp() * 1e6) + minutes * F5._US_PER_MINUTE
        kept = _contiguous_or_filter(table, F5._times(table, "feature_time") >= e)
        return kept, before - kept.num_rows

    F5._range, F5._prepare_previous, F5._embargo = _range, _prepare_previous, _embargo

    def _filter_symbols(table, symbols):
        mask = pc.fill_null(
            pc.is_in(table.column("symbol"), value_set=pa.array(sorted(symbols), pa.string())),
            False,
        )
        if pc.all(mask).as_py():
            return table
        return table.filter(mask)

    F7._filter_symbols = _filter_symbols

    def _finite(table, columns, target):
        names = columns + (target,)
        mask = pc.is_finite(table.column(names[0]))
        for name in names[1:]:
            mask = pc.and_(mask, pc.is_finite(table.column(name)))
        valid = pc.fill_null(mask, False)
        if pc.all(valid).as_py() is True:
            return table
        return _contiguous_or_filter(table, valid.to_numpy(zero_copy_only=False))

    T._finite = _finite

    original_load = T._load_fold_rows

    def _load_fold_rows(manifest, plan, horizon_minutes, *, dataset=None, columns=None):
        if dataset is None:
            return original_load(manifest, plan, horizon_minutes, columns=columns)
        cond = (
            (ds.field("feature_time") >= pa.scalar(plan.train_start))
            & (ds.field("feature_time") < pa.scalar(plan.test_end))
            & (ds.field("horizon_minutes") == horizon_minutes)
        )
        if "year" in dataset.schema.names:
            end_year = (plan.test_end - timedelta(microseconds=1)).year
            cond = (
                (ds.field("year") >= plan.train_start.year) & (ds.field("year") <= end_year) & cond
            )
        names = list(columns) if columns is not None else [n for n in dataset.schema.names]
        keys = dataset.to_table(filter=cond, columns=["feature_time", "symbol"])
        order = pc.sort_indices(
            keys, sort_keys=[("feature_time", "ascending"), ("symbol", "ascending")]
        )
        del keys
        arrays = {}
        for i in range(0, len(names), group_size):
            part = dataset.to_table(filter=cond, columns=names[i : i + group_size]).take(order)
            for n in part.column_names:
                arrays[n] = part.column(n).combine_chunks()
            del part
            pa.default_memory_pool().release_unused()
        return pa.table({n: arrays[n] for n in names})

    T._load_fold_rows = _load_fold_rows
