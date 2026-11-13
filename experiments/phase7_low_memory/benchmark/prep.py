# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
"""Fold-0 G0/A6/60m/raw preparation (+ optional fit) on SYNTHETIC Gold. Modes: baseline | patched."""

import argparse
import gc
import hashlib
import json
import os
import pathlib
import resource
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

ap = argparse.ArgumentParser()
ap.add_argument("gold")
ap.add_argument("mode")
ap.add_argument("--symbols", type=int, default=0)
ap.add_argument("--fit", action="store_true")
ap.add_argument("--cache")
ap.add_argument("--out", required=True)
ap.add_argument("--spill")
ap.add_argument("--mmap-matrices", action="store_true")
a = ap.parse_args()
GIB = 1024**3
PAGE = os.sysconf("SC_PAGE_SIZE")


def rss():
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * PAGE


def anon():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("RssAnon:"):
                return int(line.split()[1]) * 1024
    return 0


class Samp:
    peak = 0
    stage = 0
    stop = False
    apeak = 0
    astage = 0


def _run():
    while not Samp.stop:
        r = rss()
        Samp.peak = max(Samp.peak, r)
        Samp.stage = max(Samp.stage, r)
        q = anon()
        Samp.apeak = max(Samp.apeak, q)
        Samp.astage = max(Samp.astage, q)
        time.sleep(0.005)


threading.Thread(target=_run, daemon=True).start()
STAGES = []
LAST = [time.time()]
T0 = time.time()


def mark(stage, **extra):
    gc.collect()
    if a.mode == "patched":
        pa.default_memory_pool().release_unused()
    now = rss()
    rec = dict(
        stage=stage,
        rss_gib=round(now / GIB, 3),
        stage_peak_gib=round(max(Samp.stage, now) / GIB, 3),
        anon_gib=round(anon() / GIB, 3),
        anon_stage_peak_gib=round(max(Samp.astage, anon()) / GIB, 3),
        seconds=round(time.time() - LAST[0], 1),
        **extra,
    )
    STAGES.append(rec)
    print(json.dumps(rec), flush=True)
    Samp.stage = now
    Samp.astage = anon()
    LAST[0] = time.time()


def col_digest(col):
    col = col.combine_chunks() if isinstance(col, pa.ChunkedArray) else col
    if pa.types.is_timestamp(col.type):
        b = col.cast(pa.int64()).to_numpy(zero_copy_only=False).tobytes()
    elif pa.types.is_string(col.type) or pa.types.is_dictionary(col.type):
        b = "\x00".join(map(str, col.to_pylist())).encode()
    else:
        b = col.to_numpy(zero_copy_only=False).tobytes()
    return hashlib.sha256(b).hexdigest()


def table_digest(t):
    return {
        "rows": t.num_rows,
        "columns": t.column_names,
        "values": hashlib.sha256(
            "".join(col_digest(t.column(n)) for n in t.column_names).encode()
        ).hexdigest(),
    }


if a.mode == "patched":
    import patches

    patches.apply()
if a.mmap_matrices:
    import uuid

    import crypto_ai.phase7.models as M

    _orig_matrix = M._matrix

    def _matrix(table, columns):
        if table.num_rows < 1_000_000:
            return _orig_matrix(table, columns)
        missing = [n for n in columns if n not in table.column_names]
        if missing:
            raise ValueError(f"Phase 7 model input is missing features: {missing}")
        pathlib.Path(a.spill).mkdir(parents=True, exist_ok=True)
        matrix = np.lib.format.open_memmap(
            pathlib.Path(a.spill) / f"matrix-{uuid.uuid4().hex}.npy",
            mode="w+",
            dtype=np.float64,
            shape=(table.num_rows, len(columns)),
        )
        for i, n in enumerate(columns):
            matrix[:, i] = M._floats(table, n)
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Phase 7 model features must be a finite matrix")
        return matrix

    M._matrix = _matrix
from crypto_ai.phase5.folds import plan_folds, slice_hardened_fold
from crypto_ai.phase7 import folds as F7
from crypto_ai.phase7 import training as T
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.features import FOLD_CONTEXT_SOURCE_COLUMNS, bind_fold_cross_sectional_context
from crypto_ai.phase7.folds import MultiAssetFoldData
from crypto_ai.phase7.gold import feature_ablation_sets
from crypto_ai.phase7.models import fit_architecture

