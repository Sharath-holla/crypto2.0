#!/usr/bin/env python3
"""Smoke-test or compare a requested LightGBM GPU backend without using Gold."""

from __future__ import annotations

import argparse
import json

from crypto_ai.phase7.backend import compare_cpu_gpu_backends, smoke_test_backend


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), required=True)
    parser.add_argument("--compare-cpu", action="store_true")
    args = parser.parse_args()
    if args.compare_cpu:
        if args.backend == "cpu":
            parser.error("--compare-cpu requires --backend gpu or cuda")
        result = compare_cpu_gpu_backends(args.backend)
    else:
        result = smoke_test_backend(args.backend)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
