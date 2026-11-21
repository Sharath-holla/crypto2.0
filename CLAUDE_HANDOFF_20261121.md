# Crypto2.0 — 21 November 2026 project hold and handoff

**The project is on hold as of 21 November 2026, about 18:45 IST.** The owner first held the project after the 4-fold pilot. Later that day the owner chose to spend the remaining balance on more folds anyway. **9 of 16 canonical folds are now trained:** 0, 1, 2, 3, 4, 5, 6, 10 and 15. Folds 7, 8, 9, 11, 12, 13 and 14 are not trained.

**The results are not good:** 1 of 9 folds is net-positive, and only barely. Do not treat this model as tradable.

- The driver holds on `OWNER_STOP_20261121b.json`.
- Before any compute, get explicit owner approval and a fresh cost cap and deadline (AGENTS.md). Earlier approvals never carry over.
- **Report times to the owner in IST (UTC+5:30).** Logs are in UTC.
- Read this file, `CLAUDE_HANDOFF_20261119.md` and `AGENTS.md` first.

## Owner goal (context)

- The owner wants Crypto2.0 to trade automatically: the model decides **take this trade or skip it**, with no manual decisions.
- This model, `architecture-G0-A6-60m-raw`, is the **first of six** planned models, so its success matters a lot.
- The model decides on **5-minute candles** and also uses **12h and 1d** context (`configs/phase7/research_v1.toml`). The `60m` in the spec name is most likely the prediction horizon; the configs list horizons of 15, 30, 60 and 120 minutes.
- The owner calls it "HFT". True microsecond HFT (order book data, colocation, C++/Rust) is a separate future project, planned once there are resources.

## Results (9 folds)

The model is LightGBM; Ridge is the simple linear baseline it is compared against.

| Fold | Trades | Directional accuracy, LightGBM vs Ridge | Spearman IC, LightGBM vs Ridge | Beats Ridge (IC) | Net expectancy per trade at 1.0× cost |
|---|---|---|---|---|---|
| 0 | 0 | 51.1% vs 50.4% | 0.023 vs 0.016 | yes | no trades |
| 1 | 146 | 49.5% vs 50.2% | 0.023 vs 0.021 | marginal | **+0.034%**; −0.004% at 1.25× cost |
| 2 | 0 | 51.4% vs 50.3% | 0.023 vs 0.008 | yes | no trades |
| 3 | 0 | 50.4% vs 49.5% | **0.066** vs −0.001 | yes | no trades |
| 4 | 0 | 51.5% vs 49.6% | 0.035 vs 0.020 | yes | no trades |
| 5 | 0 | 51.6% vs 49.1% | 0.046 vs −0.006 | yes | no trades |
| 6 | 0 | 51.6% vs 48.9% | 0.035 vs −0.018 | yes | no trades |
| 10 | 0 | 50.4% vs 50.8% | 0.013 vs 0.018 | no | no trades |
| 15 | 218 | 50.5% vs 50.6% | 0.013 vs 0.012 | marginal | **−0.146%** (summed −31.8%); negative at every cost level |

**Reading the results:**

- **There is a small, consistent signal.** LightGBM beats Ridge on IC in 8 of 9 folds.
- **Folds 0, 2, 3, 4, 5, 6 and 10 took no trades.** Their predictions are tiny (calibrated std 1e-5 to 1e-3), so they never clear the cost threshold.
- **Fold 1 is net-positive but fragile.** It turns negative at 1.25× cost.
- **Costs are about 0.14% per trade.** That figure comes from the expectancy slope between 1.0× and 2.0× cost. The gross edge is about 0%.
- **The frozen criteria are not met.** `docs/research/PHASE7_SUCCESS_CRITERIA_V1.md` requires at least 10 of 16 folds net-positive; this run has 1 of 9.
- These are development metrics only. Funding is not modelled, costs are static, and statistics are trade-level rather than portfolio-level.
- The August 2026 holdout is still `LOCKED_UNUSED`, and July 2026 is unused.

## Diagnosis: why most folds take no trades (21 Nov, 20:45 IST, from Cal-B diagnostics)

**The rule.** `economics._policy_indices` trades only when `|prediction| × 10⁴ ≥ round-trip cost (about 14 bps) + threshold`. The threshold comes from the grid 2–10 bps and is chosen on Cal-B. It needs at least 30 Cal-B trades and strictly positive Cal-B net expectancy; otherwise the result is `NO_TRADE`.

