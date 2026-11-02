"""Independent review regressions for accounting."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pyarrow as pa

from crypto_ai.phase7 import training


def test_finite_attrition_survives_prepared_cache_round_trip(tmp_path):
    from crypto_ai.phase7.prepared_cache import PreparedDataCache
    from tests.phase7.test_prepared_cache import _fixture

    plan, fold, _, identity = _fixture()
    values = fold.train["f1"].to_pylist()
    values[0] = np.nan
    raw_train = fold.train.set_column(
        fold.train.schema.get_field_index("f1"), "f1", pa.array(values)
    )
    fold = replace(fold, train=raw_train)
    prepared = training._prepare_training_segments(fold, ("f1",), "raw_future_return")
    assert prepared.pre_filter_rows["train"] == 6
    assert prepared.train.num_rows == 5
    cache = PreparedDataCache(tmp_path / "cache", "auto")
    cache.write(identity, fold, prepared)
    loaded = cache.load(identity, plan)
    assert loaded.fold.train.num_rows == 5  # cached table is already finite-filtered
    assert loaded.prepared.pre_filter_rows == prepared.pre_filter_rows
    accounting = training.finite_row_accounting(
        {
            "train": (loaded.prepared.pre_filter_rows["train"], loaded.prepared.train.num_rows),
        }
    )
    assert accounting["segments"]["train"]["dropped_rows"] == 1
