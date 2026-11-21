"""Cheap local horizon probe (diagnostic, not Phase 7 training).

Question: does the A6 feature set carry more *tradable* signal at 4h/12h/24h than at 1h?

Data: existing Phase 7A Gold (research cutoff 2026-07-01; July and the August holdout are never
read). Features come from the 60m rows at an hourly stride. Exact 4h/12h/24h forward returns are
built by chaining consecutive 120m Gold returns from the same entry reference; any gap -> NaN.

Protocol: rolling 24-month train / 3-month test, stepping 3 months, test windows 2022-01..2026-06,
with a purge of horizon + 2h before each test window. Fixed LightGBM settings (no tuning, no early
stopping) and a Ridge control. Test rows never fit, tune or select anything.
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

GOLD = Path(
    "/Users/cortex/Crypto2Data/lightning-full/crypto2-persistent/data/gold/"
    "phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/dataset"
)
ROOT = Path(__file__).resolve().parents[2]
CUTOFF = pd.Timestamp("2026-07-01", tz="UTC")
HORIZONS_H = (1, 4, 12, 24)
COST_BPS = 14.0
LGB_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=500,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.7,
    reg_lambda=1.0,
    n_jobs=8,
    verbosity=-1,
    random_state=42,
)


def log(message):
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}Z] {message}", flush=True)


def load():
    dataset = ds.dataset(GOLD, format="parquet", partitioning="hive")
    schema = dataset.schema.names
    features = [
        c
        for c in json.loads(
            (
                ROOT / "docs/reviews/evidence_pilot_4fold_20261121/models/"
                "fold-015-ed49f0aadaf7__mpmcoe794qqgkr/train-result.json"
            ).read_text()
        )["reports"][0]["same_row_feature_columns"]
    ]
    assert all(f in schema for f in features)
    parts = []
    for batch in dataset.to_batches(
        columns=["symbol", "feature_time", "entry_time", "raw_future_return", *features],
        filter=ds.field("horizon_minutes") == 60,
    ):
        table = pa.Table.from_batches([batch])
        minute = pc.minute(table.column("feature_time"))
        table = table.filter(pc.equal(minute, 0))
        if table.num_rows:
            parts.append(table.to_pandas())
    frame = pd.concat(parts, ignore_index=True)
    frame[features] = frame[features].astype(np.float32)
    log(f"hourly feature rows {len(frame):,}")
    chain = dataset.to_table(
        columns=["symbol", "entry_time", "raw_future_return"],
        filter=ds.field("horizon_minutes") == 120,
    ).to_pandas()
    log(f"120m chain rows {len(chain):,}")
    frame = frame.rename(columns={"raw_future_return": "r_1h"})
    lookup = chain.set_index(["symbol", "entry_time"])["raw_future_return"]
    for hours in HORIZONS_H[1:]:
        growth = np.ones(len(frame))
        for step in range(hours // 2):
            key = pd.MultiIndex.from_arrays(
                [frame["symbol"], frame["entry_time"] + pd.Timedelta(hours=2 * step)]
            )
            growth *= 1.0 + lookup.reindex(key).to_numpy()
        frame[f"r_{hours}h"] = growth - 1.0
        end = frame["entry_time"] + pd.Timedelta(hours=hours)
        frame.loc[end >= CUTOFF, f"r_{hours}h"] = np.nan
        log(f"r_{hours}h finite {np.isfinite(frame[f'r_{hours}h']).mean():.3f}")
    return frame, features


def fold_windows():
    start = pd.Timestamp("2022-01-01", tz="UTC")
    while start < CUTOFF:
        yield start, min(start + pd.DateOffset(months=3), CUTOFF)
        start = start + pd.DateOffset(months=3)


def cs_ic(times, pred, actual):
    frame = pd.DataFrame({"t": times, "p": pred, "a": actual})
    values = []
    for _, group in frame.groupby("t"):
        if len(group) >= 5:
            values.append(spearmanr(group["p"], group["a"]).statistic)
    return float(np.nanmean(values))


def evaluate(times, symbols, pred, actual):
    signed = np.sign(pred) * actual * 1e4
    confident = np.abs(pred) >= np.quantile(np.abs(pred), 0.9)
    deciles = pd.qcut(pd.Series(pred).rank(method="first"), 10, labels=False).to_numpy()
    # Market-neutral cross-section: each hour long the top 3 / short the bottom 3 forecasts.
    frame = pd.DataFrame({"t": times, "p": pred, "a": actual})
    rank = frame.groupby("t")["p"].rank(method="first")
    count = frame.groupby("t")["p"].transform("size")
    long_leg = frame.loc[(rank > count - 3) & (count >= 8), "a"].mean() * 1e4
    short_leg = -frame.loc[(rank <= 3) & (count >= 8), "a"].mean() * 1e4
    return {
        "rows": int(len(pred)),
        "pooled_spearman": float(spearmanr(pred, actual).statistic),
        "cs_ic": cs_ic(times, pred, actual),
        "direction_acc": float((np.sign(pred) == np.sign(actual)).mean()),
        "edge_all_bps": float(signed.mean()),
        "edge_top10_bps": float(signed[confident].mean()),
        "decile_spread_bps": float(
            (actual[deciles == 9].mean() - actual[deciles == 0].mean()) * 1e4
        ),
        "ls_leg_gross_bps": float((long_leg + short_leg) / 2),
        "abs_move_median_bps": float(np.median(np.abs(actual)) * 1e4),
    }


def main():
    out = ROOT / "output/horizon_probe"
    out.mkdir(parents=True, exist_ok=True)
    frame, features = load()
    times = frame["feature_time"]
    results = []
    for hours in HORIZONS_H:
        target = f"r_{hours}h"
        purge = pd.Timedelta(hours=hours + 2)
        for fold, (test_start, test_end) in enumerate(fold_windows()):
            train_mask = (
                (times >= test_start - pd.DateOffset(months=24))
                & (times < test_start - purge)
                & np.isfinite(frame[target])
            )
            test_mask = (times >= test_start) & (times < test_end) & np.isfinite(frame[target])
            if train_mask.sum() < 50_000 or test_mask.sum() < 5_000:
                continue
            xtr = frame.loc[train_mask, features].to_numpy()
            ytr = frame.loc[train_mask, target].to_numpy()
            xte = frame.loc[test_mask, features].to_numpy()
            yte = frame.loc[test_mask, target].to_numpy()
            started = time.time()
            booster = lgb.LGBMRegressor(**LGB_PARAMS).fit(xtr, ytr)
            p_lgb = booster.predict(xte)
            median = np.nanmedian(xtr, axis=0)
            scale = np.nanstd(xtr, axis=0) + 1e-12

            def prep(x, median=median, scale=scale):
                x = np.where(np.isfinite(x), x, median)
                return np.clip((x - median) / scale, -5, 5)

            p_ridge = Ridge(alpha=1000.0).fit(prep(xtr), ytr).predict(prep(xte))
            for model, pred in (("lightgbm", p_lgb), ("ridge", p_ridge)):
                row = {
                    "horizon_h": hours,
                    "fold": fold,
                    "test_start": str(test_start.date()),
                    "model": model,
                }
                row.update(
                    evaluate(
                        times[test_mask].to_numpy(),
                        frame.loc[test_mask, "symbol"].to_numpy(),
                        pred,
                        yte,
                    )
                )
                row["always_long_bps"] = float(yte.mean() * 1e4)
                results.append(row)
            log(
                f"h={hours}h fold={fold} {test_start.date()} "
                f"train={train_mask.sum():,} test={test_mask.sum():,} "
                f"cs_ic lgb={results[-2]['cs_ic']:+.4f} ridge={results[-1]['cs_ic']:+.4f} "
                f"top10 lgb={results[-2]['edge_top10_bps']:+.1f}bps ({time.time() - started:.0f}s)"
            )
            pd.DataFrame(results).to_csv(out / "fold_results.csv", index=False)
    table = pd.DataFrame(results)
    summary = (
        table.groupby(["horizon_h", "model"])
        .agg(
            folds=("fold", "size"),
            cs_ic=("cs_ic", "mean"),
            cs_ic_pos_folds=("cs_ic", lambda s: int((s > 0).sum())),
            cs_ic_t=("cs_ic", lambda s: s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))),
            pooled_spearman=("pooled_spearman", "mean"),
            direction_acc=("direction_acc", "mean"),
            edge_all_bps=("edge_all_bps", "mean"),
            edge_top10_bps=("edge_top10_bps", "mean"),
            top10_pos_folds=("edge_top10_bps", lambda s: int((s > COST_BPS).sum())),
            decile_spread_bps=("decile_spread_bps", "mean"),
            ls_leg_gross_bps=("ls_leg_gross_bps", "mean"),
            ls_net_pos_folds=("ls_leg_gross_bps", lambda s: int((s > COST_BPS).sum())),
            abs_move_median_bps=("abs_move_median_bps", "mean"),
            always_long_bps=("always_long_bps", "mean"),
        )
        .round(4)
    )
    summary["edge_top10_net_bps"] = summary["edge_top10_bps"] - COST_BPS
    summary["ls_leg_net_bps"] = summary["ls_leg_gross_bps"] - COST_BPS
    summary.to_csv(out / "summary.csv")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(summary)


if __name__ == "__main__":
    sys.exit(main())
