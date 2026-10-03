# Lightning external state / path qualification — 2026-10-03

**BLOCKED: SILVER_STATE_MISSING; REGISTRY_STATE_MISSING on Lightning.**
EXTERNAL_STATE_QUALIFIED=NO; READY_TO_PREPARE=NO; TRAINING_READY=NO.
No scientific/configuration/source-code changes, recomputation, matrix construction,
model fitting, GPU work, July modelling or August evaluation occurred.

## Repository and Gold

Starting branch `phase7a-pre-lightning-hardening-20261003`; local HEAD and recorded
origin branch both `2076328df1ee99de9e180e12410869be39ea5a0f`. Tracked tree clean;
untracked `.pytest-linux-verification/` preserved. This document is the only change.

Gold root: `/teamspace/studios/this_studio/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598`.
Prior real validation PASS remains authoritative: 139 files, 138 Parquet,
9,672,319,402 bytes, 50,352,548 rows, 109 features, 130 physical columns,
provider MD5 139/139 and partition SHA-256 138/138 PASS. This inspection independently
recounted files/bytes and hashed the manifest:
`a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711`.
No Gold partition scan, recopy, modification or repeated full validator was needed.
See the migration report and its external evidence paths for the full byte/contract audit.

## Actual dependency map

Let A=runtime artifact root, D=runtime data root, C=checkpoint root,
R=`phase7a-core20-primary-93f987736b1a79d26b773957`,
S=`phase7-cc550337f1f4ee4654124bf6`. Paths below are logical requirements,
not accepted remappings. All historical scientific inputs must remain immutable.

| Dependency | Purpose / source code | Runtime path | Identity/hash | Required for Fold 1? | Mutable? | Can remap? | Qualification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Historical/lifecycle registry | `pipeline._load_stage_state`, `registry.read_registry` | A/R/registry/symbol_registry.json; canonical reuse A/S/registry/symbol_registry.json | registry_hash; checkpoint file SHA | YES | NO | Explicit ARTIFACT mapping plus hashes | Missing locally; canonical backup candidate exists |
| Registry checkpoint | `run_phase7a_pipeline._registry_stage` | C/S/registry.json and C/R/registry.json | checkpoint_hash/run_identity/file SHA | YES for canonical stage reuse | NO | CheckpointStore logical/legacy roots | Missing locally |
| Core universe | `_load_stage_state`, `universe.read_universe` | A/R/universe/core_universe.json | universe_hash/core hash | YES | NO | ARTIFACT plus SHA | Missing |
| Expansion policy | `_load_stage_state` even CORE runner | A/R/universe/expansion_policy.json | policy hash | YES | NO | ARTIFACT plus SHA | Missing |
| Discovery/selection history | `_reuse_discovery`, `_core_universe_stage` | Canonical discovery store; A/R/universe/discovery_data.json, selection_descriptors.json, fold_memberships.json | request/config/registry identities and files | Historical reuse prerequisite | NO | Verified source references | Missing locally; backup metadata candidate |
| Acquisition/data manifest | `_load_stage_state` | A/R/data/data_manifest.json | SHA and configuration binding | YES | NO | ARTIFACT plus SHA | Missing |
| Daily Silver | `pipeline._fold_descriptors` → `acquisition.load_candle_family` | D/phase7/... from data.candle_silver_manifests[1d] | child/output SHA; quality status; lifecycle range | YES, numerical descriptor input | NO | Explicit DATA root plus checked hashes | Missing; backup explicitly excludes Silver Parquet |
| Source/segment manifests | `validated_candle_manifest_range`, `_silver_segment_manifests` | Source paths and child manifests referenced by Silver | source range; silver_manifest_sha256; output_files.sha256 | YES for daily input resolution | NO | DATA mapping | Exact list unavailable without data manifest |
| Other candle/derivative state | data checkpoint validation / Gold lineage | 5m/12h/1d and derivative references | checkpoint and manifest inventories | Daily data directly; others if required by completed-stage inventory | NO | DATA mapping | Full required closure unknown |
| Quality/acquisition checkpoints | discovery/acquisition stores and completed stage guard | C and referenced quality/source files | config/request/checkpoint/file hashes | YES for reuse trust | NO | Logical roots or explicit legacy roots | Historical 507/507 and 60 sets not independently revalidated |
| Gold manifest/result | train stage resolves result then locate_gold_manifest | Gold root; A/R/gold/result.json | dataset ID/manifest SHA/partition SHA | YES | NO | GOLD and ARTIFACT separately | Gold PASS; result/checkpoint missing |
| Fold plan | `phase5.folds.plan_folds` | Checked-in schedule, no external planner file required | fold_id and boundaries | YES | NO | Not applicable | Metadata-only planning PASS |
| Fold descriptors/context | `_fold_descriptors`, causal_descriptor_identity, select_fold_active_universe | Daily Silver-derived descriptors; A/R/fold_descriptors.json written by runner | causal numerical descriptor and membership hashes | YES | Historical inputs NO | Hash-preserving inputs only | Blocked on registry/data/Silver |
| Prepared cache | training.load_payload | runtime cache root | Gold/fold/registry/universe/descriptor/science/backend identity | Cache optional; identities required | Rebuildable only with separate authorization | Explicit runtime override | No production entries built |
| Models/reports/artifacts/logs | training.experiment_output_root / runtime / lease | Explicit output roots + run identity | publication/run/science hashes | Output destinations required | Append/atomic publication | Runtime-only roots | Default isolation FAIL |

