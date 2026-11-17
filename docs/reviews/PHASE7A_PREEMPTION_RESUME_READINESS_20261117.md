# Phase 7A preemption and recovery readiness — 17 November 2026

**READY_FOR_TRAINING_BUT_RESTART_MODEL_AFTER_PREEMPTION**

Native mid-fit continuation is **not qualified**. The implemented recovery preserves a qualified prepared cache, native partial Boosters and execution evidence, then requires fresh owner authorization to restart that one model from round zero. It does not pretend to continue the interrupted boosting trajectory. This verdict describes the implemented fallback; actual Linux/filesystem/cache/resource gates, live stop control and a fresh cost/deadline contract remain mandatory before real training.

Only tiny artificial non-market CPU fixtures, local filesystem copies and mocked provider operations ran. No Pod was created, started or restarted; no real cache was built, no real-data model fitted, and no Gold/Silver/sidecar was written. July/August were not accessed. No full grid or GPU fitting is authorized by this work.

## Wallet and provider stopping

The fixed absolute floor is **$1.00**. The configurable checkpoint-and-stop trigger defaults to **$1.75**, raised conservatively to:

```
max(configured_trigger,
    1.00 + all_in_upper_rate * reserve_seconds / 3600 + 0.25)
```

Default reserves: checkpoint grace 90 seconds, shutdown 120, billing lag 300, minimal export 30 and API latency 30: 570 seconds in total. The controller uses the higher of the approved all-in rate and account-observed spend/hour; applicable network storage must be included. Session spend is the maximum of identified Pod/network-volume billing, wallet decline, and elapsed time times the conservative rate. It also enforces the owner deadline and remaining session ceiling. This avoids adding the same charge multiple times while remaining conservative about lagging bills.

The outside-Pod Mac controller requests a checkpoint first when safe. Grace cannot exceed the remaining wallet/session/deadline headroom after shutdown reserve. Low balance near $1 or unhealthy wallet/billing/API/SSH access bypasses grace and prioritizes provider stopping. No multi-GB cache export occurs at that boundary. The last independently verified persistent snapshot remains available if a new request times out or cannot be published.

The successful graceful sequence is `RUNNING → CHECKPOINT_REQUESTED → CHECKPOINT_WRITTEN → CHECKPOINT_VERIFIED → EVIDENCE_EXPORTED → PROVIDER_STOP_REQUESTED → PROVIDER_EXITED`. Timeout/corruption/publication failures are explicit journal events, not manufactured success states. Reasons distinguish normal completion, low wallet, deadline/session budget, resource/invariant failures and owner stop. Operational wallet status includes balance, effective trigger, all-in rate, remaining safe minutes and latest persisted checkpoint; it is separate from model metrics.

Provider stopping uses the control plane and requires readback of **EXITED** plus preserved volume `kz9axr9t9v`. Killing Python, SSH or the shell is insufficient. The supervisor can retry stopping its exact previously armed Pod even after its contract expires. Strict SSH host checking, launchd supervision, caffeinate and fresh heartbeats remain required. The non-disruptive same-permission-scope probe is not an actual stop test: **live provider confirmation is still required**, and none was attempted during this task.

The floor is a conservative compute-stop policy, not an unlimited account-balance guarantee. Network-volume storage continues billing after compute stops; an extended provider/network outage or unexpectedly delayed billing can exceed assumed reserves. There is no auto-top-up, automatic deployment or automatic recovery after funding, and no deletion of the persistent volume.

## Native partial checkpoints

The callback saves every **25 completed boosting rounds**, and at the next safe callback after SIGTERM, SIGINT or an owner/controller request. Signal handlers only set a flag; no asynchronous handler performs model/filesystem operations. The original fit parameters, statistical observer and native early-stopping callback remain unchanged. Checkpoint-enabled ordinary fits reproduce the baseline fixture's predictions and native model string exactly.

