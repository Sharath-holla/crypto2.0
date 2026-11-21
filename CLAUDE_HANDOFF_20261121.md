# Crypto2.0 — 21 November 2026 project hold and handoff

**The owner put the project on hold on 21 November 2026 (about 05:40 UTC).** The Phase 7A 4-fold pilot is complete. **Its results are not good**, so the owner's rule applies: **do not start the full 16-fold run.** The driver holds on `OWNER_STOP_20261121.json`. Before any compute, get explicit owner approval plus a fresh cost cap and deadline (AGENTS.md). Earlier approvals never carry over. Read this file, `CLAUDE_HANDOFF_20261119.md` and `AGENTS.md` first.

## Owner goal (context)

- The owner wants Crypto2.0 to trade automatically: the model decides **take this trade or skip it**, with no manual decisions.
- This model, `architecture-G0-A6-60m-raw`, is the **first of six** planned models, so its success matters a lot.
- The model decides on **5-minute candles** and also uses **12h and 1d** context (`configs/phase7/research_v1.toml`). The `60m` in the spec name is most likely the prediction horizon; the configs list horizons of 15, 30, 60 and 120 minutes.
- The owner calls it "HFT". True microsecond HFT (order book data, colocation, C++/Rust) is a separate future project, planned once there are resources.

## Pilot status — complete

| Fold | Fold ID | Model SHA-256 | Trained |
|---|---|---|---|
| 0 | `fold-000-a0e9a4f72689` | `1562cae6…7c41` | 18 Nov |
| 5 | `fold-005-2cf830b9f251` | `c2304d64…1c76` | 20 Nov 19:32Z |
| 10 | `fold-010-01be2e390a0b` | `7b978e82…451c` | 20 Nov 20:14Z |
| 15 | `fold-015-ed49f0aadaf7` | `f9558ae0…35b4` | 21 Nov 05:15Z |

- Fold 5's `fold_id` proves the selected-fold fix (`0034184`) works end to end on Linux.
- All models are on network volume `kz9axr9t9v` (EU-SE-1, 50 GB, retained). **They are not downloaded to the Mac.**
- July 2026 is unused. The August 2026 holdout remains `LOCKED_UNUSED`.
- Nothing is running. Every Pod is `EXITED`, and only storage is billed ($0.005/h).

## Results

| Fold | Trades | Directional accuracy, LightGBM vs Ridge | Spearman IC, LightGBM vs Ridge | Beats Ridge? | Net expectancy per trade |
|---|---|---|---|---|---|
| 0 | 0 | 51.1% vs 50.4% | 0.023 vs 0.016 | yes | no trades |
| 5 | 0 | 51.6% vs 49.1% | 0.046 vs −0.006 | yes | no trades |
| 10 | 0 | 50.4% vs 50.8% | 0.013 vs 0.018 | no | no trades |
| 15 | 218 | 50.5% vs 50.6% | 0.013 vs 0.012 | marginal | **−0.146%** (1.0× cost) |

- On fold 15 the expectancy is negative at every cost stress level (1.0×, 1.25×, 1.5× and 2.0×) and under both the fixed and adaptive policies. Summed net return is −31.8% at 1.0× cost.
- The 1.0× to 2.0× expectancy slope implies a cost of about **0.14% per trade**. The gross edge is therefore about 0%: the model roughly breaks even before costs and costs make it a loser.
- On folds 0, 5 and 10 the calibrated predictions are tiny (std 1e-3, 1e-4 and 1e-5), so they never clear the cost threshold and no trade is taken.
- The frozen criteria (`docs/research/PHASE7_SUCCESS_CRITERIA_V1.md`) require at least 10 of 16 net-positive folds and at least 10 of 16 beating the baseline. The pilot has 0 of 4 net-positive, so a 16-fold run would almost certainly fail.
- These are development metrics only. Funding is not modelled, costs are static, and statistics are trade-level rather than portfolio-level.

## Recommendation (owner agreed: decide later)

