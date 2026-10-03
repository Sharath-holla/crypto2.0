# Lightning Gold migration and validation — 2026-10-03

Migration and byte integrity: **PASS**. Final canonical real-Gold validation: **PASS**.
The initial **VALIDATOR_BUG_FOUND** / blocked result is preserved below as history;
the authorized validator-only correction and final result are recorded in the continuation.
No validator weakening, Gold mutation, methodology change, training, preparation or GPU work occurred.

## Repository and authorization

Branch: `phase7a-pre-lightning-hardening-20261003`.
Local and origin HEAD: `9a904ee18ee369043413fce858042d817241baed`.
Tracked checkout was clean; existing `.pytest-linux-verification/` evidence was preserved.
The previously verified Linux gate (764 passed, zero failures/warnings) was not rerun.
Owner authorized only GCS migration and read-only real Gold validation.
Scientific methodology, canonical configs, historical v1.9 JSON and code are unchanged.

## Source, destination and transfer

Source bucket: `gs://crypto2-phase7-migration-258783580370`.
Source prefix:
`gs://crypto2-phase7-migration-258783580370/gold-phase7-0cbf2910e8d96c9d19826598`.
Read-only GCS access: **PASS**, using the owner-authenticated `~/gcloud-user-config`.
No credentials, tokens or keys are recorded in this report or migration evidence.

Persistent root: `/teamspace/studios/this_studio/crypto2-persistent`.
Destination:
`/teamspace/studios/this_studio/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598`.
Filesystem: `lightning`, mounted at `/teamspace/studios/this_studio`; total 395,184,570,368 bytes.
Initial free capacity: 355,812,212,736 bytes. Destination did not exist; no partial migration
was overwritten, deleted, quarantined or resumed.

Transfer tool: Google Cloud SDK 587.0.0 (`gcloud storage rsync`); gsutil 5.37 also available.
Command (source is read-only; no destructive synchronization flags):

```bash
CLOUDSDK_CONFIG=~/gcloud-user-config gcloud storage rsync \
  gs://crypto2-phase7-migration-258783580370/gold-phase7-0cbf2910e8d96c9d19826598 \
  /teamspace/studios/this_studio/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598 \
  --recursive --no-clobber
```

Transfer ended at **2026-10-03T09:08:40.125804+00:00**, exit 0, elapsed **49.985 seconds**.
Transfer log reported average throughput 193.6 MiB/s; that is the tool's observation,
not a measurement of validator scan throughput.

| Inventory | Source | Destination |
| --- | --- | --- |
| Objects/files | 139 | 139 |
| Parquet partitions | 138 | 138 |
| Metadata files | 1 (`manifest.json`) | 1 (`manifest.json`) |
| Total bytes | 9,672,319,402 | 9,672,319,402 |
| Size in GiB | Approximately 9.01 | Approximately 9.01 |

There are no unexpected destination files, temporary files or symlinks. Partition structure
is `dataset/symbol=SYMBOL/year=YEAR/part-*.parquet`. Symbol is also physically present;
year is directory partition metadata. The seven year chunks span 2020–2026. Their recorded
partition counts are 20/20/20/20/20/19/19; their row counts sum to 50,352,548.
Seven chunk records are not independently qualified 7/7 checkpoint completion: the external
Gold checkpoints were not part of this 139-object transfer.

## Transport and byte integrity

- Before-copy inventory records relative names, sizes, generation IDs, MD5 and CRC32C for
  every object. A second read-only source inventory confirms all 139 object generations,
  sizes and checksums remained unchanged during the transfer.
- Local MD5 was computed and compared with GCS `md5Hash`: **139/139 PASS**.
- CRC32C is recorded for 139/139 objects; an independent local CRC32C comparison was not run.
  ETag was not interpreted as SHA-256.
- Local SHA-256 was computed and compared with manifest partition hashes: **138/138 PASS**.
- Manifest SHA-256:
  `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711`.
  The manifest itself has no independent historical SHA-256 supplied here; its local bytes
  match the source object's MD5. Partition SHA values establish binding to that transported
  manifest, not independent authentication of the original dataset's provenance.

