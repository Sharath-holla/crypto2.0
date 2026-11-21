# CRYPTO 2.0 — COMPLETE READ-ONLY AUDIT (MacBook clone)

Audit date: 2026-11-01. Mode: READ-ONLY. Nothing in the Mac repository was edited, built, trained,
committed or cleaned.

## 0. Method and limits (read this first)

| Item | What actually happened |
| --- | --- |
| Access to the Mac | Folder access granted to `/Users/cortex/Projects/crypto2.0` only. Used **only** directory listing and file staging (read copies). |
| Mac shell | **Never became available** ("workspace still downloading"). Therefore `git status`, `uname`, `sw_vers`, `sysctl`, `df`, `python3 --version` **could not be run**. |
| How git was audited | The Mac `.git` data (HEAD, config, packed-refs, index, one pack) was copied to a cloud scratch directory and read there with git. All history, all 7 remote branches and 3 tags were inspected without touching the Mac working tree. |
| Code execution | **None of the project code was executed.** PyPI is blocked from the audit sandbox, so no dependencies could be installed and no tests were run. Fold count, spec count and cache-key count were verified by replaying the logic in standard-library Python. |
| Documentation | Read in full or in part: `AGENTS.md`, `PROJECT_CONTEXT.md`, laptop-migration docs, membership-lookahead fix doc, Fold-1 bottleneck doc, prior `PHASE7A_CODE_AUDIT.md` (searched). The other ~70 docs were mapped by name/size/branch and **not read line by line**. |
| Source | Read in full or in the relevant parts: `phase7/{config,targets,folds,segments,universe(selection),features(HTF/cross-sectional),gold,gold_validation(diff),models,backend,prepared_cache,artifacts,run_lease,recovery(parts),runtime,resources,environment,metrics,economics,phase7a,training}`, `phase5/{folds,calibration}`, `research/metrics`, `phase6/labels`, shell scripts, `cli.py` (parsers). Not read line by line: `acquisition.py` (69 KB), `discovery_checkpoint.py`, `pipeline.py`, `quality.py`, `progress.py`, `preflight.py`, the Aiventra tree, legacy trading code. |
| Mac hardware | From the app only: **macOS (darwin), arm64, device name "sharaths-macbook-air-local"**. RAM, core count, free disk, Python version: **NOT VERIFIED**. |
| Report location | Saved with the session outputs (cloud). Writing to the Mac `/tmp` or into the repo was not possible/allowed. |

Every finding below says whether it is **confirmed from source**, **inferred**, or **unverified on real data**.

---

## 1. Repository, branches, and which branch is authoritative

| Item | Value |
| --- | --- |
| Path (Mac) | `/Users/cortex/Projects/crypto2.0` |
| Checked-out branch | `main` |
| HEAD | `4ef91d53f2eb6b83157394078452cf4c1a85a5fe` (2026-10-03, "docs(phase7a): normalize finalization report ending") |
| Remote | `https://github.com/Sharath-holla/crypto2.0.git` |
| Working tree | Clean by evidence (see §1.3); `git status` itself not runnable |

### 1.1 Branch map (all read-only, from packed-refs)

| Branch / tag | Relation to `main` | Meaning |
| --- | --- | --- |
| `origin/main` = checked out | — | Standalone lineage, through `4ef91d5` |
| **`origin/codex/laptop-migration-20261024`** (tag `laptop-migration-20261024` → `7102b87`) | main + 6 commits (472 files) | **Declared latest tested root state** (docs: "Use this branch for the full latest checkout"). Contains Oct-3 hardening, Oct-22/23 remediation (membership-lookahead fix, training metrics, environment identity), Aiventra tree, 886-test verification record. |
| `origin/phase7a-pre-lightning-hardening-20261003` | main + 8 | Contains the 3 hardening commits **plus 5 commits not in the migration branch** (Gold-validator column-order fix, hermetic Linux tests, Lightning/GCP recovery docs). Diverged independently. |
| `origin/integration/aiventra-crypto-os` | main + 5 | Earlier Aiventra integration snapshot (`b8a574d`). Not scientific. |
| `origin/codex/laptop-checkpoint-wip-20261024` | main-based older (26 behind) | Explicitly **unverified WIP**. Do not use. |
| `origin/codex/phase7-discovery-checkpoint`, `...workload-optimization` | ancestors of main | Historical. |
| Tags `crypto2.0-handoff-20260906`, `phase7a-hold-20260906` | historical | Frozen September handoff/hold state. |

