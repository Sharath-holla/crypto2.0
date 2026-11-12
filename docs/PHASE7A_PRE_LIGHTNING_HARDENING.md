# Phase 7A final local pre-Lightning hardening — 2026-10-03

This is local engineering evidence, not training authorization. Project on hold;
TRAINING_READY=NO. No cloud work, actual Gold access, July/August access, GPU fit,
real preparation profile, real one-model benchmark, production training or Phase 8.
The full suite includes existing tiny synthetic CPU estimator tests, not a production fit.

## 1. Starting state

Starting HEAD: `4ef91d53f2eb6b83157394078452cf4c1a85a5fe`, local main. Verified origin:
`https://github.com/Sharath-holla/crypto2.0.git`. Tracked checkout initially clean;
unrelated untracked prior audits, patch/work directories and test evidence preserved.
Read project context/handoff, current finalization/remediation/audit and Lightning runbook.
Before-edit focused gate: 69 passed. Prior historical full gate: 696 passed,
0 failed, 5 Windows Bash skips, 0 warnings; not substituted for this turn's final gate.

Remote snapshot before push: main `28d3098a82952a3d09073e4d81b5281f856c072e`;
handoff tag object `ceea99ef20e02431beb94a41fa655dcc91e51e32`;
hold tag object `46a73e6cc55dc44a47f3a21e300cef5cc1bb7448`. Requested branch absent.

## 2. Remaining findings addressed

| Latest audit ID | Local result | Still external |
| --- | --- | --- |
| POST-NEW-02 | One-horizon/key retention retained; exact contiguous array views, all-finite Arrow reuse, unique-scope validation; stage telemetry and optional admission | Real RSS/working-set profile; early completion triage still follows fold/context load: structural bound PARTIAL |
| POST-NEW-06 | Model → receipt → bound report → checkpoint; read-only state machine; deterministic reconciliation; model-only preservation | Linux filesystem durability/process-kill qualification |
| POST-NEW-07 | Configurable output/temp filesystem floors and preconstruction cache cap; no eviction; ENOSPC tests | Real disk/cache profile, no reservation or guarantee against concurrent external consumers |
| POST-NEW-08 | Persistent OS-lock-backed single-run lease across production stages/direct training and isolated benchmark | Linux and actual persistent filesystem cross-process qualification |
| POST-NEW-09 | Explicit threshold comparison, no automatic PASS; native fitted backend plus independent PID/device observation | Actual GPU smoke, owner-approved CPU/GPU numerical/policy equivalence |

No large training/acquisition/progress split. POST-NEW-10 conservative normalized full-source
hash policy retained. Previously fixed 01/03/04/05 not reopened or overwritten.

## 3. Single-run lease

`.phase7-run-lease.guard` is a stable, never-unlinked inode: nonblocking POSIX flock,
or a Windows byte lock for local tests. Persistent `.phase7-run-lease.json` records UUID,
PID, hostname, process creation time when available, acquired time, run/scientific identity,
and production/benchmark mode. Second writer fails before mutable run work. Nested calls
are allowed only for the same PID, thread, mode and identity. Config/selector checks
precede lease creation. A benchmark has its own `benchmark-only-*` run root/lease.

Clean exit removes ownership JSON, fsyncs its directory on POSIX and releases the lock.
Kill/crash retains ownership JSON. Age never permits stealing. Recovery requires exact
reviewed ownership SHA-256 and reason under the guard, same run/mode, and proven PID death
or PID reuse. Live/unknown-start/access-denied owners are refused; foreign-host death needs
explicit owner confirmation. Prior bytes and a recovery record are archived, not discarded.
Do not delete guard files or hand-edit ownership. This is filesystem locking, not a claim
of distributed lease guarantees on unqualified network/object storage.

Read-only inspection (substitute the exact reviewed run root):

```bash
uv run python -m crypto_ai.phase7.run_lease --run-root /reviewed/run-id --mode production
```

Only after reviewing host/PID/evidence, add `--recover --expected-sha256 REVIEWED_SHA256
--reason "reviewed abandoned owner"`. Foreign-host confirmation is a separate explicit flag.
Recovery does not start or authorize training.