TRANSPORT_INTEGRITY: **PASS**. BYTE_LEVEL_VALIDATION: **PASS**.
SCIENTIFIC_DATASET_VALIDATION: **INCOMPLETE / BLOCKED**, separately from those byte checks.

## Producer and independent metadata checks

Checked-in producer catalogs/config and handoff documents were inspected before validation.
The expected feature set is 54 native + 22 completed 12h + 33 completed 1d = 109.
Every physical schema has exactly 130 canonical fields with expected types:
119 float64 (109 features, three helper fields, seven target/scale/excursion fields),
six strings, four UTC microsecond timestamps and one int64 horizon.
All 138 footer schemas match each other, including metadata; there are no missing or extra
canonical columns. Physical feature order matches the manifest in all 138 files.

Parquet footer row total: **50,352,548**, matching both manifest and expected handoff value.
Footer/schema observations do not prove row-level timing, duplicate absence or numeric quality.

Dataset ID: `gold-phase7-0cbf2910e8d96c9d19826598`.
No separate `dataset_version` field exists in this manifest; its identity uses `dataset_id`.
Feature version: `multiasset_features_v2`; target version: `multiasset_targets_v2`.
Classification: `RETROSPECTIVE_MULTI_ASSET_RESEARCH`.
Registry: `symbol_registry_v1`, hash `b2c973f0050f205e58672558`.
Universe: `dual_universe_v3`, hash `94a9ce4759dd8d3303841f13`.
Manifest lineage research-universe hash matches that universe hash. Configuration lineage hash
`93f987736b1a79d26b773957` matches the checked-in Core20-primary config.
The recorded core hash `f71cdf65d161466037b34420` and source data-manifest SHA
`e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0` match handoff documentation.
The registry, universe and source data-manifest files themselves were not migrated or opened.
Historical absolute lineage paths remain untouched; hash-preserving path mapping is future work.

Directory symbol inventory is exactly the expected Core20, including HNTUSDT and excluding XPIN.
Row-level universe/PIT membership and cross-sectional membership consistency were not evaluated.
The manifest has no separate research-view selector: execution scope remains CORE in the config;
Gold's preview context is not independently proof of a fold-local CORE research view.

## Canonical validator invocation and failure

CLI `--help` was inspected first. Canonical command, with no hash skip:

```bash
.venv/bin/python -m scripts.validate_phase7_gold \
  --gold-root /teamspace/studios/this_studio/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598 \
  --output /teamspace/studios/this_studio/crypto2-persistent/migration-evidence/gold-migration-20261003/gold-validation.json
```

`PHASE7_ALLOW_CLOUD_RESEARCH` was removed from the subprocess environment;
`PHASE7_LGBM_DEVICE=cpu`. No backend smoke or estimator was invoked.
Exit code: **1**. Failure in `validate_gold_manifest`, before row scanning:

```text
production feature count/order mismatch (native feature contract included);
A6 feature-group ordering mismatch
```

No `gold-validation.json` PASS report was produced. Failure log and separate integrity/resource
evidence were preserved. No exception was hidden or interpreted as a successful validation.

### VALIDATOR_BUG_FOUND

File: `src/crypto_ai/phase7/gold_validation.py`.
Functions: `production_feature_columns()`, `validate_gold_manifest()` and the downstream
physical order comparison in `validate_phase7_gold()`.

Problem: `production_feature_columns()` uses the Phase 6 `FEATURE_GROUPS_V3_RESEARCH` grouping
catalog's HTF order. Actual `_higher_timeframe_values()` in `src/crypto_ai/phase6/features.py`
emits dictionary keys in a different insertion order. Phase 7 `build_higher_timeframe_context()`
and `_asof_higher_context()` preserve that physical context-column order, which is appended
to native fields by `build_multiasset_features()`. The migrated manifest and all physical
schemas agree with this actual producer order. Its A6 list also exactly matches the existing
`feature_ablation_sets(tuple(manifest["feature_columns"]))["A6"]` result.

Evidence: 109 expected/actual names, zero missing/extra fields, but 33 positional differences.
For example at index 63 the producer/manifest has `htf_12h_rsi14`, while the validator expects
`htf_12h_ema20_slope_3bar`. Producer dictionary insertion order was independently recovered
from its source AST without generating production features or prepared matrices.
The grouping catalog expresses membership but does not describe actual physical producer order.

