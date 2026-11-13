# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
"""Stage-by-stage RSS profiler for the production Fold-0 G0/A6/60m/raw path on SYNTHETIC Gold."""

import gc
import json
import os
import pathlib
import resource
import sys
import threading
import time

import pyarrow as pa

PAGE = os.sysconf("SC_PAGE_SIZE")


def rss():
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * PAGE


class Sampler:
    def __init__(s):
        s.peak = 0
        s.stage_peak = 0
        s.stop = False
        threading.Thread(target=s.run, daemon=True).start()

    def run(s):
        while not s.stop:
            r = rss()
            s.peak = max(s.peak, r)
            s.stage_peak = max(s.stage_peak, r)
            time.sleep(0.01)


SAMP = Sampler()
RESULTS = []
T0 = time.time()
LAST = [time.time()]
GIB = 1024**3


def mark(stage, **extra):
    gc.collect()
    if "release" in sys.argv[2:]:
        pa.default_memory_pool().release_unused()
    now = rss()
    rec = dict(
        stage=stage,
        rss_gib=round(now / GIB, 3),
        stage_peak_gib=round(max(SAMP.stage_peak, now) / GIB, 3),
        arrow_pool_gib=round(pa.total_allocated_bytes() / GIB, 3),
        seconds=round(time.time() - LAST[0], 1),
        **extra,
    )
    RESULTS.append(rec)
    print(json.dumps(rec), flush=True)
    SAMP.stage_peak = now
    LAST[0] = time.time()


import numpy as np
import pyarrow.compute as pc
import pyarrow.dataset as ds

from crypto_ai.phase5.folds import plan_folds, slice_hardened_fold
from crypto_ai.phase7 import training as T
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.features import (
    FOLD_CONTEXT_SOURCE_COLUMNS,
    bind_fold_cross_sectional_context,
)
from crypto_ai.phase7.folds import MultiAssetFoldData, _filter_symbols
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.models import fit_architecture

gold = pathlib.Path(sys.argv[1])
variant = sys.argv[2] if len(sys.argv) > 2 else "baseline"
config = load_phase7_config(pathlib.Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
mark("imports")
paths = sorted(str(p) for p in gold.rglob("*.parquet"))
dataset = ds.dataset(paths, format="parquet", partitioning="hive")
all_doubles = tuple(f.name for f in dataset.schema if pa.types.is_floating(f.type))
A6 = feature_ablation_sets(all_doubles)["A6"]
target = "raw_future_return"
assert len(A6) == 109, len(A6)
table = T._load_fold_rows({}, plan, 60, dataset=dataset)
mark(
    "1_load_fold_rows_all_columns",
    rows=table.num_rows,
    cols=table.num_columns,
    table_gib=round(table.nbytes / GIB, 3),
)
# Sidecar-equivalent: an independent (copied) feature-only source table, as load_sidecar_source returns.
context = table.select(list(FOLD_CONTEXT_SOURCE_COLUMNS)).take(pa.array(np.arange(table.num_rows)))
mark("2_fold_context_source(retained_for_whole_fold)", context_gib=round(context.nbytes / GIB, 3))
symbols = set(pc.unique(table["symbol"]).to_pylist())
eligible = _filter_symbols(table, symbols)
ctx = _filter_symbols(context, symbols)
bound = bind_fold_cross_sectional_context(eligible, context_source=ctx)
mark("3_bind_cross_section_peak_with_raw_table", bound_gib=round(bound.nbytes / GIB, 3))
sliced = slice_hardened_fold(bound, plan, config.schedule, config.prospective_holdout_start)
del table, eligible, ctx, bound
fold = MultiAssetFoldData(
    plan=plan,
    train=sliced.train,
    validation=sliced.validation,
    calibration_a=sliced.calibration_a,
    calibration_b=sliced.calibration_b,
    _test=sliced._test,
    eligibility_manifest={"eligible_symbols": sorted(symbols)},
    cluster_mapping={s: i % 4 for i, s in enumerate(sorted(symbols))},
    liquidity_tiers={},
    age_buckets={},
    research_view="CORE",
    report=sliced.report,
)
del sliced
seg = {
    n: getattr(fold, n).num_rows
    for n in ("train", "validation", "calibration_a", "calibration_b", "_test")
}
mark(
    "4_slice_segments_retained(raw_table_released)",
    segments=seg,
    fold_gib=round(sum(getattr(fold, n).nbytes for n in seg) / GIB, 3),
)
prepared = T._prepare_training_segments(fold, A6, target)
mi = prepared.model_inputs
mark(
    "5_prepare_finite_copies_and_float64_matrices",
    train_x=list(mi.train_x.shape),
    matrices_gib=round((mi.train_x.nbytes + mi.validation_x.nbytes) / GIB, 3),
    finite_rows={
        k: getattr(prepared, k).num_rows
        for k in ("train", "validation", "calibration_a", "calibration_b")
    },
)
if variant == "drop_tables_before_fit":
    pass
model = fit_architecture(
    "G0",
    prepared.train,
    prepared.validation,
    feature_columns=A6,
    target_column=target,
    config=config.models,
    model_threads=4,
    estimator_workers=1,
    cluster_mapping=fold.cluster_mapping,
    eligibility_calibration_a=prepared.calibration_a,
    prepared_inputs=mi,
)
mark(
    "6_lightgbm_G0_fit",
    best_iteration=str(model.metadata.get("best_iteration", model.metadata.get("estimators", "?")))[
        :200
    ],
)
pa_raw, cov = model.predict(prepared.calibration_a)
pb, cb = model.predict(prepared.calibration_b)
test = T._finite(fold._test, A6, target)
pt, ct = model.predict(test)
mark("7_predict_calA_calB_test", test_rows=test.num_rows)
SAMP.stop = True
summary = dict(
    variant=variant,
    process_peak_rss_gib=round(SAMP.peak / GIB, 3),
    ru_maxrss_gib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / GIB, 3),
    total_seconds=round(time.time() - T0, 1),
)
print(json.dumps(summary))
json.dump(
    {"stages": RESULTS, "summary": summary},
    open(gold.parent / f"result_{variant}.json", "w"),
    indent=1,
)
