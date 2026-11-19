# Crypto2.0 — 19 November 2026 stop and handoff

**The owner stopped all work on 19 November 2026 (about 16:30 UTC) and plans to restart training tomorrow.** Do not start compute without a fresh owner cost/deadline contract. The driver holds on `OWNER_STOP_20261119.json`. Read this file, `CLAUDE_HANDOFF_20261118.md` and `AGENTS.md` first.

## Status

- Pilot scope is unchanged: one `architecture-G0-A6-60m-raw` model each for folds 0, 5, 10 and 15. Fold 0 is complete and preserved; its model SHA-256 is `1562cae6…7c41` (see the 18 Nov handoff).
- **Folds 5, 10 and 15 have not trained.** No new model exists.
- July 2026 is unused. August 2026 remains `LOCKED_UNUSED`.
- Nothing is running. Every Pod is `EXITED`. Network volume `kz9axr9t9v` (EU-SE-1, 50 GB) is retained. No other volume was created.
- At 16:26 UTC the wallet was $12.894 at $0.005/hour (storage only). Today cost about **$0.90**, measured as the wallet decline from $13.790. Billing may lag.

## What happened today

1. **The missing daily Silver inputs are fixed.** `apply_pilot_daily_supplement_20261119.py` is an add-only, hash-verified install. It placed 5,335 files on the volume under `/workspace/phase7a-transfer` with no conflicts and changed no manifest. They are now persistent, and a rerun reuses them. Fold 5 passed verify-transfer and preflight with them.
2. **The training code trained only fold 0.** Commit 133f49e had added `--fold-index`, but `run_phase7_training` still required the first fold in two guards and trained `folds[0]`. This is fixed in **`0034184`**. Exactly the selected canonical fold is trained, Fold 0 behaves the same as before, and an unknown fold ID is refused. Features, targets, model parameters and fold dates are unchanged. 1,540 tests pass (3 new) in the repo and again in the exported tree.
3. **New frozen source export `0034184cdf9f`.** Archive `ce85ab27…aa5b`, 1,319 files, inventory `aedcff91…`. Only `SCIENTIFIC_SOURCE_DIGEST` changes (`e05c9731` → `9569101c`); the other five identities are identical. The identity method reproduces `e05c9731` on the old 133f49e export. Kit expectations are in commit `1fdc8d0`.
4. **The heartbeat write raced with stage reads.** The controller's `cat > stop-controller.json` truncation was read once as empty, and preflight failed with "Expecting value". It now writes a `.tmp` file and renames it (**`0d8f37e`**).
5. **The Pod-local placement option failed on upload speed.** It was owner-approved and is in commit **`9e3c77c`**, kit opsfix8. A Pod in EU-RO-1, EU-CZ-1 or US-NC-1 keeps its inputs on its own container disk, and the controller downloads evidence before stopping it. An RTX PRO 4500 Pod was acquired, but the Mac uploaded at only about 0.5 MB/s (11 GB would take about 6 hours), so it was stopped after 3 minutes. This placement is **not usable from this Mac**. Its inputs need a network volume in that region, which the owner has to create because the assistant's permission check blocks volume creation. The EU-SE-1 path is unchanged.
6. EU-SE-1 capacity was very tight: no host between 13:30–14:03, 15:05–15:35 and from 16:12 onward. Restarting `5c25e572o5gohc` was refused with HTTP 400.

## Current artifacts

- Driver: `~/.crypto2-transfer/pilot_4fold_20261118.py`. It now uses the **EU-SE-1 network volume**, kit **opsfix8** (`2b29e638…4fc7`, 68 operator tests), source `0034184cdf9f`, and `REUSE_POD_ID = None`. A refused restart never falls back to creating a Pod while reuse is set.
- Kit dirs: `~/.crypto2-transfer/operator-opsfix{6,7,8}/`. Archives and the source package are in `~/Crypto2Data/reports/phase7-constrained-20261117/`.
- Persistent on the volume: `/workspace/phase7a-source-packages/0034184cdf9f-opsfix{6,7}` and the daily supplement. The opsfix8 package will stage on first use.
- Contracts: `pilot-session-20261119.json` and `pilot-session-20261119b.json`, both expired. Authorizations for today are superseded by `OWNER_STOP_20261119.json`.
- Backup with SHA256SUMS: `~/Crypto2Results/owner-stop-20261119/`. It holds scripts, packages, all pilot state and logs, and four disabled launch-job plists. Private keys were not copied.

## To restart tomorrow

1. Get a fresh owner cost cap and deadline. Write a new `pilot-session-<date>.json` and `OWNER_AUTHORIZATION_<date>.json`, then point `SESSION_PATH`, `AUTHORIZATION_PATH` and `AUTHORIZATION_NOTE` at them. Move `OWNER_STOP_20261119.json` aside only after authorization; do not delete it. Do not reset cumulative spend: `identified_cumulative_usd_at_start` should be about **6.11**, which is 5.21 plus today's $0.90.
2. Verify the source, kit and supplement hashes. Run the 68 operator tests.
3. Run the driver, preferably with the no-host retry loop (see `run_after_4h_20261119.sh` for the pattern). It resumes at fold 5. The first fold to train will prove the selected-fold fix end to end on Linux; check `train-result.json` for `fold_id == fold-005-2cf830b9f251`.
4. Expect about 35 minutes of gates per fold before fitting. Preflight takes about 9.5 minutes and verify-transfer about 6.
5. After training, download the models to the Mac with SHA checks. This is still not automated for the network-volume path.
