#!/usr/bin/env python3
"""Smoke-test or compare a requested LightGBM GPU backend without using Gold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai.phase7.backend import compare_cpu_gpu_backends, smoke_test_backend


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), required=True)
    parser.add_argument("--compare-cpu", action="store_true")
    parser.add_argument(
        "--tolerances",
        type=Path,
        help="Operator-approved JSON limits; absent/partial limits require review.",
    )
    args = parser.parse_args()
    if args.compare_cpu:
        if args.backend == "cpu":
            parser.error("--compare-cpu requires --backend gpu or cuda")
        limits = (
            json.loads(args.tolerances.read_text(encoding="utf-8")) if args.tolerances else None
        )
        result = compare_cpu_gpu_backends(args.backend, tolerances=limits)
    else:
        result = smoke_test_backend(args.backend)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