Gold does **not** eliminate Silver from preparation: `_fold_descriptors` loads daily
Silver for every planned fold, using the 90-day window `[train_end-90d, train_end)`.
It checks registry lifecycle overlap, then builds PIT liquidity/volatility/history descriptors.
Silver is not merely lineage-only. Do not replace this history with present exchange state.

## Trusted-source search and stop condition

Persistent workspace has only Gold under data and migration evidence; repo generated
artifact directories contain no restored historical registry/universe/data/checkpoint state.
The external Linux-verification directory contains no historical research bundle.
Read-only `gcloud storage ls`, always with `CLOUDSDK_CONFIG=~/gcloud-user-config`,
found only the Gold prefix in `gs://crypto2-phase7-migration-258783580370/`.

The checked-in hold record identifies this older trusted backup:
`gs://crypto-ai-data-83921/artifacts/phase7/backup-phase7-cc550337f1f4ee4654124bf6-20260904T044426Z/`.
Its `backup_manifest.json` was downloaded to `/tmp/crypto2-backup-manifest.json`
for inspection only. Inventory SHA-256:
`e5431d00ea4320d11e112c85871212739a64650a4c36d208cea1f933ec89d925`.
It records 3,360 files, canonical configuration `cc550337f1f4ee4654124bf6`,
run S and Git `070a2403fe13ca6babde1fa6be95dcf8875f4dcc`.

| Logical object | Backup-relative path | Bytes | Expected project SHA-256 | Actual local SHA | Status |
| --- | --- | ---: | --- | --- | --- |
| Canonical registry | local_artifacts/phase7/phase7-cc550337f1f4ee4654124bf6/registry/symbol_registry.json | 2193617 | 200d9d63be9d8cae9799cb81f2bb886620a8ddb033c3ab7d4687fc2c310bcbd4 | Not downloaded | Trusted inventory candidate; not qualified |
| Canonical registry checkpoint | local_artifacts/phase7/checkpoints/phase7-cc550337f1f4ee4654124bf6/registry.json | 1004 | 5c241ded1e2658c2723548eedcca9143c0342ce1a85797387ad3176c2bd712aa | Not downloaded | Not qualified |
| Phase7A data manifest | A/R/data/data_manifest.json | Unknown | e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0 | Missing | Required, hash anchored by Gold and handoff |
| Phase7A data checkpoint | C/R/data.json | Unknown | d7bb7e99dda07ec62cd493a3c06951d6dae230f340c065b9bd42bd2423a99c0f | Missing | Required, hash anchored by handoff |

