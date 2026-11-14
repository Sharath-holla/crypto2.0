# Phase 7A → RunPod migration plan (prepared 2026-11-14; NOTHING launched or purchased)

Added by Claude for the owner (Sharath NS). Status: **PREPARED — awaiting owner approval of
(a) the freeze-v4 admission change and (b) RunPod spending.** No pod, volume or payment exists.

## 1. Where we start

| Item | State |
| --- | --- |
| Claude Cloud execution | `STOPPED_ARCHIVED` 2026-11-14T13:40Z; 0 processes, 0 scheduled tasks |
| Completed runs | 6/768 `COMPLETE_VERIFIED` (Fold `fold-000-a0e9a4f72689`, 60m/raw: G0, C0, P0, H0, G0-symbol-id, G0-unbalanced), class `BENCHMARK_ONLY`, low-memory profile, freeze v3 (`e3e6051`) |
| Mac copies | `~/Crypto2Results/phase7a-fold0/<spec>/` — every file SHA-256-verified by the Mac server before it was renamed into place; final ledger SHA `74d2c810…8996` |
| Final archive | `phase7a_claude_cloud_final_20261114.tar` (SHA `fb7412ce…eed7d`), sent to the owner |
| Dataset | Original on the Mac: `/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107` (2,777 files, 10,998,003,736 bytes, list SHA `5ebe6f7a…05b3`, committed manifest `docs/reviews/evidence_combined_closure_20261108/runpod_data_only_manifest.json`) |
| Holdout | August 2026 `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`; July unused |

## 2. Measured workload (real Fold 0, Claude VM: 4 vCPU, 13.35 GiB)

| Step | Wall time | Of which byte-level Gold validation | Peak memory |
| --- | --- | --- | --- |
| Prepare one cache group (`--prepare-only`) | 332 s | ~200 s | 5.1 GiB anon (15.4 GiB RSS incl. page cache) |
| Train one spec from the read-only cache (6 runs) | 322–354 s | ~200 s | 3.1 GiB anon (8.5–9.4 GiB RSS) |
| LightGBM fitting inside a training run | 13–26 s (G0/H0/ablations); 4 + 20 small fits (C0/P0) | – | – |
| Prepared cache on disk | 6.35 GB per group | – | – |
| Results per run (model, report, logs) | ~6.7 MB | – | – |

**Conclusions.** (1) About 60 % of every process is the repeated Gold validation. (2) Model
fitting is under 10 % of wall time, so a GPU cannot pay for itself; it would also change
`backend=cpu`, which every approval binds, and LightGBM GPU results are not bit-identical to CPU.
(3) Memory per worker is small (≤16 GiB with page cache), so a 64 GiB pod can run 4 cache groups
in parallel.

The study is 768 runs = 128 cache groups (16 folds × 4 horizons × 2 targets) × 6 architectures;
each group needs one preparation. Later folds contain more listed-symbol rows than Fold 0 (Fold 0
dropped 38 % of TRAIN rows as non-finite/unlisted), so data-dependent time is scaled by 1.4.

## 3. RunPod hardware recommendation

Pricing could not be read live: `runpod.io` and `docs.runpod.io` are not reachable from this VM.
Figures below come from RunPod's API documentation as indexed by search (cpu3c example
`securePerVcpu = $0.04`/vCPU-h, compute-optimized 2–2.5 GB RAM/vCPU, general-purpose 4 GB/vCPU,
memory-optimized 8 GB/vCPU, sizes 2–32 vCPU) and RunPod's storage documentation (network volume
$0.07/GB-month < 1 TB; volume disk $0.10 running / $0.20 stopped; container disk $0.10, erased on
stop). **Confirm the exact $/h in the console's deploy screen before approving.**

| Option | vCPU / RAM | Est. $/h (at $0.04–0.05/vCPU-h) | Workers × threads | Fits the 64 GiB / 8 CPU / 150 GB floor |
| --- | --- | --- | --- | --- |
| **A — recommended: general-purpose 16 vCPU / 64 GB** (`cpu3g`/`cpu5g`-16-64) | 16 / 64 GB | **$0.64–0.80** | 4 × 4 | yes |
| B — faster: general-purpose 32 vCPU / 128 GB | 32 / 128 GB | $1.28–1.60 | 8 × 4 | yes |
| C — compute-optimized 32 vCPU / 64–80 GB | 32 / 64–80 GB | $1.28 | 4–5 × 6 | yes (RAM tighter per vCPU) |
| GPU pods (A4000/A5000 class, ~25 GB RAM) | 8–9 / 25 GB | $0.16–0.27 | – | **no** (RAM; GPU unused) |