**Authoritative scientific implementation: `codex/laptop-migration-20261024`** — stated by `PROJECT_CONTEXT.md` and `docs/LAPTOP_MIGRATION_2026_10_24.md` ("do not assume cloning `main` restores the latest local fixes").

**No single branch contains every fix** (see H-01).

### 1.2 The Mac is on the wrong branch (C-01)
`main` lacks, among others: `run_lease.py`, `recovery.py`, `resources.py`, `telemetry.py`, `device_evidence.py`, `equivalence.py`, `verify_linux.py`, `environment.py`, `training_metrics.py`, and the `TRAIN_HISTORY_ONLY_V2` universe gate (grep confirms the string is absent on `origin/main`).

### 1.3 Working-tree evidence
All 20 top-level entries are tracked; every tracked file's mtime lies in `1793513837019–1793513837054` (single checkout instant) and equals `.git/index`'s mtime; only `.git/FETCH_HEAD` is newer. The listing taken at the end of the audit is identical to the initial one. This is strong but **indirect** evidence the tree was not changed; the formal `git status/diff` comparison could not be run.

---

## 2. Project understanding (verified against source, `laptop-migration` branch)

| Item | Finding |
| --- | --- |
| Phase / profile / view | Phase 7A, CORE20_PRIMARY, view CORE (`scripts/run_phase7a_pipeline.py`) |
| Run identity | Code builds `phase7a-core20-primary-{configuration_hash}`. The value `…93f987736b1a79d26b773957` was **not recomputed** (needs pydantic runtime) → NOT VERIFIED |
| Research cutoff / holdout | `2026-07-01T00:00:00Z` exclusive / `2026-08-01`; both **hard-locked** in `Phase7Config` validators; `prospective_holdout_status: Literal["LOCKED_UNUSED"]`, `used: Literal[False]`, `evaluation_authorized: Literal[False]` ✔ |
| Folds | **16** ✔ (replayed: 24m train, 3m validation, 3m calibration, 3m test, 3m step, from 2020-01-01; Fold 1 = 2020-01-01 → 2022-10-01; Fold 16 test ends exactly 2026-07-01) |
| Canonical Fold-1 specs | **48** ✔ (4 horizons × 2 targets × 6 variants: G0, C0, P0, H0, G0+symbol-id, G0-unbalanced). `primary_specs()` asserts the exact set. 58 total exist (6 A0–A5 ablations + 4 HTF controls are deferred) |
| Production features | **109 = 54 native + 22 (12h) + 33 (1d)**. 54 native verified by counting (24 base + 11 coin + 11 anchor + 8 market, with 3 derivative columns inside the 24 → A6 groups them last). 22/33 HTF consistent with source and with a later-branch assertion; not enumerated at runtime |
| Gold physical columns (130) | NOT VERIFIED |
| Targets | `multiasset_targets_v2`: raw `open[i+2+steps]/open[i+2]−1`; entry = open of the 2nd bar after the feature candle (`decision_latency_bars=1`); `label_end_time = open[i+2+steps]`; gap-safe (needs contiguous bars); excluded if `label_end ≥ cutoff`. Volatility-normalized = raw / max(|daily_volatility|, 1e-8). v1 kept for audit only ✔ |
| Purge | Rows dropped unless `label_end_time < next segment start` (actual label end, not fixed bars) ✔ |
| Embargo | 120 min dropped at the start of Validation / Cal-A / Cal-B / Test; config validator requires embargo ≥ longest horizon (120) ✔ |
| Segments | Train, Validation (early stopping), Cal-A (calibrator), Cal-B (thresholds), Test; Cal-A/B split at calibration-window midpoint |
| Algorithms | LightGBM `LGBMRegressor`, objective `regression` (L2), lr 0.02, ≤500 trees, 31 leaves, min_child 100, subsample 0.9 (freq 1), colsample 0.9, L1 0.1, L2 1.0, early stopping 50 rounds (`first_metric_only`) on Validation, `random_state=42`; CPU path `deterministic=True, force_col_wise=True`; float64 end to end |
| Model families | G0 global; C0 per-cluster (train-only KMeans, 4 clusters); P0 per-coin; H0 = G0 + per-symbol/cluster corrections fit on Validation; G0+one-hot symbol; G0 unbalanced |
| Metrics | Regression: MAE, RMSE, R², directional accuracy, Pearson, Spearman, cross-sectional Spearman IC (≥3 assets), coverage, per-symbol/cluster/age bucket, economics. No classification metrics ✔ |
| EXPANDING | Disabled for 7A **only by runtime patching** (H-03). `enable_expansion = true` is still set in the 7A TOML |