**Blockers by fold:**

| Blocker | Folds |
|---|---|
| Fewer than 30 Cal-B trades | 2, 3, 6, 10 (fold 6 had 22–24 trades at +48 to +77 bps) |
| Negative Cal-B expectancy | 0, 4, 5 |
| Traded | 1 (Cal-B +200 bps, test +3.4 bps) and 15 (Cal-B +34 bps, test −14.6 bps); Cal-B selection on about 30 trades overfits |

**The real cause is the size of the edge, not the threshold.**

- Calibration-set deciles (`calibration.reliability_after`) show that the top-decile realized return is at most about +10 bps (folds 6 and 10).
- A top-minus-bottom decile spread averages about **+2 bps** across the 9 folds, ranging from −17 to +14.
- That is roughly 7× smaller than the ~14 bps cost.
- So no threshold or rank-based policy change can make the 60m model profitable.
- The calibrator is effectively a no-op: the raw and calibrated distributions are identical.

**Training runs on CPU.** LightGBM uses about 9 minutes per fold and peaks at 11.7 GB RSS. The Mac is an M5 with 16 GB RAM, so full-size local training is too tight under the kit's 48 GB `constrained_48gb` admission. A reduced research loop (fewer symbols, one fold) could run locally for free.

**Move size vs cost** (median |log return| from local 5m Silver data, Jan 2024 to Jun 2026, no holdout data):

| Symbol | 15m | 1h | 2h | 4h | 12h | 24h |
|---|---|---|---|---|---|---|
| BTCUSDT | 11 | 21 | 30 | 43 | 83 | 126 |
| ETHUSDT | 15 | 30 | 43 | 62 | 119 | 178 |
| DOGEUSDT | 22 | 42 | 60 | 87 | 166 | 248 |
| FILUSDT | 24 | 46 | 65 | 94 | 176 | 264 |
| ZECUSDT | 29 | 57 | 80 | 115 | 209 | 314 |

All values are in bps. At the current 1h horizon, the ~14 bps cost is **25–65% of a typical move**. At 4h it is 12–32%, and at 12h it is 7–17%. A longer horizon is the cheapest lever to try first.

## Recommendation (owner: decide later)

1. Fix the model in code on the Mac, without a GPU:
   - Use a longer horizon (2–4 hours) or a triple-barrier / take-profit-before-stop-after-fees target. Meta-labelling fits the owner's take-or-skip goal.
   - Find why predictions collapse toward zero; most folds took no trades. Check regularisation, target scale and the trade threshold.
   - Consider adding funding rate, open interest and cross-coin features. Model funding before any live claim.
2. Re-run a few folds (for example 1, 3, 6 and 15) for about $4, and then all 16 only if most are net-positive after costs.
3. Open the August holdout once only, at the very end. Before any real money: measure slippage, compute portfolio drawdown and Sharpe, paper trade, then go live with small size.

## Models and evidence (all on the Mac)

**All 11 trained models are downloaded and SHA-verified** against the `model_artifact_sha256` in their own `train-result.json`. There are 11 because fold 0 and fold 4 each have two runs.

- Repo copy: `docs/reviews/evidence_pilot_4fold_20261121/models/<fold>__<pod>/` holds `model.joblib`, `model_receipt.json` and `train-result.json`. The index is `MODEL_INDEX.json`.
- Full volume evidence (360 MB): `~/Crypto2Results/volume-evidence/<pod>/<utc>/`, plus its own `MODEL_INDEX.json`. Excluded from that copy: `stage-checkpoints`, `logs` and `linux`.
- Models downloaded directly by the driver: `~/Crypto2Results/models/` for folds 2, 3 and 6. Fold 1's folder there is empty.
- Backups: `~/Crypto2Results/project-hold-20261121/` (morning hold backup).

## RunPod state

- Nothing is running; all Pods are `EXITED`.
- **Network volume `kz9axr9t9v` ("extra_blush_galliform", EU-SE-1, 50 GB) still exists.** The owner asked to delete it, but the API key returned `UNAUTHORIZED` for `deleteNetworkVolume`. **The owner must delete it in the RunPod dashboard** (Storage → that volume → Delete).
- Everything needed from the volume is on the Mac. The 11 GB of training inputs are originals in `~/Crypto2Data`.
- Restarting later in EU-SE-1 needs a new volume plus about 6 hours of upload from this Mac, or a faster path.
- The wallet was **$2.20** at about 18:30 IST. Storage costs $0.12 per day until the volume is deleted.