## 4. Publication state machine

| State | Safe action |
| --- | --- |
| NONE | No published evidence; execution still needs authorization |
| MODEL_ONLY | Preserve model/receipt; operator decision; no fit or invented report |
| MODEL_REPORT | Bound COMPLETE evidence proven; explicit checkpoint reconciliation available |
| COMPLETE | Valid inventory, checkpoint hash and scientific identities; reuse |
| CORRUPT | Preserve bytes; investigate; never silently overwrite |
| INCONSISTENT | Preserve; resolve run/spec/fold/Gold/backend/science/inventory mismatch |

The receipt binds scientific input identity, model SHA and publication envelope. Report binds
model and receipt SHA and has its own content digest. The serialized bundle carries matching
scientific input/publication identity. Checksums are integrity evidence, not cryptographic
authentication of malicious pickle files: only trusted owner-controlled artifacts may be loaded.
Hash/report identity checks precede deserialization. Frozen model/calibrator/threshold identities
and completion evidence, mode, backend, July and August flags must agree. Missing receipt in an
old orphan is not fabricated; the conservative operator path is retained. Historical artifacts
are never upgraded in place. Genuine INELIGIBLE resume handling remains separate and unchanged.

## 5. Orphan reconciliation

`crypto_ai.phase7.recovery` is read-only by default. Supply independently trusted expected
identity JSON, not an identity copied blindly from the orphan. CLI accepts exact run/checkpoint,
model/report paths, stage and mode; logical/legacy runtime mappings preserve checkpoint bytes.
Only `--reconcile-checkpoint` writes, beneath the run lease. Current reviewed source identity,
all existing completion evidence and absence of an invalid checkpoint are required. It writes
only a missing checkpoint; never predicts, loads Gold, constructs metrics, refits, replaces
model/report evidence or counts benchmark evidence as production completion.

```bash
uv run python -m crypto_ai.phase7.recovery \
  --run-root /reviewed/run-id --checkpoint-root /reviewed/checkpoints \
  --model /reviewed/model.joblib --report /reviewed/report.json \
  --stage train/CORE/fold-id/spec-id --mode production \
  --expected-identity /reviewed/independently-verified-identity.json
```

An already authorized `--resume` also reconciles a fully proven model/report orphan under
its held lease; a model-only or corrupt/inconsistent orphan blocks instead. Direct offline
utility reconciliation is the explicit non-training option. No real artifacts reconciled here.

## 6. Resource telemetry

Structured events cover PREFLIGHT, GOLD_VALIDATE, FOLD_LOAD, PREPARE, CACHE_WRITE/READ,
MODEL_FIT_START/END, CALIBRATE, THRESHOLD, TEST, MODEL_PUBLISH, REPORT_PUBLISH, CHECKPOINT.
Fields include stage/phase/timestamp, sampled RSS/observed RSS peak, available/total RAM,
cache bytes, each output/temp filesystem free bytes, backend, thread context, elapsed time
where a stage start exists, and shape/bytes at preparation/model-fit boundaries. GPU mode
samples current-PID VRAM when independently available; unavailable values stay null/statused.
Telemetry failures cannot mask a publication/ENOSPC exception. These are boundary samples,
not continuous peaks. Machine observations do not enter numerical/frozen scientific keys.

## 7. RAM admission

`PHASE7_MIN_FREE_RAM_GIB` (legacy alias `PHASE7_MIN_AVAILABLE_RAM_GB`) is optional.
Unset means report availability and continue, not "RAM sufficient." Explicit values must be
positive finite numbers; malformed/zero/negative/NaN/Inf fail closed. Available RAM strictly
below the configured floor blocks fold load/cache read/preparation/cache write/fit/publication;
exact equality is admitted. No default 32/64 GiB assertion. Preserve float64 and frozen seeds,
parameters, weights, row ordering, train/validation/CalA/CalB/TEST and H0 reuse semantics.

## 8. Disk admission

