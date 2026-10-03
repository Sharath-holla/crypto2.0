# Crypto 2.0 — Pre-Lightning Finalization

Date: 2026-10-03. Starting HEAD: `2dcf12bb2b7bdc8ec089d3248bbc157a9a9ef2a8`, branch `main`.
Focused local remediation only. No reset, baseline-tag change, cloud access, migration,
production fit, real-data benchmark, GPU benchmark, holdout access or push.

## 1. Spec-count investigation

Traced `configs/phase7/research_core20_primary_v1.toml` → `load_phase7_config` →
`training.phase7_experiment_specs` → Phase 7A `primary_specs` → CORE runner.
Canonical configuration hash remains `93f987736b1a79d26b773957`; source Phase 7
configuration remains `cc550337f1f4ee4654124bf6`. Both G0 control switches are enabled.
The pre-edit generator and runner already produced **48**, not 40. The pre-edit
targeted gate passed 48 tests in 9.98 seconds; existing count tests asserted 48.

## 2. Canonical count and exact formula

EXPECTED_COUNT_FORMULA = 4 horizons × 2 targets × 6 variants = 48.
ACTUAL_GENERATED_COUNT = 48.
Documented count = 48. Missing/extra primary specifications = 0.

Horizons: 15/30/60/120 minutes. Targets: raw/volatility_normalized.
For every horizon/target pair the six variants are:

| Variant | Symbol-balanced | Explicit symbol ID |
| --- | --- | --- |
| G0 | true | false |
| C0 | true | false |
| P0 | false | false |
| H0 | true | false |
| G0 symbol-ID | true | true |
| G0 unbalanced | false | false |

Equivalently: base architectures 4 × 4 × 2 = 32, plus 8 symbol-ID and
8 unbalanced G0 controls = 48. Primary G0 totals 24; C0/P0/H0 each total 8.
Deferred A0–A5 ablations add 6; deferred HTF controls add 4; total generator count = 58.
EXPANDING is deferred for Phase 7A, not another primary-count multiplier.

## 3. Complete machine-verifiable generated table

Generated directly from the unchanged canonical config and approved enumerator.
Reproduce without training:

```bash
uv run python -m crypto_ai.phase7.benchmark_one_spec --enumerate
```

JSON prints all fields below and counts PRIMARY_A6=48, DEFERRED_ABLATIONS=6,
DEFERRED_HTF=4, TOTAL=58. Deferred rows are listed for audit, not selected for training.