**Storage:** one **150 GB network volume** in the same data center as the CPU pod ($10.50 per
month, billed whether or not a pod runs; ~$0.35/day). Peak need: dataset 11 GB + environment
~2 GB + 4–8 live caches × ≤10 GB + 768 × 6.7 MB results ≈ 5 GB → ≤100 GB. The volume keeps the
dataset, environment, caches and ledger across pod stops, so the dataset is uploaded **once**.
If the chosen CPU data center does not offer network volumes for CPU pods, use a 150 GB *volume
disk* on the pod instead ($0.10/GB-month running, $0.20 stopped) and never terminate the pod
until results are pulled.

## 4. Schedule and cost estimate (conservative; Fold-0 measurements × 1.4 for later folds)

| Scenario | Sequential 4-vCPU-equivalent hours | Option A (4 workers, 80 % efficiency) | Option B (8 workers, 70 %) |
| --- | --- | --- | --- |
| As installed (Gold validated in every process) | ~97 h | **~30 h → $19–24** | ~17 h → $22–27 |
| With identity-bound Gold receipt (freeze v4, §7) | ~48 h | **~15 h → $10–12** | ~9 h → $11–14 |

Add ~2–3 pod-hours for setup, the Linux gate, verification and the canary (~$2), and the
volume (~$1–2 for the few days). **Recommended budget for approval: Option A with the Gold
receipt, cost ceiling 25 USD, ~2 calendar days**, with automatic stops at 95 % of the ceiling and
45 minutes before the deadline. These are estimates from one fold; the runner re-estimates after
Fold 0 is complete (stage gate below) and the owner may stop there.

Cheapest transfer path: create the volume, attach it to the **smallest CPU pod** (2 vCPU, a few
cents per hour) for the upload and SHA-256 verification, terminate that pod, then start the
16-vCPU pod on the same volume only for training.

## 5. Setup and data transfer (owner runs; Claude cannot reach RunPod from this VM)

1. RunPod console: Storage → create network volume, 150 GB, data center that lists the chosen
   CPU type. Add your SSH **public** key under Settings → SSH Public Keys (never paste a private
   key anywhere). Deploy a CPU pod with the volume mounted at `/workspace` and **TCP port 22
   exposed**. Copy "SSH over exposed TCP" (`root@<ip> -p <port>`); the proxied `ssh.runpod.io`
   form does not support scp/rsync.
2. On the pod:
   ```bash
   cd /workspace && git clone --branch experiment/phase7-runpod-migration https://github.com/sharath-holla/crypto2.0.git && cd crypto2.0
   ```
   ```bash
   bash scripts/runpod/setup_pod.sh
   ```
3. On the Mac (resumable; copies only the 2,777 manifest files; deletes nothing):
   ```bash
   POD=root@<ip> PORT=<port> bash ~/Projects/crypto2.0/scripts/runpod/mac_send_dataset.sh
   ```
4. On the pod (SHA-256 of every file against the committed manifest, then one byte-level Gold
   validation and the identity summary):
   ```bash
   bash scripts/runpod/verify_dataset.sh
   ```
5. Copy the verified low-memory record (`low_memory_validation.json`, `ecd83e71…3702`) and
   `study_ledger.json` from `~/Crypto2Results/phase7a-fold0/architecture-G0-unbalanced-A6-60m-raw/evidence/`
   to `/workspace/crypto2run/evidence/` (scp over the same SSH). Without them nothing can train.

Security: SSH key authentication only; the dataset never leaves Mac→pod SSH; no public URL; no
token or key in the repository, logs or this document. Results come back by the Mac **pulling**
over SSH, so the pod never holds credentials for the Mac.

## 6. Execution, checkpoints, resume, monitoring, export

