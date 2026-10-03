#!/usr/bin/env python3
"""Small synthetic float64 preparation benchmark; never opens Gold or trains."""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.models import _matrix
from crypto_ai.phase7.runtime import memory_snapshot


def benchmark(rows: int = 20_000, features: int = 109) -> dict[str, object]:
    if not 1 <= rows <= 100_000 or not 1 <= features <= 109:
        raise ValueError("synthetic benchmark requires 1..100000 rows and 1..109 features")
    rng = np.random.default_rng(42)
    names = tuple(f"f{index}" for index in range(features))
    table = pa.table({name: rng.normal(size=rows).astype(np.float64) for name in names})
    before = memory_snapshot()
    started = time.perf_counter()
    matrix = _matrix(table, names)
    seconds = time.perf_counter() - started
    after = memory_snapshot()
    equivalent = all(
        np.array_equal(matrix[:, index], table.column(name).to_numpy())
        for index, name in enumerate(names)
    )
    if not equivalent:
        raise RuntimeError("synthetic preparation changed values or feature ordering")
    return {
        "status": "PASS",
        "synthetic_only": True,
        "gold_used": False,
        "rows": rows,
        "features": features,
        "dtype": str(matrix.dtype),
        "matrix_bytes": matrix.nbytes,
        "elapsed_seconds": seconds,
        "exact_value_equivalence": equivalent,
        "memory_before": before,
        "memory_after": after,
        "ram_reduction_claim": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--features", type=int, default=109)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.rows, args.features), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