| spec_id | Architecture | Horizon (min) | Target | Balance | Symbol ID | Feature group | View | Classification |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| architecture-G0-A6-15m-raw | G0 | 15 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-15m-raw | C0 | 15 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-15m-raw | P0 | 15 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-15m-raw | H0 | 15 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-15m-raw | G0 | 15 | raw | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-15m-raw | G0 | 15 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-15m-volatility_normalized | G0 | 15 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-15m-volatility_normalized | C0 | 15 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-15m-volatility_normalized | P0 | 15 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-15m-volatility_normalized | H0 | 15 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-15m-volatility_normalized | G0 | 15 | volatility_normalized | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-15m-volatility_normalized | G0 | 15 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-30m-raw | G0 | 30 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-30m-raw | C0 | 30 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-30m-raw | P0 | 30 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-30m-raw | H0 | 30 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-30m-raw | G0 | 30 | raw | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-30m-raw | G0 | 30 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-30m-volatility_normalized | G0 | 30 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-30m-volatility_normalized | C0 | 30 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-30m-volatility_normalized | P0 | 30 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-30m-volatility_normalized | H0 | 30 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-30m-volatility_normalized | G0 | 30 | volatility_normalized | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-30m-volatility_normalized | G0 | 30 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-60m-raw | G0 | 60 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-60m-raw | C0 | 60 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-60m-raw | P0 | 60 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-60m-raw | H0 | 60 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-60m-raw | G0 | 60 | raw | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-60m-raw | G0 | 60 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-60m-volatility_normalized | G0 | 60 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-60m-volatility_normalized | C0 | 60 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-60m-volatility_normalized | P0 | 60 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-60m-volatility_normalized | H0 | 60 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-60m-volatility_normalized | G0 | 60 | volatility_normalized | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-60m-volatility_normalized | G0 | 60 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-120m-raw | G0 | 120 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-120m-raw | C0 | 120 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-120m-raw | P0 | 120 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-120m-raw | H0 | 120 | raw | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-120m-raw | G0 | 120 | raw | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-120m-raw | G0 | 120 | raw | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-A6-120m-volatility_normalized | G0 | 120 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-C0-A6-120m-volatility_normalized | C0 | 120 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-P0-A6-120m-volatility_normalized | P0 | 120 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| architecture-H0-A6-120m-volatility_normalized | H0 | 120 | volatility_normalized | true | false | A6 | CORE | PRIMARY_A6 |
| architecture-G0-symbol-id-A6-120m-volatility_normalized | G0 | 120 | volatility_normalized | true | true | A6 | CORE | PRIMARY_A6 |
| architecture-G0-unbalanced-A6-120m-volatility_normalized | G0 | 120 | volatility_normalized | false | false | A6 | CORE | PRIMARY_A6 |
| feature-ablation-G0-A0-60m-raw | G0 | 60 | raw | true | false | A0 | CORE | DEFERRED_ABLATIONS |
| feature-ablation-G0-A1-60m-raw | G0 | 60 | raw | true | false | A1 | CORE | DEFERRED_ABLATIONS |
| feature-ablation-G0-A2-60m-raw | G0 | 60 | raw | true | false | A2 | CORE | DEFERRED_ABLATIONS |
| feature-ablation-G0-A3-60m-raw | G0 | 60 | raw | true | false | A3 | CORE | DEFERRED_ABLATIONS |
| feature-ablation-G0-A4-60m-raw | G0 | 60 | raw | true | false | A4 | CORE | DEFERRED_ABLATIONS |
| feature-ablation-G0-A5-60m-raw | G0 | 60 | raw | true | false | A5 | CORE | DEFERRED_ABLATIONS |
| htf-control-G0-BASE-60m-raw | G0 | 60 | raw | true | false | BASE | CORE | DEFERRED_HTF |
| htf-control-G0-BASE_PLUS_12H-60m-raw | G0 | 60 | raw | true | false | BASE_PLUS_12H | CORE | DEFERRED_HTF |
| htf-control-G0-BASE_PLUS_1D-60m-raw | G0 | 60 | raw | true | false | BASE_PLUS_1D | CORE | DEFERRED_HTF |
| htf-control-G0-BASE_PLUS_12H_1D-60m-raw | G0 | 60 | raw | true | false | BASE_PLUS_12H_1D | CORE | DEFERRED_HTF |

## 4. Historical origin of the discrepancy

`git log -S'48' -- scripts/run_phase7a_pipeline.py` identifies `bee3771`,
the original cost-capped Core20 runner. `git show bee3771:scripts/run_phase7a_pipeline.py`
already filters A6 and asserts 48. `git log -G'primary.*48' -- docs scripts`
also identifies hold commit `b641e8b` and handoff commit `3cea3b9`.
`git blame` on `docs/PROJECT_HANDOFF/11_PHASE7A_EXPERIMENT.md:15` attributes
the explicit 4 × 2 × 6 formula to `3cea3b9`. The hold/handoff retain 0/48 reports.

A. Original approved expectation: 48. B. No reviewed history evidence of intentional 40.
C. No eight-spec deferral. D. No eight-spec drop. E. No missing generator variant.
F. The quoted 40 claim is stale/incorrect; current source and handoff agree.
G. Existing tests already assert 48; new tests additionally assert every ID/combination.

The exact human arithmetic behind the stale claim cannot be proved. Disabling either
G0-control family would yield 40, but neither is disabled. This observation is not
evidence that one particular family was historically forgotten. The latest fresh
post-remediation audit already corrected the draft's 40 claim.

## 5. Exact resolution / no hidden expansion