Safe proposed fix (not applied): derive the validator's expected HTF physical order from the
existing producer; preserve the exact inventory and types; validate the separately derived
A6 order; add synthetic producer-to-validator regressions rejecting reordering, missing/extra
fields and A6 tampering. Do not reorder historical Gold, change model order or relax to set-only
validation. Rerun focused/full Linux tests and the real read-only validator after owner review.

## Checks not reached

The early manifest-order failure blocked actual-row target versions/horizons, entry timing,
label endpoint consistency, duplicate primary keys, NaN/Inf statistics, row-level universe,
scope/version/membership fields and cutoff/holdout exclusion checks. These are **NOT RUN**,
not zero counts and not PASS. No performance, calibration or model evaluation was performed.

Manifest research cutoff is `2026-07-01T00:00:00+00:00`, exclusive.
Manifest July flag remains false; August starts `2026-08-01T00:00:00+00:00` and remains
`LOCKED_UNUSED`, used=false, evaluation_authorized=false. No July/August modelling or evaluation
occurred. Physical exclusion of unauthorized rows remains unvalidated until the blocked scan runs.

## Read-only proof and resource telemetry

All 139 files were inventoried before and after the validator with exact relative path, size,
SHA-256, MD5 and nanosecond mtime. The inventories are identical: **Gold modified: NO**.
No source object, scientific metadata, partition, manifest or historical artifact was changed.

Validator start: `2026-10-03T09:10:55.850159+00:00`.
End: `2026-10-03T09:10:57.605526+00:00`.
Elapsed: **1.755 seconds**, an early failure, not a full scan benchmark.
Sampled peak validator RSS: **154,730,496 bytes (147.6 MiB)**, sampled every 0.25 seconds;
this is not a guaranteed continuous maximum and excludes the independent hashing wrapper.
Available system RAM before/after: 10,431,901,696 / 10,408,837,120 bytes.
Disk free before/after validator: 346,134,925,312 / 346,134,921,216 bytes.
The four-KiB difference was outside immutable Gold; dataset size remained unchanged.
No claim is made that this four-CPU, 15.6-GiB machine is adequate for training.

Evidence root:
`/teamspace/studios/this_studio/crypto2-persistent/migration-evidence/gold-migration-20261003/`.
Key files: `source-inventory.json`, `source-inventory-after-copy.json`, `source-summary.json`,
`transfer.log`, `transfer-result.json`, `checksum-results.json`, `independent-footer-lineage.json`,
`validator-bug-evidence.json`, `gold-validator.log`, `validation-resources.json`,
`local-before-validation.json`, `local-after-validation.json`, `read-only-proof.json`.
No data or generated evidence is added to Git; only this documentation file was created in the repo.

## Readiness and next safe action

GOLD_MIGRATION_READY: **PASS** (completed transfer and integrity).
REAL_GOLD_VALIDATED: **NO**. READY_FOR_PREPARATION_PROFILE: **NO**.
READY_FOR_GPU_SMOKE / READY_FOR_ONE_MODEL_BENCHMARK / READY_FOR_48_MODEL_FOLD1: **NO**.
TRAINING_READY: **NO**. Prepared matrices not built; Fold 1, 48-spec run, benchmark, GPU,
training, Phase 8, paper and live trading not started.

Remaining blockers:
1. Producer-versus-validator HTF/A6 ordering bug requires reviewed, tested validator-only repair.
2. Full actual-row schema/target/timing/quality/universe/holdout validation remains blocked.
3. Independent registry/universe/data/checkpoint migration and legacy path qualification remain
   outside this Gold-only transfer; 7/7 completion checkpoints are not newly verified here.

Next safe action: owner reviews this failure evidence and the proposed validator-only correction.
Preserve the migrated bytes; do not reacquire or regenerate Gold. No preparation or model work
may follow from this incomplete scientific validation.

## Validator correction and final validation continuation — 2026-10-03

This continuation does not recopy Gold. The original migration and transport/partition-byte
qualification above remain valid; their bytes, manifest and partition structure are unchanged.
The earlier blocked outcome is retained as history and will be superseded only by the final
read-only scan result below.

### VALIDATOR BUG ROOT CAUSE

