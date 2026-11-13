# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
"""Training-process memory: production PreparedDataCache read_only (mmap) load + G0 fit + fixed-round timing. SYNTHETIC data."""

import gc
import json
import pathlib
import resource
import sys
import threading
import time

GIB = 1024**3


def anon():
    with open("/proc/self/status") as f:
        d = {
            l.split(":")[0]: int(l.split()[1]) * 1024
            for l in f
            if l.startswith(("RssAnon", "VmRSS", "RssFile"))
        }
    return d


peak = {"VmRSS": 0, "RssAnon": 0}
stop = [False]


def samp():
    while not stop[0]:
        d = anon()
        [peak.__setitem__(k, max(peak[k], d[k])) for k in peak]
        time.sleep(0.005)


threading.Thread(target=samp, daemon=True).start()


def mark(stage, **kw):
    gc.collect()
    d = anon()
    print(
        json.dumps(
            {
                "stage": stage,
                **{k: round(v / GIB, 3) for k, v in d.items()},
                "peak_anon_gib": round(peak["RssAnon"] / GIB, 3),
                "peak_rss_gib": round(peak["VmRSS"] / GIB, 3),
                **kw,
            }
        ),
        flush=True,
    )


from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7.backend import lightgbm_estimator_parameters
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.models import fit_architecture
from crypto_ai.phase7.prepared_cache import PreparedDataCache

config = load_phase7_config(pathlib.Path("configs/phase7/research_core20_primary_v1.toml"))
plan = plan_folds(
    config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
)[0]
cache_root = pathlib.Path(sys.argv[1])
entry = next(p for p in cache_root.iterdir() if not p.name.startswith("."))
identity = json.loads((entry / "manifest.json").read_text())["identity"]
t0 = time.time()
bundle = PreparedDataCache(cache_root, "read_only").load(identity, plan)
p = bundle.prepared
mi = p.model_inputs
mark(
    "load_read_only_mmap_cache_with_sha256_validation",
    seconds=round(time.time() - t0, 1),
    train_x_type=type(mi.train_x).__name__,
)
t0 = time.time()
model = fit_architecture(
    "G0",
    p.train,
    p.validation,
    feature_columns=p.feature_columns,
    target_column=p.target_column,
    config=config.models,
    model_threads=4,
    estimator_workers=1,
    cluster_mapping=bundle.fold.cluster_mapping,
    eligibility_calibration_a=p.calibration_a,
    prepared_inputs=mi,
)
mark("production_G0_fit_from_cache", seconds=round(time.time() - t0, 1))
from crypto_ai.phase7.training import _finite

for t in (
    p.calibration_a,
    p.calibration_b,
    _finite(bundle.fold._test, p.feature_columns, p.target_column),
):
    model.predict(t)
mark("predict_calA_calB_test")
import lightgbm as lgb

params = lightgbm_estimator_parameters(config.models, model_threads=4)
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
params["n_estimators"] = rounds
est = lgb.LGBMRegressor(**params)
t0 = time.time()
est.fit(mi.train_x, mi.train_y, eval_set=[(mi.validation_x, mi.validation_y)])
el = time.time() - t0
mark(
    "timing_fixed_rounds_no_early_stop",
    rounds=rounds,
    seconds=round(el, 1),
    seconds_per_round=round(el / rounds, 3),
    params={
        k: params[k]
        for k in (
            "num_leaves",
            "learning_rate",
            "min_child_samples",
            "subsample",
            "colsample_bytree",
            "n_jobs",
            "deterministic",
            "force_col_wise",
        )
    },
)
stop[0] = True
print(
    json.dumps(
        {
            "peak_anon_gib": round(peak["RssAnon"] / GIB, 3),
            "peak_rss_gib": round(peak["VmRSS"] / GIB, 3),
            "ru_maxrss_gib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / GIB, 3
            ),
        }
    )
)
