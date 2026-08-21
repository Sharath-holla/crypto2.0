# Final Phase 5 Hardening Verification

Status: **PASS**. Result version: `walkforward_v1_1`.

## Evidence preservation and retraining

The pre-hardening `local_artifacts` inventory was 964 files,
547,050,167 bytes, with tree SHA-256
`6e01b1e55db7e69b54f5d9d4289211b7ab513a00996f8eef18449fdd9cbc6e64`.
After excluding the newly created `phase5_hardening` directory, the count,
bytes, and SHA-256 are identical. Original Phase 5 remains 803 files and
296,652,515 bytes. `ORIGINAL_PHASE5_ARTIFACTS_CHANGED = FALSE`.

The hardening tree contains no model/joblib artifact. Every hardened fold
references the historical model path and SHA-256, and all 66 hashes match.
The runner imports `load_model` only; it has no LightGBM estimator fit path.
`MODELS_RETRAINED = NO`.

## Completeness and fold integrity

| Candidate | Expected | Complete | Missing | Invalid | Duplicate OOS times |
| --- | ---: | ---: | ---: | ---: | ---: |
| L0 | 17 | 17 | 0 | 0 | 0 |
| L5 | 17 | 17 | 0 | 0 | 0 |
| D0 | 16 | 16 | 0 | 0 | 0 |
| D2 | 16 | 16 | 0 | 0 | 0 |

The verifier checked all 66 hardened fold manifests, all 66 source fold
manifests, root artifact manifests, prediction/backtest/trade files, and model
hashes. Checksum or invariant failures: 0.

## Calibration and TEST isolation

Sample L0 fold 000:

```text
Cal-A: [2021-12-18T05:40:00Z, 2022-02-01T05:40:00Z)
Cal-B: [2022-02-01T05:40:00Z, 2022-03-18T05:40:00Z)
Cal-A remaining rows: 12,936
Cal-B remaining rows: 12,936
Cal-A -> Cal-B purged rows: 12
Cal-B embargoed rows: 12 (60 minutes)
calibrator: linear, fitted/selected on Cal-A only
threshold: NO_TRADE, selected on Cal-B only
```

Every fold records false for TEST use in early stopping, calibrator fit/method
selection, and threshold selection. Cal-B does not influence calibrator fit.
TEST is loaded only after the source-model/calibrator/policy identity is frozen.

## Fixed and adaptive stress

For every candidate and fold, fixed-policy 1x/1.25x/1.5x/2x trade count,
trade IDs, entry/exit timestamps, and direction are identical. Every computed
trade-identity hash matches its metric record. Fixed net PnL is monotonically
non-increasing at higher costs. Fixed and adaptive outputs have separate file
names, summary keys, and explicit stress types. `COST_STRESS_SEPARATION = PASS`.

## Holdout and immutable research inputs

```text
prospective_holdout_start: 2026-08-01T00:00:00Z
max development feature_time: 2026-07-08T23:55:00Z
max scanned feature/entry/label timestamp: 2026-07-09T00:55:00Z
rows intersecting holdout: 0
prospective_holdout_used: FALSE
```

Feature schemas, Feature V2.1, Label V1 (`1.0.0`,
`future_return_60m`), model configuration SHA-256, and all qualification gates
match Phase 5. `features changed = FALSE`, `labels changed = FALSE`,
`hyperparameters changed = FALSE`, `qualification rules changed = FALSE`.

## Resume/idempotency

The complete hardening tree contained 1,136 files and 340,921,485 bytes with
SHA-256 `466752f21dc013e7b2989356e865672ccd8cbd2e2ea90434be8ef38a2f491124`.
Both hardened commands were repeated with resume. The post-resume count, size,
and SHA-256 were identical; no duplicate, model fit, or artifact rewrite
occurred.

## Safety and architecture

No private Binance API, account, position, leverage, or order operation ran.
No ETH/altcoin model, advanced model, new feature/label, fear/sentiment API,
TP/SL engine, risk/portfolio engine, or live component was added. The future
architecture is documentation-only in `FUTURE_TRADING_SYSTEM.md`.

The machine-readable audit is:

```text
local_artifacts/phase5_hardening/walkforward_v1_1/verification_report.json
```

Champion decision: **NO QUALIFIED MODEL**. Phase 6 has not started.

Final repository checks: 164 tests passed, 0 failed, 0 skipped in 32.89s;
Ruff check passed; all 96 supported files were formatted; Python compilation
and `uv lock --check` passed.