Each versioned checkpoint contains `model.txt`, `model.sha256`, `checkpoint.json`, `telemetry-tail.jsonl` and `CHECKPOINT_COMPLETE`. Native [`Booster.save_model(num_iteration=-1)`](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.Booster.html) saves all completed trees, including post-best rounds; the default best-round save would lose that state. No pickle is trusted as a model artifact.

Manifest bindings include schema/time, completed/tree/best/remaining rounds, best Validation L2 and RMSE, patience, 500-round cap, parameters/seeds/thread budget, target/spec/fold/horizon/architecture, ordered features, row/cache/weight identities, Gold/sidecar and all six scientific identities, Python/LightGBM versions, logical run and execution session/Pod. Marker and file hashes must agree. Independent verification loads the native Booster and checks tree count and feature names. Inside the active fit the writer verifies hashes without constructing another predictor, preserving native CPU thread state; the external controller parses the persisted model in a separate process.

Publication writes a temporary directory, fsyncs files and directory, then renames atomically. An independently hashed add-only copy is published under:

```
/workspace/phase7a-evidence/training-checkpoints/<logical-run-id>/<execution-session-id>/iter-<round>-<uuid>/
```

Only after persistent publication does the writer acknowledge the request nonce and checkpoint SHA. The controller independently verifies that receipt. Keep the latest three verified payloads, with immutable retention audit metadata; corrupt/incomplete newer evidence does not evict an older valid fallback. The full per-session JSONL is mirrored by append offset, with a small telemetry tail in each snapshot.

Partial state is `TRAINING_PARTIAL_CHECKPOINT` / `PREEMPTED_RESTART_REQUIRED`. It never enters the completed canonical ledger, publishes calibration/TEST results, or claims a successful smoke/model. A preempted call reports zero completed specifications; canonical final publication only follows normal completion.

On the tiny fixture, saving the 251-tree baseline took **8.44–9.14 ms** across three native saves. That supports the initial 25-round interval, not a prediction of real network-volume overhead. Actual serialization/copy wall time is recorded and must be assessed during the separately approved real smoke.

## Continuation experiment and decision

Installed LightGBM **4.7.0**, CPython **3.12.16**, CPU. The harness uses separate fresh processes, native serialization and documented [`init_model`](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html), preserving prior best/patience through public callback state. It tests 1,600 artificial non-market rows, 24 columns, weighted 1,000-row TRAIN and 600-row Validation. Fixture-only minimum leaf size is 10. Production sampling/seed semantics are retained: learning rate .02, max 500, 50-round patience, seed 42, subsample .9 with frequency 1, column sample .9, deterministic CPU/column-wise mode.

| Interruption | Maximum prediction difference | Best / stop round, uninterrupted | Best / stop round, continued |
| --- | ---: | --- | --- |
| Round 125, before best | 0.0016205665978972243 | 251 / 301 | 262 / 312 |
| Round 252, after best | 0.0006251274212288223 | 251 / 301 | 268 / 318 |
| Round 276, inside patience | 0 | 251 / 301 | 251 / 301 |
| Round 300, one before stop | 0 | 251 / 301 | 251 / 301 |
| Round 499, one before cap | 0.00007523209736306352 | 500 trees | 500 trees, one additional round |

Before-best baseline Validation RMSE/MAE were **0.010473007339254133 / 0.008320619031689009**; continuation gave **0.010476234284171673 / 0.008323561502602642**. After-best continuation gave **0.010464175760951372 / 0.008319432135618029**, with changed best/stop rounds. A numerically better value does not make it the same research run. Full detailed scores, tree comparisons and timings are in [continuation_qualification.json](evidence_preemption_20261117/continuation_qualification.json).

The [`early_stopping`](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html) history was explicitly restored in the experiment, yet some trajectories and decisions differed. The precise internal cause was not proven. No tolerance was invented to qualify those discrepancies, and sampling was not altered to force equality. Therefore production **never passes `init_model`**; an attempted mid-fit resume raises `MID_FIT_RESUME_NOT_QUALIFIED`.

Independent full restarts using one versus two CPU threads had zero fixture prediction difference and the same best iteration. This is limited evidence, not universal portability proof; recovery conservatively requires the original recorded model thread budget and numerical environment. A larger host may cap its threads to that budget.