```bash
tmux new -s study        # survives SSH disconnects; reattach with: tmux attach -t study
```
```bash
source scripts/runpod/runpod_env.sh && uv run python scripts/runpod/study_runner.py plan --ledger $CRYPTO2_LOCAL/evidence/study_ledger.json
```
```bash
uv run python scripts/runpod/study_runner.py run --ledger $CRYPTO2_LOCAL/evidence/study_ledger.json --owner "Sharath NS" --deadline <UTC from approval> --cost-ceiling <approved> --currency USD --hourly-cost <console $/h> --workers 4 --delete-done-caches --execute
```
```bash
bash scripts/runpod/monitor.sh      # second tmux window: CPU load, RAM, disk, verified runs
```
```bash
POD=root@<ip> PORT=<port> bash ~/Projects/crypto2.0/scripts/runpod/mac_pull_results.sh   # on the Mac, any time
```

* **Checkpoint unit = one verified run.** A run counts only when its report is `COMPLETE`, its
  model reloads with the registered SHA-256, TEST was not used for selection and the holdout was
  not used; then the ledger is updated under a file lock. Caches are deleted only after all six
  runs of their group are verified.
* **Resume:** re-run the same `run` command after any interruption or pod restart (everything is
  on the volume). Verified runs are skipped; a group whose cache survived resumes from the cache;
  a half-written cache is never adopted (atomic publish) and is prepared again.
* **Fail closed:** any failed preparation, training, reload or ledger check stops all new work.
* **Export:** `mac_pull_results.sh` is incremental, never deletes on the Mac, and checks every
  ledger model SHA-256 against the files received. Pull after every stage gate and at the end.

## 7. Required before the full grid: freeze v4 (owner decision; code-only, no compute)

The installed admission deliberately refuses the full study: `benchmark_one_spec` always targets
Fold 0 and `approval_binding` accepts only the six Fold-0 60m/raw specs (v3); the runner refuses
every other fold (`plan` lists them). Proposed v4, implemented and tested free of charge on Claude
Cloud **only after the owner approves this design**:

1. `--fold-id` on `benchmark_one_spec` and `write_owner_approval.py` (default Fold 0, unchanged).
2. Low-memory admission scope = the 48 frozen primary specs × the 16 planned folds; everything
   else (expansion view, August, other configs) still refused. Each run still needs its own
   identity-bound approval file, generated by the runner from the owner's single written approval
   (owner, deadline, ceiling).
3. Identity-bound Gold receipt: the first process per pod session runs the full byte-level
   validation and records the Gold manifest SHA, report SHA and a (path, size, inode, mtime_ns)
   fingerprint of every Gold file, which are made read-only. Later processes accept the receipt
   only on an exact match; any change, missing or extra file forces full validation. Every new pod
   session and every new fold re-validates in full.
4. Tests (scope, refusal outside scope, receipt tamper/touch/rename cases) and a v4 freeze record
   whose preparation and scientific digests are **unchanged** (so cache identities, the low-memory
   validation record and the six existing results stay valid; only the control digest changes).

## 8. Stage gates

| Gate | Work | Pod time (Option A) | Owner decision after |
| --- | --- | --- | --- |
| R0 | volume, small pod, transfer, SHA-256 + Gold verification | 1–3 h small pod | – |
| R1 | big pod: Linux gate, canary = re-train G0 Fold-0 60m/raw and compare with model `79aa64e7…acb7` / report metrics | ~1 h | cross-host reproducibility OK? |
| R2 | rest of Fold 0 (42 runs, 7 groups) | ~1.5 h | measured time per group → final cost projection |
| R3 | folds 1–15 (720 runs) | ~13–28 h | – |
| R4 | final pull to Mac, verify, stop pod; keep or delete volume | – | delete volume when results are confirmed on the Mac |

## 9. Storage and cleanup

* Caches: deleted per group after verification (`--delete-done-caches`).
* Stop the pod whenever no stage is running (a stopped pod with a network volume costs only the
  volume). After R4 and a verified Mac pull, delete the pod and then the volume; the Mac copy and
  the original dataset remain the record.
* Claude Cloud: the 6.35 GB cache, redundant export snapshots and pytest temp files were removed;
  the 11 GB dataset copy is kept until the owner confirms the Mac original (command in the
  migration report), then removed.

Sources: RunPod docs (pricing, storage types, network volumes, SSH over exposed TCP, transfer with
rsync), RunPod API reference for CPU types; links in the migration report.
