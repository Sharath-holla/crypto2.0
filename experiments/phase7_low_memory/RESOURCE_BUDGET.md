# Resource budget — Phase 7A Core20 on the Claude Code cloud VM

Status 2026-11-13: measured on SYNTHETIC data with the exact Gold schema at real Fold-0 scale.
Real-data numbers are produced by tomorrow's prepare-only run; until then these are the plan.

## The machine (measured in this session)

| Resource | Value | How measured |
|---|---|---|
| CPU | 4 vCPU Intel Xeon 2.30 GHz, x86_64 | `nproc`, `/proc/cpuinfo` |
| RAM | 15 GiB host, **14,337,294,336 B effective (13.35 GiB)**, no swap | `runtime.system_snapshot` (cgroup-aware) |
| GPU | none | `nvidia-smi` absent |
| Disk | ~31.5 GB writable free; the device reports 252–270 GB but that is NOT writable | `shutil.disk_usage` |
| Network | allow-listed; `storage.googleapis.com` reachable (auth via credential card); Binance archive host blocked | proxy |
| Session | temporary; idles pause, containers can be reclaimed; background commands ≤ 2 h | platform docs |

## Memory (peak anonymous = what can trigger the OOM killer)

| Path | Fold-0 shape (4.92 M rows) | All-20 worst case (5.78 M rows) | Evidence |
|---|---|---|---|
| Standard profile (unmodified) | OOM-killed (exit 137); extrapolated ~24.9 GiB | — | `results/run_baseline.log`, `scale_*.json` |
| `low_memory` profile | **8.81 GiB** | **10.34 GiB** | `results/repo_profile_*.json` |
| `low_memory` + `PHASE7_STAGING_DAYS=30` | **4.99 GiB** | not run (expected ≈ 5–6 GiB: year read unit) | `results/staged_compare_staged.json` |
| `low_memory` + staging 7 days | 4.97 GiB | — | `results/staged_compare_staged_7d.json` |
| Training process (read-only cache, LightGBM G0) | 1.98 GiB (from 11-13 morning, before the no-fit rule) | 1.71 GiB | `results/worst_train.log` |

Admission floors for the profile: ≥ 13 GiB effective RAM, ≥ 4 CPUs (this VM passes with
~0.35 GiB margin on the RAM floor, which is a TOTAL, not a usage figure). The standard 64 GiB
guard stays in force when the profile is not selected.

Remaining memory risk: real-data non-finite patterns and the real sidecar size may differ from
synthetic; the prepare-only run measures them before any training is authorized.

## Disk (Fold 0)

`uv run python -m crypto_ai.phase7.low_memory_disk budget --path /home/user --fold-rows 4922887 --data-bytes-pending 10998003736`

| Component | Bytes |
|---|---|
| Free now | 31.47 GB |
| Data set (2,777 files) | 11.00 GB |
| Spill (unfiltered fold segments) | 5.52 GB |
| Prepared cache (tables + matrices; staged files adopted by rename) | 9.01 GB |
| Models, reports, checkpoints | 0.30 GB allowance |
| Logs, telemetry | 0.30 GB allowance |
| Safety margin | 2.00 GB |
| **Planned peak** | **28.13 GB → ~5.3 GB free at peak** |

Already occupied (excluded from "free"): repository + virtualenv 0.59 GB, uv cache 0.57 GB.
Worst-case later folds (5.78 M rows): spill 6.49 + cache 10.58 GB → planned peak 30.67 GB
against 31.47 GB free: **fits with only ~0.8 GB beyond the 2 GB safety margin (marginal)**. It
requires that the spill of a finished preparation is gone before the next one (the spill session
deletes it at process exit) and that only one prepared cache exists at a time
(`low_memory_disk release` after all of its specifications are terminal). Run `budget` before
every preparation; it exits non-zero when the plan does not fit.

## Time (estimates, not measurements on real data)

* Preparation of one fold/horizon/target: ~1.5–3.5 min synthetic (`results/*`).
* LightGBM G0 on 3.28 M × 109: 0.43 s/round with 4 threads (measured 11-13 morning, synthetic);
  ≤ 500 rounds with early stopping 50 → ≤ ~3.6 min per estimator.
* Full study estimate (48 specs × 16 folds): ~55–110 compute hours, i.e. many sessions.
