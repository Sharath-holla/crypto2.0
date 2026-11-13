# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
"""Synthetic Gold-schema dataset at measured Fold-0/60m scale. NOT market data."""

import json
import pathlib
import sys
from datetime import timedelta

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7.config import load_phase7_config

HTF12 = [
    "return",
    "log_return",
    "range_pct",
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "close_location",
    "ema20_distance",
    "ema20_50_spread",
    "ema20_slope_3bar",
    "rsi14",
    "roc4",
    "realized_vol_1d",
    "realized_vol_3d",
    "realized_vol_7d",
    "atr14_pct",
    "relative_quote_volume",
    "volume_zscore",
    "trade_count_intensity",
    "taker_buy_share",
    "taker_sell_share",
    "taker_flow_imbalance",
]
HTF1D = [
    "return",
    "log_return",
    "range_pct",
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "close_location",
    "ema20_distance",
    "ema50_distance",
    "ema100_distance",
    "ema200_distance",
    "ema20_50_spread",
    "ema50_200_spread",
    "ema20_slope_5d",
    "rsi14",
    "roc7",
    "realized_vol_3d",
    "realized_vol_7d",
    "realized_vol_30d",
    "atr14_pct",
    "volatility_zscore",
    "volatility_of_volatility",
    "relative_quote_volume",
    "volume_zscore",
    "trade_count_intensity",
    "taker_buy_share",
    "taker_sell_share",
    "taker_flow_imbalance",
    "distance_from_20d_high",
    "distance_from_20d_low",
    "distance_from_60d_high",
    "distance_from_60d_low",
    "drawdown_from_60d_high",
]
CORE20 = [
    "BTCUSDT",
    "ETHUSDT",
    "ZRXUSDT",
    "NEOUSDT",
    "FLMUSDT",
    "KNCUSDT",
    "ONTUSDT",
    "BLZUSDT",
    "HNTUSDT",
    "UNIUSDT",
    "TRXUSDT",
    "KSMUSDT",
    "COMPUSDT",
    "IOTAUSDT",
    "STORJUSDT",
    "OMGUSDT",
    "ZECUSDT",
    "FILUSDT",
    "BCHUSDT",
    "DOGEUSDT",
]
out = pathlib.Path(sys.argv[1])
nan_frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
sample = pq.read_table(out.parent / "gold_sample.parquet")
fields = (
    list(sample.schema)
    + [pa.field(f"htf_12h_{n}", pa.float64()) for n in HTF12]
    + [pa.field(f"htf_1d_{n}", pa.float64()) for n in HTF1D]
)
schema = pa.schema(fields)
config = load_phase7_config(pathlib.Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
step = timedelta(minutes=5)
train_bars = int((plan.train_end - plan.train_start) / step)
target_train = 3_350_407
deficit = (20 * train_bars - target_train) if (len(sys.argv) <= 3 or sys.argv[3] != "0") else 0
late = int(sys.argv[3]) if len(sys.argv) > 3 else 7
late_offset = [0] * (20 - late) + [
    deficit // late + (1 if i < deficit % late else 0) for i in range(late)
]
rng = np.random.default_rng(7)
const = {
    f.name: sample[f.name][100].as_py()
    for f in sample.schema
    if pa.types.is_string(f.type) and f.name != "symbol"
}
total = 0
for symbol, offset in zip(CORE20, late_offset):
    start = plan.train_start + offset * step
    n = int((plan.test_end - start) / step)
    ft = np.datetime64(start.replace(tzinfo=None), "us") + np.arange(n) * np.timedelta64(5, "m")
    cols = {}
    for f in schema:
        if f.name == "symbol":
            cols[f.name] = pa.array([symbol] * n, pa.string())
        elif f.name == "feature_time":
            cols[f.name] = pa.array(ft, pa.timestamp("us", tz="UTC"))
        elif f.name == "open_time":
            cols[f.name] = pa.array(ft - np.timedelta64(5, "m"), pa.timestamp("us", tz="UTC"))
        elif f.name == "entry_time":
            cols[f.name] = pa.array(ft + np.timedelta64(5, "m"), pa.timestamp("us", tz="UTC"))
        elif f.name == "label_end_time":
            cols[f.name] = pa.array(ft + np.timedelta64(65, "m"), pa.timestamp("us", tz="UTC"))
        elif f.name == "horizon_minutes":
            cols[f.name] = pa.array(np.full(n, 60, np.int64))
        elif f.name in const:
            cols[f.name] = pa.array([const[f.name]] * n, pa.string())
        elif f.name == "market_member_count":
            cols[f.name] = pa.array(np.full(n, 20.0))
        elif f.name in ("listing_age_days", "history_length_days"):
            cols[f.name] = pa.array(np.linspace(400, 1400, n))
        else:
            v = rng.standard_normal(n) * 0.01
            if nan_frac and f.name.startswith(("htf_1d_ema200", "funding")):
                v[rng.random(n) < nan_frac] = (
                    np.nan
                )  # warm-up/staleness style nulls -> finite filter copies
            cols[f.name] = pa.array(v)
    table = pa.table(cols, schema=schema)
    years = np.asarray(ft.astype("datetime64[Y]").astype(int) + 1970)
    for year in np.unique(years):
        idx = np.flatnonzero(years == year)
        d = out / f"symbol={symbol}" / f"year={year}"
        d.mkdir(parents=True, exist_ok=True)
        pq.write_table(table.slice(idx[0], len(idx)), d / "part-0.parquet")
    total += n
json.dump(
    {
        "rows": total,
        "columns": len(schema),
        "plan": {
            k: str(getattr(plan, k))
            for k in (
                "fold_id",
                "train_start",
                "train_end",
                "validation_start",
                "validation_end",
                "calibration_start",
                "calibration_end",
                "test_start",
                "test_end",
            )
        },
        "nan_frac": nan_frac,
    },
    open(out / "synthetic_manifest.json", "w"),
    indent=1,
)
print(total, len(schema), plan.fold_id, plan.train_start, plan.test_end)