## Cache survival and exact recovery

After canonical qualification and two read-only reloads, optional cache retention occurs **before fitting**, under `/workspace/phase7a-cache/<cache-id>/`. Both actual free bytes and the provisioned 50 GB quota are checked using metadata, leaving 5 GiB reserve. Copying verifies the qualified manifest/payload hashes and publishes atomically; incomplete, corrupt, conflicting or wrong-identity copies are refused. The retained cache is not the high-churn training working directory.

Actual Phase 7A cache size and available network capacity are unknown until the separately authorized prepare gate. Thus retention is **CONDITIONAL**. If unavailable, report `MODEL_RESUME_WITH_CACHE_REPREPARATION`; a separately approved prepare must reproduce the exact identity and payload hashes before a model restart. That status never means equivalent native continuation has become qualified.

Recovery requires the same source/control/preparation/selection/Gold/sidecar, feature order, target, weights, TRAIN/Validation rows/timestamps/symbols, fold/spec, cache manifest/payloads, model configuration, versions and CPU thread budget. Mismatch refuses restart. The logical run ID survives; the new Pod has a distinct execution session. Append-only telemetry records `MODEL_RESTARTED_AFTER_PREEMPTION`, original checkpoint SHA/round and old/new session, then honest round-zero training. It never invents round 276 or emits a false `TRAINING_RESUMED`. Previous partial evidence remains distinct from the completed new attempt.

### Exact operator sequence after owner top-up

1. Confirm the old Pod is EXITED from its provider receipt. Owner adds funds manually.
2. Obtain fresh owner approval and a new qualifying Pod/session contract with current wallet, live price, maximum USD and hard UTC deadline. No automatic creation/restart is implemented. Record previous Pod and original model thread budget.
3. Use the new frozen export and separate kit; pass actual Linux/x86_64, local filesystem, resource, transferred input, six-identity and independent stop-control gates. Host/Pod/API permissions must be freshly verified.
4. Fill `OWNER_RESUME_TEMPLATE_20261118.json` only with explicit **RESUME ONE CPU SMOKE** approval. It binds `operation:RESUME_ONE_CPU_SMOKE_RESTART_FROM_ZERO`, exact logical run ID/checkpoint SHA and the new session's limits.
5. Run `runpod_restore_cache_phase7.sh --execute --approval <new-approval> --checkpoint <persistent-checkpoint-directory>`. It restores to local disk and canonically requalifies. Missing retained cache requires separate prepare approval; no silent rebuild or substitute identity.
6. Run `runpod_resume_one_smoke_phase7.sh --execute --approval <new-approval> --checkpoint <same-directory>`. This starts one new attempt at round zero, CPU only, maximum 500 rounds, same canonical Fold-0 G0/A6/60m/raw specification.
7. Only normal completion publishes a final model/result. Export evidence, signal completion, and require provider EXITED readback. No other fold/model/grid follows.

Full paths, bootstrap/source transfer and environment variables are in the [updated runbook](../runpod/RUNPOD_PHASE7A_TRAINING_RUNBOOK_20261118.md). All distributed approvals remain pending, and default shell invocations are dry runs.

## New verified source and identities

Training source is **`1b6a027b180979981eb76a4d6cbdec22510960df`**, superseding 7a64ee0 for this runtime. Subsequent documentation commits do not change that frozen training export.

Archive: `/Users/cortex/Crypto2Data/reports/phase7-preemption-20261117/crypto2-source-1b6a027b1809.tar.gz`, **5,719,805 bytes**.

SHA-256: `f1737c335d98cca4832251dc674b46fa17d6f53cfa434b42c1f0bf55a84c26d9`.

Committed inventory: **1,230 files / 25,118,775 bytes**; inventory SHA `50d2a570ac3beb1276635f642ddd72fd04608f177f2d135a45d0735bb9a0e5c6`. Including `source-freeze.json`, shipping inventory is **1,231 regular files / 25,343,270 bytes**. Exact committed Git bytes are shipped, without Git, venv, credentials, data or unrelated uncommitted work.

