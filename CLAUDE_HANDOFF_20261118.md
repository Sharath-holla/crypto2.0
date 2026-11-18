# Crypto2.0 — owner stop and Claude handoff

**OWNER STOPPED ALL WORK on 18 November 2026. Do not automatically start or resume training or cloud compute.** The owner intends to discuss resuming with Claude tomorrow. Obtain a fresh explicit cost/deadline contract before any new compute. Old session approvals are not a new authorization.

## Saved state

- Verified source: `133f49ef5b2c5b31d4d6d5ffef3c5c72db5f6e70`; source archive SHA-256 `a5f1cc244b500a8bae5f7677455462a59ab0ee34ad8a7e8468c0adf83d981b57`.
- Frozen operator kit: **opsfix5**, SHA-256 `25bb60403a6c718847338c0b833a2f32f13901b978b36828a0037bb7211557e5`.
- Pilot protocol: [frozen four-fold protocol](docs/research/PHASE7A_G0_A6_60M_RAW_4FOLD_PILOT_PROTOCOL_20261118.json), committed as `0d159d1` before the formal pilot.
- Scope: one CPU LightGBM `architecture-G0-A6-60m-raw` model for each of folds **0, 5, 10, 15**, with **109 ordered float64 A6 features** and canonical point-in-time CORE20 membership. This is not the full 16-fold/48-specification study.
- Formal pilot **fold 0 trained successfully**. Folds **5, 10 and 15 have not trained**. Fold 5 stopped in preparation before its memory probe or fit.
- Keep all historical baseline models, Phase 1–6 artifacts, and the historical attempt-14 Fold-0 diagnostic model. Do not confuse the historical model with the formal pilot model.
- July 2026 remains unused; August 2026 remains `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.

## Formal fold-0 model

Model SHA-256: `1562cae6c4d9538c93627480ce2f2f983b6cfac71234cc62b19a064a9c8b7c41`.

Its completed result is saved locally at:

`/Users/cortex/.crypto2-transfer/phase7-pilot-4fold-20261118/fold000/pipeline/train-result.json`

The model and complete evidence were last verified exported to persistent RunPod volume **`kz9axr9t9v`**, under:

`/workspace/phase7a-evidence/0qkirtrlazqxdk/20261118T143835.716117Z/`

**The formal model's weights have not been downloaded to this Mac.** Local reports and its recorded hash are backed up. Existing local historical models are inventoried separately. No Pod was started just to download weights after the owner's stop instruction. Preserve the network volume and verify the model hash before future loading or copying.

## Current blocker and prepared fix

Fold 5 failed with the loader's generic `Silver checksum mismatch` error at:

`data/phase7/silver/binance/versions/silver_dataset_version=silver-cc64eaea10ff267e5ffe55c9/klines/transport=archive/market=usdm/symbol=BCHUSDT/interval=1d/date=2023-01-01/part-1672531200000-1672617600000.parquet`

That file is absent from the original Fold-0 transfer definition and local transfer folder. Its authoritative existing local file **does** match the original immutable Silver manifest: SHA-256 `86d41996bb584cef38d6f70ab07ca266486d1c1268146a6c9466d15e853e2d87`, 7,508 bytes. The loader uses the same error for absence and byte mismatch; do not claim that the authoritative data is corrupt.

The 11 GB transfer pack includes full Gold but only Fold-0 descriptor support. Later descriptor windows need additional original daily Silver files. A metadata-only plan using the frozen registry, 90-day lookback and existing manifests identified **5,335 additional files / 40,203,304 bytes** required by folds 5, 10 and 15. Every selected local file was checked against its existing Silver-manifest SHA-256. No market data was generated, altered or downloaded.

Ready locally, **NOT uploaded or applied**:

- Directory: `/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117/pilot-daily-supplement-20261118/`
- `daily-supplement.tar.gz`: **2,850,923 bytes**, SHA-256 `13a236798ea8069f5dc87b1fcd4629b9fff90a41ee9d900b8f62982f18edebcf`.
- `manifest.json`: SHA-256 `19c081c90999d35a58c1ac76d90fc3f121854a605af987e16d7b86ede3852513`.
- `summary.json` records exact windows, symbols and sizes.
- Planner: `/Users/cortex/.crypto2-transfer/plan_pilot_daily_supplement_20261118.py`.

After fresh owner authorization, transfer only this supplement into the existing `/workspace/phase7a-transfer/` structure. Reuse already matching files, preserve any conflicting bytes separately for audit, and verify expected hashes. Do not change manifests to make a mismatch pass; do not redownload Binance data, synthesize missing candles or upload the whole 58 GiB folder. **The current driver has NOT yet been extended to apply this supplement. Do not blindly rerun it.** Fix and verify input completeness before restarting the pilot. Preserve completed fold 0.

## Operational work preserved

Private driver: `/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py`.

It now has an owner-stop sentinel, unique per-fold session/control directories, direct-SSH readiness checking, ambiguous-create reconciliation, setup watchdog, guarded handoff to the original training controller, and persistent source-package reuse. IPv4 curl setup requests worked more reliably than the previous urllib transport. The original operator kit and scientific source remain unchanged.

Frozen code packages are staged on the existing volume at:

`/workspace/phase7a-source-packages/133f49ef5b2c-opsfix5/`

A setup-only watchdog protects uploads without fabricating a training-controller heartbeat. The original training controller is armed and independently verified before scientific gates. The transport-only IPv4 wrapper leaves its logic unchanged. Private setup-guard simulations passed for budget stop, API failure, valid/invalid handoff, and lower live quotes without resetting shared financial limits.

Future-fold quote refresh is operational metadata only: it narrows the per-Pod compute ceiling to the observed price and lowers the conservative all-in projection only when justified by historical/live resource quotes plus storage and a 20% margin. It preserves the original spending cap, session start, wallet origin and deadline. The stopped fold-5 contract was not mutated after its gates started.

Latest host was `k7nwrw6kfq84lk`: 1× A40, $0.59/hour, 55 decimal GB RAM, 10 nominal vCPUs; measured **8 effective CPUs, 51.2 GiB RAM, 200 GiB local disk**. Bootstrap, 62 operator tests, input/Gold gate and full Linux preflight passed; preparation then stopped on the missing later-fold Silver input. All compute is now off.

## Stop, backup and financial evidence

- Local backup: **`/Users/cortex/Crypto2Results/owner-stop-20261118/`**.
- Contains pilot state/logs/results, frozen archives, the verified supplement, operator helpers, working-tree patch, local-model hash inventory, provider stop evidence and archived disabled launch jobs. Private API and SSH keys were not copied into the backup.
- Stop evidence: `/Users/cortex/.crypto2-transfer/owner-stop-20261118/provider-state.json`.
- All Crypto2 Pods verified `EXITED`; network volume retained. Fifteen `com.crypto2.phase7*` launch jobs were unloaded and their plists preserved outside LaunchAgents.
- Owner-stop sentinel: `/Users/cortex/.crypto2-transfer/phase7-pilot-4fold-20261118/OWNER_STOP_20261118.json`. Driver entry was tested to return `OWNER_HOLD` without starting compute.
- Last observed wallet: **$13.8923332623**; account rate **$0.005/hour**, consistent with retained storage and no running compute. Billing may lag.
- Old pilot contract: $7 cap, $1 wallet floor, origin `2026-11-18T13:59:39.896928Z`, deadline `2026-11-18T18:59:39.896928Z`. **Owner stop overrides it now; it is not authorization for tomorrow. Do not reset its counters to conceal prior spending.**

Before tomorrow's restart: read this handoff and AGENTS.md, get fresh owner authorization and cost/deadline limits, fix supplement transfer/completeness, verify required gates and stopping controls, and resume at fold 5. No full 16-fold study or model redesign is authorized by this handoff.
