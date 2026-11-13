# ruff: noqa: E402
"""PREPARATION ONLY (no model fit): staged vs non-staged low-memory fold preparation, full scale.

SYNTHETIC Gold only. Point-in-time membership needs the real registry/descriptors, which do not
exist for synthetic data, so both paths use the same stubbed "all symbols eligible" membership
and metadata; everything else is the committed repository code. Reports peak RSS/RssAnon, disk,
time, and whether the two prepared digests (tables, matrices, purge/embargo report) are equal.
"""

import argparse
import json
import shutil
import threading
import time
from datetime import timedelta
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("gold", type=Path)
ap.add_argument("--mode", choices=["staged", "unstaged"], required=True)
ap.add_argument("--days", type=int, default=30)
ap.add_argument("--cache-root", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
args = ap.parse_args()
GIB = 1024**3


def status() -> dict[str, int]:
    with open("/proc/self/status") as handle:
        return {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in handle
            if line.startswith(("VmRSS", "RssAnon"))
        }


peak = {"VmRSS": 0, "RssAnon": 0}
disk_min = [shutil.disk_usage(args.cache_root.parent).free]
stop = [False]


def sampler() -> None:
    while not stop[0]:
        current = status()
        for key in peak:
            peak[key] = max(peak[key], current[key])
        disk_min[0] = min(disk_min[0], shutil.disk_usage(args.cache_root.parent).free)
        time.sleep(0.005)


threading.Thread(target=sampler, daemon=True).start()
import os

os.environ["PHASE7_MEMORY_PROFILE"] = "low_memory"
if args.mode == "staged":
    os.environ["PHASE7_STAGING_DAYS"] = str(args.days)
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7 import folds as F7
from crypto_ai.phase7 import low_memory, staged_fold, training
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.features import FOLD_CONTEXT_SOURCE_COLUMNS, bind_fold_cross_sectional_context
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.low_memory_validation import prepared_digest

config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
dataset = ds.dataset(
    sorted(str(p) for p in args.gold.rglob("*.parquet")), format="parquet", partitioning="hive"
)
symbols = set(pc.unique(dataset.to_table(columns=["symbol"])["symbol"]).to_pylist())
a6 = feature_ablation_sets(tuple(f.name for f in dataset.schema if pa.types.is_floating(f.type)))[
    "A6"
]
METADATA = {
    "clusters": {s: i % 4 for i, s in enumerate(sorted(symbols))},
    "cluster_report": {},
    "liquidity": {s: "synthetic" for s in symbols},
    "age_buckets": {},
    "eligibility_manifest": {"eligible_symbols": sorted(symbols), "fold_membership_hash": "syn"},
}
F7.fold_membership = lambda *a, **k: (None, None, set(symbols))  # synthetic stub (see doc)
F7.fold_metadata = lambda *a, **k: METADATA
t0 = time.time()
with low_memory.spill_session(args.cache_root) as spill:
    context = training._load_fold_rows(
        {}, plan, 60, dataset=dataset, columns=FOLD_CONTEXT_SOURCE_COLUMNS
    )
    context = context.take(pa.array(range(context.num_rows)))  # independent sidecar-like copy
    low_memory.release_unused_memory()
    if args.mode == "staged":
        fold = staged_fold.slice_fold_staged(
            dataset,
            plan,
            60,
            context_source=context,
            registry=None,
            universe=None,
            expansion_policy=None,
            research_view="CORE",
            descriptors=[],
            universe_config=None,
            schedule=config.schedule,
            holdout_start=config.prospective_holdout_start,
            cluster_count=4,
            seed=42,
            window=timedelta(days=args.days),
            directory=spill,
        )
    else:
        table = training._load_fold_rows({}, plan, 60, dataset=dataset)
        bound = bind_fold_cross_sectional_context(
            F7._filter_symbols(table, symbols), context_source=context
        )
        del table
        sliced = low_memory.slice_hardened_fold(
            bound, plan, config.schedule, config.prospective_holdout_start
        )
        del bound
        fold = F7.MultiAssetFoldData(
            plan=plan,
            train=sliced.train,
            validation=sliced.validation,
            calibration_a=sliced.calibration_a,
            calibration_b=sliced.calibration_b,
            _test=sliced._test,
            eligibility_manifest=METADATA["eligibility_manifest"],
            cluster_mapping=METADATA["clusters"],
            liquidity_tiers=METADATA["liquidity"],
            age_buckets=METADATA["age_buckets"],
            research_view="CORE",
            report=sliced.report,
        )
        del sliced
        fold = low_memory.spill_fold(fold)
    low_memory.release_unused_memory()
    slice_seconds = time.time() - t0
    prepared = training._prepare_training_segments(fold, a6, "raw_future_return")
    digest = prepared_digest(fold, prepared)
stop[0] = True
summary = {
    "mode": args.mode,
    "staging_days": args.days if args.mode == "staged" else None,
    "peak_rss_gib": round(peak["VmRSS"] / GIB, 3),
    "peak_anon_gib": round(peak["RssAnon"] / GIB, 3),
    "min_disk_free_gb": round(disk_min[0] / 1e9, 2),
    "slice_seconds": round(slice_seconds, 1),
    "total_seconds": round(time.time() - t0, 1),
    "segment_rows": {k: v["rows"] for k, v in digest["tables"].items()},
    "model_fit": "NONE (preparation only)",
}
print(json.dumps(summary))
args.out.write_text(json.dumps({"summary": summary, "digest": digest}, indent=1))