`PHASE7_MIN_FREE_DISK_GIB` (legacy `PHASE7_MIN_FREE_DISK_GB`) checks artifact, cache,
checkpoint, model, report and temporary roots (including actual publication destinations).
`PHASE7_TEMP_ROOT` otherwise defaults to cache root for admission evidence; it does not
relocate atomic same-filesystem model/report temporary files. Checks cover preconstruction,
fit/publication and checkpoint boundaries. Cache preconstruction estimate and exact final
cap remain; temporary bytes are not counted twice. No LRU/deletion/reservation. Preflight
retains a conservative 25 GiB disk screening default, not an empirical workload guarantee.
Production admission has no unconfigured free-disk guarantee. Concurrent external consumers
can still cause ENOSPC; failures propagate and cannot produce a false completed checkpoint.

## 9. Cache cleanup

`scripts.manage_phase7_cache --dry-run` reports bytes, protected/deletable reasons and estimated
reclaimable bytes; no reference roots means no proposed deletions. Supply all active production,
fold, report, checkpoint AND benchmark reference roots (repeat flags). Invalid/unreadable JSON
fails closed. Referenced IDs, symlinks/aliases and temporary/non-entry directories are protected.
Removal still requires `--offline`, exact IDs, complete reference roots and locked reference
revalidation. No cleanup or protected deletion was performed in this turn.

## 10. GPU equivalence policy

Future comparison accepts `--tolerances /reviewed/operator-approved-limits.json`. No defaults.
All limits are required for prediction-only PASS: `prediction_correlation_min`,
`mean_abs_prediction_difference_max`, `max_abs_prediction_difference_max`, `coverage_delta_max`,
`best_iteration_delta_max`, and `mae/rmse/r2/directional_accuracy/pearson_ic/spearman_ic_delta_max`
(one key per named metric). Explicit finite limits only; undefined metrics remain unverifiable.
Absent/partial limits yield REVIEW_REQUIRED (or FAIL for a supplied failing criterion), never
automatic PASS. CLI exit is nonzero for review/failure. Report includes both metrics, prediction
deltas, coverage, best iterations and decisions. No threshold/no-trade policy is invented by a
synthetic regression smoke; production policy equivalence remains REVIEW_REQUIRED even after
prediction-only PASS. Thresholds must be owner-approved, not tuned to make a device pass.

## 11. Device attestation

GPU/CUDA fit requires both native fitted-booster backend and independent live current-PID,
specific GPU UUID and positive VRAM evidence sampled during/at the fit boundary. Inventory
records GPU name/driver/ordinal where available, LightGBM version, requested/actual backend,
fit success and elapsed time. Unobservable CUDA/OpenCL runtime details are labeled unavailable,
not inferred. Requested parameter labels, GPU inventory or a successful fit alone are
insufficient. No CPU retry exists. Missing process visibility (including some container/WDDM
or non-NVIDIA OpenCL setups) fails closed; qualify instrumentation on the actual target host.
This is conservative sampled attestation, not kernel tracing or a claim of universal hardware
support. CPU unit tests never assert GPU_READY. Actual GPU smoke/equivalence NOT RUN.

