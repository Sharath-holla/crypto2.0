"""Read-only RAM / disk estimate for ONE spec (default: architecture-G0-A6-60m-raw).

CHANGED BY CLAUDE (2026-11-06, final hardening) - new file. It reads only the Gold manifest (row
count and feature list) and the host's free RAM/disk. It builds no cache, opens no market data and
starts no training. The numbers are conservative UPPER BOUNDS (the whole Gold horizon table, not
just Fold 1), so a pass here is a necessary condition, not a promise.

    python -m crypto_ai.phase7.resource_estimate --manifest <gold manifest.json> --path <work dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GIB = 1024**3


def estimate_spec_resources(
    *,
    total_gold_rows: int,
    feature_count: int,
    horizon_count: int = 4,
    dtype_bytes: int = 8,
    memory_copies: float = 3.0,
    cache_copies: float = 1.5,
    headroom: float = 1.2,
) -> dict[str, Any]:
    """Upper-bound sizes for one horizon: rows ~ total/horizon_count, float matrix x copies."""

    if min(total_gold_rows, feature_count, horizon_count, dtype_bytes) <= 0:
        raise ValueError("rows, features, horizons and dtype size must be positive")
    rows = total_gold_rows // horizon_count
    matrix = rows * feature_count * dtype_bytes
    return {
        "rows_per_horizon_upper_bound": rows,
        "feature_count": feature_count,
        "feature_matrix_bytes": matrix,
        "ram_required_bytes": int(matrix * memory_copies * headroom),
        "cache_disk_required_bytes": int(matrix * cache_copies * headroom),
        "assumptions": {
            "dtype_bytes": dtype_bytes,
            "memory_copies": memory_copies,
            "cache_copies": cache_copies,
            "headroom": headroom,
            "basis": "whole horizon table (upper bound); not Fold 1 only",
        },
    }


def check_capacity(estimate: dict[str, Any], *, ram_available: int, disk_free: int) -> list[str]:
    errors = []
    if estimate["ram_required_bytes"] > ram_available:
        errors.append(
            f"RAM: need ~{estimate['ram_required_bytes'] / GIB:.1f} GiB, "
            f"available {ram_available / GIB:.1f} GiB"
        )
    if estimate["cache_disk_required_bytes"] > disk_free:
        errors.append(
            f"DISK: need ~{estimate['cache_disk_required_bytes'] / GIB:.1f} GiB, "
            f"free {disk_free / GIB:.1f} GiB"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="where the cache will live")
    parser.add_argument("--dtype-bytes", type=int, default=8, choices=(4, 8))
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    # Imported lazily so the pure functions above stay importable without psutil.
    from crypto_ai.phase7.runtime import system_snapshot

    system = system_snapshot(args.path)
    estimate = estimate_spec_resources(
        total_gold_rows=int(manifest["row_count"]),
        feature_count=len(manifest["feature_columns"]),
        dtype_bytes=args.dtype_bytes,
    )
    errors = check_capacity(
        estimate,
        ram_available=system["ram_available_bytes"],
        disk_free=system["disk_free_bytes"],
    )
    print(
        json.dumps(
            {
                "estimate": estimate,
                "ram_available_bytes": system["ram_available_bytes"],
                "disk_free_bytes": system["disk_free_bytes"],
                "errors": errors,
                "verdict": "INSUFFICIENT_RESOURCES" if errors else "RESOURCES_OK_UPPER_BOUND",
            },
            indent=2,
        )
    )
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