---

## 3. Documentation map (subset; "read" = read in full/part)

| File | Purpose | Status |
| --- | --- | --- |
| `AGENTS.md`, `PROJECT_CONTEXT.md` (read) | Operating rules, frozen state. On `main` they predate the Oct work; on the migration branch `PROJECT_CONTEXT` points to the migration doc | CURRENT on migration branch / STALE on `main` |
| `docs/LAPTOP_MIGRATION_2026_10_24.md`, `…_VERIFICATION_…` (read) | Which branch to restore; what Git does/doesn't preserve; 886 passed/5 skipped | CURRENT |
| `docs/PHASE7A_MEMBERSHIP_LOOKAHEAD_FIX_2026_10_23.md` (read) | P1 defect + fix (`TRAIN_HISTORY_ONLY_V2`) | CURRENT (migration branch only) |
| `docs/PROJECT_HANDOFF/*` (00–30, partly read) | Sept-6 long-term handoff | HISTORICAL but definitive for frozen state; its "missing prepared-matrix checkpoint" blocker is superseded by code |
| `docs/PROJECT_HANDOFF/21_FOLD1_PREPARATION_BOTTLENECK.md` (read) | 6h21m of Fold-1 compute produced 0/48; hot function UNKNOWN | HISTORICAL; see H-04 |
| `docs/PHASE7A_CODE_AUDIT.md` (searched) | Earlier audit: "leakage verdict PASS" | PARTLY STALE (predates Oct fix; conflicts with M-01) |
| `docs/PHASE7A_PRE_LIGHTNING_*`, `LIGHTNING_PHASE7A_RUNBOOK.md`, `PHASE7_CLOUD_RUNBOOK.md` | Lightning / GCP operations | HISTORICAL / provider-specific |
| `docs/phase7/*` (hold docs, Sept 6) | Frozen hold state | HISTORICAL |
| `docs/PHASE7_UNIVERSE.md`, `…MULTI_ASSET_FEATURES.md`, `…MODEL_ARCHITECTURES.md` | Phase 7 design | CURRENT (not verified line by line) |
| `docs/WALK_FORWARD.md`, `LABELS.md`, `FEATURES.md`, `MODELING.md`, `BACKTESTING.md` | Phases 3–6 | HISTORICAL |
| `docs/aiventra-crypto-integration/`, `aiventra/` (migration branch) | Separate application | OUT OF SCOPE (not read, not run) |
| `README.md` | Install and CLI examples | PARTLY STALE (L-09) |

---

## 4. Pipeline (code level)

| Stage | Module(s) | Notes |
| --- | --- | --- |
| Acquisition / Bronze | `phase7/acquisition.py`, `data/binance/*`, `data/ingestion/*` | Binance USD-M perpetual archives + REST reconciliation; immutable Bronze, SHA manifests. *Not read line by line.* |
| Silver | `data/quality/*`, `phase7/quality.py` | Quality engine, exact-duplicate removal, promotion, causal gap segments (`phase7/segments.py` → `CausalDataGap`) |
| Registry / universe | `phase7/registry.py`, `universe.py` | Lifecycle (`available_from/until`, onboard), Core20 frozen at 2022-01-01, per-fold point-in-time eligibility, HNT kept (survivorship), XPIN not forced |
| Features | `phase7/features.py`, `phase6/features.py` | Rolling features reset at gaps; HTF = completed-candle as-of join (`availability_time = open+interval`, `side="right"`, `valid_until = availability+1 interval`) ✔ causal |
| Targets | `phase7/targets.py` | §2 |
| Gold | `phase7/gold.py`, `gold_validation.py` | **Inner join** features×targets; partitioned `symbol/year`; manifest with per-file SHA, holdout flags; validator raises `HoldoutViolationError` on any row ≥ cutoff/holdout |
| Folds | `phase5/folds.py`, `phase7/folds.py` | Calendar folds from config (never row maxima); hardened Cal-A/Cal-B |
| Prepared cache | `phase7/prepared_cache.py` | §6 |
| Training | `phase7/training.py`, `models.py` | §7 |
| Calibration / thresholds | `phase5/calibration.py`, `phase7/economics.py` | Cal-A: identity vs linear by in-sample MAE. Cal-B: non-overlapping per-symbol policy, thresholds by granularity (global/cluster/per-coin) |
| Evaluation | `phase7/metrics.py` | Always evaluated on **raw** returns (normalized specs are rescaled by `ex_ante_volatility_scale`) ✔ comparable |
| Checkpoints | `artifacts.py`, `recovery.py`, `run_lease.py` | §8 |

