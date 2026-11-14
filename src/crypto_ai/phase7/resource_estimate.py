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
    observed_rows: int | None = None,
) -> dict[str, Any]:
    """Labelled size estimates for one horizon (rows ~ total / horizon_count)."""

    if min(total_gold_rows, feature_count, horizon_count, dtype_bytes, gold_columns) <= 0:
        raise ValueError("rows, features, horizons, columns and dtype size must be positive")
    rows = total_gold_rows // horizon_count if observed_rows is None else observed_rows
    if rows <= 0:
        raise ValueError("observed rows must be positive")
    matrix = rows * feature_count * dtype_bytes
    arrow = int(rows * gold_columns * 8 * arrow_copies)
    return {
        "estimated_rows_per_horizon_average": total_gold_rows // horizon_count,
        "matrix_rows": rows,
        "rows_label": ESTIMATED_AVERAGE if observed_rows is None else MEASURED,
        "feature_count": feature_count,
        "estimated_raw_matrix_bytes": matrix,
        "estimated_raw_matrix_bytes_label": ESTIMATED_AVERAGE
        if observed_rows is None
        else "DERIVED_FROM_MEASURED_ROWS",
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
            "basis": (
                "total rows / horizon count"
                if observed_rows is None
                else "observed fold rows before purge/finite filtering"
            )
            + "; copy factors are a planning heuristic, not an upper bound",
            "lightgbm_memory": "NOT_MEASURED; generic copy factor only",
        },
    }


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _reclaimable_cache(root: Path) -> int:
    """Clean file cache in this cgroup (v2 ``memory.stat`` or v1 ``total_*`` keys); 0 if unknown."""

    raw = _read(root / "memory.stat") or _read(root / "memory/memory.stat")
    if not raw:
        return 0
    stats: dict[str, int] = {}
    for line in raw.splitlines():
        key, _, value = line.partition(" ")
        if value.strip().isdigit():
            stats[key] = int(value)
    if "file" in stats:  # cgroup v2
        unreclaimable = (
            stats.get("shmem", 0)
            + stats.get("file_dirty", 0)
            + stats.get("file_writeback", 0)
            + stats.get("file_mapped", 0)
        )
        return max(0, stats["file"] - unreclaimable)
    cache = stats.get("total_cache", stats.get("cache"))
    if cache is None:
        return 0
    unreclaimable = sum(
        stats.get(f"total_{name}", stats.get(name, 0))
        for name in ("shmem", "dirty", "writeback", "mapped_file")
    )
    return max(0, cache - unreclaimable)


def _direct_cgroup_limits(root: Path) -> dict[str, Any]:
    """Linux cgroup v2/v1 RAM and CPU limits; all-None on macOS or when unlimited/unreadable."""

    memory: int | None = None
    for name in ("memory.max", "memory.limit_in_bytes", "memory/memory.limit_in_bytes"):
        raw = _read(root / name)
        if raw and raw != "max" and raw.isdigit() and int(raw) < 1 << 60:
            memory = int(raw)
            break
    # CHANGED BY CLAUDE (2026-11-06, RunPod review): also report the cgroup's CURRENT memory use so
    # the runtime can compute what is really left inside a container.
    memory_current: int | None = None
    for name in ("memory.current", "memory.usage_in_bytes", "memory/memory.usage_in_bytes"):
        raw_current = _read(root / name)
        if raw_current and raw_current.isdigit():
            memory_current = int(raw_current)
            break
    # CHANGED BY CLAUDE (2026-11-14, real-data run): cgroup usage includes CLEAN page cache that the
    # kernel reclaims on demand (e.g. 8.6 GB of cache vs 0.7 MB of process memory after reading
    # Gold). Counting it as used made the RAM floor refuse a run that had ample memory. Subtract
    # only clean, UNMAPPED file cache (memory.stat); shmem, dirty, writeback and mapped file pages
    # (e.g. memory-mapped matrices in active use) still count as used. The limit is unchanged.
    if memory_current is not None:
        memory_current = max(0, memory_current - _reclaimable_cache(root))
    cpus: float | None = None
    raw = _read(root / "cpu.max")
    if raw:
        quota, _, period = raw.partition(" ")
        if quota != "max" and quota.isdigit() and period.isdigit() and int(period) > 0:
            cpus = int(quota) / int(period)
    else:
        quota_raw = _read(root / "cpu.cfs_quota_us") or _read(root / "cpu/cpu.cfs_quota_us")
        period_raw = _read(root / "cpu.cfs_period_us") or _read(root / "cpu/cpu.cfs_period_us")
        if (
            quota_raw
            and period_raw
            and quota_raw.lstrip("-").isdigit()
            and int(quota_raw) > 0
            and period_raw.isdigit()
            and int(period_raw) > 0
        ):
            cpus = int(quota_raw) / int(period_raw)
    return {
        "cgroup_memory_limit_bytes": memory,
        "cgroup_memory_current_bytes": memory_current,
        "cgroup_cpu_quota_cpus": cpus,
        "label": MEASURED,
        "observed": memory is not None or cpus is not None,
    }