| Identity | New expected value |
| --- | --- |
| PREPARATION_DIGEST | `07b510b1ebacdf80e22ad142861318b1052387973260605cdea509d2a9b31581` |
| SCIENTIFIC_SOURCE_DIGEST | `9e48d9b49b5c75dcb3f7f45132d530c35a095d61a841e1346c2a61b33ce2772f` |
| EXPERIMENT_CONTROL_DIGEST | `25dd40e410ed59a835c38f33d103f3ad903bb213ede029d6121eb792c5177f9d` |
| SELECTION_PROTOCOL_DIGEST | `562dbf8203f476e446cd9968d336fa74b022924c01e5b1c34f3167c065c73826` |
| SIDECAR_SHA | `ea5f25a2a7c009c79a9ecbbe795960234b67074d36d2db7c21424724fabc2048` |
| GOLD_MANIFEST_SHA | `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711` |

Repository and exact export identities match. Preparation, selection and data/sidecar identities remain unchanged; source and experiment-control identities changed deliberately. `uv.lock` SHA remains `d0cf77d737384e0d35e6175daf74bfa9716ece8a9f246d1f107beb0a01556d85`. Current manifests and all approval templates bind the new values; operator metadata ships separately to avoid a source commit referring to its own future hash.

## Verification and practical limits

The exact Git-free export passed **1,506 tests**, zero failures/errors/skips, in 168 seconds; Ruff passed and **754 Python files** passed format checking. The additional combined checkpoint/controller/operator gate passed **75 tests** (including 40 operator cases). Evidence is in [evidence_preemption_20261117](evidence_preemption_20261117/), including XML, logs, source inventory verification, six-identity comparison and independent-process continuation measurements.

Tests cover ordinary-fit equivalence, all-tree native saves, atomic publication, forced preemption without final publication, retention/corrupt-newest fallback, network-copy failure, unsafe signal work avoidance, identity/approval/thread mismatches, qualified-cache persistence/missing/corruption/partial copy/capacity refusal, same-cache round-zero restart equality, multiple wallet/billing/deadline/API signals, bounded grace success/timeout/corruption, control-plane stop failure and EXITED readback. Provider and cross-Pod filesystem transitions are mocks/local temporary directories; they are not real RunPod results. No live provider permission, shutdown, Linux mount or real cache qualification is claimed here.

## Requested status

PASS below means the implemented local fixture/mock gate passed. Continuity FAIL rows refer to equivalent mid-fit continuation, which is deliberately disabled; they do not describe the ordinary full fit or honest round-zero restart.

| Setting | Status |
| --- | --- |
| WALLET_FLOOR | USD_1.00 |
| CHECKPOINT_STOP_TRIGGER | USD_1.75 default; dynamically raised |
| PERIODIC_MODEL_CHECKPOINT | PASS |
| PERSISTENT_CHECKPOINT | PASS — local copy/hash protocol; live mount pending |
| CACHE_RETENTION | CONDITIONAL |
| MID_FIT_RESUME | NOT_QUALIFIED |
| EARLY_STOPPING_CONTINUITY | FAIL |
| MAX_ROUND_CONTINUITY | PASS — 500 cap maintained; continuation disabled |
| OBSERVER_CONTINUITY | FAIL — equivalent continued fit not qualified |
| TELEMETRY_CONTINUITY | PASS — separate sessions, explicit restart event |
| IDENTITY_CONTINUITY | PASS |
| CROSS_POD_RESUME | FAIL — mid-fit; guarded round-zero recovery tested locally |
| LOW_WALLET_CONTROLLER | PASS — mocks |
| PROVIDER_STOP_CONFIRMATION | LIVE_TEST_REQUIRED |
| AUTO_TOPUP | DISABLED |
| AUGUST | LOCKED_UNUSED |
| FULL_GRID | NOT_AUTHORIZED |
| REAL_TRAINING | NOT_STARTED |