---

## 5. Scientific safety verdicts

| Control | Verdict | Basis |
| --- | --- | --- |
| Lookahead controls | **RISK** | Targets/HTF/rolling features are causal. M-01 (label-conditioned cross-sectional context) and C-01 (main lacks the membership fix) |
| Target leakage | PASS | Entry `open[i+2]`, exit `open[i+2+steps]`, gap-safe, cutoff-bounded; asserts re-check entry/horizon invariants |
| Purging | PASS | actual `label_end_time` strictly before next segment |
| Embargo | PASS | 120 min at each later segment start; validator ≥ max horizon |
| Cal-A isolation | PASS | Calibrator fit only on Cal-A; method chosen on the same Cal-A (L-03) |
| Cal-B isolation | PASS | Thresholds from Cal-B only (`selection_source="CAL_B_ONLY"` enforced) |
| Test isolation | PASS by code path, weak enforcement | Test is read only after model/calibrator/thresholds are hashed; but `release_test()` accepts any non-empty string (M-02) |
| Point-in-time universe | PASS on migration branch / **FAIL on `main`** | `TRAIN_HISTORY_ONLY_V2` |
| Survivorship | PASS (design) | Delisted/legacy names retained; per-fold eligibility from train-end descriptors. Caveat: Core20 chosen as of 2022-01-01 (no later-listed coins) |
| August | **LOCKED_UNUSED** in all train/eval/prep paths | No path loads or evaluates ≥ 2026-08-01. **Acquisition-side RISK**: M-07 |

---

## 6. Prepared cache

* Implementation: Arrow IPC tables (train / validation / cal_a / cal_b / test) + NumPy `.npy` (float64 X, y, symbol arrays), `manifest.json`, `CACHE_COMPLETE` marker holding the manifest SHA-256.
* **Unique Fold-1 cache keys = 8** ✔ (replayed): `(CORE, horizon∈{15,30,60,120}, target∈{raw, volatility_normalized}, feature_group=A6)`. Architecture, `symbol_balanced`, `explicit_symbol_id` are **not** in the identity (one-hot symbol encoding is deferred to fit time: `deferred_sorted_train_symbols_one_hot_v1`), so the 6 variants per (horizon,target) share one entry. The Gold slice is shared per horizon (4 slices), prepared per (horizon, target) (8).
* Identity (64-hex SHA) covers: Gold dataset id + manifest SHA + partition SHAs/row counts, config hash, source fingerprint, scientific-source hash (≈50 files), fold id, view, horizon, target, feature columns **in order**, membership/universe/registry/descriptor hashes, purge+embargo, preprocessing version, dtype, **scientific environment** (Python patch version, numpy/pyarrow/lightgbm/sklearn/joblib/pydantic versions, `pyproject.toml`/`uv.lock` hashes).
* Atomic publication: PASS — temp dir → write → SHA each file → fsync → marker → **full validation of temp** → global publication lock → move → re-validate → quarantine/rollback on failure. Capacity checks (`PHASE7_CACHE_MAX_GB`, free disk).
* Checksum validation: PASS — every file hashed on every load; shape/dtype, row counts, schema, matrix-vs-table alignment (train, validation, Cal-A symbols). Memory-mapped read, `allow_pickle=False`.
* Partial-cache acceptance: none found (marker + inventory equality + manifest identity equality).
* Training itself **requires** `PHASE7_CACHE_MODE=read_only` (`require_training_runtime_contract`): cold preparation is a separate prior step.

---

## 7. Training, calibration, checkpoint/resume