1. **Do not run 16 folds yet.** It would cost about $15–20 and 12 GPU-hours to confirm a failure, and it would wear out the test periods.
2. Fix these in code on the Mac, without a GPU:
   - Use a longer horizon (2–4 hours) or a triple-barrier / take-profit-before-stop-after-fees target. Meta-labelling fits the owner's take-or-skip goal.
   - Find why predictions collapse toward zero, especially on folds 5 and 10. Check regularisation and target scale.
   - Consider adding funding rate, open interest and cross-coin features. Model funding before any live claim.
3. Re-run only the 4 pilot folds, for about $3–4.
4. Run all 16 folds only if at least 3 of 4 pilot folds are net-positive after costs. Open the August holdout once only, at the very end.
5. Later, before any real money: model funding, measure slippage, compute portfolio drawdown and Sharpe, paper trade, then go live with small size.

## Spend

- 20 Nov session: $7 cap, about $2.43 spent.
- 21 Nov session: $3 cap, about $0.86 spent.
- The wallet is **$9.447** (21 Nov 05:16Z).
- **Identified cumulative spend is about $9.56.** Carry it forward; never reset it.

## What happened 20–21 November

1. EU-SE-1 had no host from 16:56 to 18:13 on 20 Nov. The no-host retry loop (2-minute interval) got a host by itself.
2. The first fold 5 attempt failed at `memory-probe` at 18:50 with SSH exit 255 ("Connection reset by peer"). It was a network drop, not memory: 67 GB were free and RSS was 8 GB. The Pod was stopped and confirmed. The retry got a Pod in 30 s and passed all stages.
3. The owner stopped before fold 15 (20 Nov, about 20:06Z). `stop_after_fold10_20261120.sh` killed the driver after fold 10's `POD_EXITED`, during the driver's 20-second sleep before it writes state. **Fold 10 was therefore missing from `pilot-state.json` and was added by hand** on 21 Nov from `pilot.log` and the verified `train-result.json` SHA. The backup is `pilot-state.json.pre-fold10-manual-20261121.bak`. Lesson: stop the driver only after `FOLD_DONE`, not after `POD_EXITED`.
4. On 21 Nov, fold 15 got 2× A40 at $1.18/h immediately and finished in 44 minutes, ending with `PILOT_ALL_FOLDS_COMPLETE`.

## Artifacts

- Driver: `~/.crypto2-transfer/pilot_4fold_20261118.py`. It now holds on `OWNER_STOP_2026112{0,1}.json` and `OWNER_STOP_20261119.json`. Driver backups: `.pre-20261120.bak` and `.pre-20261121.bak`.
- Contracts:
  - `pilot-session-20261120.json` and `OWNER_AUTHORIZATION_20261120.json`, superseded by `OWNER_STOP_20261120.superseded-20261121.json`.
  - `pilot-session-20261121.json` and `OWNER_AUTHORIZATION_20261121.json`, superseded by `OWNER_STOP_20261121.json`.
- Loops and helpers: `run_20261120.sh`, `run_20261121.sh`, `start_pilot_20261120.py`, `start_pilot_20261121.py`, `stop_after_fold10_20261120.sh`.
- Per-fold results: `~/.crypto2-transfer/phase7-pilot-4fold-20261118/fold0*-resume-*/pipeline/train-result.json`.
- **Backup with SHA256SUMS:** `~/Crypto2Results/project-hold-20261121/`. It holds the four `train-result.json` files (fold IDs and model SHAs verified), pilot state, logs, contracts and scripts.
- Models are still only on the network volume. Before deleting the volume, download them with SHA checks; this is not automated for the network-volume path.

## To resume

1. Read this file. Get an owner decision on the fixes above. Code work needs no compute approval.
2. For any GPU run, follow the restart steps in `CLAUDE_HANDOFF_20261119.md`:
   - Fresh `pilot-session-<date>.json` and `OWNER_AUTHORIZATION_<date>.json`.
   - Move `OWNER_STOP_20261121.json` aside without deleting it.
   - Carry cumulative spend forward.
   - Verify hashes and run the 68 operator tests.
3. A changed model means a new frozen source export, kit expectations, and a fresh pilot state. Do not mix new-model folds into this pilot's `pilot-state.json`.
