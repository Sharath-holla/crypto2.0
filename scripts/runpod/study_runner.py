#!/usr/bin/env python3
"""Resumable Phase 7A study runner for a RunPod CPU pod: one prepared cache per cache group.

ADDED BY CLAUDE (2026-11-14). Orchestration only: it calls the EXISTING, unchanged entrypoints
(``benchmark_one_spec --prepare-only``, ``benchmark_one_spec`` training, ``verify_model_reload``,
``study_ledger record``) exactly as the verified Fold-0 group runner did, and adds:

* cache-group scheduling: one ``--prepare-only`` per (fold, horizon, target) group, then the six
  architecture specs of that group read the SAME read-only cache (``PHASE7_CACHE_MODE=read_only``);
* bounded parallelism: ``--workers K`` independent cache groups at once (never two workers on the
  same group), each with ``PHASE7_TOTAL_CPU_THREADS = threads // K``;
* resume: a run already ``COMPLETE_VERIFIED`` in the ledger is skipped; an interrupted group is
  re-entered (the cache is reused if present and valid, otherwise prepared again);
* a file lock around every ledger write (parallel workers);
* a stop deadline (no new run starts within ``--deadline-margin-min`` of it) and an hourly cost
  ceiling estimate (``--hourly-cost`` x elapsed hours must stay below ``--cost-ceiling``);
* cache removal ONLY after every spec of the group is COMPLETE_VERIFIED (``--delete-done-caches``).

It never fabricates approvals: the owner name, deadline and cost ceiling come from the command
line (the owner's own approval message), and ``write_owner_approval.py`` binds each run to the
real identities. Scope: the runner REFUSES any fold the installed admission does not support. With
freeze v3 that is only Fold 0 / 60m / raw; the full grid needs the separately approved freeze v4
(``docs/runpod/RUNPOD_MIGRATION_PLAN.md`` section 7). Nothing here touches TEST selection or the
August holdout.

  python scripts/runpod/study_runner.py plan   --ledger L
  python scripts/runpod/study_runner.py run    --ledger L --owner "<name>" \\
      --deadline 2026-11-20T18:00:00Z --cost-ceiling 40 --currency USD --hourly-cost 0.80 \\
      --workers 4 [--fold fold-000-a0e9a4f72689 ...] [--execute]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
SPEC_ORDER = ("G0", "C0", "P0", "H0", "G0-symbol-id", "G0-unbalanced")


def _arch(spec: str) -> str:
    # architecture-<ARCH>-A6-<h>m-<target>
    return spec[len("architecture-") :].split("-A6-")[0]


def cache_groups(ledger: dict[str, Any], folds: Iterable[str] | None = None) -> list[dict]:
    """Group ledger runs by cache group, in chronological fold order, specs in SPEC_ORDER."""
    wanted = set(folds) if folds else None
    groups: dict[str, dict] = {}
    for run in ledger["runs"].values():
        if wanted and run["fold_id"] not in wanted:
            continue
        group = groups.setdefault(
            run["cache_group"],
            {"cache_group": run["cache_group"], "fold_id": run["fold_id"], "runs": []},
        )
        group["runs"].append(run)
    for group in groups.values():
        group["runs"].sort(key=lambda r: SPEC_ORDER.index(_arch(r["spec"])))
        group["pending"] = [r["spec"] for r in group["runs"] if r["status"] != "COMPLETE_VERIFIED"]
    return sorted(groups.values(), key=lambda g: g["cache_group"])


def supported_folds(first_fold: str) -> set[str] | None:
    """Folds the INSTALLED admission accepts. ``None`` = any fold (freeze v4 entrypoint)."""
    help_text = subprocess.run(
        [PY, "-m", "crypto_ai.phase7.benchmark_one_spec", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    ).stdout
    return None if "--fold-id" in help_text else {first_fold}


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.evidence = Path(os.environ["CRYPTO2_LOCAL"]) / "evidence"
        self.out = Path(os.environ["CRYPTO2_LOCAL"]) / "out"
        self.started = time.time()
        self.deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00")).timestamp()
        self.threads = max(1, (os.cpu_count() or 1) // args.workers)
        self.fold_arg = supported_folds(args.first_fold) is None
        self.halted = False  # any failure stops NEW groups/runs (fail closed)

    def log(self, message: str) -> None:
        line = f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {message}"
        print(line, flush=True)
        with (
            locked(self.evidence / ".runner.lock"),
            open(self.evidence / "study_runner.log", "a") as handle,
        ):
            handle.write(line + "\n")

    def budget_ok(self) -> bool:
        if self.halted:
            return False
        hours = (time.time() - self.started) / 3600 + self.args.hours_already_spent
        margin = self.args.deadline_margin_min * 60
        if time.time() + margin >= self.deadline:
            self.log("STOP: inside the deadline margin; no new run starts")
            return False
        if hours * self.args.hourly_cost >= self.args.cost_ceiling * 0.95:
            self.log(f"STOP: estimated spend {hours * self.args.hourly_cost:.2f} near ceiling")
            return False
        return True

    def env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "PHASE7_TOTAL_CPU_THREADS": str(self.threads),
                "PHASE7_LIGHTGBM_THREADS_PER_MODEL": str(self.threads),
                "PHASE7_MODEL_PARALLELISM": "1",
                **extra,
            }
        )
        return env

    def step(self, name: str, command: list[str], log_file: Path, **extra: str) -> bool:
        remaining = int(self.deadline - time.time())
        with open(log_file, "w") as handle:
            result = subprocess.run(
                ["timeout", "-s", "TERM", str(max(remaining, 1)), *command],
                cwd=REPO,
                env=self.env(**extra),
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if result.returncode != 0:
            self.log(f"FAILED {name} (exit {result.returncode}); see {log_file}")
        return result.returncode == 0

    def approval(self, spec: str, fold: str, mode: str) -> Path | None:
        tag = f"{fold}-{spec}-{mode}"
        path = self.evidence / "approvals" / f"approval-{tag}.json"
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [PY, "scripts/cloud/write_owner_approval.py", "--mode", mode, "--spec-id", spec]
        command += ["--owner", self.args.owner, "--deadline", self.args.deadline]
        command += ["--cost-ceiling", str(self.args.cost_ceiling), "--currency", self.args.currency]
        command += ["--output", str(path), "--confirm"]
        if self.fold_arg:
            command += ["--fold-id", fold]
        ok = self.step(f"approval {tag}", command, self.evidence / "logs" / f"approval-{tag}.out")
        return path if ok else None

    def entry(self, spec: str, fold: str, *flags: str) -> list[str]:
        command = [PY, "-m", "crypto_ai.phase7.benchmark_one_spec", "--spec-id", spec]
        command += ["--output-root", str(self.out), "--execute", *flags]
        return command + (["--fold-id", fold] if self.fold_arg else [])

    def run_group(self, group: dict) -> str:
        result = self._run_group(group)
        if "STOPPED" in result:
            self.halted = True
        return result

    def _run_group(self, group: dict) -> str:
        fold, key = group["fold_id"], group["cache_group"].replace("|", "_")
        logs = self.evidence / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        if not group["pending"]:
            return f"{key}: already complete"
        first = group["runs"][0]["spec"]
        if not self.budget_ok():
            return f"{key}: not started (budget/deadline)"
        approval = self.approval(first, fold, "prepare")
        if approval is None:
            return f"{key}: STOPPED (prepare approval)"
        self.log(f"== {key}: prepare (no fit)")
        ok = self.step(
            f"prepare {key}",
            self.entry(first, fold, "--prepare-only"),
            logs / f"prepare-{key}.out",
            PHASE7_ALLOW_CLOUD_RESEARCH="1",
            PHASE7_CACHE_MODE="auto",
            PHASE7_OWNER_APPROVAL_FILE=str(approval),
        )
        if not ok:
            return f"{key}: STOPPED (prepare)"
        for spec in group["pending"]:
            if not self.budget_ok():
                return f"{key}: paused before {spec}"
            approval = self.approval(spec, fold, "train")
            if approval is None:
                return f"{key}: STOPPED (train approval {spec})"
            self.log(f"== {key}: train {spec}")
            if not self.step(
                f"train {spec}",
                self.entry(spec, fold),
                logs / f"train-{fold}-{spec}.out",
                PHASE7_ALLOW_CLOUD_RESEARCH="1",
                PHASE7_CACHE_MODE="read_only",
                PHASE7_OWNER_APPROVAL_FILE=str(approval),
            ):
                return f"{key}: STOPPED (train {spec})"
            report = next(self.out.glob(f"*/report/models/core/{fold}/{spec}/report.json"), None)
            model = next(self.out.glob(f"*/model/models/core/{fold}/{spec}/model.joblib"), None)
            if report is None or model is None:
                self.log(f"FAILED {spec}: report/model missing")
                return f"{key}: STOPPED (artifacts {spec})"
            reload_record = self.evidence / "reload" / f"{fold}-{spec}.json"
            reload_record.parent.mkdir(parents=True, exist_ok=True)
            if not self.step(
                f"reload {spec}",
                [PY, "scripts/cloud/verify_model_reload.py", "--model", str(model)]
                + ["--cache-root", os.environ["PHASE7_CACHE_ROOT"], "--output", str(reload_record)],
                logs / f"reload-{fold}-{spec}.out",
            ):
                return f"{key}: STOPPED (reload {spec})"
            with locked(self.evidence / ".ledger.lock"):
                result = subprocess.run(
                    [PY, "scripts/cloud/study_ledger.py", "record", "--ledger"]
                    + [str(self.args.ledger), "--report", str(report), "--reload"]
                    + [str(reload_record)],
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if "COMPLETE_VERIFIED" not in result.stdout:
                self.log(f"FAILED ledger {spec}: {result.stdout[-300:]}{result.stderr[-300:]}")
                return f"{key}: STOPPED (verification {spec})"
            self.log(f"{fold}|{spec} COMPLETE_VERIFIED")
        if self.args.delete_done_caches:
            self.delete_cache(group)
        return f"{key}: COMPLETE"

    def delete_cache(self, group: dict) -> None:
        ledger = json.loads(Path(self.args.ledger).read_text())
        runs = [r for r in ledger["runs"].values() if r["cache_group"] == group["cache_group"]]
        ids = {r.get("prepared_cache_id") for r in runs}
        if any(r["status"] != "COMPLETE_VERIFIED" for r in runs) or len(ids) != 1 or None in ids:
            self.log(f"KEEP cache for {group['cache_group']} (group not fully verified)")
            return
        cache = Path(os.environ["PHASE7_CACHE_ROOT"]) / ids.pop()
        if cache.is_dir() and cache.parent == Path(os.environ["PHASE7_CACHE_ROOT"]):
            subprocess.run(["rm", "-rf", "--", str(cache)], check=True)
            self.log(f"deleted verified-group cache {cache.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        command = sub.add_parser(name)
        command.add_argument("--ledger", type=Path, required=True)
        command.add_argument("--fold", action="append", help="limit to these fold ids")
        command.add_argument("--first-fold", default="fold-000-a0e9a4f72689")
        if name == "run":
            command.add_argument("--owner", required=True)
            command.add_argument("--deadline", required=True)
            command.add_argument("--cost-ceiling", type=float, required=True)
            command.add_argument("--currency", required=True)
            command.add_argument("--hourly-cost", type=float, required=True)
            command.add_argument("--hours-already-spent", type=float, default=0.0)
            command.add_argument("--workers", type=int, default=1)
            command.add_argument("--deadline-margin-min", type=int, default=45)
            command.add_argument("--delete-done-caches", action="store_true")
            command.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    ledger = json.loads(args.ledger.read_text())
    groups = cache_groups(ledger, args.fold)
    supported = supported_folds(args.first_fold)
    refused = sorted({g["fold_id"] for g in groups if supported and g["fold_id"] not in supported})
    pending = [g for g in groups if g["pending"]]
    summary = {
        "cache_groups": len(groups),
        "groups_with_pending_runs": len(pending),
        "pending_runs": sum(len(g["pending"]) for g in groups),
        "folds_refused_by_installed_admission": refused,
    }
    print(json.dumps(summary, indent=1))
    if args.command == "plan":
        return 0
    if refused:
        print("REFUSED: these folds need the owner-approved freeze v4 admission first.")
        return 2
    if not args.execute:
        print("DRY RUN: nothing started (add --execute only after the owner approves).")
        return 0
    runner = Runner(args)
    runner.log(
        f"START workers={args.workers} threads/worker={runner.threads} groups={len(pending)}"
    )
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed(pool.submit(runner.run_group, g) for g in pending):
            runner.log(future.result())
    runner.log("RUNNER FINISHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