Do not modify TOML, features, targets, fold boundaries, model hyperparameters or
scientific variant generation. Move the small canonical selection helper into
`crypto_ai.phase7.phase7a`; fail closed on non-48 count, duplicate IDs, missing
variant tuples or deferred control leakage. The preserved Phase 7A dispatcher imports
that helper. Ordinary Phase 7A remains 48 CORE specs; generic Phase 7 enumeration remains 58.
No artificial eight-spec expansion was made.

## 6. Tests and verification

New finalization tests cover all 48 canonical IDs and exact per-horizon/target variants,
58 unique generated IDs and classifications; unknown/deferred benchmark rejection;
isolated one-spec planning/accounting; direct/repository-module/installed-module startup;
same-object rebuild and runner-to-fit sentinel integration; float64 equivalence;
capacity boundaries/protected evidence/no temporary construction on rejection;
causal descriptor changes/future exclusion; model/report corruption;
HTF/helper/target/schema mutations; historical/current identity separation;
weak-reference release of prior horizon payloads; stale native-only Gold PASS rejection;
fsync ordering and publication failure. Existing tiny producer/model integration now
verifies estimator/report checksums and scientific input binding, plus injected model/report
publication failures. All market data in these checks are existing synthetic unit fixtures,
not real research data or a real one-model benchmark.

Pre-edit focused gate: 48 passed / 0 failed / 0 skipped.
Intermediate focused gates: 55 passed; then 32 passed including structural/fault tests.
Final full pytest: **696 passed / 0 failed / 5 Windows-only skips / 0 warnings**
in 335.98 seconds. JUnit evidence: local `.pytest-pre-lightning-final-report.xml`;
fresh temporary root `.pytest-pre-lightning-final-gate` (not committed).
Ruff: PASS. Format: PASS (225 Python files). `uv lock --check`: PASS.
`uv run python -m compileall -q src/crypto_ai scripts tests`: PASS.
`git diff --check`: PASS. No separately configured mypy gate exists.

The prior full-suite baseline of 665 passed / 0 failed / 5 skipped / 0 warnings
was independently measured during the immediately preceding fresh audit (178.53 seconds).
It is historical baseline evidence, not this turn's pre-edit full rerun.
Tests that set the cloud guard do so only in mocked/synthetic orchestration fixtures;
they do not grant or perform a production execution.

## 7. Historical freeze versus current scientific identity

HISTORICAL_BASELINE_IDENTITY: `phase7_scientific_baseline_v1_9.json` is preserved
byte-for-byte; SHA-256:
`a22c17b164792e909f39f619c59ea40db23411c8e611398e11e28d0e98e3f493`.
Its Git-anchored baseline tests remain active. It verifies historical science and must
not be rewritten to describe the remediated runtime.

CURRENT_REMEDIATION_SCIENTIFIC_IDENTITY: `phase7_scientific_source_manifest_v2`,
now 44 scientific files (previously 42), including new production selection/benchmark
code and existing backend/cache/Gold validator. Current digest:
`b4672a9c338bd13c6981538c291cc429bfa4636959f741d30ba94b50157c76d2`.
Operational source manifest has 10 files, including the production Lightning launcher;
digest `49da6227a97c8c31b1c7baf196e04c45ca67a77a1dea551b3e78ddadf959c6f1`.

Current cache/model/stage resume uses current scientific identity; old freeze evidence
does not authorize changed-runtime reuse. Both remain independently verified.
Approved code remediation intentionally changes the current digest; old caches/models
must fail compatibility rather than silently inherit trust. Source hashing remains
conservative: comments affect scientific hashes, paths and LF/CRLF normalization do not.
No historical Phase 5/6 or completed Phase 7A data artifacts were modified.

## 8. Cache capacity and per-filesystem admission

The draft's “projected=current omits incoming” diagnosis was NOT_REPRODUCIBLE:
the previous final check's current usage already included the temporary entry.
The real confirmed defect was checking only after construction and inspecting only
one output filesystem.