The validator incorrectly treated the Phase 6 grouping catalog as physical HTF order.
The grouping catalog and actual producer have identical inventory but differ at 33 positions.
The actual producer, all 138 persisted schemas and the manifest agree. No Gold corruption
or change to scientific feature definitions was found.

### PHYSICAL ORDER SOURCE

`phase6.features._higher_timeframe_values()` defines HTF dictionary insertion order.
`phase7.features._segmented_higher_timeframe_values()` preserves that order with `setdefault`;
`build_higher_timeframe_context()` uses `payload.update(values)`; `_asof_higher_context()`
reads HTF names in context-table order. `generate_multiasset_features()` appends these names
after native catalogs and emits them in that same order. Gold producers preserve that ordered
`feature_columns` tuple in the manifest. Storage validation constrains the physical feature
subsequence, exact 130-column inventory/types and consistency of all partition schemas.

### A6 MODEL ORDER SOURCE

The authoritative model order is `phase7.gold.feature_ablation_sets(feature_columns)["A6"]`,
serialized as `manifest.feature_groups.A6`. It traverses native/coin, BTC, ETH and market
catalogs, then HTF features in supplied producer order, and finally the three derivative
features. Physical order and A6 order are **not identical**: derivative features move to the
end in A6. The Phase 6 grouping catalog is not an independent A6 override.
`training.run_phase7_training()` reads the stored group tuple; `models._matrix()` selects
columns by that tuple's names/order. Neither training nor model-column selection was changed.

### VALIDATOR FIX

Only `src/crypto_ai/phase7/gold_validation.py` changed in production code.
`production_feature_columns()` now obtains HTF key order by calling the existing producer
with an empty, correctly typed candle table. This zero-row schema probe creates no market
data, feature values or prepared matrices. It still checks the grouping catalog's exact
inventory/count (22/33), independent of grouping order. Native count/order, 109 total fields,
130 physical columns and all expected types remain unchanged.

`production_a6_model_columns()` separately delegates to the established `feature_ablation_sets()`
logic. The validator checks manifest physical order against producer order and manifest A6
against model order independently. Its report now records both orders. Existing checksum,
schema, timing, duplicate, numeric, universe and holdout assertions remain in force.
No producer, grouping catalog, training/model code, canonical config or historical v1.9
contract changed. Runtime/scientific source identity changes because validator code is part
of the conservative source manifest; no historical artifact was rewritten to match it.

### TESTS

Targeted Gold validation/finalization tests: **45 passed**, zero failures/warnings.
New regressions use an independently generated tiny synthetic HTF context to check actual
producer order and the exact 54+22+33 inventory; accept distinct correct physical/A6 order;
reject swapped physical fields, missing/extra features and wrong types after recomputing
the test partition hash; reject A6-only tampering with unchanged physical bytes; and prove
that reversing grouping-catalog order cannot redefine storage or model order.

Full Linux verification: **771 passed, 0 failed, 0 skipped, 0 warnings**, 113.94 seconds.
All five Bash tests, Ruff, format (233 files), lock, compile and diff checks passed; full
lease/publication/recovery/resource tests passed. Software evidence:
`.pytest-linux-verification/software-gate-25ce38ecaf9c463db75fcbc9c9d6a9b1/verification-result.json`.
No production preparation, training or GPU work occurred in either test gate.

### FINAL REAL GOLD VALIDATION

**PASS**, exit 0, using the existing migrated dataset, no recopy and no hash skip.
Command:

```bash
.venv/bin/python -m scripts.validate_phase7_gold \
  --gold-root /teamspace/studios/this_studio/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598 \
  --output /teamspace/studios/this_studio/crypto2-persistent/migration-evidence/final-gold-validation-20261003/gold-validation.json
```

Start: `2026-10-03T09:27:09.291449+00:00`.
End: `2026-10-03T09:33:11.026107+00:00`.
Elapsed: **361.735 seconds**. Sampled peak validator RSS: **1,437,487,104 bytes (1.34 GiB)**,
at 0.25-second intervals; not a continuous-peak or training-capacity claim.
Available RAM before/after: 12,707,098,624 / 12,638,523,392 bytes.
Disk free before/after validator: 346,080,763,904 / 346,078,830,592 bytes.
Evidence output is outside Gold and outside Git.

