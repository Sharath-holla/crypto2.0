"""ADDED BY CLAUDE (2026-11-14): clean page cache is reclaimable, not used memory."""

from __future__ import annotations

from pathlib import Path

from crypto_ai.phase7.resource_estimate import _direct_cgroup_limits

GB = 10**9


def _write(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(text)
    return root


def test_v1_clean_cache_is_not_counted_but_dirty_and_shmem_are(tmp_path: Path) -> None:
    stat = "\n".join(
        [
            f"total_cache {9 * GB}",
            f"total_rss {1 * GB}",
            f"total_shmem {GB // 2}",
            f"total_dirty {GB // 4}",
            "total_writeback 0",
        ]
    )
    root = _write(
        tmp_path / "v1",
        {
            "memory.limit_in_bytes": str(14 * GB),
            "memory.usage_in_bytes": str(10 * GB),
            "memory.stat": stat,
        },
    )
    limits = _direct_cgroup_limits(root)
    # 10 GB usage - (9 GB cache - 0.5 shmem - 0.25 dirty) = 1.75 GB really in use
    assert limits["cgroup_memory_current_bytes"] == 10 * GB - (9 * GB - GB // 2 - GB // 4)


def test_v2_file_accounting(tmp_path: Path) -> None:
    root = _write(
        tmp_path / "v2",
        {
            "memory.max": str(14 * GB),
            "memory.current": str(6 * GB),
            "memory.stat": f"anon {2 * GB}\nfile {4 * GB}\nshmem 0\nfile_dirty {GB}\n"
            "file_writeback 0\n",
        },
    )
    assert _direct_cgroup_limits(root)["cgroup_memory_current_bytes"] == 3 * GB


def test_missing_stat_keeps_the_conservative_raw_usage(tmp_path: Path) -> None:
    root = _write(
        tmp_path / "raw",
        {"memory.limit_in_bytes": str(14 * GB), "memory.usage_in_bytes": str(10 * GB)},
    )
    assert _direct_cgroup_limits(root)["cgroup_memory_current_bytes"] == 10 * GB