Before making a temporary directory, measure Arrow IPC size with a mock output stream
(no second serialized data buffer), count matrix and Unicode symbol bytes, reserve 64 KiB
for headers/manifest, and require current + incoming_estimate ≤ configured cap and
enough free cache-filesystem space. This is conservative admission, not a strict
upper bound on arbitrary metadata or concurrent disk consumption.
Under the publication lock, use exact temporary bytes:
(current including temporary − incoming) + incoming. Equality is allowed; excess fails.
Protected, temporary, old and quarantine bytes remain charged. Rebuild replacement may
temporarily require both generations. No automatic LRU or deletion of protected entries.

Preflight now requires positive finite floors and inspects data-independent output
filesystems for artifact/cache/checkpoint/model/report roots. These checks do not
reserve storage against other processes; Linux ENOSPC/process-kill qualification remains pending.

## 9. Lightning import/startup path

Production launcher is `crypto_ai.phase7.lightning`; the old script is a compatibility shim.
It imports production package code rather than `scripts.run_phase7a_pipeline`.
The tiny production dispatcher resolves the preserved runner by its reviewed file path.

Verified locally: absolute direct script from a temporary cwd, `-m scripts.run_phase7a_lightning`
from repo root, and `-m crypto_ai.phase7.lightning` from a temporary cwd, all with `--help`.
No training/preflight smoke occurs for help. Install the locked project/editable environment;
a standalone wheel without the reviewed repository/configs/source artifacts is insufficient.
Use the reviewed repo as working directory for relative configuration paths.
`PHASE7_REPOSITORY_ROOT` can explicitly locate that reviewed checkout; never point it
at different unverified code. No Linux execution is claimed by Windows startup tests.
Normal training still requires explicit runtime paths/backend/cache mode and passing preflight.

## 10. Exactly-one canonical benchmark entrypoint

`python -m crypto_ai.phase7.benchmark_one_spec` defaults to a plan-only JSON operation.
It requires unchanged canonical configuration, an exact primary spec ID, and an isolated
output root outside protected production/input roots. Exactly first canonical fold and
CORE view only. Unknown/deferred/ablation/HTF IDs fail.

Example **plan only**, not an executed fit:

```bash
uv run python -m crypto_ai.phase7.benchmark_one_spec \
  --spec-id architecture-G0-A6-60m-raw \
  --output-root /persistent/crypto2-benchmark-isolated
```

Only a later explicit `--execute` under separately authorized owner cost/deadline
contract may run. That path requires cloud guard, existing validated registry/universe/data/Gold
checkpoints, full Gold byte validation and passing preflight. It never calls canonical
run initialization or declares a primary training stage complete.

Artifacts/checkpoint scientific identity carry BENCHMARK_ONLY; separate run identity/root,
model/report directories and benchmark_summary.json. Canonical completion flags are false,
production fold_count/completed_reports remain zero, and production fold completion is not called.
Runtime model/report-root overrides cannot redirect benchmark models into production.
Prepared entries may reuse the independently validated scientific cache (not a completion marker).
One specification can include multiple estimators for C0/P0/H0; the illustrated G0 spec is
the intended single global estimator benchmark. Ordinary `--canary` still means all 48 Fold-1
specifications, not one model. No real benchmark was executed.

## 11. Rebuild mode status — CONFIRMED, FIXED

Previously rebuild lookup always missed, including immediately after a successful write.
New semantics: build → publish → validate → `open_published` → return usable entry.
Lookup policy remains “rebuild”; only explicit post-publication validation bypasses the forced miss.
Tests prove same-object roundtrip and synthetic runner arrival at the fit sentinel.

## 12. Memory-retention status — CONFIRMED, PARTIALLY_FIXED

Remove eager cache preload and all-four-horizon tables/slices. Load the current key lazily;
retain at most one horizon slice and one prepared cache key; release prior prepared
payload/reusable models at target/horizon/view change and fold end. Durable disk cache remains.
Weak-reference tests prove previous horizon Arrow payload release before the next spec.

