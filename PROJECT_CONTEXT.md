AI AGENT / ENGINEER: READ
docs/PROJECT_HANDOFF/00_START_HERE.md
BEFORE MODIFYING OR RUNNING THIS PROJECT.

# Crypto 2.0 Project Context

- Owner: Sharath N. S.
- Status: **PROJECT HOLD**
- Current phase: **Phase 7A CORE20 PRIMARY**

Crypto 2.0 is a production-oriented quantitative ML research system using official Binance USD-M
perpetual-futures market data. It separates immutable data, validation, causal features/targets,
point-in-time universe construction, chronological models, calibration, cost-aware `NO_TRADE`,
research economics, and future risk/execution. It is not a profitability guarantee and has no
current paper/live/order path.

## Exact frozen state

- VM `crypto-phase7` in `asia-south1-a`: **TERMINATED**, auto restart false. Keep it stopped.
- Discovery: 507/507; acquisition complete; data checkpoint valid; 60 candle checkpoints validated.
- Gold: 7/7, 138 partitions, 50,352,548 rows, dataset
  `gold-phase7-0cbf2910e8d96c9d19826598`, stored only on the VM boot disk.
- Fold 1: `STARTED_NOT_COMPLETE`, 0/48 reports, zero models. Folds complete: 0/16. Fold 2 never
  started. Qualified model: none; quality is not yet evaluable.
- July 2026 unused. August begins 2026-08-01 and is permanently `LOCKED_UNUSED`, `used=false`,
  `evaluation_authorized=false`.
- Phase 8, paper trading, risk automation, account access, and live trading have not started.
- Open blocker: `FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING`.

The persistent disk is 250 GB `pd-balanced`, `READY`, and `autoDelete=true`; deleting the VM would
delete the only current Gold copy. GCS bucket: `gs://crypto-ai-data-83921`. Project:
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

**DO NOT START TRAINING.** Verify Git/tag/cloud/disk/checkpoints and holdout first. Profile Gold scan,
fold filtering/context, purge/slicing, finite filtering, and Arrow→NumPy preparation. Add an atomic,
content-addressed prepared-matrix checkpoint bound to every scientific identity and prove cached/
uncached equivalence. Then, only with a fresh owner-approved cost/deadline, run one Fold 1 and
measure it before deciding on folds 2–16.

Detailed entry: `docs/PROJECT_HANDOFF/00_START_HERE.md`. Resume procedure:
`docs/PROJECT_HANDOFF/29_ONE_YEAR_RESUME_RUNBOOK.md`. Exact state:
`docs/PROJECT_HANDOFF/20_CURRENT_STATE.md`.