Crucially, this backup explicitly excludes `data/phase7/silver/binance/klines`
and `data/phase7/silver/binance/versions`, as well as raw candle Parquet.
Its historical assertion that excluded data are regenerable is **not authorization**
to regenerate them. It predates final Phase7A acquisition/Gold and cannot be substituted
for the final run bundle merely because names look similar.
An attempted recursive name inventory of the historical bucket was interrupted;
the partial `/tmp/crypto2-historical-gcs-names.txt` is not a complete bucket inventory.
No claim is made that no additional objects exist elsewhere in that bucket.
No trusted final Silver copy was established. Stop: **SILVER_STATE_MISSING**.
No external research state was restored, no remap accepted, and no copy plan executed.
Only the small backup inventory was read into disposable `/tmp`; this is not state restoration.

Registry listing/delisting dates, version and symbol coverage cannot be qualified from
an absent file. Expected Gold registry identity is `b2c973f0050f205e58672558`
(`symbol_registry_v1`); core hash `f71cdf65d161466037b34420`;
research universe hash `94a9ce4759dd8d3303841f13`.
Gold already proves HNT retained and XPIN excluded; PIT registry/membership proof remains blocked.

## Legacy references and proposed mapping

Scope: the migrated Gold manifest's runtime-relevant lineage fields. Exactly one absolute
external reference was found there; one blocking/unresolved, zero accepted remaps,
zero historical-only references within that scope. Whole-checkpoint counts are unknown
because the checkpoints are absent. Documentation/backup metadata contain additional historical
GCP references; they are not evidence that every runtime dependency has been enumerated.

| Old logical reference | Old absolute path | Proposed Lightning path | Expected SHA | Actual SHA | Match? |
| --- | --- | --- | --- | --- | --- |
| Gold lineage data manifest | /home/nssharath123/crypto2.0/local_artifacts/phase7/phase7a-core20-primary-93f987736b1a79d26b773957/data/data_manifest.json | /teamspace/studios/this_studio/crypto2-persistent/artifacts/phase7a-core20-primary-93f987736b1a79d26b773957/data/data_manifest.json | e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0 | Missing | NO |

`runtime.resolve_runtime_input_path` uses explicit PHASE7_LEGACY_{DATA,ARTIFACT,GOLD,MODEL,REPORT}_ROOT
and corresponding current roots, longest matching prefix first, with escape rejection.
`CheckpointStore` accepts logical roots/relative paths or explicit legacy roots and always
checks content SHA. Neither mechanism rewrites checkpoint bytes. Mapping is available,
but unavailable objects cannot pass hash/content identity. No hidden path dependency is
declared eliminated; full closure requires the missing manifests/checkpoints.

## Read-only resume simulation and metadata work

No runner, preflight smoke or production resume was invoked. Static source trace plus
metadata-only config/fold planning shows:

1. Lightning launcher immediately rejects absent required runtime environment variables.
2. Even with proposed overrides, `run_phase7a_pipeline._run_stage_owned(stage=train)`
   requires valid completed registry/universe/data/Gold checkpoints. All are absent locally.
3. If restored, `_load_stage_state` reads registry/core/policy/data; Gold result resolves
   the independently validated dataset. `_fold_descriptors` then loads daily Silver.
4. Training binds causal descriptor, membership, Gold and source identity before cache lookup.
   Cache misses load/slice/rebind Gold. The reference fold/context load precedes per-spec
   completion triage: completed-checkpoint resume is not necessarily zero-scan.
5. Preparation/Arrow-to-NumPy/cache publication/LightGBM Dataset/fit are forbidden here.

Fold 1 metadata plan: `fold-000-a0e9a4f72689`, TRAIN [2020-01-01,2022-01-01),
Validation through 2022-04-01, Calibration through 2022-07-01, TEST through 2022-10-01.
This calendar TEST July is 2022, not the unused July 2026 buffer.
Historical hold evidence remains STARTED_NOT_COMPLETE, 0/48 reports, zero models,
0/16 folds, Fold 2 not started. Missing real checkpoints prevent independent resume verification.
No completion or new checkpoint was fabricated.

METADATA_ONLY_WORK_REQUIRED_BEFORE_PREP=YES: config/fold plan, inventories,
checkpoint/source/Gold hash validation and root resolution. Descriptor derivation additionally
requires reading historical daily Silver values; it is not a metadata-only scan.
Those reads and the downstream Gold context scan were not performed in this phase.

## Runtime roots and storage trust