Working-set retention: PARTIALLY_BOUNDED. Payload cardinality is bounded, but full per-payload
bytes, finite-filter copies, Arrow/memmap pages, symbol-ID augmentation, LightGBM internals and
parallel estimator allocations are not yet measured/capped. A completed-checkpoint resume still
needs its current fold/context/cache identity before triage; this is not a zero-scan shortcut.
Production peak RSS, exact real-fold cache/uncached equivalence and target-host resource
admission remain mandatory before fits. Do not equate structural release with a proven RAM limit.

## 13. Descriptor identity — CONFIRMED, FIXED

Hash all fields of canonical latest descriptor records known at TRAIN end, sorted by symbol;
exclude later as-of records. Bind causal descriptor digest to cache and model/checkpoint identities.
Model identity also binds resulting cluster/tier/age context. Serialized model metadata includes
scientific_input_identity before calibration/test freezing. Descriptor numerical changes now
invalidate reuse even if membership remains the same. No descriptor selection/clustering
algorithm or eligibility criterion changed.

## 14. Orphan model/report integrity — CONFIRMED, FIXED

Publish model first, then put independent model SHA-256 and report content identity into report.
Validate expected scientific/spec/Gold/config/fold/backend/descriptor identity and both content
bindings before joblib load; after load require serialized scientific_input_identity equality
and existing frozen schema/model/calibrator/threshold checks. G0/H0 restore uses the same binding.
Pre-binding reports fail closed rather than being silently grandfathered.
Hashes are integrity anchors, not cryptographic authorization: roots must remain trusted.

POST-NEW-06 publication is PARTIALLY_FIXED: file fsync before replace, POSIX directory fsync
after replace, then model → bound report → checkpoint order. Synthetic fault tests prove no
COMPLETE report without model when model/report publication fails. Windows directory fsync
is intentionally unsupported. There is no shared multi-file transaction or automatic recovery
for a model-only orphan: preserve/reconcile it explicitly; do not overwrite or refit into its
immutable path. Linux power-loss/process-kill/fault-state qualification is still pending.

## 15. Complete production Gold schema — CONFIRMED, FIXED

Derive from checked-in producer catalogs, not the supplied manifest: 54 native + 22 completed
12h + 33 completed 1d = 109 features. Producer order is native→12h→1d; A6 model order is
independently derived via the established ablation catalog (do not confuse the two orders).
Require exact feature inventory/order and derived A6 group; reject extra/missing physical fields.

Physical Parquet schema: 130 columns = 109 float64 features + 3 float64 cross-sectional source
helpers + 7 float64 target/scale/excursion fields + 6 strings + 4 UTC microsecond timestamps
+ 1 int64 horizon. Partition directories carry symbol/year; symbol also exists physically,
year does not. All canonical physical types are validated; existing metadata values/versions,
membership/scope, time/entry/label constraints and holdout flags remain checked.
HTF and helper Inf/NaN audits are included. Preflight rejects old native-only PASS reports.
`listing_age_days` and `history_length_days` remain intentionally retained.
Actual Gold byte validation: NOT RUN. Synthetic self-consistent mutations fail even with
updated partition checksums; this does not assert actual persisted Gold is corrupt or valid.

## 16. Finding crosswalk and remaining blockers

IDs refer to the latest fresh audit's final findings table, not an earlier draft numbering.

