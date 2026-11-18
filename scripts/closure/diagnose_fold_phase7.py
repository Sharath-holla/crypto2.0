"""Read-only diagnosis of one completed Phase 7A fold (no fitting, no parameter changes).

Loads the fold's prepared cache and its saved model, re-scores Validation to prove the cached
matrices align with the canonical result, then writes descriptive diagnostics: prediction and
target distributions, per-feature univariate relationships, feature redundancy, per-symbol and
chronological-block metrics, and LONG/SHORT event confusion at the diagnostic threshold.
TEST rows are never read.
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pyarrow.ipc as ipc

QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
EVENT_BPS = 5


def table(path):
    with ipc.open_file(path) as reader:
        return reader.read_all()


def dist(values):
    values = np.asarray(values, dtype=np.float64)
    q = np.quantile(values, QUANTILES)
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "std": float(values.std()),
        "mad": float(np.median(np.abs(values - np.median(values)))),
        "min": float(values.min()),
        "max": float(values.max()),
        "quantiles": {f"p{int(k * 100):02d}": float(v) for k, v in zip(QUANTILES, q, strict=True)},
    }


def rank(values):
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.arange(len(values), dtype=np.float64)
    return ranks


def corr(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def scores(y, p):
    err = p - y
    nonzero = y != 0
    return {
        "rows": int(y.size),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "zero_rmse": float(np.sqrt(np.mean(y**2))),
        "pearson": corr(p, y),
        "spearman": corr(rank(p), rank(y)),
        "directional_accuracy_nonzero": float(np.mean(np.sign(p[nonzero]) == np.sign(y[nonzero])))
        if nonzero.any()
        else None,
        "prediction_std": float(p.std()),
        "target_std": float(y.std()),
    }


def events(y, p, bps=EVENT_BPS):
    t = bps / 10_000
    out = {}
    for side, sign in (("long", 1), ("short", -1)):
        actual, predicted = sign * y >= t, sign * p >= t
        tp = int(np.sum(actual & predicted))
        fp = int(np.sum(~actual & predicted))
        fn = int(np.sum(actual & ~predicted))
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        out[side] = {
            "predicted_signals": int(predicted.sum()),
            "actual_events": int(actual.sum()),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    out["coverage"] = float(np.mean(np.abs(p) >= t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--report", required=True, help="canonical train-result.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=400_000)
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261118)

    report = json.loads(Path(args.report).read_text())["reports"][0]
    bundle = joblib.load(args.model)
    cols = list(bundle.feature_columns)
    if cols != report["same_row_feature_columns"]:
        raise SystemExit("FEATURE_ORDER_MISMATCH")
    booster = bundle.estimators["global"].booster_

    x = {s: np.load(cache / f"{s}_x.npy", mmap_mode="r") for s in ("train", "validation")}
    y = {
        s: np.asarray(np.load(cache / f"{s}_y.npy"), dtype=np.float64)
        for s in ("train", "validation")
    }
    symbols = {
        s: np.load(cache / f"{s}_symbols.npy", allow_pickle=True) for s in ("train", "validation")
    }
    for s in ("train", "validation"):
        if x[s].shape != (report["segment_rows"][s], len(cols)) or y[s].shape[0] != x[s].shape[0]:
            raise SystemExit(f"SEGMENT_SHAPE_MISMATCH_{s}")

    pred_val = booster.predict(np.asarray(x["validation"]), num_iteration=booster.best_iteration)
    val = scores(y["validation"], pred_val)
    canonical = report["phase7b"]["baselines"]["lightgbm"]["rmse"]
    alignment = {
        "rescored_validation_rmse": val["rmse"],
        "canonical_validation_rmse": canonical,
        "abs_difference": abs(val["rmse"] - canonical),
        "status": "PASS" if abs(val["rmse"] - canonical) < 1e-9 else "FAIL",
    }
    result = {"alignment": alignment, "validation": val}
    if alignment["status"] != "PASS":
        (out / "fold_diagnosis.json").write_text(json.dumps(result, indent=1))
        raise SystemExit("VALIDATION_RESCORE_MISMATCH")

    sample = np.sort(
        rng.choice(x["train"].shape[0], size=min(args.sample, x["train"].shape[0]), replace=False)
    )
    train_x = np.asarray(x["train"][sample])
    pred_train = booster.predict(train_x, num_iteration=booster.best_iteration)
    result["train_sample"] = scores(y["train"][sample], pred_train)
    result["train_sample"]["sampled_rows"] = int(sample.size)

    result["prediction_distribution_validation"] = dist(pred_val)
    result["target_distribution"] = {}
    for s in ("train", "validation"):
        d = dist(y[s])
        target = y[s]
        d.update(
            positive_fraction=float(np.mean(target > 0)),
            negative_fraction=float(np.mean(target < 0)),
            zero_fraction=float(np.mean(target == 0)),
            within_5bps_fraction=float(np.mean(np.abs(target) < EVENT_BPS / 10_000)),
            beyond_1pct_fraction=float(np.mean(np.abs(target) >= 0.01)),
            beyond_3pct_fraction=float(np.mean(np.abs(target) >= 0.03)),
        )
        result["target_distribution"][s] = d
    result["prediction_to_target_std_ratio"] = val["prediction_std"] / val["target_std"]
    result["events_validation_5bps"] = events(y["validation"], pred_val)

    # Univariate relationships: TRAIN sample and full Validation, same rows for every feature.
    val_x = np.asarray(x["validation"])
    y_train_sample, y_val = y["train"][sample], y["validation"]
    y_train_rank, y_val_rank = rank(y_train_sample), rank(y_val)
    univariate = []
    for j, name in enumerate(cols):
        a, b = train_x[:, j].astype(np.float64), val_x[:, j].astype(np.float64)
        univariate.append(
            {
                "feature": name,
                "train_pearson": corr(a, y_train_sample),
                "train_spearman": corr(rank(a), y_train_rank),
                "validation_pearson": corr(b, y_val),
                "validation_spearman": corr(rank(b), y_val_rank),
                "train_std": float(a.std()),
                "train_unique_values_in_sample": int(np.unique(a).size),
            }
        )
    result["univariate"] = univariate

    # Redundancy on the TRAIN sample only.
    matrix = np.corrcoef(train_x.astype(np.float64), rowvar=False)
    pairs = [
        {"a": cols[i], "b": cols[j], "pearson": float(matrix[i, j])}
        for i in range(len(cols))
        for j in range(i + 1, len(cols))
        if np.isfinite(matrix[i, j]) and abs(matrix[i, j]) >= 0.95
    ]
    result["redundancy"] = {
        "train_sample_rows": int(sample.size),
        "pairs_abs_pearson_ge_0_95": sorted(pairs, key=lambda r: -abs(r["pearson"])),
        "near_constant_features": [
            u["feature"]
            for u in univariate
            if u["train_unique_values_in_sample"] <= 2 or u["train_std"] == 0
        ],
    }

    # Per symbol and chronological blocks (Validation only).
    per_symbol = {}
    for sym in sorted(set(symbols["validation"].tolist())):
        mask = symbols["validation"] == sym
        per_symbol[str(sym)] = scores(y_val[mask], pred_val[mask]) | {
            "events_5bps": events(y_val[mask], pred_val[mask])
        }
    result["per_symbol_validation"] = per_symbol

    times = table(cache / "validation.arrow").column("feature_time").to_numpy()
    if np.issubdtype(times.dtype, np.datetime64):
        times = times.astype("datetime64[us]").astype(np.int64)
    if times.shape[0] != y_val.shape[0]:
        raise SystemExit("VALIDATION_TIME_ROWS_MISMATCH")
    order = np.argsort(times, kind="mergesort")
    blocks = []
    for k, idx in enumerate(np.array_split(order, 6)):
        blocks.append(
            {
                "block": k,
                "start": str(np.datetime64(int(times[idx].min()), "us")),
                "end": str(np.datetime64(int(times[idx].max()), "us")),
            }
            | scores(y_val[idx], pred_val[idx])
        )
    result["chronological_blocks_validation"] = blocks

    (out / "fold_diagnosis.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({"status": "PASS", "alignment": alignment, "out": str(out)}))


if __name__ == "__main__":
    main()
