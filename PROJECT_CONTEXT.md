AI AGENT / ENGINEER: READ
docs/PROJECT_HANDOFF/00_START_HERE.md
BEFORE MODIFYING OR RUNNING THIS PROJECT.

# Crypto 2.0 Project Context

- Owner: Sharath N. S.
- Status: **PROJECT HOLD**
- Current phase: **Phase 7A CORE20 PRIMARY**

## Latest local readiness — 2026-11-08

Read `docs/reviews/CRYPTO2_FINAL_MASTER_READINESS_REPORT_20261106.md` for the measured November
baseline and `docs/reviews/CRYPTO2_LOCAL_REVIEW_20261108.md` for the subsequent local review.
The master report was committed as `3ec73e3`; its verified source export is `99cf12f`, with
1,394 passing tests and passing Ruff checks. Claude's subsequent local development has finished:
see `docs/reviews/CLAUDE_PRE_RUNPOD_CODE_AND_ARCHITECTURE_REVIEW_20261108.md` (reported 1,471 passing
tests). The combined diagnostic/fit-boundary/baseline changes are being frozen and independently
verified as one source export; the earlier export does not qualify those newer changes.

Recovery, Silver/Gold validation, feature-only context sidecar qualification, local admission
guards, CPU accounting, publication/recovery tests and an exact local transfer set were completed.
The recovered canonical data root is `/Users/cortex/Crypto2Data/lightning-full/crypto2-persistent`;
Gold is no longer known only from the historical VM disk. Reuse the verified data and sidecar.

The project remains **NOT_READY_FOR_SMOKE**. Required external gates are actual Linux/x86_64
verification, target filesystem qualification, cross-host identity equality, one real prepared
cache with measured resource use and equivalent read-only reload, and a fresh owner cost/deadline
contract. The conservative admission floor is 64 GiB effective RAM, 8 effective CPUs and 150 GB
local disk. No real prepared cache or real-data model was built by the November closure.
The owner will arrange the RunPod/Linux setup later; this is not authorization to provision
compute or start training. After concurrent edits finish, freeze and test a new source export
before transfer; do not substitute the older export for the newer working tree.

## Laptop migration and later local remediation

For the latest laptop snapshot and restoration instructions, read
`docs/LAPTOP_MIGRATION_2026_10_24.md`. Restore branch `codex/laptop-migration-20261024`;
do not assume cloning `main` restores the latest local fixes. That branch preserves the existing
integration tree without launching it; standalone research still installs from the root package.

The September handoff below is historical remote evidence, not a fresh cloud verification.
October local work implemented prepared-matrix caching and hardened identities, live training
metrics, non-overlapping Cal-B selection, preflight, and TRAIN-only universe gap gating. Read
`docs/PHASE7A_MEMBERSHIP_LOOKAHEAD_FIX_2026_10_23.md` and the migration verification record.
Real-data cached/uncached equivalence, Linux verification, resource profiling, and a fresh owner
cost/deadline authorization are still required. Do not rerun already valid acquisition or Gold.

Crypto 2.0 is a production-oriented quantitative ML research system using official Binance USD-M
perpetual-futures market data. It separates immutable data, validation, causal features/targets,
point-in-time universe construction, chronological models, calibration, cost-aware `NO_TRADE`,
research economics, and future risk/execution. It is not a profitability guarantee and has no
current paper/live/order path.

## Historical remote freeze and continuing scientific state

The following cloud resource facts come from the September handoff; they are not a fresh remote
resource inspection. The November local recovery/readiness evidence above supersedes the older
claim that Gold exists only on that VM disk.

- VM `crypto-phase7` in `asia-south1-a`: **TERMINATED**, auto restart false. Keep it stopped.
- Discovery: 507/507; acquisition complete; data checkpoint valid; 60 candle checkpoints validated.
- Gold: 7/7, 138 partitions, 50,352,548 rows, dataset
  `gold-phase7-0cbf2910e8d96c9d19826598`; the recovered local copy has been validated.
- Fold 1: `STARTED_NOT_COMPLETE`, 0/48 reports, zero models. Folds complete: 0/16. Fold 2 never
  started. Qualified model: none; quality is not yet evaluable.
- July 2026 unused. August begins 2026-08-01 and is permanently `LOCKED_UNUSED`, `used=false`,
  `evaluation_authorized=false`.
- Phase 8, paper trading, risk automation, account access, and live trading have not started.
- Original blocker: `FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING`. The cache implementation now
  exists; real-data preparation/reload equivalence and external qualification remain incomplete.

The historical persistent disk was 250 GB `pd-balanced`, `READY`, and `autoDelete=true`; deleting
the VM would delete its boot-disk copy. Preserve it. GCS bucket: `gs://crypto-ai-data-83921`. Project:
`crypto-ai-trading-506300`. VM repo: `/home/nssharath123/crypto2.0`.

## Frozen science

Core20: BTCUSDT, ETHUSDT, ZRXUSDT, NEOUSDT, FLMUSDT, KNCUSDT, ONTUSDT, BLZUSDT,
HNTUSDT, UNIUSDT, TRXUSDT, KSMUSDT, COMPUSDT, IOTAUSDT, STORJUSDT, OMGUSDT,
ZECUSDT, FILUSDT, BCHUSDT, DOGEUSDT. HNT remains for survivorship protection; XPIN was not
forced.

Phase 7 uses 5m primary data, completed 12h/1d context, 54 native A6 columns (109 A6 model columns
including 22+33 HTF), `multiasset_targets_v2`, horizons 15/30/60/120m, G0/C0/P0/H0 LightGBM,
`open[i+2]`, actual `label_end_time` purge, 120-minute embargo, train-only preprocessing,
Validation/Cal-A/Cal-B/frozen TEST, and cost-aware `NO_TRADE`. Sixteen rolling folds use 24m TRAIN,
3m Validation, 3m Calibration, 3m TEST, 3m step. Phase 7A runs only CORE and 48 primary A6 specs;
EXPANDING, six A0–A5 ablations, and four HTF controls are deferred.

## Architecture and technology

Official archives/REST → immutable Bronze → quality/lifecycle Silver → registry/PIT universe →
Gold → folds/prepared matrices → G0/C0/P0/H0 → calibration/threshold → OOS/economics. Stack:
Python/uv, PyArrow/Parquet, NumPy, LightGBM, scikit-learn, joblib, Pydantic, httpx, pytest, Ruff,
Git, Bash/PowerShell, Ubuntu/GCE/persistent disk/GCS. DuckDB/pandas/neural/challenger libraries are
not Phase 7A direct dependencies.

## First future action

**DO NOT START TRAINING.** Finish the local review, reconcile concurrent edits, and freeze a new
verified source export. On a subsequently owner-authorized Linux host, verify the transferred
checkpoints/identities and run the full software/filesystem gate. Then separately authorize one
prepare-only run, measure its resource use and prove cached/uncached and read-only reload
equivalence. Only after all smoke-critical gates pass and a fresh owner cost/deadline contract is
in place may one CPU training smoke run proceed. A smoke is not approval for all 48 specifications
or all 16 folds.

Detailed entry: `docs/PROJECT_HANDOFF/00_START_HERE.md`. Resume procedure:
`docs/PROJECT_HANDOFF/29_ONE_YEAR_RESUME_RUNBOOK.md`. Exact state:
`docs/PROJECT_HANDOFF/20_CURRENT_STATE.md`.