| ID | Finding | Evidence / remediation | Tests | Status |
| --- | --- | --- | --- | --- |
| POST-NEW-01 HIGH | Rebuild post-write miss | Separate open_published from rebuild lookup | Roundtrip + runner sentinel | RESOLVED |
| POST-NEW-02 HIGH | Eager horizon/cache retention, expensive resume | One-key/horizon lazy retention; real profile and early triage still pending | Prior-horizon weakref release + isolated runner | UNRESOLVED (PARTIALLY_FIXED) |
| POST-NEW-03 HIGH | Descriptor omission | Causal descriptor and fold-context binding | Changed numerical descriptors/future exclusion; source identity | RESOLVED |
| POST-NEW-04 HIGH | Orphan estimator not independently bound | Pre-load SHA/report/science checks + serialized input identity | Corruption/mismatch + actual tiny model roundtrip | RESOLVED |
| POST-NEW-05 HIGH | Native-only Gold validation | Derived full 109/130 contract and strict preflight evidence | Seven schema mutations + stale PASS rejection | RESOLVED |
| POST-NEW-06 MEDIUM | Publication order/durability/recovery | Model first, fsync, bound report; multi-file recovery incomplete | Model/report failure + replace/fsync ordering | UNRESOLVED (PARTIALLY_FIXED) |
| POST-NEW-07 MEDIUM | Late cap/per-filesystem admission | Estimate before build + exact final check + finite mount floors | Capacity/protected/temp + runtime trust tests | PARTIALLY_FIXED; Linux/resource qualification pending |
| POST-NEW-08 MEDIUM | Conflicting process publication race | No new run lease in this focused scope; single process only | Existing cache lock tests do not qualify all artifacts | UNRESOLVED; before multi-process/48-spec production |
| POST-NEW-09 MEDIUM | GPU computation PASS is not equivalence | No tolerances/device attestation changed or approved | No GPU benchmark run | UNRESOLVED; before GPU qualification |
| POST-NEW-10 LOW | Comment edits change source hash | Conservative normalized-byte policy retained | Existing identity tests | DOCUMENTED; policy change deferred |

The five HIGHs were all CONFIRMED on starting source; 01/03/04/05 are now fixed;
02 is structurally improved but remains PARTIALLY_FIXED as an end-to-end resource/resume finding.
No current audit findings were silently renumbered as the stale draft's spec/freeze/cap items.

Remaining gates: owner-approved Lightning plan/cost/deadline; reviewed source/locked Linux
environment and full suite including the five skipped Bash tests; trusted migrated Gold
bytes/checkpoint hashes and full validation; actual preparation equivalence/RSS/disk profiling;
publication fault/recovery and single-writer policy; GPU tolerance/attestation and real smoke;
then an authorized isolated one-G0 benchmark and separate 48-spec budget/stop contract.
Preserve discovery/acquisition/60 candle checkpoints and Gold 7/7. No recomputation of those data.

## 17. Final readiness and safety

| Gate | Status |
| --- | --- |
| SPEC_CONTRACT | RESOLVED: 48 primary, 6 deferred ablations, 4 deferred HTF, 58 total |
| Historical v1.9 freeze | PRESERVED |
| Current scientific / descriptor identity | PASS |
| Rebuild / capacity / orphan checksum binding / full Gold schema | PASS (local synthetic scope) |
| Working-set retention | PARTIALLY_BOUNDED |
| Automatic LRU | NO |
| Lightning import/startup / runtime portability | PASS locally; Linux pending |
| Exact-one canonical selector | READY (code), execution NOT AUTHORIZED |
| READY_FOR_LIGHTNING_MIGRATION | NO — fresh owner approval/contract pending |
| READY_FOR_LINUX_VERIFICATION | YES — next proposed verification phase, owner approval required |
| READY_FOR_GPU_SMOKE_TEST | NO — Linux/build/device gates and equivalence policy pending |
| READY_FOR_ONE_MODEL_BENCHMARK | NO — target-host/data/resource/recovery gates pending |
| READY_FOR_48_MODEL_FOLD1 | NO |
| TRAINING_READY | NO |
| Scientific methodology changed | NO; integrity/admission/orchestration code changed |
| July / August | July unused; August LOCKED_UNUSED, used=false, evaluation_authorized=false |
| Production Fold 1 / one-model benchmark / 48-model run | NOT STARTED |
| Phase 8 / live trading | NOT STARTED |
| Actual Gold byte validation / GPU benchmark / migration | NOT RUN |
| Push | NOT PERFORMED |

Logical local code/tests commit: `0cf62a67d55b9ff51e3b34f8d2726c4e9beb58b0`.
Documentation is committed separately; see final response for its immutable commit hash.
Unrelated owner untracked audit/work/pytest/patch artifacts are
preserved, not staged. No baseline tags removed or history rewritten.

NEXT SAFE ACTION: owner reviews this report and authorizes a bounded Linux verification/
migration plan with a fresh cost/deadline contract. STOP here; do not migrate, fit, use July/August,
or execute GPU/real-data benchmarks without that authorization.