* Early stopping uses Validation only. When the diagnostics observer is active the eval set becomes (train, validation) with an appended display metric; correctness relies on LightGBM skipping the training set in early stopping (same-object identity). Equivalence of observed vs unobserved fits is test-covered in the repo but **not verified here** (INFO).
* **Completed-spec resume: safe.** `CheckpointStore.is_complete` checks status, run id, stage, exact scientific-identity equality, SHA-256 of every listed file and a self-hash. Model receipts, report identity, orphan-report validation and `MODEL_ONLY` refusal ("preserve model; explicit operator decision required, no refit") are present.
* **Mid-spec resume: does not exist.** A LightGBM fit is atomic per spec; an interrupted fit restarts from zero. Consequently no scientific-equivalence question arises, but all in-flight work is lost on a crash.
* Any change to ≈50 hashed source files, `uv.lock`, Python patch version or package versions makes existing checkpoints/caches non-matching (M-03).
* Threading: C0/P0 estimators may fit in a `ThreadPoolExecutor`; results are collected in canonical key order; `ComputeBudget` rejects oversubscription. Single-writer protection per run via `flock` lease.

---

## 8. Mac and RunPod portability

### 8.1 Mac (arm64)
| Item | Finding |
| --- | --- |
| CODE_DEVELOPMENT | **YES** (any modern arm64 Mac) |
| UNIT_TESTING | NOT VERIFIED (no Python env inspected). Pure-Python/NumPy tests should run; 5 tests are Linux-only skips |
| SMALL_FIXTURE_TESTING | NOT VERIFIED (likely yes) |
| DOCUMENTATION | YES |
| FULL_GOLD_PROCESSING | NOT VERIFIED — Gold is documented as 50.35 M rows / 138 partitions (data not on this Mac). Not appropriate to attempt |
| COLD_PREPARATION | NOT VERIFIED — see H-04; RAM/disk of this machine unknown. Not recommended on a laptop |
| FULL_FOLD1_TRAINING | NOT VERIFIED — no GPU path on macOS (`cuda`/`gpu` unavailable), CPU only |

Mac-specific issues: `/usr/bin/time -v` (GNU only) and `stat -c` (GNU only) in worker scripts; hard-coded `/home/nssharath123/.local/bin/uv`; `os.fsync` on macOS does not force media flush (needs `F_FULLFSYNC`); LightGBM on macOS needs `libomp` (wheel usually bundles/handles it; **not verified**); run-lease liveness degrades to `UNKNOWN` when `psutil` raises `AccessDenied` (handled, fail-closed); `core.ignorecase = true` in the clone (APFS default is case-insensitive) — no case-colliding tracked filenames were found in the file list; `multiprocessing` is not used (threads only), so spawn-vs-fork is moot; no `/proc` or `/sys` use in `src` (only `nvidia-smi`, guarded by `OSError`).

### 8.2 Linux / RunPod
| Item | Finding |
| --- | --- |
| Python | `requires-python >=3.11`; recorded dev setup 3.12; lock file `uv.lock` (frozen, 31 packages) |
| Package manager | `uv sync --frozen --extra dev` |
| System packages | `libgomp1` (LightGBM), `time` (for `/usr/bin/time -v`), `git`; `nvidia-smi` only if GPU requested |
| Storage assumptions | Gold, Silver, caches, models, reports, logs, checkpoints rooted by `PHASE7_*_ROOT` env vars; legacy absolute paths remappable via `PHASE7_LEGACY_*_ROOT`; checkpoints store logical roots (portable) |
| Required env (Lightning wrapper) | `PHASE7_DATA_ROOT, GOLD_ROOT, ARTIFACT_ROOT, CACHE_ROOT, CHECKPOINT_ROOT, MODEL_ROOT, REPORT_ROOT, LOG_ROOT, LGBM_DEVICE, CACHE_MODE`; training also needs `PHASE7_MIN_FREE_RAM_GIB`, `PHASE7_ALLOW_CLOUD_RESEARCH=1` |
| Lightning hard-coding | Wrapper `lightning.py` is thin; real hard-codes are GCE/`nssharath123` paths in worker scripts and GCP-specific supervisor (`phase7_vm_supervisor.py`) |
| GCS restore | Not implemented in the scientific code; Gold/state must be restored out-of-band and re-verified by SHA (manifest check does this) |
| Verdict | **PARTIAL** — Python code portable; launch scripts and cached-state reuse are not (H-02, M-03) |

---

## 9. Security (tracked files, migration branch)

