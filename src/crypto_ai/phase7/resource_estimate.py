"""Read-only RAM / disk estimate for ONE spec (default: architecture-G0-A6-60m-raw).

CHANGED BY CLAUDE (2026-11-06, closure) - terminology and measurements corrected. It reads only the
Gold manifest (row count and feature list) and the host's RAM/disk/cgroup limits. It builds no
cache, opens no market data and starts no training.

Every number is labelled by how it was obtained:

* MEASURED - read from the host or the cgroup (free disk, physical RAM, available RAM, limits);
* ESTIMATED_AVERAGE - total Gold rows / number of horizons (horizons do NOT have equal row
  counts, so this is an average, not a bound);
* ESTIMATED_HEURISTIC_PEAK - averaged matrix and Arrow bytes times fixed copy/headroom factors.
  It is a planning heuristic, NOT an upper bound: nothing here proves a run will fit.

    python -m crypto_ai.phase7.resource_estimate \\
        --manifest <gold manifest.json> --path <dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GIB = 1024**3
MEASURED = "MEASURED"
ESTIMATED_AVERAGE = "ESTIMATED_AVERAGE"
ESTIMATED_HEURISTIC_PEAK = "ESTIMATED_HEURISTIC_PEAK"


def estimate_spec_resources(
    *,
    total_gold_rows: int,
    feature_count: int,
    horizon_count: int = 4,
    dtype_bytes: int = 8,
    memory_copies: float = 3.0,
    cache_copies: float = 1.5,
    headroom: float = 1.2,
    gold_columns: int = 130,
    arrow_copies: float = 2.0,
) -> dict[str, Any]:
    """Labelled size estimates for one horizon (rows ~ total / horizon_count)."""

    if min(total_gold_rows, feature_count, horizon_count, dtype_bytes, gold_columns) <= 0:
        raise ValueError("rows, features, horizons, columns and dtype size must be positive")
    rows = total_gold_rows // horizon_count
    matrix = rows * feature_count * dtype_bytes
    arrow = int(rows * gold_columns * 8 * arrow_copies)
    return {
        "estimated_rows_per_horizon_average": rows,
        "rows_label": ESTIMATED_AVERAGE,
        "feature_count": feature_count,
        "estimated_raw_matrix_bytes": matrix,
        "estimated_raw_matrix_bytes_label": ESTIMATED_AVERAGE,
        "estimated_arrow_source_bytes": arrow,
        "ram_required_bytes": int((matrix * memory_copies + arrow) * headroom),
        "ram_required_label": ESTIMATED_HEURISTIC_PEAK,
        "cache_disk_required_bytes": int(matrix * cache_copies * headroom),
        "cache_disk_required_label": ESTIMATED_HEURISTIC_PEAK,
        "assumptions": {
            "dtype_bytes": dtype_bytes,
            "memory_copies": memory_copies,
            "cache_copies": cache_copies,
            "headroom": headroom,
            "gold_columns": gold_columns,
            "arrow_copies": arrow_copies,
            "basis": "total rows / horizon count; Fold 1 is a subset and horizons differ - "
            "a planning heuristic, not an upper bound",
        },
    }


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def cgroup_limits(root: Path = Path("/sys/fs/cgroup")) -> dict[str, Any]:
    """Linux cgroup v2/v1 RAM and CPU limits; all-None on macOS or when unlimited/unreadable."""

    memory: int | None = None
    for name in ("memory.max", "memory/memory.limit_in_bytes"):
        raw = _read(root / name)
        if raw and raw != "max" and raw.isdigit() and int(raw) < 1 << 60:
            memory = int(raw)
            break
    cpus: float | None = None
    raw = _read(root / "cpu.max")
    if raw:
        quota, _, period = raw.partition(" ")
        if quota != "max" and quota.isdigit() and period.isdigit() and int(period) > 0:
            cpus = int(quota) / int(period)
    else:
        quota_raw = _read(root / "cpu/cpu.cfs_quota_us")
        period_raw = _read(root / "cpu/cpu.cfs_period_us")
        if quota_raw and period_raw and quota_raw.lstrip("-").isdigit() and int(quota_raw) > 0:
            cpus = int(quota_raw) / int(period_raw)
    return {
        "cgroup_memory_limit_bytes": memory,
        "cgroup_cpu_quota_cpus": cpus,
        "label": MEASURED,
        "observed": memory is not None or cpus is not None,
    }


def effective_ram_available(system: dict[str, Any], cgroups: dict[str, Any]) -> int:
    """The smaller of host-available RAM and the cgroup limit (a container cannot exceed it)."""

    available = int(system["ram_available_bytes"])
    limit = cgroups.get("cgroup_memory_limit_bytes")
    return min(available, int(limit)) if limit else available


def check_capacity(estimate: dict[str, Any], *, ram_available: int, disk_free: int) -> list[str]:
    errors = []
    if estimate["ram_required_bytes"] > ram_available:
        errors.append(
            f"RAM: need ~{estimate['ram_required_bytes'] / GIB:.1f} GiB "
            f"({ESTIMATED_HEURISTIC_PEAK}), available {ram_available / GIB:.1f} GiB"
        )
    if estimate["cache_disk_required_bytes"] > disk_free:
        errors.append(
            f"DISK: need ~{estimate['cache_disk_required_bytes'] / GIB:.1f} GiB "
            f"({ESTIMATED_HEURISTIC_PEAK}), free {disk_free / GIB:.1f} GiB"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="where the cache will live")
    parser.add_argument("--dtype-bytes", type=int, default=8, choices=(4, 8))
    parser.add_argument("--json", action="store_true", help="machine-readable output only")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    # Imported lazily so the pure functions above stay importable without psutil.
    from crypto_ai.phase7.runtime import system_snapshot

    system = system_snapshot(args.path)
    cgroups = cgroup_limits()
    estimate = estimate_spec_resources(
        total_gold_rows=int(manifest["row_count"]),
        feature_count=len(manifest["feature_columns"]),
        dtype_bytes=args.dtype_bytes,
    )
    ram_available = effective_ram_available(system, cgroups)
    errors = check_capacity(
        estimate, ram_available=ram_available, disk_free=system["disk_free_bytes"]
    )
    payload = {
        "estimate": estimate,
        "measured": {
            "label": MEASURED,
            "physical_ram_total_bytes": system["ram_total_bytes"],
            "ram_available_bytes": system["ram_available_bytes"],
            "effective_ram_available_bytes": ram_available,
            "disk_free_bytes": system["disk_free_bytes"],
            "cpu_count": system["cpu_count"],
            **cgroups,
        },
        "errors": errors,
        "verdict": "INSUFFICIENT_RESOURCES" if errors else "HEURISTIC_CHECK_PASSED_NOT_A_GUARANTEE",
    }
    if not args.json:
        print(
            "NOTE: sizes below are ESTIMATED_* heuristics; only 'measured' values are measured.",
            file=sys.stderr,
        )
    print(json.dumps(payload, indent=None if args.json else 2, sort_keys=True))
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