No PHASE7_* root overrides or cloud-training guard were present in this shell.
Actual defaults are inside `/teamspace/studios/this_studio/crypto2.0`:
Gold `data/gold/phase7a_core20_primary_v1` (absent), data `data`, artifact
`local_artifacts/phase7`, cache `local_artifacts/phase7/prepared_cache`, checkpoints
`local_artifacts/phase7/checkpoints`, models `local_artifacts/phase7/models`, reports
`local_artifacts/phase7/reports`, logs `local_artifacts/phase7/logs`.
Temp admission defaults to cache unless PHASE7_TEMP_ROOT is supplied; atomic publication
temporary files still live beside their destination.

| Role | Proposed persistent root | Exists / active? | Trust / mutability |
| --- | --- | --- | --- |
| Gold | crypto2-persistent/data/gold/phase7a_core20_primary_v1 | Exists; not configured | Immutable input, logically read-only |
| Data | crypto2-persistent/data | Exists; Silver absent; not configured | Historical inputs immutable |
| Artifact | crypto2-persistent/artifacts | Absent; not configured | Persistent run-critical state |
| Checkpoint | crypto2-persistent/checkpoints | Absent; not configured | Resume-critical; never fabricate |
| Cache | crypto2-persistent/prepared_cache | Absent; not configured | Rebuildable only with authorization |
| Model | crypto2-persistent/models | Absent; not configured | Persistent publication |
| Report | crypto2-persistent/reports | Absent; not configured | Persistent publication |
| Log | crypto2-persistent/logs | Absent; not configured | Persistent evidence |
| Temp | crypto2-persistent/tmp | Absent; not configured | Disposable; no matrix allocation |
| Benchmark | crypto2-persistent/benchmark-isolated | Absent; not configured | Must be separate from production |

All proposed paths are relative to `/teamspace/studios/this_studio/` and outside the repo.
`df -T` reports filesystem `lightning`, mounted at `/teamspace/studios/this_studio`.
Available bytes at inspection: 346,064,429,056 (~322.3 GiB).
This is an available-space observation, not full preparation capacity or training adequacy.
No write probes/output directories were created after missing-state discovery.
Active-root isolation FAIL; persistent output/writability qualification NOT COMPLETE.
Do not silently activate these proposed mappings or modify canonical TOML.

## Focused software verification

29 passed, 0 failed in 2.69s: remediation runtime trust, config/registry/universe,
discovery completion checkpoints, checkpoint relocation/partial resume, and causal
descriptor identity tests. Tests cover hash mismatch rejection, source mapping/root escape,
unchanged relocated checkpoint bytes, independent execution/scientific identity, future
descriptor exclusion, historical lifecycle and no-create/no-training launcher preconditions.
Synthetic test fixtures remain isolated in `/tmp`; no production state fabricated.
These results qualify mechanisms, not missing real state. No source change necessitated
a repeat full Linux gate; the prior 771-pass Linux gate remains separately recorded.

## Remaining blockers and next safe action

1. Restore final historical Phase7A registry/universe/policy/data/checkpoint/run bundle,
   with anchored data-manifest and data-checkpoint hashes; canonical registry backup alone
   does not supply final Phase7A completion evidence.
2. Provide an immutable trusted copy of the daily Silver/source/segment/quality closure
   referenced by that manifest. Current inspected backup excludes its Parquet bytes.
   Do not rebuild it, boot old compute or use a different version without separate approval.
3. After restoration, verify every relative identity/hash, configure reviewed persistent
   runtime/legacy roots and rerun read-only resume qualification before preparation profiling.

NEXT SAFE ACTION: owner identifies the trusted final external-state/Silver archive (or
authorizes a separate recovery plan for preserved disk state). Stop pending review.
READY_FOR_PREPARATION_PROFILE=NO; READY_FOR_GPU_SMOKE=NO;
READY_FOR_ONE_MODEL_BENCHMARK=NO; READY_FOR_48_MODEL_FOLD1=NO.
July 2026 UNUSED; August LOCKED_UNUSED, used=false, evaluation_authorized=false.
Gold unchanged; Bronze/Silver/Gold not recomputed; prepared matrices not built;
training/GPU/48-spec run/Phase 8 not started by this qualification.