| Final check | Result |
| --- | --- |
| Dataset/manifest identity | PASS; expected `gold-phase7-0cbf2910e8d96c9d19826598` |
| Files / bytes | 139 / 9,672,319,402 |
| Provider MD5 | Freshly verified 139/139 against saved GCS inventory |
| Manifest partition SHA-256 | Freshly verified 138/138; canonical validator also verified every partition |
| Manifest SHA-256 | Unchanged `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711` |
| Partitions / actual decoded rows | 138 / 50,352,548 |
| Native / completed 12h / completed 1d features | 54 / 22 / 33; 109 total |
| Physical schema | PASS; exact 130-field inventory/types, consistent metadata and producer feature order |
| A6 model order | PASS; separate 109-name tuple matching established manifest order |
| Targets / horizons | PASS; `multiasset_targets_v2`, raw/normalized fields, 15/30/60/120 minutes |
| Timestamp types / target timing | PASS; UTC microseconds, entry=feature+5m, label end=entry+horizon |
| Universe | PASS for dataset contract; exact Core20, HNT retained, XPIN excluded |
| Cross-sectional scope/version/helpers | PASS for acquisition-union preview contract; fold rebinding still required |
| Duplicate primary keys | 0; within-partition and inter-partition boundary checks passed |
| Infinite numeric values | 0 across all audited fields |
| NaN audit | PASS; 111,243,465 numeric cell occurrences across 109 of 119 audited numeric fields |
| Research cutoff | PASS; feature and label endpoint timestamps strictly before 2026-07-01 UTC |
| July / August | July unused; August LOCKED_UNUSED, used=false, evaluation_authorized=false; no forbidden feature/label rows |

NaNs are counts of cells, not distinct rows. They include source gaps, warm-up and unavailable
context; they are not imputed, removed or filled by validation. Detailed per-field counts are
in the immutable report. This PASS is an audit under the existing contract, not a claim of
zero NaNs, profitability, training eligibility or complete-case row availability.

Before/after inventories compare every file's relative name, size, SHA-256, MD5 and nanosecond
mtime. They are identical for all 139 files. **Gold bytes were never changed**, including
the manifest, physical order, partition structure and scientific metadata. Existing provider
CRC32C evidence remains recorded; MD5, rather than independent CRC32C, was recomputed here.

Final evidence root:
`/teamspace/studios/this_studio/crypto2-persistent/migration-evidence/final-gold-validation-20261003/`.
Files: `gold-validation.json`, `gold-validator.log`, `validation-resources.json`,
`checksum-results.json`, `independent-footer-lineage.json`, `local-before-validation.json`,
`local-after-validation.json`, `read-only-proof.json`. No raw data or generated evidence is
committed. Historical migration/failure evidence remains preserved in its original directory.

### Final scope and readiness limits

REAL_GOLD_VALIDATED: **YES** for the current canonical read-only dataset contract.
The reported scope is `ACQUISITION_UNION_PREVIEW_REQUIRES_FOLD_REBIND`. No fold-specific
PIT membership selection, cross-sectional rebinding, matrix preparation, model fit,
benchmark or performance evaluation occurred. Passing Core20/scope/version checks does not
independently requalify registry history or prove every row's membership hash against an
unmigrated registry. Registry/universe/source data and completion checkpoints referenced by
historical absolute paths still need separate hash-preserving migration/path qualification
before the canonical preparation path can run. Gold 7/7 checkpoint completion is not inferred
from the seven manifest chunks or this validator's success.

READY_FOR_PREPARATION_PROFILE: **NO** until required external state/path prerequisites are
qualified and a separate profiling scope is authorized. READY_FOR_GPU_SMOKE: **NO**.
READY_FOR_ONE_MODEL_BENCHMARK: **NO**. TRAINING_READY: **NO**.
Scientific methodology changed: **NO**. Prepared matrices: **NOT BUILT**; training, GPU,
Fold 1, 48 specs, Phase 8, paper/live trading: **NOT RUN**.

Next safe action: owner reviews the final Gold report and authorizes qualification of the
required registry/Silver/data/checkpoint state and legacy path mappings, followed by a bounded
preparation-only profile. No such work is started by this continuation.