Behavior references: [LightGBM parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html),
[LightGBM installation](https://lightgbm.readthedocs.io/en/stable/Installation-Guide.html),
[NVIDIA process/device observation](https://docs.nvidia.com/deploy/nvidia-smi/index.html).

## 12. Linux verification command

Future owner-approved Linux software-only entrypoint:

```bash
uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" \
  --output-root "$PWD/.pytest-linux-verification"
```

Runs complete pytest/JUnit, Ruff, format, lock, compile, diff check and verification-only
preflight. All five Bash rotation cases must execute without skip/failure/error. Removes the
cloud-training guard in test subprocesses and selects CPU there; tests use synthetic fixtures.
Preflight does not open Gold or fit a backend. Checks writable configured output paths/capacity
but does not create production roots. Configure/create approved empty output roots beforehand.
PASS is Linux software verification only, never training readiness. Non-Linux returns FAIL/NOT
RUN without executing commands. Output directory overlap with protected inputs/artifacts is
refused. Reports omit full success logs from the CLI. Actual Linux validation NOT RUN.

## 13. Gold validation command

Later only, against the approved pre-July research copy:

```bash
uv run python -m scripts.validate_phase7_gold --gold-root "$PHASE7_GOLD_ROOT"
```

No output flag means entirely read-only. Optional immutable report output must be outside Gold;
no hash skip for qualification. Expected dataset `gold-phase7-0cbf2910e8d96c9d19826598`,
138 partitions, 50,352,548 rows, ordered 109 production features/130 physical fields, native54,
Core20 including HNT, four horizons, exact types/source identities, cutoff, no August, and
manifest/partition hashes. Existing validator tests exercise synthetic partitions only.
Actual Gold byte validation NOT RUN; July/August never accessed.

## 14. Exact-one benchmark safety

Existing selector remains canonical and plan-only by default. Valid intended spec:
`architecture-G0-A6-60m-raw`, first canonical fold, CORE only. BENCHMARK_ONLY root/checkpoints,
own lease, no canonical completion counters/summary/fold qualification, no all-spec expansion.
Deferred/unknown specs and protected overlapping roots are refused. `--canary` still means
the full 48-primary Fold-1 canary and was not repurposed. No benchmark executed.

```bash
uv run python -m crypto_ai.phase7.benchmark_one_spec \
  --spec-id architecture-G0-A6-60m-raw --output-root /approved/isolated-benchmark
```

Do not add `--execute` without reviewed Linux/Gold/resource/GPU gates and separate owner
authorization plus cost/deadline contract. Training-ready is NO.

## 15. Files changed and identity discipline

New focused helpers: run_lease.py, recovery.py, resources.py, telemetry.py, device_evidence.py,
equivalence.py, verify_linux.py. Integrated training.py, artifacts.py, models.py, backend.py,
prepared_cache.py, preflight.py, gold_validation.py, run_phase7a_pipeline.py. Updated the existing
backend, cache and Gold CLIs. New synthetic hardening tests; existing tiny integration and
error-classification fixtures adapted to valid run identities/publication metadata. This report,
append-only changelog and Lightning runbook updated. No scientific configs or old artifacts edited.

Current scientific manifest intentionally has 46 files (adds recovery/device evidence); execution
manifest has 15. Implementation digests change because code changed; runtime observations do not.
Current normalized scientific digest:
`7618d4b85fea7b1971fe2c0bbe786a84335310ccb77b7fbbb932267d142d39a7`.
Execution digest: `087cbc5729f6acc7e6445de20d3ce576fe44821cca191a97f2c0e14896e40d7e`.
Historical v1.9 bytes remain SHA-256
`a22c17b164792e909f39f619c59ea40db23411c8e611398e11e28d0e98e3f493`.
Canonical configuration hash `93f987736b1a79d26b773957` and 48+6+4=58 unchanged.
No AST/comment-only identity rewriting; no artifact mutation to match new source identities.

## 16. Tests

Final local full gate: **751 passed, 0 failed, 5 Windows-only Bash skips, 0 warnings**
in 190.52 seconds. JUnit: `.pytest-pre-lightning-hardening-final-report.xml` (756 cases).
Ruff PASS; format PASS (233 files); dependency lock PASS; compile PASS; Git diff check PASS.
No failing checks represented as success.
Selective local code commit: `ed4e1ccaf88a2453a3250d38ff5ec0ece3ed7017`.
Tests/operator tools commit: `ac9e649cc393e286d3f15ad73eabfee4c52f648f`.
Documentation is committed separately; its final HEAD and push verification are reported
in the owner-facing final Git report (a commit cannot contain its own hash).
Final focused hardening + tiny integration gate: 58 passed in 40.84 seconds; preceding
integration/finalization/error gate 89 passed. CLI help/import checks passed without execution.
Tests cover real local subprocess kill at model/receipt/report/checkpoint boundaries (no fitting),
second writer rejection, stale/live/foreign owner policy, source/spec/fold/Gold/backend mismatch,
truncation/hash-before-load, explicit no-fit reconciliation, exact float64 contiguous views,
floor boundaries, synthetic ENOSPC, protected dry-run references, no-threshold GPU review,
mocked attestation, Linux command plan/Bash gate and no-Gold/no-fit preflight. Existing tiny
pipeline test verifies actual serialized synthetic estimator output is accepted by recovery.
No local Windows result is represented as Linux filesystem qualification.

## 17. Remaining external gates

Linux full gate/five Bash cases and Linux persistent-filesystem crash/concurrency qualification:
NOT RUN. Actual Gold bytes: NOT RUN. Real preparation RSS/disk/cache profile: NOT RUN. Actual
GPU smoke: NOT RUN. Owner-approved CPU/GPU prediction AND policy equivalence: NOT RUN.
Real one-model benchmark: NOT RUN. GPU_READY=NEEDS_LIGHTNING_TEST; training on hold.
Preserve discovery 507/507, acquisition, 60 candle checkpoints and Gold 7/7; validate hashes
before any recomputation. Current Fold 1 remains historically incomplete 0/48, not evidence
of bad model performance. This turn started no production Fold 1, 48-spec run or Phase 8.

## 18. Readiness

READY_FOR_LIGHTNING_LINUX_VERIFICATION: YES (tooling ready, not compute authorization).
READY_FOR_GOLD_MIGRATION: NO (owner contract and Linux/migration mapping review required).
READY_FOR_GOLD_VALIDATION: YES (tooling only; approved migrated copy required).
READY_FOR_GPU_SMOKE: YES (tooling only; qualified Linux GPU host/build required).
READY_FOR_ONE_MODEL_BENCHMARK: NO (external gates and separate authorization pending).
READY_FOR_48_MODEL_FOLD1: NO. TRAINING_READY: NO.

Next safe action: owner reviews the pushed branch and this report, then authorizes only the
Linux verification/migration phase under a fresh cost/deadline contract. Stop after local
commits, safe new-branch push and exact remote verification. No PR/merge/main/tag changes.

## 19. Lightning Linux software verification — 2026-10-03

Starting branch: `phase7a-pre-lightning-hardening-20261003`; starting HEAD:
`24dd8148af8cc1db4827dd40d2754d5ec1846ee6`. Initial Linux result at this continuation:
**754 passed / 2 failed**, with all five Bash tests passing. The previous external
verification directory was empty; this continuation's evidence is preserved separately
under `.pytest-linux-verification/`, outside production artifact roots.

### Phase 5 software lineage contract

`test_real_plans_freeze_lineage_and_use_different_family_periods` was a software planning
contract that accidentally depended on a local historical production Gold manifest. Its
failure was `FileNotFoundError`, not a scientific or numerical failure. It now uses minimal,
explicitly synthetic Parquet/manifest fixtures under `tmp_path`, with different planning
periods ending before June 2026. Only the in-memory test config's manifest path changes.
The real `read_gold_v2_1` and `walk_forward_plan` execute; no reader or planner is mocked.
All original 17/16 fold counts, feature schemas, family-period and holdout assertions remain.
The test additionally verifies the manifest's dataset identity and rejects wrong checksums,
wrong Parquet/manifest lineage, missing checksum/version, missing feature timestamps and
missing files. Existing resume identity/checksum rejection tests remain intact. These are
software fixtures, not reconstructed market data or fake production Gold.

REAL_GOLD_LINEAGE_VALIDATION = NOT RUN. This software result cannot qualify actual dataset
lineage; any future real-data validation requires separate owner authorization.

### Historical v1.9 checksum provenance and canonical identity

The earlier `a22c17b164792e909f39f619c59ea40db23411c8e611398e11e28d0e98e3f493`
claim in section 15 and the finalization/remediation documentation is superseded by this
Git-byte investigation. The historical JSON was not modified.

| Source | Exact blob SHA-256 |
| --- | --- |
| Working tree and starting HEAD | `03f74723105f3f4a389fabd0a0140bdccefa5f8e1ea9449ee71b26f5408897bb` |
| Final v1.9 source-freeze update `be3a164f3fe283885dff1e3a201dbac2dfc303af` | Same |
| Frozen handoff commit `28d3098a82952a3d09073e4d81b5281f856c072e` | Same |
| `crypto2.0-handoff-20260906` (targets that frozen commit) | Same |
| `phase7a-hold-20260906` (targets `b641e8b914a27f6b9a00ae4be7a2cbd75a02d9ed`) | Same |
| Assertion-introducing commit `0cf62a67d55b9ff51e3b34f8d2726c4e9beb58b0` | Same |
| That blob represented with CRLF | `c2e9467b3d7e4a8fe283e367442372239b2d3cc8e4277ff7d73c52d733ac1f4f` |

Every inspected frozen blob is 6,769 bytes with LF and no CRLF. All nine historical
file-changing commits were also checked: neither their exact blobs nor their CRLF
representations match `a22c17b...`. The file was first introduced at `8f040652...` and its
source hashes were amended before the final freeze; the initial revision is not the final
handoff identity. The old constant is unsupported by this Git evidence, not a demonstrated
Windows CRLF checksum. Its original provenance remains unproven; no Windows-origin claim
is inferred. Linux failed because the test compared canonical committed bytes with that
unsupported constant. No checkout drift or scientific-contract mutation was found.

The corrected test pins the immutable handoff commit (also used by baseline noninterference
tests), checks its exact Git blob SHA-256, and requires the current checkout to equal that
blob after CRLF-to-LF normalization. It never derives its expected identity from current
HEAD or mutable tags. Parameterized LF/CRLF checkout regressions prove the same identity
on either representation and prove a substantive feature-count mutation is rejected.
Production source identity already normalizes CRLF to LF; historical identity now remains
anchored to exact immutable Git bytes. No production hashing behavior changed.

### Review of the two preceding Linux test fixes

- Rotation failure injection previously replaced only `gzip`, while Lightning has `pigz`
  and the script prefers it. Intercepting both compressors retains the original assertion
  that a failed compression restores the exact live log and leaves no archive.
- CPU-budget testing requested eight threads without controlling detected CPU count;
  this Studio has four CPUs. Mocking eight CPUs in that unit test retains the two-threads
  per model and no-oversubscription assertions. Production resource admission is unchanged.

### Final Linux gate

Ubuntu 24.04.5, kernel `6.8.0-1070-gcp`, Python 3.14.5, four logical CPUs.
The locked dev extra is enabled with `UV_EXTRA=dev` for the gate and its child commands;
required output directories exist. No resource floors were lowered.

- Targeted software/lineage/freeze/noninterference/rotation/resource checks: **102 passed**;
  nine GPU/device cases excluded from that focused command.
- Full pytest: **764 passed, 0 failed, 0 skipped, 0 warnings**, 111.19 seconds.
- Bash/Linux log rotation: **5/5 passed**.
- Ruff, format (233 files), `uv lock --check`, compileall and `git diff --check`: **PASS**.
- Run lease, persistent-filesystem process-kill/publication/recovery and resource telemetry:
  **PASS**, using synthetic fixtures. No production artifacts were reconciled.
- Verification-only preflight: **PASS**; Gold manifest, Gold byte report and backend smoke
  remain null. CPU resource telemetry emitted successfully.

Full report: `.pytest-linux-verification/software-gate-e01e5a0261ff4ed1a7fd060cc483fb9f/verification-result.json`;
JUnit is alongside it. Detailed checksum comparison: `.pytest-linux-verification/baseline-provenance.json`.
Evidence is local and intentionally excluded from the commit.

Only tests and this document changed. All `src/`, scientific configs, historical v1.9 JSON,
data/artifacts and `uv.lock` remain unchanged. Gold: **NOT ACCESSED** in this continuation;
GPU: **NOT RUN**; production training/Fold 1/48 specs: **NOT RUN**. The full software suite's
existing tiny synthetic CPU estimator and mocked backend tests do not qualify GPU or
production training. July remains unused; August remains `LOCKED_UNUSED`, used=false,
evaluation_authorized=false.

LINUX_VERIFICATION: **PASS**. READY_FOR_GOLD_MIGRATION: **NO** until a separately approved
migration scope, complete state/path mapping and fresh resource contract are reviewed.
TRAINING_READY: **NO**. No main merge, force push or tag changes are authorized or performed.
