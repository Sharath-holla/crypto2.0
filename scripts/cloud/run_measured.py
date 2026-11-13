#!/usr/bin/env python3
"""Run ONE command and record peak memory, minimum free disk and elapsed time as JSON evidence.

ADDED BY CLAUDE (2026-11-13). It starts nothing by itself: the command to run is given
explicitly after ``--``. Memory is summed over the whole process tree every 0.5 s (VmRSS and
RssAnon); free disk is sampled on ``--disk-path``. Optionally stops the command (SIGTERM) if free
disk falls below ``--min-free-gb`` so the filesystem can never be filled.

  uv run python scripts/cloud/run_measured.py --output EVIDENCE.json --disk-path /home/user \\
      --min-free-gb 2 -- uv run python -m crypto_ai.phase7.benchmark_one_spec ...
"""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

GIB = 1024**3


def _tree_memory(root: psutil.Process) -> tuple[int, int]:
    rss = anon = 0
    for process in [root, *root.children(recursive=True)]:
        try:
            rss += process.memory_info().rss
            with open(f"/proc/{process.pid}/status") as handle:
                for line in handle:
                    if line.startswith("RssAnon:"):
                        anon += int(line.split()[1]) * 1024
        except (psutil.Error, OSError):
            continue
    return rss, anon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--disk-path", type=Path, default=Path("/home/user"))
    parser.add_argument("--min-free-gb", type=float, default=2.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the command after --")
    started = time.time()
    child = subprocess.Popen(command)
    root = psutil.Process(child.pid)
    peak_rss = peak_anon = 0
    min_free = shutil.disk_usage(args.disk_path).free
    stopped_for_disk = False
    while child.poll() is None:
        rss, anon = _tree_memory(root)
        peak_rss, peak_anon = max(peak_rss, rss), max(peak_anon, anon)
        free = shutil.disk_usage(args.disk_path).free
        min_free = min(min_free, free)
        if free < args.min_free_gb * 1e9 and not stopped_for_disk:
            stopped_for_disk = True
            child.send_signal(signal.SIGTERM)
        time.sleep(0.5)
    evidence = {
        "command": command,
        "exit_code": child.returncode,
        "elapsed_seconds": round(time.time() - started, 1),
        "peak_tree_rss_gib": round(peak_rss / GIB, 3),
        "peak_tree_anon_gib": round(peak_anon / GIB, 3),
        "min_free_disk_gb": round(min_free / 1e9, 2),
        "stopped_for_low_disk": stopped_for_disk,
        "sampling_interval_seconds": 0.5,
        "label": "MEASURED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=1), encoding="utf-8")
    print(json.dumps(evidence), flush=True)
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
