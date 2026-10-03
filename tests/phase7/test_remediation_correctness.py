from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.features import _ema
from crypto_ai.phase7.metrics import _spearman, cross_sectional_ic
from crypto_ai.phase7.training import _load_fold_rows


def _plan(start: datetime, end: datetime) -> FoldPlan:
    span = end - start
    return FoldPlan(
        fold_id="fold-test",
        index=0,
        train_start=start,
        train_end=start + span / 4,
        validation_start=start + span / 4,
        validation_end=start + span / 2,
        calibration_start=start + span / 2,
        calibration_end=start + span * 3 / 4,
        test_start=start + span * 3 / 4,
        test_end=end,
    )


def _write_partition(
    root: Path, symbol: str, year: int, times: list[datetime], horizon: int = 60
) -> Path:
    path = root / f"symbol={symbol}" / f"year={year}" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    size = len(times)
    table = pa.table(
        {
            "symbol": [symbol] * size,
            "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
            "entry_time": pa.array(
                [item + timedelta(minutes=5) for item in times],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "label_end_time": pa.array(
                [item + timedelta(minutes=65) for item in times],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "horizon_minutes": [horizon] * size,
            "raw_future_return": np.arange(size, dtype=np.float64) / 100,
            "feature_a": np.arange(size, dtype=np.float64),
        }
    )
    pq.write_table(table, path)
    return path


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2021, 6, 1, tzinfo=UTC), datetime(2022, 6, 1, tzinfo=UTC)),
        (datetime(2020, 6, 1, tzinfo=UTC), datetime(2023, 6, 1, tzinfo=UTC)),
        (datetime(2021, 6, 1, tzinfo=UTC), datetime(2023, 1, 1, tzinfo=UTC)),
    ],
)
def test_year_partition_pruning_is_logically_equivalent(
    tmp_path: Path, start: datetime, end: datetime
) -> None:
    paths: list[Path] = []
    for symbol in ("BTCUSDT", "HNTUSDT"):
        for year in range(2020, 2025):
            # HNT has no 2020 partition, modelling a later listing/delisted-style
            # sparse symbol/year layout without manufacturing missing rows.
            if symbol == "HNTUSDT" and year == 2020:
                continue
            paths.append(
                _write_partition(
                    tmp_path,
                    symbol,
                    year,
                    [
                        datetime(year, 1, 1, tzinfo=UTC),
                        datetime(year, 7, 1, tzinfo=UTC),
                    ],
                )
            )
    manifest = {"partition_files": [{"path": str(path)} for path in paths]}
    plan = _plan(start, end)
    legacy = (
        ds.dataset([str(path) for path in paths], format="parquet")
        .to_table(
            filter=(ds.field("feature_time") >= pa.scalar(start))
            & (ds.field("feature_time") < pa.scalar(end))
            & (ds.field("horizon_minutes") == 60)
        )
        .sort_by([("feature_time", "ascending"), ("symbol", "ascending")])
    )
    partitioned = ds.dataset([str(path) for path in paths], format="parquet", partitioning="hive")
    actual = _load_fold_rows(manifest, plan, 60, dataset=partitioned)
    assert actual.select(legacy.column_names).equals(legacy)


def test_ema_waits_for_first_causal_contiguous_seed_and_restarts_after_gap() -> None:
    values = np.asarray([np.nan, 1.0, 2.0, 3.0, 4.0, np.nan, 10.0, 11.0, 12.0])
    result = _ema(values, 3)
    assert np.all(np.isnan(result[:3]))
    assert result[3] == pytest.approx(2.0)
    assert result[4] == pytest.approx(3.0)
    assert np.all(np.isnan(result[5:8]))
    assert result[8] == pytest.approx(11.0)


def test_cross_sectional_ic_matches_reference_group_formula() -> None:
    times = np.repeat(np.asarray([3, 1, 2, 4], dtype=np.int64), 4)
    symbols = np.tile(np.asarray(["A", "B", "C", "D"], dtype=object), 4)
    actual = np.asarray([0.1, 0.4, 0.2, 0.3] * 4, dtype=np.float64)
    predicted = np.asarray([0.2, 0.3, 0.1, 0.4] * 4, dtype=np.float64)
    predicted[13] = np.nan
    report = cross_sectional_ic(times, symbols, actual, predicted, minimum_assets=3)
    expected = []
    for timestamp in np.unique(times):
        rows = (times == timestamp) & np.isfinite(actual) & np.isfinite(predicted)
        value = _spearman(actual[rows], predicted[rows])
        if value is not None:
            expected.append(value)
    assert [row["feature_time_us"] for row in report["timestamps"]] == [1, 2, 3, 4]
    assert report["mean_spearman_ic"] == pytest.approx(float(np.mean(expected)))