* Potential secrets: **NONE found** by pattern scan (private-key headers, AWS/GitHub/OpenAI/Slack token formats, `key=` literals). `.env.example` has empty placeholders only; `.env*` and `*.pem|*.key` ignored.
* `shell=True`, `os.system`, `eval/exec`: none in source (matches were PyTorch `.eval()`).
* Unsafe deserialization: `joblib.load` for Phase 4/7 models (guarded by report-bound SHA — but the report lives beside the model, so the check detects corruption, not tampering); legacy `pickle.load` in `pipeline/inference.py`, `data/inference.py`, `extra/inference_dl.py`. No YAML.
* Subprocess use: fixed argv lists (`git`, `nvidia-smi`); no user-controlled strings.
* Legacy order-capable code (CoinSwitch `place_hft_order`, `live_trader.py`, `main_trader.py`, `dashboard.py`) is present; protection is documentation only (M-08).

---

## 10. Test suite (not executed)

718 `def test_` functions across 15 directories (phase7 = 317); the repo's own verification record claims 886 passed / 5 skipped (parametrization) on Windows. Not re-run here: dependencies could not be installed and the Mac environment was not inspected. Do not treat the old count as a requirement.

---

## 11. BUG / RISK TABLE

Severity counts: **CRITICAL 1 · HIGH 4 · MEDIUM 9 · LOW 10 · INFO 5**