def cgroup_limits(
    root: Path = Path("/sys/fs/cgroup"), *, membership_path: Path | None = None
) -> dict[str, Any]:
    """Read process cgroups and their ancestors, including v1 controller mounts.

    Namespace-root containers often expose limits directly at root. Non-namespaced
    processes can instead be members of nested groups. Parent ceilings also apply.
    """
    paths = {root}
    if membership_path is None and root == Path("/sys/fs/cgroup"):
        membership_path = Path("/proc/self/cgroup")
    membership = _read(membership_path) if membership_path else None
    for line in (membership or "").splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3:
            continue
        controllers, relative = fields[1], Path(fields[2].lstrip("/"))
        if ".." in relative.parts:
            continue
        mounts = [root] if not controllers else [root / controllers]
        if controllers:
            mounts.extend(root / controller for controller in controllers.split(","))
        for mount in mounts:
            current = mount / relative
            while current.is_relative_to(mount):
                paths.add(current)
                if current == mount:
                    break
                current = current.parent
    observed = [_direct_cgroup_limits(path) for path in sorted(paths)]
    memory = [item for item in observed if item["cgroup_memory_limit_bytes"] is not None]
    quotas = [
        item["cgroup_cpu_quota_cpus"]
        for item in observed
        if item["cgroup_cpu_quota_cpus"] is not None
    ]
    tightest = min(memory, key=lambda x: x["cgroup_memory_limit_bytes"]) if memory else {}
    remaining = [
        max(0, item["cgroup_memory_limit_bytes"] - item["cgroup_memory_current_bytes"])
        if item["cgroup_memory_current_bytes"] is not None
        else 0
        for item in memory
    ]
    return {
        "cgroup_memory_limit_bytes": tightest.get("cgroup_memory_limit_bytes"),
        "cgroup_memory_current_bytes": tightest.get("cgroup_memory_current_bytes"),
        "cgroup_memory_available_bytes": min(remaining) if remaining else None,
        "cgroup_cpu_quota_cpus": min(quotas) if quotas else None,
        "label": MEASURED,
        "observed": bool(memory or quotas),
    }


def effective_ram_available(system: dict[str, Any], cgroups: dict[str, Any]) -> int:
    """The smaller of host-available RAM and the cgroup limit (a container cannot exceed it)."""

    available = int(system["ram_available_bytes"])
    limit = cgroups.get("cgroup_memory_limit_bytes")
    if not limit:
        return available
    current = cgroups.get("cgroup_memory_current_bytes")
    remaining = 0 if current is None else max(0, int(limit) - int(current))
    if cgroups.get("cgroup_memory_available_bytes") is not None:
        remaining = min(remaining, cgroups["cgroup_memory_available_bytes"])
    return min(available, remaining)


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


def observed_fold_rows(
    manifest_path: Path, config_path: Path, index: int, horizon: int
) -> dict[str, Any]:
    """Count canonical rows only; never load features, targets, or create matrices."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from crypto_ai.phase5.folds import calibration_split_time, plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.feature_census import canonical_parquet_paths

    config = load_phase7_config(config_path)
    plans = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )
    if index < 0 or index >= len(plans):
        raise ValueError("fold index is outside the frozen calendar")
    plan = plans[index]
    middle = calibration_split_time(plan)
    windows = {
        "TRAIN": (plan.train_start, plan.train_end),
        "Validation": (plan.validation_start, plan.validation_end),
        "Cal-A": (plan.calibration_start, middle),
        "Cal-B": (middle, plan.calibration_end),
        "TEST": (plan.test_start, plan.test_end),
    }
    counts = dict.fromkeys(windows, 0)
    for path in canonical_parquet_paths(manifest_path):
        for batch in pq.ParquetFile(path).iter_batches(
            columns=["feature_time", "horizon_minutes"], batch_size=65536
        ):
            times, horizons = batch.column(0), batch.column(1)
            selected = pc.equal(horizons, horizon)
            for split, (start, end) in windows.items():
                mask = pc.and_(
                    selected,
                    pc.and_(
                        pc.greater_equal(times, pa.scalar(start, type=times.type)),
                        pc.less(times, pa.scalar(end, type=times.type)),
                    ),
                )
                counts[split] += pc.sum(pc.cast(mask, pa.int64())).as_py() or 0
    return {
        "fold_id": plan.fold_id,
        "horizon_minutes": horizon,
        "segment_rows": counts,
        "total_rows": sum(counts.values()),
        "label": MEASURED,
        "scope": "Gold rows before membership/purge/embargo/finite filtering; no model fit",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="where the cache will live")
    parser.add_argument("--dtype-bytes", type=int, default=8, choices=(4, 8))
    parser.add_argument("--fold-index", type=int)
    parser.add_argument("--horizon-minutes", type=int, choices=(15, 30, 60, 120), default=60)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase7/research_core20_primary_v1.toml")
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output only")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    # Imported lazily so the pure functions above stay importable without psutil.
    from crypto_ai.phase7.runtime import system_snapshot

    system = system_snapshot(args.path)
    cgroups = cgroup_limits()
    fold = (
        observed_fold_rows(args.manifest, args.config, args.fold_index, args.horizon_minutes)
        if args.fold_index is not None
        else None
    )
    estimate = estimate_spec_resources(
        total_gold_rows=int(manifest["row_count"]),
        feature_count=len(manifest["feature_columns"]),
        dtype_bytes=args.dtype_bytes,
        observed_rows=fold["total_rows"] if fold else None,
    )
    ram_available = effective_ram_available(system, cgroups)
    errors = check_capacity(
        estimate, ram_available=ram_available, disk_free=system["disk_free_bytes"]
    )
    payload = {
        "estimate": estimate,
        "observed_fold": fold,
        "measured": {
            "label": MEASURED,
            "physical_ram_total_bytes": system["host_ram_total_bytes"],
            "effective_ram_total_bytes": system["ram_total_bytes"],
            "ram_available_bytes": system["ram_available_bytes"],
            "effective_ram_available_bytes": ram_available,
            "disk_free_bytes": system["disk_free_bytes"],
            "cpu_count": system["cpu_count"],
            "host_cpu_count": system["host_cpu_count"],
            "affinity_cpu_count": system["affinity_cpu_count"],
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
