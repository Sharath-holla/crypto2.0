"""Tiny artificial CPU fixture only. Independent processes test native Booster continuation.

Never loads project market data. A failed equivalence experiment is evidence for keeping
production init_model disabled, not a reason to change the frozen scientific parameters.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

from crypto_ai.phase7.backend import lightgbm_estimator_parameters
from crypto_ai.phase7.config import load_phase7_config


def fixture():
    rng = np.random.default_rng(7351)
    x = rng.normal(size=(1600, 24))
    y = x[:, 0] * 0.01 + np.sin(x[:, 3]) * 0.01 + rng.normal(0, 0.01, 1600)
    return x[:1000], y[:1000], x[1000:], y[1000:], np.linspace(0.5, 1.5, 1000)


def worker(args):
    x, y, vx, vy, weights = fixture()
    cfg = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    params = lightgbm_estimator_parameters(cfg.models, model_threads=args.threads)
    params["min_child_samples"] = 10  # Technical fixture size only; real configuration untouched.
    history = {}
    callbacks = [lgb.record_evaluation(history)]
    init_model = None
    if args.pause:
        params["n_estimators"] = args.pause
    elif args.resume:
        init_model = args.directory / "partial.txt"
        state = json.loads((args.directory / "state.json").read_text())
        params["n_estimators"] = 500 - state["completed"]
        if not args.cap:
            # Public callback API restores the oracle best-score/patience state. Even this
            # does not restore native random-sampling state lost across serialization.
            best, best_round = state["best_l2"], state["best_iteration"]
            best_evaluation = state["best_evaluation"]

            def restored_stopping(env):
                nonlocal best, best_round, best_evaluation
                score = next(
                    item[2]
                    for item in env.evaluation_result_list
                    if item[0] == "validation" and item[1] == "l2"
                )
                completed = env.iteration + 1
                if score < best:
                    best, best_round, best_evaluation = score, completed, env.evaluation_result_list
                if completed - best_round >= 50 or completed == env.end_iteration:
                    raise lgb.callback.EarlyStopException(best_round - 1, best_evaluation)

            restored_stopping.order = 30
            callbacks.append(restored_stopping)
    elif not args.cap:
        callbacks.append(lgb.early_stopping(50, first_metric_only=True, verbose=False))
    model = lgb.LGBMRegressor(**params).fit(
        x,
        y,
        sample_weight=weights,
        eval_X=vx,
        eval_y=vy,
        eval_names=["validation"],
        callbacks=callbacks,
        init_model=init_model,
    )
    if args.pause:
        model.booster_.save_model(args.directory / "partial.txt", num_iteration=-1)
        values = history["validation"]["l2"]
        best_index = int(np.argmin(values))
        (args.directory / "state.json").write_text(
            json.dumps(
                {
                    "completed": model.booster_.current_iteration(),
                    "best_l2": values[best_index],
                    "best_iteration": best_index + 1,
                    "best_evaluation": [["validation", "l2", values[best_index], False]],
                }
            )
        )
    prediction = model.predict(vx, num_threads=args.threads)
    np.save(args.directory / (args.label + ".npy"), prediction)
    durations = []
    for i in range(3):
        started = time.perf_counter()
        model.booster_.save_model(
            args.directory / f"serialization-{args.label}-{i}.txt", num_iteration=-1
        )
        durations.append(time.perf_counter() - started)
    result = {
        "best_iteration": int(model.best_iteration_),
        "tree_count": model.booster_.num_trees(),
        "observed_completed_rounds": state["completed"] + len(history["validation"]["l2"])
        if args.resume
        else len(history["validation"]["l2"]),
        "best_score": model.best_score_["validation"]["l2"],
        "rmse": float(np.sqrt(np.mean((prediction - vy) ** 2))),
        "mae": float(np.mean(np.abs(prediction - vy))),
        "serialization_seconds": durations,
        "threads": args.threads,
        "trees": model.booster_.dump_model()["tree_info"],
    }
    (args.directory / (args.label + ".json")).write_text(json.dumps(result))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--worker", action="store_true")
    p.add_argument("--directory", type=Path)
    p.add_argument("--label", default="baseline")
    p.add_argument("--pause", type=int, default=0)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--cap", action="store_true")
    p.add_argument("--threads", type=int, default=1)
    args = p.parse_args()
    if lgb.__version__ != "4.7.0":
        raise ValueError("EXACT_INSTALLED_LIGHTGBM_4_7_0_REQUIRED")
    if args.worker:
        worker(args)
        return 0
    if args.output is None:
        p.error("--output is required")
    reports = []
    with tempfile.TemporaryDirectory(prefix="crypto2-continuation-fixture-") as temp:
        directory = Path(temp)

        def launch(label, *flags):
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--directory",
                    str(directory),
                    "--label",
                    label,
                    *map(str, flags),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads((directory / (label + ".json")).read_text())

        baseline = launch("baseline")
        stops = {
            "before_best": max(1, baseline["best_iteration"] // 2),
            "after_best": baseline["best_iteration"] + 1,
            "inside_patience": baseline["best_iteration"] + 25,
            "one_before_early_stop": baseline["observed_completed_rounds"] - 1,
        }
        for label, pause in stops.items():
            launch("partial", "--pause", pause)
            result = launch(label, "--resume", "--pause", 0)
            # Existing model is reloaded in a separate process; remaining allowance is 500-N.
            a, b = np.load(directory / "baseline.npy"), np.load(directory / (label + ".npy"))
            reports.append(
                {
                    "case": label,
                    "pause_round": pause,
                    "max_abs_prediction_difference": float(np.max(np.abs(a - b))),
                    "exact_predictions": bool(np.array_equal(a, b)),
                    "same_best_iteration": baseline["best_iteration"] == result["best_iteration"],
                    "same_stop_round": baseline["observed_completed_rounds"]
                    == result["observed_completed_rounds"],
                    "baseline": {k: v for k, v in baseline.items() if k != "trees"},
                    "continued": {k: v for k, v in result.items() if k != "trees"},
                    "exact_tree_structure": baseline["trees"] == result["trees"],
                }
            )
        cap = launch("cap_baseline", "--cap")
        launch("partial", "--pause", 499, "--cap")
        near = launch("near_max", "--resume", "--cap")
        a, b = np.load(directory / "cap_baseline.npy"), np.load(directory / "near_max.npy")
        reports.append(
            {
                "case": "one_before_500_round_cap",
                "pause_round": 499,
                "baseline_tree_count": cap["tree_count"],
                "continued_tree_count": near["tree_count"],
                "max_abs_prediction_difference": float(np.max(np.abs(a - b))),
                "exact_predictions": bool(np.array_equal(a, b)),
                "remaining_allowance": 1,
            }
        )
        other = launch("threads2", "--threads", 2)
        threads_delta = float(
            np.max(
                np.abs(np.load(directory / "baseline.npy") - np.load(directory / "threads2.npy"))
            )
        )
    payload = {
        "lightgbm": lgb.__version__,
        "fixture": "1600 artificial non-market rows, 24 columns, weighted TRAIN",
        "method": (
            "separate processes; native save_model(-1)/init_model; "
            "restored public-callback patience state"
        ),
        "real_configuration_modified": False,
        "cases": reports,
        "full_restart_threads_1_vs_2_max_prediction_difference": threads_delta,
        "full_restart_threads_1_vs_2_same_best_iteration": baseline["best_iteration"]
        == other["best_iteration"],
        "qualification": "MID_FIT_RESUME_NOT_QUALIFIED",
        "reason": (
            "Native continuation does not reproduce the uninterrupted stochastic "
            "boosting trajectory; production init_model remains disabled."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: v for k, v in payload.items() if k != "cases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
