# ruff: noqa: E402
"""Full-scale SYNTHETIC measurement of the committed low-memory profile (no runtime patches).

Runs the repository functions in the canonical order with PHASE7_MEMORY_PROFILE set by the
caller: column-group fold load, feature-only context source, symbol filter, fold context binding,
the profile's hardened slicer, spill, finite filter + matrices, production cache write (adoption),
read-only reload. Samples VmRSS/RssAnon every 5 ms and free disk at every stage.
"""

import argparse
import json
import os
import shutil
import threading
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("gold", type=Path)
ap.add_argument("--cache-root", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
args = ap.parse_args()
GIB = 1024**3


def status() -> dict[str, int]:
    with open("/proc/self/status") as handle:
        values = {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in handle
            if line.startswith(("VmRSS", "RssAnon", "RssFile"))
        }
    return values


peak = {"VmRSS": 0, "RssAnon": 0}
stage_peak = {"VmRSS": 0, "RssAnon": 0}
disk_min = [shutil.disk_usage(args.cache_root.parent).free]
stop = [False]


def sampler() -> None:
    while not stop[0]:
        current = status()
        for key in peak:
            peak[key] = max(peak[key], current[key])
            stage_peak[key] = max(stage_peak[key], current[key])
        disk_min[0] = min(disk_min[0], shutil.disk_usage(args.cache_root.parent).free)
        time.sleep(0.005)


threading.Thread(target=sampler, daemon=True).start()
stages: list[dict] = []
last = [time.time()]


def mark(stage: str, **extra) -> None:
    from crypto_ai.phase7 import low_memory

    low_memory.release_unused_memory()
    current = status()
    record = {
        "stage": stage,
        "rss_gib": round(current["VmRSS"] / GIB, 3),
        "anon_gib": round(current["RssAnon"] / GIB, 3),
        "stage_peak_rss_gib": round(stage_peak["VmRSS"] / GIB, 3),
        "stage_peak_anon_gib": round(stage_peak["RssAnon"] / GIB, 3),
        "disk_free_gb": round(shutil.disk_usage(args.cache_root.parent).free / 1e9, 2),
        "seconds": round(time.time() - last[0], 1),
        **extra,
    }
    stages.append(record)
    print(json.dumps(record), flush=True)
    stage_peak.update(status())
    last[0] = time.time()


import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7 import low_memory, training
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.features import FOLD_CONTEXT_SOURCE_COLUMNS, bind_fold_cross_sectional_context
from crypto_ai.phase7.folds import MultiAssetFoldData, _filter_symbols
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.low_memory_validation import _differences, prepared_digest
from crypto_ai.phase7.prepared_cache import PreparedDataCache

assert low_memory.enabled(), "run with PHASE7_MEMORY_PROFILE=low_memory"
config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
t0 = time.time()
with low_memory.spill_session(args.cache_root) as spill:
    mark("0_start", spill=str(spill))
    paths = sorted(str(path) for path in args.gold.rglob("*.parquet"))
    dataset = ds.dataset(paths, format="parquet", partitioning="hive")
    a6 = feature_ablation_sets(
        tuple(f.name for f in dataset.schema if pa.types.is_floating(f.type))
    )["A6"]
    table = training._load_fold_rows({}, plan, 60, dataset=dataset)
    mark("1_load_fold_rows", rows=table.num_rows, columns=table.num_columns)
    context = table.select(list(FOLD_CONTEXT_SOURCE_COLUMNS)).take(
        pa.array(np.arange(table.num_rows))
    )
    mark("2_context_source_sidecar_equivalent")
    symbols = set(pc.unique(table["symbol"]).to_pylist())
    eligible = _filter_symbols(table, symbols)
    bound = bind_fold_cross_sectional_context(
        eligible, context_source=_filter_symbols(context, symbols)
    )
    del eligible
    mark("3_filter_and_bind_context")
    sliced = low_memory.slice_hardened_fold(
        bound, plan, config.schedule, config.prospective_holdout_start
    )
    del bound
    fold = MultiAssetFoldData(
        plan=plan,
        train=sliced.train,
        validation=sliced.validation,
        calibration_a=sliced.calibration_a,
        calibration_b=sliced.calibration_b,
        _test=sliced._test,
        eligibility_manifest={
            "eligible_symbols": sorted(symbols),
            "fold_membership_hash": "synthetic",
        },
        cluster_mapping={symbol: i % 4 for i, symbol in enumerate(sorted(symbols))},
        liquidity_tiers={symbol: "synthetic" for symbol in symbols},
        age_buckets={},
        research_view="CORE",
        report=sliced.report,
    )
    del sliced
    del table
    fold = low_memory.spill_fold(fold)
    mark("4_slice_and_spill", segments={k: getattr(fold, k).num_rows for k in ("train", "_test")})
    prepared = training._prepare_training_segments(fold, a6, "raw_future_return")
    mark("5_finite_and_memmap_matrices", train_x=list(prepared.model_inputs.train_x.shape))
    uncached = prepared_digest(fold, prepared)
    mark("5b_uncached_digest")
    identity = {
        "benchmark": "synthetic-fold0-low-memory-profile",
        "feature_columns": list(a6),
        "target_column": "raw_future_return",
        "research_view": "CORE",
        "fold_membership_hash": "synthetic",
    }
    cache_path = PreparedDataCache(args.cache_root, "rebuild").write(identity, fold, prepared)
    cache_bytes = sum(item.stat().st_size for item in Path(cache_path).iterdir())
    mark("6_cache_write_with_matrix_adoption", cache_gb=round(cache_bytes / 1e9, 2))
    del prepared, fold
    loaded = PreparedDataCache(args.cache_root, "read_only").load(identity, plan)
    differences = _differences(uncached, prepared_digest(loaded.fold, loaded.prepared))
    mark("7_read_only_reload_and_compare", differences=differences)
stop[0] = True
summary = {
    "profile": low_memory.memory_profile(),
    "peak_rss_gib": round(peak["VmRSS"] / GIB, 3),
    "peak_anon_gib": round(peak["RssAnon"] / GIB, 3),
    "min_disk_free_gb": round(disk_min[0] / 1e9, 2),
    "seconds": round(time.time() - t0, 1),
    "cached_vs_uncached": "IDENTICAL" if not differences else "DIFFERENT",
    "pid": os.getpid(),
}
print(json.dumps(summary))
args.out.write_text(json.dumps({"summary": summary, "stages": stages}, indent=1))