| ID | Sev | File / function | Issue | Impact | Evidence | Recommended fix (NOT applied) |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 | CRITICAL (conditional) | Repo state: Mac is on `main` @ `4ef91d5` | The checked-out branch lacks the P1 membership-lookahead fix (`TRAIN_HISTORY_ONLY_V2`) and all Oct hardening (lease, recovery, resource gates, environment identity, training metrics) | Any training/prep from this checkout would use future gap evidence to choose TRAIN membership (changes cross-sectional context, clusters, cost tiers) | `git grep TRAIN_HISTORY_ONLY origin/main` → absent; `PHASE7A_MEMBERSHIP_LOOKAHEAD_FIX_2026_10_23.md`; migration doc | Restore/check out `codex/laptop-migration-20261024` (per the repo's own instructions) before any work |
| H-01 | HIGH | Branch topology; `gold_validation.production_feature_columns` | No branch has all fixes. Migration branch lacks commit `2076328` (Gold validator "producer order") and `9a904ee` (hermetic Linux verification) which exist only on `phase7a-pre-lightning-hardening-20261003`; that branch lacks the Oct fixes | Real Gold may be rejected by the validator (fail-closed → training blocked) or Linux gate may not be hermetic. **Unverified on real data** | `git log LM..PL`, diff of `gold_validation.py` | Owner decision: merge/cherry-pick in a reviewed branch, then re-run Linux verification |
| H-02 | HIGH (portability) | `scripts/run_phase7a_worker.sh`, `run_phase7_worker.sh`, `rotate_phase7_run_log.sh` | Hard-coded `/home/nssharath123/.local/bin/uv`; GNU-only `/usr/bin/time -v`, `stat -c %s` | Launcher fails on RunPod (different user) and macOS; log rotation silently never rotates on macOS | File contents | Resolve `uv` from PATH, use portable size/time commands, or run stages directly |
| H-03 | HIGH | `scripts/run_phase7a_pipeline.py` (`patch.object(training, "RESEARCH_VIEWS", …)`, `phase7_experiment_specs`) vs `training.py` defaults, `runner.py`, `cli.py phase7-research --stage train` | The 48-spec/CORE-only scope is enforced by **monkey-patching** at runtime. Default `run_phase7_training` runs 58 specs × CORE+EXPANDING | Running the generic CLI/runner instead of the 7A script silently launches a different, far larger, non-canonical experiment | Source lines cited; `baseline.py` also lists both views | Make the 7A set a first-class parameter; refuse generic train stage for this run identity |
| H-04 | HIGH (performance) | `phase7/features.py`: `_cross_sectional_percentile` (×3), `_market_context`, called by `bind_fold_cross_sectional_context` | Python loop over every unique timestamp, each doing a full-array boolean scan → O(unique_timestamps × rows) (~285 k timestamps × millions of rows per horizon per fold) | Strong candidate for the documented "6h21m, 0/48" Fold-1 stall (hot function listed as UNKNOWN in handoff). **Not profiled** | Source; handoff doc 21 | Group once by sorted timestamp (np.unique+split/sort) and profile before any cold prep |
| M-01 | MEDIUM | `folds.slice_multiasset_fold` → `features.bind_fold_cross_sectional_context`; `gold._joined_gold_table` | Gold is an **inner join** with targets, and context (percentiles, `market_member_count`, means, dispersion) is recomputed from the per-horizon rows that *have a valid label*. A symbol with a data gap or delisting within `[t, t+2+h]` bars is absent from the cross-section at `t` | Features at `t` depend on **future data availability** of other symbols; context differs by horizon for the same timestamp. Small, event-driven | Code path as read; prior audit declared "PASS" without this case | Compute context before label filtering (from all feature rows) or from an availability-at-`t`-only set |
| M-02 | MEDIUM | `phase5/folds.py` & `phase7/folds.py: release_test`; `training._run_one` | Test gate only checks `bool(frozen_identity)`; `test_used_for_selection: False` and `july_2026_used: False` are **literals**, not measured | Isolation depends on code review, not enforcement | Source | Verify the identity against a registered frozen hash; compute flags from actual access |
| M-03 | MEDIUM | `environment.scientific_environment_identity`, `training._prepared_cache_identity`, `TRAINING_CRITICAL_SOURCE_FILES` | Cache/checkpoint identity binds Python **patch** version, 6 package versions, lock-file hashes and ≈50 source-file hashes | Mac-built (or any different-env) caches/checkpoints can't be reused; any bug fix invalidates completed specs | Source | Intentional for reproducibility; plan one fixed environment on RunPod and freeze source before first spec |
| M-04 | MEDIUM | `PreparedDataCache._publication_lock` | `O_EXCL` lock file stores a PID but never checks liveness | A crash/OOM (likely with large matrices) leaves `.publication.lock`; later load/publish waits 60 s then raises `TimeoutError` until manually deleted | Source | Stale-lock detection with start-time check, or use `flock` like the run lease |
| M-05 | MEDIUM | `run_lease.py` | Retained lease evidence after any hard kill requires explicit hash-bound recovery; liveness is hostname-based (`UNKNOWN_FOREIGN_HOST` after pod restart); `flock` unreliable on network filesystems | Operator friction/automation stalls on RunPod; false safety on NFS | Source | Document and rehearse recovery; keep run roots on local disk |
| M-06 | MEDIUM | `folds.slice_multiasset_fold` (`later_gaps` → `ValueError`) | A known data gap after TRAIN end for any active symbol hard-blocks the whole fold | If real Silver has post-train unusable segments for Core20 symbols, many folds cannot run without data review. **Unknown without real data** | Source + fix doc | Count gaps per fold from the real acquisition manifest before scheduling |
| M-07 | MEDIUM | `cli.py` `download`, `download-archive`, `market-data`; `README.md` L131; `phase6/config.py` | No upper date guard on download commands (can fetch August); README example downloads to `2026-08-01`; Phase 6 validator allows a cutoff up to 2026-07-09 although July is "unused" | Holdout-hygiene gaps (acquisition only; no train/eval path reads August) | grep + source | Add a global max-end guard; correct README |
| M-08 | MEDIUM (safety) | `pipeline/live_trader.py`, `pipeline/coinswitch_client.py`, `main_trader.py`, `dashboard.py` | Order-capable legacy code lives beside research code; only prose forbids running it | Accidental execution with keys could place orders | grep (`place_hft_order`) | Quarantine to a separate repo/branch or add hard guards |
| M-09 | MEDIUM | `scientific_environment_identity` | Identity omits CPU architecture/OS; LightGBM is deterministic only for the same thread count and is not bitwise-equal across arm64/x86 | Same cache id could hold different floating-point results across Mac vs RunPod | Source | Record arch/threads in identity or declare tolerance-based equivalence |
| L-01 | LOW | `research.metrics.regression_metrics` | Directional accuracy uses `sign(actual)==sign(pred)`; an exactly-zero actual (flat 5m opens, illiquid coins) always counts as a miss | Slightly understated accuracy | Source | Exclude zero actuals or report separately |
| L-02 | LOW | `training._finite`, test path | Non-finite rows are dropped silently; pre-filter counts not stored; raw and normalized specs can have different row sets | Weakens paired comparisons; hides data issues | Source | Record dropped counts per segment |
| L-03 | LOW | `phase5/calibration.fit_calibrator` | identity vs linear chosen by in-sample MAE on the same Cal-A rows | Mild bias to the linear calibrator | Source | Select on a held-out Cal-A part or use a fixed method |
| L-04 | LOW | `fit_architecture(hybrid_calibration=validation)` | H0 corrections fit on the early-stopping Validation set | H0 not independent of its stopping set (no test leakage) | Source | Document or fit on a separate slice |
| L-05 | LOW | `slice_hardened_fold` | Cal-A/Cal-B overlap check compares `[-1]`/`[0]` elements instead of max/min | Redundant safeguard weaker than it appears (purge already exact) | Source | Use max/min |
| L-06 | LOW (portability) | `fsync_*` helpers | `os.fsync` on macOS is not a full flush; Windows skips fsync | Weaker durability on Mac/Windows | Source | `F_FULLFSYNC` on macOS |
| L-07 | LOW | `registry.py`, `acquisition.py` (`assert`) | `assert` used for production invariants | Removed under `python -O` | grep | Raise explicit exceptions |
| L-08 | LOW (security) | `phase7/models.load_model`, `research/models.py`, legacy `pickle.load` | Pickle-based loading; integrity check is co-located with the artifact | Tampering undetected if both files replaced (local trust model) | grep | Sign/anchor hashes externally |
| L-09 | LOW (doc drift) | `README.md` | Examples reference July-2026 datasets/legacy Phase 3–5 flow; `main` docs describe the cache as missing | Misleads new users | Diff main vs migration | Update docs on the authoritative branch |
| L-10 | LOW (dead/dup code) | `data/inference.py` vs `pipeline/inference.py` | Near-identical, diverged signal logic | Confusion/maintenance risk | `diff` | Remove or consolidate in a separate approved change |
| I-01 | INFO | `universe` | Core20 selected at 2022-01-01 — later listings never enter CORE (representativeness limit, not leakage) | — | config | — |
| I-02 | INFO | Early stopping observer | Equivalence of observed vs unobserved fit relies on LightGBM internals | — | `models._fit` | Keep regression test |
| I-03 | INFO | Configs | `enable_expansion=true` with CORE-only run; 10 versioned baseline + 4 supervisor contract JSONs; 4 walk-forward TOMLs (legacy) | Dead/legacy config | listing | — |
| I-04 | INFO | Hard-coded flags | Holdout status payloads are constants by design (`Literal`) — strong by construction | — | `config.py` | — |
| I-05 | INFO | Prior audit | `PHASE7A_CODE_AUDIT.md` leakage verdict predates Oct fix and does not cover M-01 | — | doc | Re-audit after merge |

---

## 12. Readiness

* **SOURCE_CODE_TRAINING_READY: PARTIAL** — migration branch is substantially complete and heavily tested (per repo records), but: Mac checkout is the wrong branch (C-01); validator-order fix not on that branch (H-01); preparation stage likely too slow until profiled (H-04); no Linux gate/real-data cache equivalence has been run.
* **SCIENTIFIC_DATA_TRAINING_READY: UNKNOWN** — no Gold/Silver/cache/checkpoints/models are on this Mac. **LOCAL_STATE_MISSING, not DATA_LOST.** Per project docs Gold (7/7, 138 partitions, 50,352,548 rows, dataset `gold-phase7-0cbf2910e8d96c9d19826598`) lived on the stopped GCE VM's boot disk (`autoDelete=true`) and GCS bucket `gs://crypto-ai-data-83921`; current state of those was not checked (no cloud access attempted).
* ONE_MODEL_SOURCE_PATH_IDENTIFIED: **YES** (`phase7a.select_one_spec` + `benchmark_one_spec` / `--canary`).
* ALL_FOLD1_SOURCE_PATH_IDENTIFIED: **YES** (`scripts/run_phase7a_pipeline.py --stage train`).
* Actual training started: **NO**.

## 13. Repository integrity
No command that writes to the Mac repository was issued. Only directory listings and read-only file staging were used. Formal `git status --porcelain`, `git diff --exit-code`, `git diff --cached --exit-code` were **not executable**; indirect evidence in §1.3 indicates the tree is unchanged. No files were created in the repository.

## 14. Recommended next action
Do not run anything yet. First decide the branch strategy: restore `codex/laptop-migration-20261024` on the Mac (non-destructively, e.g. a separate clone), and decide how to bring in the two commits that only exist on `phase7a-pre-lightning-hardening-20261003`. Then, on a Linux/RunPod machine with the real Gold mounted: run the Gold validator, profile the preparation stage (H-04), and only then plan cold preparation.
