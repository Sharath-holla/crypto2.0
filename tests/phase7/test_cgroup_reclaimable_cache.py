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


def test_mapped_file_pages_stay_counted_as_used(tmp_path: Path) -> None:
    root = _write(
        tmp_path / "mapped",
        {
            "memory.limit_in_bytes": str(14 * GB),
            "memory.usage_in_bytes": str(8 * GB),
            "memory.stat": f"total_cache {6 * GB}\ntotal_rss {2 * GB}\ntotal_mapped_file {3 * GB}\n"
            "total_dirty 0\ntotal_writeback 0\ntotal_shmem 0\n",
        },
    )
    assert _direct_cgroup_limits(root)["cgroup_memory_current_bytes"] == 5 * GB


def test_inactive_only_cache_and_v2_writeback(tmp_path: Path) -> None:
    root = _write(
        tmp_path / "v2wb",
        {
            "memory.max": str(14 * GB),
            "memory.current": str(5 * GB),
            "memory.stat": f"anon {GB}\nfile {4 * GB}\ninactive_file {4 * GB}\nactive_file 0\n"
            f"file_writeback {GB}\nfile_dirty 0\nshmem 0\nfile_mapped 0\n",
        },
    )
    assert _direct_cgroup_limits(root)["cgroup_memory_current_bytes"] == 2 * GB


def test_genuine_low_memory_still_trips_the_1_gib_floor(tmp_path, monkeypatch) -> None:
    import pytest

    from crypto_ai.phase7 import resource_estimate, resources, runtime

    # 13.35 GiB limit, 13 GB of ANONYMOUS memory in use, almost no cache: genuinely low.
    root = _write(
        tmp_path / "low",
        {
            "memory.limit_in_bytes": "14338772992",
            "memory.usage_in_bytes": str(13_900_000_000),
            "memory.stat": "total_cache 100000000\ntotal_rss 13800000000\ntotal_dirty 0\n"
            "total_writeback 0\ntotal_shmem 0\ntotal_mapped_file 0\n",
        },
    )
    fake = _direct_cgroup_limits(root)
    assert fake["cgroup_memory_limit_bytes"] == 14338772992  # the real limit is preserved
    monkeypatch.setattr(
        resource_estimate,
        "cgroup_limits",
        lambda *a, **k: {
            **fake,
            "cgroup_memory_available_bytes": max(
                0, fake["cgroup_memory_limit_bytes"] - fake["cgroup_memory_current_bytes"]
            ),
            "cgroup_cpu_quota_cpus": None,
        },
    )
    snapshot = runtime.memory_snapshot()
    assert snapshot["ram_total_bytes"] <= 14338772992
    assert snapshot["ram_available_bytes"] < 1024**3
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "1")
    with pytest.raises(MemoryError, match="below configured 1.0 GiB floor"):
        resources.resource_admission("TEST_STAGE", additional_roots=(tmp_path,))