## Spend

| Session | Cap | Spent |
|---|---|---|
| 20 Nov | $7 | about $2.43 |
| 21 Nov morning (fold 15) | $3 | about $0.86 |
| 21 Nov full run (contracts b–e, one approval) | $8.40, hard stop 20:12 IST | about $7.21 |

**Identified cumulative spend is about $16.82** of the kit's $18 lifetime cap. Carry it forward; never reset it.

## What went wrong on 21 November, and what was fixed (driver `~/.crypto2-transfer/pilot_4fold_20261118.py`)

1. **Models live on the Pod container disk, which is wiped on stop.**
   - The driver now downloads `model.joblib` to `~/Crypto2Results/models/` before stopping, locating it by SHA-256. Benchmark mode writes under `benchmarks/…/model.joblib`, not `models/`.
   - The kit's `collect()` also mirrors evidence, models and benchmarks to `/workspace/phase7a-evidence/<pod>/<utc>/` on the volume **before** `SESSION_COMPLETE`. That is how every earlier model was recovered.
2. **Daily Silver inputs were missing for all non-pilot folds.**
   - The transfer covered fold 0 only, and supplement A covered folds 5, 10 and 15.
   - Supplement B covers folds 1–4, 6–9 and 11–14. Planner: `plan_pilot_daily_supplement_20261121.py`. Installer: `apply_pilot_daily_supplement_20261121.py`. Archive `afee4517…`, manifest `5be4e5f1…`, 21,417 files, all hash-verified against Silver manifests.
   - The driver installs both supplements. It reuses a prior PASS install receipt rather than re-verifying 21k files over the network volume (about 6 minutes).
3. **The upload throttle was too low.** scp `-l 256` (32 KB/s) timed out on supplement B; it is now `-l 2400` with a 30-minute timeout.
4. **SSH dropped repeatedly (exit 255), 5 times today.**
   - Remote commands now run detached (`setsid nohup`, `control/jobs/<name>/{script.sh,out,rc}`) with 15-second polling.
   - Evidence reads retry (`read_remote`), and the loop retries on exit 255.
5. **The controller stops the Pod the moment training completes (`NORMAL_COMPLETE`).**
   - With polling, the driver often lost the race to read the receipt.
   - The driver now treats `NORMAL_COMPLETE` after an exception as success (`MODEL_ON_VOLUME`), because the kit has already exported the evidence.
   - Fold 4 was recorded this way by hand, after it trained twice.
6. **The wallet policy projects elapsed time × $1.72/h from session start.** Long sessions therefore hit `LOW_WALLET_PREEMPTION` early.
   - The contract was re-based to the real unspent remainder (`pilot-session-20261121c/d/e.json`), keeping the same approval and hard stop.
7. **A stale `__pycache__` loaded an old driver after a same-size edit.** Delete `__pycache__` after editing.

## Artifacts

- **Driver backups:**
  - `pilot_4fold_20261118.py.pre-20261121b.bak`
  - `.pre-supplementB.bak`
  - `.pre-dlfix.bak`
  - `.pre-readretry.bak`
  - `.pre-skipreinstall.bak`
  - `.pre-20261121c.bak`
  - `.pre-volumeevidence.bak`
- **Scripts** (copied to `docs/reviews/evidence_pilot_4fold_20261121/scripts/`):
  - `run_20261121b.sh`
  - `start_pilot_20261121{b,c,d,e}.py`
  - `download_volume_models_20261121.py`
  - the supplement B planner and installer
- **Pilot state:** `pilot-state.json` lists completed folds `[0, 1, 2, 3, 4, 5, 6, 10, 15]`. Fold 4's and fold 10's entries were recorded by hand; see `recorded_manually`.

## To resume

1. Read this file. Decide the model fixes with the owner. Code work needs no compute approval.
2. Any GPU run needs:
   - a new network volume, with inputs uploaded, if `kz9axr9t9v` was deleted;
   - a fresh owner cost cap and deadline;
   - new `pilot-session-<date>.json` and `OWNER_AUTHORIZATION_<date>.json` files;
   - `OWNER_STOP_20261121b.json` moved aside without deleting it;
   - cumulative spend carried forward. The lifetime cap of $18 is nearly reached, so the owner must decide whether to raise it.
3. A changed model needs a new frozen source export, kit expectations, and a fresh state file. Do not mix it into this `pilot-state.json`.