config = load_phase7_config(pathlib.Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
mark("0_imports")
symdirs = sorted(pathlib.Path(a.gold).glob("symbol=*"))
if a.symbols:
    symdirs = symdirs[: a.symbols]
paths = sorted(str(p) for d in symdirs for p in d.rglob("*.parquet"))
dataset = ds.dataset(paths, format="parquet", partitioning="hive")
A6 = feature_ablation_sets(tuple(f.name for f in dataset.schema if pa.types.is_floating(f.type)))[
    "A6"
]
assert len(A6) == 109
target = "raw_future_return"
table = T._load_fold_rows({}, plan, 60, dataset=dataset)
mark(
    "1_load_fold_rows",
    rows=table.num_rows,
    cols=table.num_columns,
    table_gib=round(table.nbytes / GIB, 3),
)
context = table.select(list(FOLD_CONTEXT_SOURCE_COLUMNS)).take(
    pa.array(np.arange(table.num_rows))
)  # sidecar-equivalent copy
mark("2_context_source", context_gib=round(context.nbytes / GIB, 3))
symbols = set(pc.unique(table["symbol"]).to_pylist())
eligible = F7._filter_symbols(table, symbols)
if a.mode == "patched":
    del table
bound = bind_fold_cross_sectional_context(
    eligible, context_source=F7._filter_symbols(context, symbols)
)
if a.mode == "patched":
    del eligible
mark("3_filter_and_bind_context")
sliced = slice_hardened_fold(bound, plan, config.schedule, config.prospective_holdout_start)
del bound
if a.mode != "patched":
    del table, eligible
fold = MultiAssetFoldData(
    plan=plan,
    train=sliced.train,
    validation=sliced.validation,
    calibration_a=sliced.calibration_a,
    calibration_b=sliced.calibration_b,
    _test=sliced._test,
    eligibility_manifest={"eligible_symbols": sorted(symbols), "fold_membership_hash": "synthetic"},
    cluster_mapping={s: i % 4 for i, s in enumerate(sorted(symbols))},
    liquidity_tiers={s: "synthetic" for s in symbols},
    age_buckets={},
    research_view="CORE",
    report=sliced.report,
)
del sliced
if a.spill:
    import pyarrow.ipc as ipc

    spill = pathlib.Path(a.spill)
    spill.mkdir(parents=True, exist_ok=True)
    for n in ("train", "validation", "calibration_a", "calibration_b", "_test"):
        t = getattr(fold, n)
        f = spill / f"{n}.arrow"
        with pa.OSFile(str(f), "wb") as sink, ipc.new_file(sink, t.schema) as w:
            w.write_table(t)
        del t
    tables = {}
    for n in ("train", "validation", "calibration_a", "calibration_b", "_test"):
        with pa.memory_map(str(spill / f"{n}.arrow"), "r") as src:
            tables[n] = ipc.open_file(src).read_all()
    fold = MultiAssetFoldData(
        plan=fold.plan,
        train=tables["train"],
        validation=tables["validation"],
        calibration_a=tables["calibration_a"],
        calibration_b=tables["calibration_b"],
        _test=tables["_test"],
        eligibility_manifest=fold.eligibility_manifest,
        cluster_mapping=fold.cluster_mapping,
        liquidity_tiers=fold.liquidity_tiers,
        age_buckets=fold.age_buckets,
        research_view="CORE",
        report=fold.report,
    )
    del tables
seg = {
    n: getattr(fold, n).num_rows
    for n in ("train", "validation", "calibration_a", "calibration_b", "_test")
}
mark("4_slice_purge_embargo", segments=seg)
prepared = T._prepare_training_segments(fold, A6, target)
mi = prepared.model_inputs
mark(
    "5_finite_filter_and_float64_matrices",
    train_x=list(mi.train_x.shape),
    matrices_gib=round((mi.train_x.nbytes + mi.validation_x.nbytes) / GIB, 3),
    finite_rows={
        k: getattr(prepared, k).num_rows
        for k in ("train", "validation", "calibration_a", "calibration_b")
    },
)
digests = {
    "segments": {
        k: table_digest(getattr(prepared, k))
        for k in ("train", "validation", "calibration_a", "calibration_b")
    },
    "test": table_digest(fold._test),
    "report": json.loads(json.dumps(fold.report, default=str)),
    "matrices": {
        k: hashlib.sha256(np.ascontiguousarray(getattr(mi, k)).tobytes()).hexdigest()
        for k in ("train_x", "validation_x", "train_y", "validation_y")
    },
}
if a.cache:
    from crypto_ai.phase7.prepared_cache import PreparedDataCache

    identity = {
        "benchmark": "synthetic-fold0-G0-A6-60m-raw",
        "feature_columns": list(A6),
        "target_column": target,
        "research_view": "CORE",
        "fold_membership_hash": "synthetic",
    }
    path = PreparedDataCache(pathlib.Path(a.cache), "rebuild").write(identity, fold, prepared)
    mark(
        "6_write_prepared_cache",
        cache_path=str(path),
        cache_gib=round(sum(f.stat().st_size for f in pathlib.Path(path).iterdir()) / GIB, 3),
    )
if a.fit:
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
    est = model.estimators["global"] if hasattr(model, "estimators") else None
    mark("7_lightgbm_G0_fit", best_iteration=getattr(est, "best_iteration_", None))
    preds = {}
    for k, t in (
        ("cal_a", prepared.calibration_a),
        ("cal_b", prepared.calibration_b),
        ("test", T._finite(fold._test, A6, target)),
    ):
        p, c = model.predict(t)
        preds[k] = hashlib.sha256(
            np.asarray(p, dtype=np.float64).tobytes() + np.asarray(c).tobytes()
        ).hexdigest()
    digests["predictions"] = preds
    mark("8_predict_calA_calB_test")
Samp.stop = True
summary = dict(
    mode=a.mode,
    symbols=len(symbols),
    peak_rss_gib=round(Samp.peak / GIB, 3),
    peak_anon_gib=round(Samp.apeak / GIB, 3),
    ru_maxrss_gib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / GIB, 3),
    seconds=round(time.time() - T0, 1),
)
print(json.dumps(summary))
json.dump(
    {"summary": summary, "stages": STAGES, "digests": digests},
    open(a.out, "w"),
    indent=1,
    default=str,
)
