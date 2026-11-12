# Crypto 2.0 — final master readiness report

Requested report date: **2026-11-06**. Final verification continued on **2026-11-07**. This report supersedes the earlier readiness/audit conclusions; those records remain preserved. Evidence paths refer to this Mac and the retained source export.

## 1. Executive summary

**NOT_READY_FOR_SMOKE.** The current local scientific invariants, recovered data checks, canonical publication tests and Mac software checks pass. Exactly **1,394 tests passed**, with **zero failures, errors or skips**, on a committed source export without `.git`; Ruff also passes. This follows a real exported-tree failure and its repair, not a theoretical portability assertion.

The outstanding smoke-critical gates are actual Linux/x86_64 execution, qualification of the intended local cache/output filesystem, Mac-versus-RunPod identity equality, and one real prepared cache with read-only reload equivalence. No authorized Linux endpoint or fresh owner cost/stop-deadline contract was supplied. The Mac has 16 GiB RAM and is correctly refused; the measured Fold-0 row count gives a **25.8 GiB heuristic working set**, not a capacity guarantee. No VM was created, started, resized or modified; no real-data cache/model was prepared/fitted; no order or credential access occurred. Synthetic tiny fits inside the actual tests are verification fixtures.

`PIPELINE_VALIDATED=false`; `TRADABILITY_VALIDATED=false`. This is a functioning, substantially hardened research framework whose operational deployment and economic validity remain unestablished. Historical **0/48** is incomplete execution, not evidence of poor model performance.

## 2. Exact branch/SHA

Branch: `fix/phase7-final-architecture-repair-20261106`. Initial HEAD: `c892cc0298669620778585b3a7330b04a6092de2`. First repair commit: `930cfe9f2335628e09709f054593ba89d8a2337b`. **Final verified source commit: `99cf12fbcc6ee6397ee0caf4c40b768c87ae430c`**. The report/evidence are published in a separate documentation commit; they cannot embed their own future commit hash.

Initial branch, 40-commit log, tracked/untracked state and staged/unstaged diffs are preserved in [initial_state.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/initial_state.json), [initial_status.txt](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/initial_status.txt), [initial_log.txt](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/initial_log.txt), [initial_diff.patch](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/initial_diff.patch) and [initial_staged.patch](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/initial_staged.patch). Original unrelated dirty review documents and untracked owner material remain untouched. A separate detached worktree of the verified source is clean; the transfer export comes from a committed tree, not dirty files. No GitHub push occurred. Remote remains `origin` at the existing Crypto 2.0 repository.

Source export: `/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107/crypto2-source-final`; **928 committed files**, content inventory `cda78ba7f1c85fec038bd9b73c8320397e4e87d7580b3a492bb032c9caf4ff92`. `.git`, `.venv`, `Claude outputs`, `._*` and `.DS_Store` are excluded. See [source_export_final.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/source_export_final.json). Git maintenance removed all **288 temporary garbage files**, preserved all **2,551 valid object IDs** including **152 unreachable objects**, and passed `git fsck`; object-store backup and exact temporary-only plan are retained in [git_maintenance.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/git_maintenance.json).

## 3. Data recovery status

**PASS — VERIFIED_RECOVERY_WITH_PRESERVED_SOURCE_PROVENANCE_DISCREPANCIES.** Read all eight requested recovery documents and the final recovery report. Remote inventory: **1,276,060 files / 34,113,175,738 bytes**; missing=0, size mismatches=0, unresolved findings=0. The recorded fresh remote audit passed; this task did not redownload Binance or use GCS.

The base checksum evidence contains **2,083,941 historical references**, including 65 non-passing historical expectations plus two supplemental discrepancies. Source-match/resolution evidence accounts for these across 11 source files. Do not restate this as every historical expectation matching. The final source bytes and preserved provenance were not rewritten. Local inventory additionally contains **67 forensic partial extras / 240,779,264 bytes**: total **1,276,127 files / 34,353,955,002 bytes**. Exact exclusions and canonical-input sets prove zero forensic extras selected by Silver, feature generation, Gold, M-01 or cache input enumeration. See [recovery_verification.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/recovery_verification.json), [forensic_exclusions.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/forensic_exclusions.json) and [forensic_selection_assertions.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/forensic_selection_assertions.json).

## 4. Gold status

**PASS.** The actual `scripts/validate_phase7_gold.py` run used pyarrow with partition hashing enabled. **138/138 partitions**, **50,352,548 physical rows**, **130 physical columns**, **109 ordered production features**, exact feature/target schema, per-file counts, duplicate/key rules, symbol/time/horizon keys, entry/label timing, timestamp bounds, non-finite accounting and exclusive cutoff all passed. Infinity count is zero; recorded NaNs are not silently filled. Versions stay `multiasset_features_v2` / `multiasset_targets_v2`.

Dataset: `gold-phase7-0cbf2910e8d96c9d19826598`. Manifest SHA: `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711`. The subsequent fresh transfer/checkpoint verification re-hashed the same immutable Gold bytes; the data-producing/validation modules were not changed after the full data inspection. Gold was read only, not rebuilt or repaired. See [gold_validation.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/gold_validation.json) and [transfer_staging_final.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/transfer_staging_final.json).

## 5. Silver status

**PASS.** Actual canonical candle validation covered **131,148 Parquet files** across **60 5m/12h/1d families**, checking hashes, exact Decimal/UTC schemas, footer/physical row counts, symbols, interval paths, actual times and declared half-open ranges. The **60 canonical funding/mark/index inputs** used by this framework also passed hashes/rows. Listing absences and WARN/segmented quality remain explicit; this is not a claim that missing candles were fabricated or all histories are continuous. None were synthesized or forward-filled. See [silver_validation.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/silver_validation.json).

The original push list was insufficient for the actual descriptor loader despite its complete stage checkpoint references. Its failure is retained in [transfer_descriptor_failure_before.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/transfer_descriptor_failure_before.json). Adding **1,840** required descriptor inputs fixed it. The canonical Fold-0 loader now derives **20** descriptors from recovered and staged data with identical hash `b019cbcf78ba5f3cb76023334b702843707afc27b2b303955bac86586505d9a7`. See [descriptor_transfer_equivalence.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/descriptor_transfer_equivalence.json).

## 6. M-01 result

Original Gold-union verdict: **MATERIAL_LOSS_SIDECAR_REQUIRED**. Actual independent feature availability came from canonical Silver producer-time keys, not Gold itself. Counts: **12,588,383 independent keys**, **12,588,302 Gold unique keys**, **81 lost** (~0.0006435%), **0 interior**, **81 terminal**, **0 extra Gold keys**. Five timestamps lose one peer; four lose multiple/all peers. The unchanged predeclared rule therefore requires a sidecar even though the percentage is small.

| Horizon | Lost keys | Cutoff-related | Unknown terminal source boundary | Interior/gap-related loss |
|---|---:|---:|---:|---:|
| 15m | 81 | 76 | 5 | 0 |
| 30m | 141 | 133 | 8 | 0 |
| 60m | 261 | 247 | 14 | 0 |
| 120m | 501 | 475 | 26 | 0 |

All symbols lose four union keys, except HNT with five. Unknown terminal events were not invented as exact delisting timestamps from coarse lifecycle evidence. Full per-symbol/fold/split/horizon classification is retained in [m01_breakdown.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/m01_breakdown.json); base CLI evidence is [m01_original.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/m01_original.json). Against the frozen feature-only sidecar, the second actual CLI census finds **zero lost keys / NO_MATERIAL_LOSS**. Thus final `M01=PASS` depends on the mandatory qualified sidecar, not an acceptance of the deficient original union. See [m01_context_coverage.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/m01_context_coverage.json).

## 7. Sidecar status

**PASS — frozen feature_context_sidecar_v3 required.** **138 partitions**, **12,588,383 rows**, two keys plus six context source columns; current hashes, schemas, source/feature/configuration/Gold/registry/universe identities and coverage verified. Manifest SHA: `ea5f25a2a7c009c79a9ecbbe795960234b67074d36d2db7c21424724fabc2048`. No target values or future target availability enter the sidecar. Tests cover changed/removed future labels, all-peer timestamp removal, gaps, cutoff behavior and symbol context.

The retained full numerical comparison covers all **50,352,548** Gold rows. Two volatility columns have historical maximum absolute differences **3.968e-16** and **5.204e-18** with identical NaN masks. The pre-existing contract is **rtol=1e-9, atol=1e-12**, unchanged. Exact equality failed at round-off scale; tolerance equivalence passed. Frozen v3 bytes and producer code remain unchanged, so this proof applies without rebuilding. **Transfer and consume the sidecar; do not recompute on RunPod.** Stat-only hash memoization is deferred because mtime/size do not establish immutable content. See [sidecar_validation.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/sidecar_validation.json) and the earlier numerical artifact in the parent evidence directory.

## 8. Test results

Final committed, `.git`-free export: **1,394 passed / 0 failed / 0 errors / 0 skipped**, elapsed **170.486 seconds**, using locked managed Python 3.12 on this Mac. Full tests were also executed repeatedly on the working repository, including **1,392 passed** before the final export-only repairs and two new history-bundle tests. The export reused the same locked environment; its import-path evidence confirms production modules came from the exported tree. It does not substitute for a clean Linux dependency install.

The first real export run had **18 failures / 1,374 passes**, preserved in `pytest_committed_export.log`. Root causes were Git-dependent historical-baseline tests and integration read-only identity. The repair packages **36 actual historical git-show blobs**, preserves the historical tree and exact original expected hashes, pins the bundle SHA, tests tamper/wrong-commit rejection, and leaves integration job branch authorization strict. No test was skipped or expected value relaxed. Final evidence: [pytest_committed_export_final.xml](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/pytest_committed_export_final.xml), [pytest_committed_export_final.log](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/pytest_committed_export_final.log), [export_import_path_final.txt](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/export_import_path_final.txt) and [gate_test_proof_master.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/gate_test_proof_master.json).

## 9. Ruff results

**PASS.** Whole-tree `ruff check .` and `ruff format --check .` passed on the final source/export. The count includes the new checksum-anchored history helper and tests. `git diff --check` also passed. Source and test changes were inspected; no frozen feature/target/data values changed. Logs: [ruff_committed_export_final_check.log](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/ruff_committed_export_final_check.log) and [ruff_committed_export_final_format.log](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/ruff_committed_export_final_format.log).

## 10. Mac environment

Managed **Python 3.12.16**, **uv 0.13.7**, macOS **27.2 arm64**, 10 host/effective logical CPUs, **16 GiB RAM**. The system Python is distinct and was not used for the locked suite. Packages: numpy **2.4.6**, pyarrow **24.0.0**, LightGBM **4.7.0**, pydantic **2.13.4**, pytest **9.1.1**, Ruff **0.16.3**, psutil **7.2.2**. `uv sync --locked --extra dev` passed without dependency edits; `pyproject.toml`/`uv.lock` remain unchanged. Lock SHA: `d0cf77d737384e0d35e6175daf74bfa9716ece8a9f246d1f107beb0a01556d85`. See [environment.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/environment.json).

## 11. Linux verification

**FAIL / NOT RUN**, meaning unqualified rather than a reproduced Linux test failure. Actual Mac calls to `verify_linux` and the filesystem qualifier reject the platform before work. Docker/OrbStack/Colima/Podman/Lima/QEMU executables were not available; no runtime was installed or started. See [actual_admission_and_external_gates.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/actual_admission_and_external_gates.json).

The canonical Linux/x86_64 script performs locked Python-3.12 sync, committed export validation, actual filesystem primitives, full pytest, whole-tree Ruff and `verify_linux`, including five executed shell rotation tests, leases, cache locks, ledger/crash cases and verification-only preflight. It does not scan Gold or fit a real model. Git-free verification is now actually tested on Mac, but genuine Linux remains a separate required gate. Script syntax passes. No Linux PASS is inferred from mocked gate-plan tests.

## 12. Source identity Mac vs RunPod

**Local Mac vs committed export: PASS, all six exact matches**, using relocated Gold and sidecar with no `.git`. **RunPod comparison: NOT RUN**, so the requested aggregate `IDENTITY=FAIL` conservatively denotes the missing cross-host proof.

| Identity | Verified Mac/export value |
|---|---|
| EXPERIMENT_CONTROL_DIGEST | `d96dc32cf4168f13916addd24ddf6ccf4595ac25d1ec2feba2a24d7e4c42fb4b` |
| GOLD_MANIFEST_SHA | `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711` |
| PREPARATION_DIGEST | `07b510b1ebacdf80e22ad142861318b1052387973260605cdea509d2a9b31581` |
| SCIENTIFIC_SOURCE_DIGEST | `b037c5b590542493ca5912a030b4fddc03b2569090102309b71c14b633a520da` |
| SELECTION_PROTOCOL_DIGEST | `562dbf8203f476e446cd9968d336fa74b022924c01e5b1c34f3167c065c73826` |
| SIDECAR_SHA | `ea5f25a2a7c009c79a9ecbbe795960234b67074d36d2db7c21424724fabc2048` |

One portable command:

```bash
uv run python -m crypto_ai.phase7.identity_summary --gold-manifest /path/to/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/manifest.json --sidecar /path/to/feature_context_sidecar_v3/manifest.json --expect /path/to/identity.expected.json
```

Explicit input hashes are path independent; the scientific environment/platform identity is separate and may correctly differ between arm64 Mac and x86_64 Linux. Model/report hashes are distinct canonical artifact bindings, not one of these six source/input summaries. See [identity_source_freeze_mac.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/identity_source_freeze_mac.json) and [identity_source_export_final.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/identity_source_export_final.json).

## 13. Cache identity

**PASS for tested identity semantics; no real cache qualification implied.** Matrix keys bind Gold partitions/manifest, target/horizon, fold, membership, registry/universe, descriptors, ordered features, dtype/transformation, sidecar and preparation code. Changes to matrix-affecting feature/target/context/fold/member semantics invalidate. Pure downstream economics, CSV, console/docs/selection presentation do not invalidate matrices; they can still invalidate model/report/control resume where appropriate. Token-normalized mixed-module function closures avoid hashing unrelated training/reporting functions.

Current preparation digest is `07b510b1ebacdf80e22ad142861318b1052387973260605cdea509d2a9b31581`. The prior cache preparation digest was superseded by the explicit context-admission change; historical caches remain preserved and are not silently reused. Active environment/architecture restrictions still apply. See `test_preparation_identity`, `test_context_sidecar`, `test_prepared_cache` and [gate_test_proof_master.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/gate_test_proof_master.json).

## 14. One cache qualification

**NOT_QUALIFIED.** No real-data prepare-only run or read-only reload ran. The Mac fails resource admission; Linux/filesystem/owner prerequisites are absent. Fixture caches test atomic publication, hashes, row/feature/target/weight/time/symbol/dtype alignment and corruption handling, but cannot qualify this real 4.9-million-row cache.

After all prior external gates and owner authorization, prepare only **CORE/A6/60m/raw/Fold 0**, CPU, one worker; then require `PHASE7_CACHE_MODE=read_only` and reload equivalence. Qualification must verify exact row keys, ordering, targets, weights, timestamps, symbols, float64 arrays, fold boundaries and all hashes. No model fit belongs to preparation qualification. No old cache was deleted or re-labeled qualified.

## 15. Result ledger

**PASS for executed publication/recovery tests.** Official order is **model → report → canonical result → hashed receipt → checkpoint COMPLETE → CSV as derived view**. Same identity/same bytes is idempotent; conflicting content is rejected. Tests exercise partial publication, crash boundaries, model/report orphan detection, missing receipts, checkpoint ordering, resume, duplicate result/fold rejection, CSV corruption/regeneration and changed experiment identities. New five-file canonical publication contracts are verified; historical three-file artifacts remain explicitly historical and are not promoted without canonical ledger verification. See [gate_test_proof_master.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/gate_test_proof_master.json).

## 16. Selection chronology

**PASS.** Current generation exactly reproduces all **16 fold calendars** and **120 temporal-overlap records** in `phase7_selection_chronology_v1.json`. Earlier TEST periods can become later TRAIN/Validation/Cal-A/Cal-B. Therefore a winner selected using all historical development scores does not gain independent confirmation from that historical TEST path. The code separates **DESCRIPTIVE_REPORT**, **DEVELOPMENT_SELECTION** and **INDEPENDENT_EVALUATION** and rejects contaminated independent evidence. See [selection_protocol_comparison.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/selection_protocol_comparison.json).

## 17. Admission

**PASS for the fail-closed implementation/tests, not permission to run.** The canonical benchmark CLI, pipeline launcher and public training wrapper use shared admission; generic Phase 7 training CLI fails `NON_CANONICAL_RESEARCH_ENTRYPOINT`. The full-grid route is refused. Unknown `PHASE7_*` names fail explicitly. Actual Mac admission returns `SMOKE_RESOURCES_REQUIRED: effective RAM >=64 GiB` before preparation.

A real owner contract is required, binding the six content identities plus configuration, dataset, exact G0/A6/60m/raw spec, first fold, CORE view, CPU, one worker, mode, hardware floor, owner, finite positive cost ceiling/currency and future UTC stop deadline. Train approval does not approve prepare mode or changed identities. No real owner approval was manufactured. Admission records resolved TOML configuration, active hardening settings, resource floors, runtime paths, compute budget, recognized environment names and approval hash; immutable execution manifests are content addressed. This is not an independently verified provider billing/stop controller. See [actual_admission_and_external_gates.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/actual_admission_and_external_gates.json).

## 18. CPU/GPU policy

**PASS.** First eligible candidate is only `architecture-G0-A6-60m-raw`, first canonical fold, CORE, CPU and one logical worker. GPU/CUDA requests fail for the smoke even if hardware is present. General GPU paths require explicit qualification evidence, but no GPU equivalence is established here. Effective thread budgeting uses host count, sched affinity and cgroup quota, with explicit oversubscription rejected and per-estimator threads clamped. Minimum target hardware is **8 effective CPUs**; one worker does not mean a requirement to use a single CPU thread.

## 19. RunPod filesystem

**FAIL / NOT RUN.** Actual APFS primitive tests exercise production file/directory fsync, atomic replace/rename, cross-process cache exclusion/release and RunLease/flock exclusion/release; these are Mac evidence only. The Linux probe requires genuine x86_64 Linux and writes only a new isolated probe directory.

The intended **pod-local** cache/model/temp/output/log/checkpoint filesystem must be identified and exercised, separately from a network volume containing immutable recovered inputs. Primitive success does not prove power-loss durability or a provider's underlying mount topology. Do not assume a conventional mount path is local. Foreign-host stale leases remain fail-closed. Provider/mount proof and off-pod evidence backup remain outstanding.

## 20. RunPod memory/disk

Actual `--fold-index 0 --horizon-minutes 60` counts, before membership/purge/embargo/finite filtering:

| Split | Observed Gold rows |
|---|---:|
| TRAIN | 3,350,407 |
| Validation | 518,400 |
| Cal-A | 262,080 |
| Cal-B | 262,080 |
| TEST | 529,920 |
| Total | **4,922,887** |

Shape-planning basis: **4,922,887 × 109 float64**. Raw NumPy shape bytes **4,292,757,464**; Arrow copy-planning bytes **10,239,604,960**; cache heuristic **7,726,963,435**; combined heuristic peak **27,741,452,822 bytes / 25.836 GiB**. LightGBM bins/histograms are not separately measured; generic copy/headroom terms are not an upper bound. Rows are `MEASURED`, whole-horizon fallback is `ESTIMATED_AVERAGE`, peak/cache are `ESTIMATED_HEURISTIC_PEAK`.

The Mac's physical/effective total is **16 GiB** with changing available RAM; disk planning passes. Thus **RESOURCE_ADMISSION=FAIL** and no cache is attempted. Use conservative initial target **>=64 GiB effective RAM, >=8 effective vCPU, >=150 GB pod-local disk**, CPU only; no paid SKU selected. Container v1/v2 usage, nested parent ceilings/headroom, quota/affinity and free disk are accounted for. See [resource_estimate_fold0_final.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/resource_estimate_fold0_final.json) and [actual_admission_and_external_gates.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/actual_admission_and_external_gates.json).

Transfer inputs were actually copied and hashed: original **793 files / 10,199,220,789 bytes**, four checkpoints, **140 sidecar files** and **1,840 descriptor supplement files** = **2,777 data/checkpoint/sidecar files / 10,998,003,736 bytes**. The committed source export and expected identity summary are additional small files. All four stage checkpoints validate, with **893 referenced records / 793 unique paths / zero hash failures**. No physical `/home/nssharath123` directory was needed. **RUNPOD_TRANSFER_SET=PASS means the local verified set is complete; actual remote transfer is NOT RUN.** See [transfer_staging_final.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/transfer_staging_final.json) and the final transfer inventory.

## 21. Target correctness

Synthetic/manual boundary tests cover **15/30/60/120m**: `feature_time=open[i+1]`, entry=`open[i+2]`, label end=`open[i+2+steps]`, raw return=`open[label_end]/open[entry]-1`. Actual Gold schema/timing checks also pass. Splits use actual `label_end_time` purge and **120-minute separation/embargo**, half-open UTC ranges. TRAIN owns model fitting and train-derived descriptors/weights; Validation owns stopping; Cal-A owns calibration; Cal-B owns threshold policy; TEST is fixed-policy evaluation after frozen identities. No August rows enter these paths.

## 22. Feature causality

**PASS for executed invariants**, not a formal proof of every future software change. Native, closed 12h/1d as-of mapping and cross-sectional features pass prefix/truncation tests with multiple symbols, gaps and future extension. Feature-only context is independent of future target values and label existence. The independent producer-key census and mandatory frozen sidecar close the measured all-peer loss case. No interpolation, synthesis or forward-fill was added. Annual HTF seed/gap definitions and redundancies remain documented frozen-design limitations for a future versioned study.

## 23. Universe causality

**PASS for current construction and tested causal membership.** Frozen Core20 at **2022-01-01**, registry `b2c973f0050f205e58672558`, Core hash `f71cdf65d161466037b34420`, research-universe hash `94a9ce4759dd8d3303841f13`. Actual selection reproduces the frozen Core20; all **16 active CORE membership sets** match stored sets. Existing `TRAIN_HISTORY_ONLY_V2` versus historical `FULL_FOLD_REQUIRED_RANGE_V1` excluded-member metadata/hash differences are recorded, not overwritten; 22 excluded-member metadata differences do not alter the active sets.

Future listing/delisting/liquidity/gap changes cannot choose earlier TRAIN membership in the tested path. Post-TRAIN active-member gaps block the fold instead of removing symbols with future knowledge. HNT remains; XPIN is not forced. This does not prove an exhaustive census of every failed historical instrument. See [universe_provenance_report.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/universe_provenance_report.json).

## 24. Calibration

Phase 7 supplies actual feature/label endpoint times to internal Cal-A timestamp selection and purges fit labels before the selection tail plus embargo. All four horizons and insufficient-data/identity fallback are tested. The selected calibrator may refit on its authorized Cal-A source; full-Cal-A reliability is in-sample diagnostics, not independent evidence. Frozen Phase 5 behavior/artifacts were not rewritten. See `test_phase7b_calibration_heldout` and `test_phase7b_calibration_separation`.

## 25. H0 ownership

Official H0 corrections use **purged Cal-A1**; H0 calibrator uses **disjoint Cal-A2**. Validation remains early stopping. Actual endpoint purge/embargo and overlap rejection are tested for all horizons; canonical metadata must declare `SEPARATE_ROWS_DISJOINT_FROM_EARLY_STOPPING`. H0 is outside the first G0 smoke. The low-level model API retains explicit legacy metadata for reuse cases; official runner behavior is the enforced scientific path.

## 26. Thresholding / NO_TRADE

**PASS.** Cal-B compares eligible thresholds with an explicit **NO_TRADE** option of zero trading expectancy. All eligible non-positive expectancy selects NO_TRADE; insufficient eligible samples also do not force trades. Cal-B owns selection, with fixed policy then evaluated on TEST. This repairs forced least-negative selection, not the uncertainty of a 30-trade development estimate.

## 27. Baselines

Zero-return, TRAIN-mean and Ridge controls with comparable scored-row accounting exist; current tests verify baseline deltas and per-timestamp cross-sectional IC. Ridge's capped/strided unweighted TRAIN sample is not identical to full symbol-balanced G0's objective. Disclose this and register matched paired OOS comparison before claiming model superiority. No real independent baseline advantage is established by unit fits or a plumbing smoke.

## 28. Metrics

Regression reporting includes RMSE, MAE, baseline deltas, directional accuracy with explicit zero-actual policy, coverage/finite-row accounting and IC variants. Cross-sectional IC ranks within timestamps with thin/constant guards; macro/micro measures remain distinct. Monitor best iteration, rounds since best, elapsed/RSS/disk and validation-only training progress. Observer tests protect stopping behavior.

Known open diagnostic: normalized-target live fixed-threshold precision/recall operates on target units, so its nominal bps label is not a raw-return threshold; undefined values render as zero for LightGBM. This does not affect the raw smoke or L2 stopping, but must be corrected/labeled before normalized diagnostic comparisons. TEST never drives live early stopping.

## 29. Economics

`PIPELINE_VALIDATED=false`, `TRADABILITY_VALIDATED=false`, **TRADABILITY=NOT_ESTABLISHED**. Static trade summaries are research diagnostics. A functioning regression fit would not prove profitability, edge, model selection validity or execution feasibility. The explicit tradability gate requires qualified funding/cost/policy/capital/concurrency/equity/risk/model/OOS/fold/sample/baseline/stress evidence with matching hashes/experiment identity; missing evidence fails. No portfolio, leverage, risk or execution engine was added. See [economic_status.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/economic_status.json) and [tradability_readiness.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/tradability_readiness.json).

## 30. Funding

**NOT_MODELLED** as settlement cash flow. Verified historical funding features do not deduct funding charges in trade returns. No positive net-return/tradability claim is authorized until separately approved timestamped funding-cost work and independent evidence exist.

## 31. Execution assumptions

**STATIC_COST_STRESS**: base/spread/slippage stress totals **11/14/20 bps**. **REFERENCE_EXECUTION_PRICE** at specified opens is not a simulated exchange fill. Size/depth/latency/queue/market impact/partial fills/settlement/capital constraints are not modeled. Trade-level Sharpe/drawdown proxies must not be labeled portfolio Sharpe, portfolio maximum drawdown or Calmar; those remain unavailable.

## 32. Multiple testing

48 primary specifications over 16 folds create selection risk. Current ranking/success helpers are descriptive, reject duplicates/mixed identities, and do not supply discovery p-values from early-stopped Validation skill. Bonferroni cannot repair invalid marginal p-values or reused temporal evidence. A preregistered independent, dependence-aware evaluation and complete trial inventory are still required before inferential or tradability claims. No such real multi-fold evidence exists here.

## 33. Holdout safety

**AUGUST=LOCKED_UNUSED**, `used=false`, `evaluation_authorized=false`; July remains unused. Phase 7 research cutoff is **2026-07-01T00:00:00Z exclusive**. Actual Gold/sidecar bounds and runtime configuration checks enforce this research path. No July/August outcomes were accessed or evaluated. Generic legacy download surfaces and stale examples are broader than this canonical path; they were not executed and are not claimed to be an adversarial filesystem access-control system. Frozen Phase 1–6 artifacts and HNT/XPIN methodology were preserved.

## 34. Live-order isolation

**PASS.** Static research import boundaries and seven actual safety tests execute with zero skips. `CRYPTO_AI_RESEARCH_MODE=1` is set by official admission. The legacy CoinSwitch module now raises at import before optional dependencies or live configuration, with its existing constructor guard retained. No `main_trader.py`, `pipeline/live_trader.py`, `dashboard.py`, order method, account query or credential-reading command was executed. Legacy code remains deprecated and excluded from the installable research package.

## 35. Error register

This is the complete consolidated disposition of the supplied review findings plus defects reproduced during this task. Aliases map older IDs to current issues; duplicates are consolidated, not silently dropped. Severity and architectural scores are judgments. `RunPod/Smoke/Tradability` blockers are current **YES/NO** values, not a statement that every historical issue still exists. External `FAIL` statuses below can mean required evidence is absent. Full machine-readable fields are in [master_error_register.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/master_error_register.json).

### MR-01 — source integration (CRITICAL; FIXED)

Aliases: C-01; H-01. File/function: [src/crypto_ai/phase7/universe.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/universe.py), `select_fold_active_universe`.

**Problem:** Historical main lacked the causal membership and hardening integration.

**Evidence:** Current source, canonical Core20 reconstruction and full committed-source suite.

**Reproduced:** Historical finding; absent on current integrated branch.

**Scientific consequence:** Future-gap membership would bias historical comparisons.

**Operational consequence:** Wrong checkout could launch incompatible research.

**Fix/disposition:** Use the verified source commit and content identities, preserving the earlier branches.

**Test:** test_membership_gap_causality; test_phase7a; full suite

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-02 — container memory (HIGH; FIXED)

Aliases: F1. File/function: [src/crypto_ai/phase7/runtime.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/runtime.py), `_container_adjusted_memory`.

**Problem:** Host RAM could exceed container limits; nested parent headroom and missing usage also mattered.

**Evidence:** Real new v1/v2/nested resource regression tests; actual Mac rejection.

**Reproduced:** YES in isolated cgroup fixtures.

**Scientific consequence:** No feature or target change.

**Operational consequence:** False admission could cause OOM and partial artifacts.

**Fix/disposition:** Use smallest effective ceiling and ancestor headroom; missing finite-limit usage fails closed.

**Test:** test_final_runtime_guards; test_phase7a_resource_estimate

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-03 — effective CPU budget (HIGH; FIXED)

Aliases: F5. File/function: [src/crypto_ai/phase7/runtime.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/runtime.py), `cpu_availability / ComputeBudget.resolve`.

**Problem:** Host CPU count ignored affinity and cgroup quota.

**Evidence:** Four tested host/affinity/fractional quota combinations; models use the same ceiling.

**Reproduced:** YES.

**Scientific consequence:** Thread counts can affect numerical fit reproducibility and are recorded.

**Operational consequence:** Oversubscription and misleading telemetry.

**Fix/disposition:** Minimum of host, affinity and conservative whole quota; clamp estimator threads; reject explicit over-budget settings.

**Test:** test_final_runtime_guards; test_runtime_backend

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-04 — feature context (HIGH; FIXED)

Aliases: F6; IA-05; LH-04; M-01. File/function: [src/crypto_ai/phase7/training.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/training.py), `_context_sidecar_path / _load_fold_context_source`.

**Problem:** Gold union loses 81 independent feature keys, including four all-peer timestamps; old sidecar requirement named one dataset.

**Evidence:** Real independent M-01 census, frozen sidecar hash/coverage validation and generic missing-context tests.

**Reproduced:** YES on recovered production data.

**Scientific consequence:** Future label availability must not decide causal peer context.

**Operational consequence:** Preparation must stop if approved context is absent.

**Fix/disposition:** Require verified feature-only context for every dataset; bind sidecar to Gold/config/registry/universe and owner approval. Preserve Gold.

**Test:** test_context_sidecar; test_feature_truncation_invariance; m01_context_coverage.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-05 — canonical enumeration (HIGH; FIXED)

Aliases: New forensic-selection defect. File/function: [src/crypto_ai/phase7/feature_census.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/feature_census.py), `canonical_parquet_paths / _keys_from_parquet`.

**Problem:** Recursive discovery could select forensic/unreferenced Parquet files.

**Evidence:** 67 preserved extras excluded from canonical sets; poison-file and partial-reference regressions.

**Reproduced:** YES with an isolated poisoned fixture.

**Scientific consequence:** Unmanifested bytes could contaminate a census.

**Operational consequence:** Non-reproducible discovery or accidental partial reads.

**Fix/disposition:** Manifest-only enumeration, explicit-file support, path and duplicate validation; stream keys.

**Test:** test_feature_census; forensic_selection_assertions.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-06 — transfer completeness (HIGH; FIXED)

Aliases: New transfer dependency defect. File/function: [scripts/closure/stage_smoke_transfer.py](/Users/cortex/Projects/crypto2.0/scripts/closure/stage_smoke_transfer.py), `descriptor_transfer_paths`.

**Problem:** The exact 793-file list omitted daily descriptor partitions and their required Bronze lineage.

**Evidence:** Actual staged _fold_descriptors failure before repair; 20 recovered/staged descriptors now hash identically.

**Reproduced:** YES on the clean local staging tree.

**Scientific consequence:** Dropping/replacing descriptors could alter causal membership or clusters.

**Operational consequence:** Smoke would fail before preparation despite complete stage checkpoint records.

**Fix/disposition:** Add exactly 1,840 Fold-0 TRAIN descriptor dependency files, four stage checkpoints and 140 sidecar files.

**Test:** descriptor_transfer_equivalence.json; transfer_staging_final.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-07 — legacy relocation (HIGH; PARTIALLY_FIXED)

Aliases: F2. File/function: [src/crypto_ai/phase7/runtime.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/runtime.py), `resolve_runtime_input_path / legacy_checkpoint_roots`.

**Problem:** Lightning absolute paths need explicit relocation on a new host.

**Evidence:** All 893 checkpoint references resolve and hash correctly in local staging; four stages complete; descriptor equality.

**Reproduced:** Local relocation PASS; actual Linux relocation NOT RUN.

**Scientific consequence:** Do not rewrite historical identity or accept changed source bytes.

**Operational consequence:** Missing or unmapped inputs block resume.

**Fix/disposition:** Explicit longest-prefix mappings, traversal rejection, unchanged historical checkpoints. Repeat on actual Linux.

**Test:** test_runtime_backend; transfer_staging_final.json

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-08 — portable source freeze (HIGH; PARTIALLY_FIXED)

Aliases: F3. File/function: [src/crypto_ai/phase7/identity_summary.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/identity_summary.py), `identity_summary`.

**Problem:** Transferred source must match all six content identities; an older checkout is unsafe.

**Evidence:** Committed source export and six-digest Mac/export equality; no Git dependency.

**Reproduced:** Portable local export PASS; RunPod comparison NOT RUN.

**Scientific consequence:** Mixed source/data identities invalidate scientific comparability.

**Operational consequence:** Wrong source could reuse incompatible reports or cache.

**Fix/disposition:** One identity-summary command, expected-output comparison and committed-source checksum manifest.

**Test:** test_final_runtime_guards; identity_source_export.json

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-09 — Linux and filesystem (HIGH; OPEN)

Aliases: F4; LH-03; IA-09. File/function: [src/crypto_ai/phase7/filesystem_probe.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/filesystem_probe.py), `qualify_filesystem / verify_linux`.

**Problem:** Genuine Linux/x86_64 and the intended local filesystem have not been exercised.

**Evidence:** Actual Mac calls refuse; no supported local Linux runtime found. Native cross-process primitive tests pass only as Mac evidence.

**Reproduced:** External verification NOT RUN.

**Scientific consequence:** No numerical or filesystem portability claim is established.

**Operational consequence:** Unknown Linux dependency, fsync, rename, lease/cache-lock behavior.

**Fix/disposition:** Prepared genuine-platform verifier and isolated production-primitive probe. Run on an authorized Linux host and intended local disk.

**Test:** test_final_runtime_guards; actual_admission_and_external_gates.json

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-10 — resource estimation (MEDIUM; FIXED)

Aliases: F8; IA-19. File/function: [src/crypto_ai/phase7/resource_estimate.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/resource_estimate.py), `observed_fold_rows / estimate_spec_resources`.

**Problem:** Whole-horizon average was not Fold-0 size and must not be called an upper bound.

**Evidence:** Actual CLI counts 4,922,887 rows; half-open and poison-unreferenced-file test; 25.836 GiB heuristic.

**Reproduced:** YES.

**Scientific consequence:** No data selection or fitting semantics change.

**Operational consequence:** Misleading planning and avoidable OOM risk.

**Fix/disposition:** --fold-index and --horizon-minutes count canonical time/horizon rows; label measured counts and heuristic memory separately.

**Test:** test_final_runtime_guards; resource_estimate_fold0.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-11 — real cache qualification (HIGH; OPEN)

Aliases: Prepared boundary; H-04; IA-19. File/function: [src/crypto_ai/phase7/prepared_cache.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/prepared_cache.py), `PreparedDataCache / prepare-only runner`.

**Problem:** No current real Fold-0 cache has passed prepare-only publication and read-only reload.

**Evidence:** Mac has 16 GiB versus 25.8 GiB heuristic; canonical admission also requires at least 64 GiB.

**Reproduced:** Actual resource refusal reproduced; real cache NOT RUN.

**Scientific consequence:** Row/target/weight/order equivalence cannot be claimed from fixture tests alone.

**Operational consequence:** Preparation could still OOM or expose an unmeasured hot path.

**Fix/disposition:** Use authorized >=64 GiB/8 effective CPU/150 GB local environment; prepare one cache, profile and qualify reload before any real fit.

**Test:** test_prepared_cache; real-cache gate remains external

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-12 — sidecar hashing (LOW; DEFERRED)

Aliases: F7. File/function: [src/crypto_ai/phase7/context_sidecar.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/context_sidecar.py), `load_sidecar_source`.

**Problem:** Large frozen sidecar partitions can be hashed repeatedly.

**Evidence:** Source review; no production RSS/runtime profile of preparation.

**Reproduced:** Repeated hashes exist; performance cost not measured.

**Scientific consequence:** mtime/size alone cannot prove unchanged content.

**Operational consequence:** Possible additional read time.

**Fix/disposition:** Defer memoization until trusted immutable-file lifetime can be proved; retain every integrity check and frozen producer code identity.

**Test:** Current sidecar tamper rejection tests retained

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-13 — Git maintenance (LOW; FIXED)

Aliases: F9. File/function: [.git/objects](/Users/cortex/Projects/crypto2.0/.git/objects), `git prune`.

**Problem:** 288 stale tmp_obj files were Git garbage.

**Evidence:** Temporary-only dry run; object-store backup; all 2,551 valid IDs unchanged including 152 unreachable objects; fsck PASS.

**Reproduced:** YES; post-maintenance garbage=0.

**Scientific consequence:** None.

**Operational consequence:** Noisy Git diagnostics and wasted object storage.

**Fix/disposition:** Normal git prune with every unreachable valid object protected as an additional head; no working files removed.

**Test:** git_maintenance.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-14 — floating equivalence (LOW; FIXED)

Aliases: F10. File/function: [src/crypto_ai/phase7/context_sidecar.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/context_sidecar.py), `context_source_projection / read_sidecar`.

**Problem:** Two volatility columns differed from historical producer by tiny round-off amounts.

**Evidence:** Preserved full numerical proof; current frozen partition hashes unchanged.

**Reproduced:** YES historically: max 3.968e-16 and 5.204e-18.

**Scientific consequence:** Exact byte equality is stronger than the pre-existing scientific numerical contract.

**Operational consequence:** Recomputation would invalidate a frozen input unnecessarily.

**Fix/disposition:** Keep rtol=1e-9, atol=1e-12 and identical NaN masks; transfer and consume v3 unchanged.

**Test:** sidecar_validation.json; test_context_sidecar

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-15 — resolved execution configuration (MEDIUM; FIXED)

Aliases: New environment contract. File/function: [src/crypto_ai/phase7/run_contract.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/run_contract.py), `validate_environment`.

**Problem:** Unknown PHASE7_* names were silently ignored.

**Evidence:** Typo rejection tests without logging values; fully resolved config/path/budget/hardening/floor records.

**Reproduced:** YES with PHASE7_CAHCE_MODE.

**Scientific consequence:** Unintended settings could create mixed experiments.

**Operational consequence:** Silent operator mistakes.

**Fix/disposition:** Explicit known-name set; fail unknown names; immutable content-addressed execution manifests.

**Test:** test_final_runtime_guards; test_admission

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-16 — canonical smoke admission (HIGH; FIXED)

Aliases: Cloud approval strengthening; H-03; IA-11. File/function: [src/crypto_ai/phase7/admission.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/admission.py), `admit_official_training / run_phase7_training`.

**Problem:** A cloud flag alone did not bind the exact authorized run; generic or direct calls could launch broader work.

**Evidence:** Canonical CLI and public training wrapper share admission; generic CLI, full grid and missing/mismatched/expired contracts reject.

**Reproduced:** YES in regression tests; actual Mac is refused before preparation.

**Scientific consequence:** Mixing spec/fold/data/source scope would invalidate comparisons.

**Operational consequence:** Unapproved compute or incompatible resume.

**Fix/disposition:** Owner-supplied exact six-digest/config/dataset/spec/fold/CORE/CPU/worker/mode binding plus finite cost ceiling/deadline; no real approval created.

**Test:** test_admission; test_final_runtime_guards; test_standalone_training_remediation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-17 — external operations (HIGH; OPEN)

Aliases: IA-23; M-05. File/function: [src/crypto_ai/phase7/run_contract.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/run_contract.py), `validate_owner_approval`.

**Problem:** No existing Linux endpoint, fresh owner cost/deadline contract, independently tested stop/billing controller or off-host evidence workflow was supplied.

**Evidence:** Pending endpoint question; no cloud API call, provisioning, spending or actual provider-controller test.

**Reproduced:** Missing prerequisites confirmed; provider operation NOT RUN.

**Scientific consequence:** No predictive or portability evidence can be inferred.

**Operational consequence:** Billing/deadline and recovery durability remain unqualified.

**Fix/disposition:** Owner supplies authorized host and contract; rehearse external deadline stop and evidence export. New contract validation is admission-time, not a billing controller.

**Test:** Contract parser tests pass; provider stop rehearsal remains required

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-18 — statistical inference (HIGH; FIXED)

Aliases: IA-01; LH-01. File/function: [src/crypto_ai/phase7/hardening.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/hardening.py), `descriptive_rank_specs / rank_specs_with_correction`.

**Problem:** Validation stopping/selection scores cannot supply valid independent discovery p-values.

**Evidence:** Current helper returns descriptive ranking and p-values NOT_APPLICABLE.

**Reproduced:** Historical problem confirmed; inferential claim now removed.

**Scientific consequence:** No discovery/edge claim from post-selection development scores.

**Operational consequence:** Misleading success labels would drive bad research decisions.

**Fix/disposition:** Demote ranking to descriptive; preserve trial ledger and require precommitted independent evidence.

**Test:** test_phase7_final_integrity; test_selection_protocol_file

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-19 — result identity and aggregation (HIGH; FIXED)

Aliases: IA-02; IA-04; LH-16. File/function: [src/crypto_ai/phase7/result_integrity.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/result_integrity.py), `validate_result_set / experiment_control_identity`.

**Problem:** Duplicates or changed control settings must not masquerade as independent folds or one experiment.

**Evidence:** Duplicate/mixed/missing/non-COMPLETE rejection; active hardening and control source mutations change identity.

**Reproduced:** YES in regression fixtures.

**Scientific consequence:** Trial/fold counts and success could be inflated.

**Operational consequence:** Silent incompatible resume.

**Fix/disposition:** Canonical unique result identities, exact fold sets and separate preparation/science/control/protocol bindings.

**Test:** test_phase7_final_integrity; test_result_publication

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-20 — selection chronology (HIGH; FIXED)

Aliases: IA-03. File/function: [src/crypto_ai/phase7/selection_chronology.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/selection_chronology.py), `build_overlap_matrix / validate selection protocol`.

**Problem:** Earlier TEST periods recur in later development segments.

**Evidence:** All 16 frozen calendars reproduce with 120 overlap records.

**Reproduced:** YES on the actual calendar.

**Scientific consequence:** Historical ranking is not independent confirmation.

**Operational consequence:** Ambiguous result labeling.

**Fix/disposition:** Enforce DESCRIPTIVE_REPORT / DEVELOPMENT_SELECTION / INDEPENDENT_EVALUATION roles; reject contaminated confirmation.

**Test:** test_selection_protocol_file; test_phase7_final_integrity

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-21 — funding economics (HIGH; OPEN)

Aliases: IA-06; LH-02. File/function: [src/crypto_ai/phase7/economics.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/economics.py), `build_oos_trades`.

**Problem:** Funding settlement cash flow is NOT_MODELLED, despite available funding features.

**Evidence:** Actual economic status and source formula.

**Reproduced:** YES by code inspection; no real trading evidence.

**Scientific consequence:** Net strategy returns are not established.

**Operational consequence:** Cannot qualify economic viability.

**Fix/disposition:** Implement only in separately authorized economic work with timestamped cash-flow tests; keep current status explicit.

**Test:** test_tradability_readiness rejects missing funding qualification

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-22 — execution and portfolio realism (HIGH; OPEN)

Aliases: IA-07; IA-08; LH-02. File/function: [src/crypto_ai/phase7/economics.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/economics.py), `build_oos_trades / trading_metrics`.

**Problem:** Static costs/reference prices and trade-level proxies omit realistic fills, capital, concurrency and portfolio equity.

**Evidence:** STATIC_COST_STRESS 11/14/20 bps; REFERENCE_EXECUTION_PRICE; portfolio fields NOT_AVAILABLE.

**Reproduced:** YES as declared model limits.

**Scientific consequence:** Profitability and portfolio Sharpe/drawdown/Calmar cannot be inferred.

**Operational consequence:** A successful fit can be mistaken for a tradeable system.

**Fix/disposition:** Fail-closed tradability evidence gate; no portfolio/risk/live engine added under this task.

**Test:** test_tradability_readiness

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-23 — Cal-A ownership (MEDIUM; FIXED)

Aliases: IA-13; L-03; L-05. File/function: [src/crypto_ai/phase5/calibration.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase5/calibration.py), `fit_calibrator`.

**Problem:** Internal calibrator selection must split timestamps and purge actual label endpoints, not adjacent row slices.

**Evidence:** Current Phase 7 call supplies feature/label times and 120-minute embargo; all-horizon tests.

**Reproduced:** Historical defect; current regressions PASS.

**Scientific consequence:** Otherwise identity-vs-linear selection is optimistic.

**Operational consequence:** Bad calibration choice or ambiguous diagnostics.

**Fix/disposition:** Preserve frozen Phase 5 behavior; Phase 7 opts into temporal selection and identity fallback when insufficient.

**Test:** test_phase7b_calibration_heldout; test_phase7b_calibration_separation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-24 — H0 correction ownership (MEDIUM; FIXED)

Aliases: IA-14; LH-05; L-04. File/function: [src/crypto_ai/phase7/models.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/models.py), `split_calibration_a_for_h0 / _run_one`.

**Problem:** Early-stopping Validation must not also fit H0 correction parameters in the official runner.

**Evidence:** H0 corrections use purged Cal-A1; calibrator uses disjoint Cal-A2; official metadata assertion.

**Reproduced:** Historical reuse confirmed; canonical path repaired.

**Scientific consequence:** Architecture comparison would otherwise favor H0.

**Operational consequence:** Unexpected ownership can hide behind generic model API.

**Fix/disposition:** Keep official disjoint slices and exact-label-end purge. Legacy low-level metadata can describe reuse, but the official runner rejects it.

**Test:** test_h0_data_ownership; test_pretraining_integration

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-25 — threshold policy (MEDIUM; FIXED)

Aliases: IA-15. File/function: [src/crypto_ai/phase7/economics.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/economics.py), `select_cal_b_thresholds`.

**Problem:** Least-negative eligible threshold must not force trading.

**Evidence:** All-negative/zero expectancy and no-eligible-threshold regression cases.

**Reproduced:** YES in synthetic policy tests.

**Scientific consequence:** Forced negative expected-value development policy.

**Operational consequence:** Unnecessary trades.

**Fix/disposition:** Explicit zero-return NO_TRADE candidate; choose it for non-positive candidate expectancy.

**Test:** test_phase7b_hardening; test_standalone_training_remediation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-26 — baseline fairness (MEDIUM; PARTIALLY_FIXED)

Aliases: IA-16; LH-13. File/function: [src/crypto_ai/phase7/hardening.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/hardening.py), `score_baselines / _ridge_predict`.

**Problem:** Ridge sampling/weighting differs from full symbol-balanced G0, and development metrics are not independent TEST evidence.

**Evidence:** Current source; train-mean and cross-sectional IC controls tested on identical scored rows.

**Reproduced:** YES for objective/sample difference.

**Scientific consequence:** A measured advantage could reflect the estimand or sample budget.

**Operational consequence:** Overstated model superiority.

**Fix/disposition:** Disclose differences; align matched training controls and pre-register paired OOS scoring before selection claims.

**Test:** test_phase7a_final_metrics_and_baselines

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-27 — target inverse (LOW; FIXED)

Aliases: IA-17. File/function: [src/crypto_ai/phase7/training.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/training.py), `_to_raw_predictions`.

**Problem:** Normalized targets and inverse need the same effective floor, including zero/subfloor scales.

**Evidence:** Current effective_normalization_scale is shared; boundary tests.

**Reproduced:** Historical defect; fixed tests PASS.

**Scientific consequence:** Wrong reconstructed raw signal at tiny scales.

**Operational consequence:** Misleading normalized-target economics; raw smoke unaffected.

**Fix/disposition:** Use identical versioned floor in both directions.

**Test:** test_standalone_training_remediation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-28 — live diagnostic units (LOW; OPEN)

Aliases: IA-18. File/function: [src/crypto_ai/phase7/training_metrics.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/training_metrics.py), `display_metrics`.

**Problem:** Fixed precision/recall threshold is applied in target units, so normalized runs cannot interpret it as raw bps; undefined scores render as zero.

**Evidence:** Current source still passes LightGBM arrays directly.

**Reproduced:** YES by source inspection; no normalized real-data run.

**Scientific consequence:** Misleading diagnostics across target types; L2 stopping remains unchanged.

**Operational consequence:** Monitoring ambiguity outside raw smoke.

**Fix/disposition:** Label units explicitly or use aligned scales in a later version; preserve undefined values in JSON.

**Test:** Additional normalized-unit test still needed; raw observer tests pass

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-29 — canonical publication (MEDIUM; FIXED)

Aliases: IA-20; LH-12. File/function: [src/crypto_ai/phase7/training.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/training.py), `_run_one / publication loop / recovery inspection`.

**Problem:** A report or CSV append alone must not make an experiment COMPLETE.

**Evidence:** Canonical result plus receipt precedes checkpoint completion; recovery validates five-file new contract; ledger-derived CSV.

**Reproduced:** YES in crash/partial/duplicate/corruption tests.

**Scientific consequence:** Missing/duplicate trials could bias analysis.

**Operational consequence:** Crash windows could look complete.

**Fix/disposition:** Authoritative ledger and hashed receipt; CSV is rebuildable; historical three-file checkpoints explicitly distinct.

**Test:** test_result_publication; test_phase7_final_integrity; test_pre_lightning_hardening

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-30 — artifact trust (MEDIUM; PARTIALLY_FIXED)

Aliases: IA-21; L-08. File/function: [src/crypto_ai/phase7/model_registry.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/model_registry.py), `verify_registered_model / load_model`.

**Problem:** Generic joblib deserialization still trusts local provenance unless strict registry mode is selected; hashes are not signatures.

**Evidence:** Canonical runner verifies report/model hash binding before deserialization; external generic load policy remains opt-in.

**Reproduced:** YES by source inspection.

**Scientific consequence:** Matching bytes do not prove scientific correctness.

**Operational consequence:** Untrusted external model loading remains unsafe.

**Fix/disposition:** Keep smoke fresh-model-only; require strict portable trust/receipt policy before importing external models.

**Test:** test_pre_lightning_hardening; model registry tests

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-31 — feature definition limits (MEDIUM; DEFERRED)

Aliases: IA-22. File/function: [src/crypto_ai/phase7/features.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/features.py), `generate_multiasset_features / annual HTF seed`.

**Problem:** Some age/high/drawdown features are redundant; row-based pair statistics and finite annual EMA warmup have documented semantics.

**Evidence:** Formula review; causality/truncation tests pass.

**Reproduced:** Definition limits confirmed; predictive materiality NOT MEASURED.

**Scientific consequence:** Redundancy and chunk/gap interpretation, not demonstrated future leakage.

**Operational consequence:** Extra complexity and possible version-dependent behavior.

**Fix/disposition:** Preserve immutable Gold; measure full-vs-chunked/gap behavior and version any later ablation.

**Test:** test_feature_truncation_invariance; future ablation gate

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-32 — universe representativeness (MEDIUM; PARTIALLY_FIXED)

Aliases: IA-24; I-01. File/function: [src/crypto_ai/phase7/universe.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/universe.py), `select_core_universe`.

**Problem:** Archive-based historical candidate coverage is not proof of every historically tradable failed instrument; CORE excludes later listings by design.

**Evidence:** Actual frozen Core20 and all 16 active sets reproduced; HNT retained; registry provenance report.

**Reproduced:** Causal construction PASS; exhaustive historical coverage NOT ESTABLISHED.

**Scientific consequence:** Residual representativeness/archive selection limit.

**Operational consequence:** Do not force retroactive replacements.

**Fix/disposition:** Keep the frozen methodology; any completeness study or alternative universe needs a separately approved version.

**Test:** test_membership_gap_causality; universe_provenance_report.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-33 — obsolete survivor claim (MEDIUM; NOT_REPRODUCED)

Aliases: LH-07. File/function: [src/crypto_ai/phase7/universe.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/universe.py), `select_core_universe`.

**Problem:** Earlier review claimed construction from today's surviving coins.

**Evidence:** Historical registry, cutoff-known descriptors, delisted candidates and HNT evidence contradict that claim.

**Reproduced:** NOT REPRODUCED.

**Scientific consequence:** Do not infer a proven survivor leak from an unsupported historical review sentence.

**Operational consequence:** Wrong remediation could remove HNT or force XPIN.

**Fix/disposition:** Supersede with MR-32's narrower representativeness limitation.

**Test:** universe_provenance_report.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-34 — TEST release boundary (MEDIUM; PARTIALLY_FIXED)

Aliases: M-02. File/function: [src/crypto_ai/phase7/folds.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/folds.py), `MultiAssetFoldData.release_test`.

**Problem:** TEST ownership is a checked/logged API boundary, not adversarial memory access control; identical-identity rerelease is allowed and logged.

**Evidence:** Mismatch/reuse logs and canonical freeze-before-release tests.

**Reproduced:** Historical weak check repaired; physical _test access remains a library trust boundary.

**Scientific consequence:** Never treat repeated release as fresh independent evidence.

**Operational consequence:** A caller bypassing the canonical API can violate protocol.

**Fix/disposition:** Canonical checked identities and chronology; retain explicit architectural limitation.

**Test:** test_pretraining_integration; test_phase7b_test_access

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-35 — cache and environment identity (MEDIUM; FIXED)

Aliases: M-03; M-09; LH-11. File/function: [src/crypto_ai/phase7/preparation_identity.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/preparation_identity.py), `preparation_source_identity / _prepared_cache_identity`.

**Problem:** Cache reuse must be sensitive to matrix semantics and platform/environment without being invalidated by pure reporting.

**Evidence:** Mutation tests for ordering, target/context/fold/member/dtype; logging/control edits excluded; architecture environment tests.

**Reproduced:** YES in regression fixtures.

**Scientific consequence:** Improper reuse could mix scientific inputs.

**Operational consequence:** Over-invalidation wastes preparation; under-invalidation reuses wrong arrays.

**Fix/disposition:** Separate preparation/science/control identities; no Mac-built cache is claimed qualified for Linux.

**Test:** test_preparation_identity; test_environment_platform_identity

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-36 — lock/crash recovery (MEDIUM; PARTIALLY_FIXED)

Aliases: M-04; M-05. File/function: [src/crypto_ai/phase7/prepared_cache.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/prepared_cache.py), `_publication_lock / RunLease`.

**Problem:** Stale locks require PID/start-time proof; foreign-host liveness cannot be guessed.

**Evidence:** Stale-lock recovery, live-owner rejection, ENOSPC/kill boundaries and actual native cross-process probe.

**Reproduced:** Current fixture/native behavior PASS; chosen Linux filesystem NOT RUN.

**Scientific consequence:** Partial state cannot be treated as a result.

**Operational consequence:** Fail-closed recovery can require operator action after host migration.

**Fix/disposition:** Preserve evidence and explicit dead-owner reconciliation; use qualified local storage, not an assumed network-volume lease.

**Test:** test_pre_lightning_hardening; test_final_runtime_guards

**Blockers — RunPod:** YES; **Smoke:** YES; **Tradability:** NO.

### MR-37 — post-TRAIN data gaps (MEDIUM; FIXED)

Aliases: M-06. File/function: [src/crypto_ai/phase7/folds.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/folds.py), `slice_multiasset_fold`.

**Problem:** Active-member post-TRAIN gaps intentionally block a fold rather than removing a symbol using future knowledge.

**Evidence:** Typed PostTrainDataGapError and causal membership/gap tests; recovered provenance report.

**Reproduced:** Fail-closed behavior reproduced.

**Scientific consequence:** Permissive symbol removal would introduce membership lookahead.

**Operational consequence:** A blocked fold is a data-quality outcome, not bad model performance.

**Fix/disposition:** Keep the blocker; investigate exact source coverage under existing immutable policy if encountered.

**Test:** test_membership_gap_causality; test_causal_segment_quarantine

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-38 — legacy acquisition hygiene (MEDIUM; DEFERRED)

Aliases: M-07; L-09. File/function: [src/crypto_ai/cli.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/cli.py), `generic download/market-data commands`.

**Problem:** Generic historical download surfaces and legacy examples are broader than the current Phase 7 cutoff; frozen Phase 6 config is not rewritten here.

**Evidence:** Source inspection; no acquisition command executed. Phase 7 config/Gold/sidecar enforce July 1 exclusive.

**Reproduced:** Generic-surface limitation confirmed; no forbidden data access occurred.

**Scientific consequence:** An unrelated manual command could violate the owner's unused-data policy.

**Operational consequence:** Documentation/entrypoint confusion.

**Fix/disposition:** Use only canonical guarded Phase 7 paths; separately approve global CLI hygiene changes without mutating frozen phase artifacts.

**Test:** Phase 7 cutoff tests pass; generic acquisition hardening deferred

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-39 — research order isolation (HIGH; FIXED)

Aliases: M-08; LH-15. File/function: [pipeline/coinswitch_client.py](/Users/cortex/Projects/crypto2.0/pipeline/coinswitch_client.py), `module import / client constructor`.

**Problem:** Legacy order-capable code remains in the repository, and an optional-dependency skip hid the import guard.

**Evidence:** Actual import in research mode now raises before aiohttp/cryptography/live config; seven isolation tests execute with no skips.

**Reproduced:** YES: prior skipped import boundary repaired.

**Scientific consequence:** Research must have no order side effects.

**Operational consequence:** Accidental credential/config access or orders.

**Fix/disposition:** Early module guard plus existing constructor guard, static import boundary and research flag. No credentials accessed or orders sent.

**Test:** test_research_import_boundary; test_live_order_isolation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-40 — accounting and metrics (LOW; FIXED)

Aliases: L-01; L-02; LH-12; LH-13. File/function: [src/crypto_ai/phase7/training.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/training.py), `finite_row_accounting / score_baselines`.

**Problem:** Zero actuals, finite filtering and result provenance require explicit accounting; metrics must compare matching scored keys.

**Evidence:** Zero-return/finite-mask/provenance/XS-IC tests; result columns include seed/iteration/timing.

**Reproduced:** Historical omissions; current accounting tests PASS.

**Scientific consequence:** Unreported coverage differences can confound comparisons.

**Operational consequence:** Weak audit trail.

**Fix/disposition:** Explicit counts, zero-actual denominator policy, comparable coverage reporting and provenance fields.

**Test:** test_independent_review_accounting; test_phase7a_final_metrics_and_baselines

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-41 — launcher and durability portability (LOW; PARTIALLY_FIXED)

Aliases: H-02; L-06. File/function: [scripts/closure/verify_linux_external.sh](/Users/cortex/Projects/crypto2.0/scripts/closure/verify_linux_external.sh), `software verifier / durable_fsync`.

**Problem:** Historical launchers assumed one uv home, GNU commands and plain Mac fsync.

**Evidence:** Portable canonical script resolves uv; five executed shell rotation tests; F_FULLFSYNC fallback; native primitive tests.

**Reproduced:** Current Mac code passes; actual Linux proof belongs to MR-09.

**Scientific consequence:** No change to frozen scientific values.

**Operational consequence:** Failed launcher or weaker flush behavior.

**Fix/disposition:** Use canonical verifier and existing portable worker tooling; qualify intended Linux filesystem separately.

**Test:** test_log_rotation; test_pre_lightning_hardening

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-42 — production invariants (LOW; FIXED)

Aliases: L-07. File/function: [src/crypto_ai/phase7/registry.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/registry.py), `registry / acquisition validation`.

**Problem:** assert-based production invariants can disappear under python -O.

**Evidence:** Current reviewed historical sites use explicit exceptions; old assertions remain only as explanatory comments.

**Reproduced:** Historical finding; those current sites repaired.

**Scientific consequence:** Invalid registry/source evidence must fail closed.

**Operational consequence:** Optimized Python must not remove checks.

**Fix/disposition:** Retain explicit validation errors and regression tests.

**Test:** test_config_registry_universe; acquisition tests

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-43 — legacy and documentation drift (LOW; PARTIALLY_FIXED)

Aliases: L-10; LH-17; I-03; I-05. File/function: [docs/reviews/CRYPTO2_FINAL_MASTER_READINESS_REPORT_20261106.md](/Users/cortex/Projects/crypto2.0/docs/reviews/CRYPTO2_FINAL_MASTER_READINESS_REPORT_20261106.md), `authoritative report / legacy inference modules`.

**Problem:** Old reports/configs and duplicate deprecated inference paths remain; earlier PASS statements can be stale.

**Evidence:** Preserved original files and dirty review work; current report names its verified commit and executed evidence.

**Reproduced:** YES by repository inventory.

**Scientific consequence:** Old conclusions must not override current measured gates.

**Operational consequence:** Maintenance confusion.

**Fix/disposition:** Use this report as authority; preserve legacy source and defer consolidation to separately approved work.

**Test:** Final report section/evidence validation

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-44 — model robustness (MEDIUM; DEFERRED)

Aliases: LH-06; LH-08; LH-18. File/function: [src/crypto_ai/phase7/config.py](/Users/cortex/Projects/crypto2.0/src/crypto_ai/phase7/config.py), `ModelConfig / L2 objective`.

**Problem:** Single-seed defaults, outlier-sensitive L2 and unmeasured regime robustness do not establish an edge.

**Evidence:** Configuration and absence of completed real specifications; MAE/IC/baseline diagnostics exist.

**Reproduced:** Model-design limits confirmed; adverse performance NOT REPRODUCED.

**Scientific consequence:** Sensitivity and stability remain unknown.

**Operational consequence:** Do not tune a grid from smoke diagnostics.

**Fix/disposition:** After authorized pilot protocol, evaluate registered robustness/seed/regime controls on suitable independent evidence.

**Test:** Existing fit/metric tests; no real robustness result

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-45 — qualification protocol (MEDIUM; OPEN)

Aliases: LH-09; I-02; I-04. File/function: [configs/research/phase7_selection_chronology_v1.json](/Users/cortex/Projects/crypto2.0/configs/research/phase7_selection_chronology_v1.json), `protocol / success criteria`.

**Problem:** A passing pipeline or literal holdout flags do not establish owner-approved economic criteria or independent evidence.

**Evidence:** Precommitted chronology and descriptive-only success helpers; observer-equivalence regression; holdout checks.

**Reproduced:** No completed 48-spec Fold-1 report set or independent pilot exists.

**Scientific consequence:** Qualification is not yet evaluable, not failed performance.

**Operational consequence:** Full grid remains unauthorized.

**Fix/disposition:** Preserve immutable holdout status; require fresh versioned pilot approval and independent evaluation before claims.

**Test:** test_selection_protocol_file; test_phase7_final_integrity; test_hardening_audit

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** YES.

### MR-46 — recovery provenance (HIGH; FIXED)

Aliases: LH-10; IA-10. File/function: [docs/reviews/evidence_final_closure/execution_20261106T143735Z/recovery_verification.json](/Users/cortex/Projects/crypto2.0/docs/reviews/evidence_final_closure/execution_20261106T143735Z/recovery_verification.json), `recovery evidence / manifest validation`.

**Problem:** Historical checksum expectations include 67 source-provenance discrepancies; they cannot be silently repaired or described as all historical hashes matching.

**Evidence:** All eight recovery files inspected; remote/local source matches and residual resolution; 0 unresolved; 67 extras preserved separately.

**Reproduced:** YES; provenance retained, not hidden.

**Scientific consequence:** Historical expectations and recovered source identity must remain distinguishable.

**Operational consequence:** Deleting forensic evidence or replacing bytes would weaken auditability.

**Fix/disposition:** Accept verified recovery status with explicit preserved provenance discrepancies; select canonical manifested inputs only.

**Test:** recovery_verification.json; forensic_selection_assertions.json

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

### MR-47 — Git-free software verification (HIGH; FIXED)

Aliases: New exported-source verification defect. File/function: [tests/historical_source.py](/Users/cortex/Projects/crypto2.0/tests/historical_source.py), `historical_blob / historical_phase7_paths`.

**Problem:** An actual .git-free source export failed 18 tests: historical Git evidence and integration identity display assumed a repository.

**Evidence:** Preserved pytest_committed_export.log: 18 failed / 1374 passed; source export repair and complete final export rerun.

**Reproduced:** YES in a real committed export.

**Scientific consequence:** Historical baseline assertions must remain anchored to the same immutable bytes.

**Operational consequence:** Linux verification would fail before cache preparation.

**Fix/disposition:** Bundle 36 actual baseline git-show blobs plus anchored historical tree; verify pinned bundle SHA; keep all original historical SHA checks. Read-only adapter can report verified exported commit, while job branch authorization remains unchanged.

**Test:** test_historical_source_export; complete Git-free exported suite

**Blockers — RunPod:** NO; **Smoke:** NO; **Tradability:** NO.

## 36. Architecture improvements

The safe changes in this task extend the existing admission, identity, publication and recovery boundaries rather than rewriting scientific training. New separate modules cover owner/environment contract, portable identity summary, exported-source verification and isolated filesystem probing. `training.py` remains 2,334 lines; a broad pre-smoke rewrite would add risk. Funding/trading/portfolio engines remain outside authorized scope.

Qualitative priorities below are judgments; runtime impact is unmeasured unless explicitly stated.

| Rank | Improvement | Class | Scientific value | Engineering value | Memory/runtime impact | Risk | Effort / disposition |
|---:|---|---|---|---|---|---|---|
| 1 | Actual Linux/x86, local mount/lock/fsync qualification and cross-host identities | DO_BEFORE_SMOKE | High | High | Establishes operating envelope | Low code / external execution | Medium; outstanding authorized host |
| 2 | One prepare-only cache, measured peak/RSS/IO, read-only reload equivalence | DO_BEFORE_SMOKE | High | High | Measures real preparation bottleneck | Medium | Medium; blocked before execution |
| 3 | Exact owner cost/deadline, independent stop rehearsal and evidence export | DO_BEFORE_SMOKE | Medium | High | Bounds operational exposure | Medium external | Medium; missing authority/controller proof |
| 4 | Manifest-only selection, mandatory frozen context, exact transfer dependencies | DO_BEFORE_SMOKE | High | High | Prevents bad enumeration/recomputation | Low | Completed and tested locally |
| 5 | Effective container RAM/CPU, fold counts, six identities and resolved run manifests | DO_BEFORE_SMOKE | Medium | High | Prevents oversubscription; accurate row basis | Low | Completed and tested locally |
| 6 | Extract preparation/publication orchestration from training.py with equivalence checks | DO_AFTER_SMOKE | Medium | High | May simplify releasing temporary objects | Medium | Medium; defer broad refactor |
| 7 | Measure Arrow column projection, sort/index and cache buffer overlap | DO_AFTER_SMOKE | Medium | High | Potential RAM/IO reduction, magnitude unknown | Medium | Medium; no projection change made |
| 8 | Integrity-safe immutable-lifetime hash reuse | OPTIONAL_LATER | Low | Medium | Possible hashing IO reduction, unmeasured | Medium integrity risk | Defer mtime/size-only memoization |
| 9 | Matched baseline objective/sample/keys and normalized diagnostic units | DO_BEFORE_PILOT | High | Medium | Extra controlled evaluation | Low/Medium | Medium; partially open |
| 10 | Registered trial ledger, independent chronological selection and seed/regime robustness | DO_BEFORE_PILOT | High | High | More research compute only after approval | Medium statistical | Medium/High; not a smoke purpose |
| 11 | Funding settlements, execution/cost sensitivity and qualified economic evidence | DO_BEFORE_TRADABILITY_CLAIM | High | High | Additional data/evaluation | High scope | High; separate authorization needed |
| 12 | Generic acquisition cutoff hygiene, obsolete docs and legacy inference consolidation | OPTIONAL_LATER | Medium | Medium | Little direct smoke impact | Medium frozen/legacy scope | Separate approved version; preserve existing artifacts |

## 37. Architecture scores

Scores measure implemented controls and available evidence, not expected trading performance. Unverified deployment and economic realism receive low scores. These are not a weighted mathematical proof.

| Area | /10 | Reason |
|---|---:|---|
| Data acquisition | 8 | Restartable audited source; generic legacy hygiene remains |
| Data lineage | 8.5 | Immutable manifests and preserved provenance discrepancies |
| Silver | 8.5 | Actual canonical hash/schema/range checks |
| Gold | 8.5 | Actual full validation; immutable frozen data |
| Feature engineering | 8 | Broad tested features; redundancy/chunk semantics remain |
| HTF timing | 8.5 | Closed-bar as-of and truncation invariants |
| Cross-sectional context | 8.5 | Independent census and mandatory frozen sidecar |
| Targets | 9 | Exact timing and all-horizon tests |
| Universe | 8 | Causal historical construction; archive completeness limit |
| Splits | 8.5 | Calendar ownership and frozen boundaries |
| Purging | 9 | Actual endpoint checks and Cal-A/H0 repairs |
| Embargo | 9 | 120-minute tested separation |
| Leakage controls | 8.5 | Tested causal boundaries; trusted API limitations |
| Model design | 7 | Reasonable benchmarks; robustness unmeasured |
| LightGBM configuration | 7.5 | Controlled CPU/stopping/threads; no measured real fit |
| Calibration | 8 | Purged internal ownership; no economic validation |
| Thresholding | 7.5 | Explicit NO_TRADE; selection uncertainty remains |
| NO_TRADE | 9 | Non-positive and insufficient cases fail safe |
| Baselines | 6.5 | Useful controls; training-objective fairness incomplete |
| Regression metrics | 8 | RMSE/MAE/coverage/provenance tests |
| IC | 7.5 | XS/macro guards; inference still unqualified |
| Trading metrics | 4 | Trade proxies only; no portfolio equity |
| Costs | 4 | Static stress only |
| Funding | 1 | Settlement cash flow not modeled |
| Execution assumptions | 3 | Reference opens, no fills/impact |
| Multiple-testing control | 5 | Descriptive scope enforced; independent evidence absent |
| Selection chronology | 8 | 16 calendars and temporal reuse explicitly enforced |
| Holdout | 8 | Canonical research lock; generic surfaces broader |
| Cache identity | 8.5 | Matrix-specific changes and tamper tests |
| Scientific identity | 8 | Six portable identities; real cross-host proof missing |
| Results ledger | 8.5 | Atomic canonical result/receipt and derived CSV |
| Crash recovery | 8 | Strong native fixtures; target Linux unqualified |
| Concurrency | 8 | Leases/cache exclusion tested; actual target mount absent |
| Mac portability | 8.5 | Full committed-export suite and Ruff |
| Linux portability | 3 | Prepared/portable export tested; Linux execution absent |
| RunPod resource admission | 7 | Container-aware floors/tests; actual target absent |
| Monitoring | 7 | Validation/RSS/disk metrics; provider stop unqualified |
| Live-order isolation | 8.5 | No-skip import/constructor/static guards |
| Documentation | 7.5 | Authoritative evidence report; older drift preserved |

| Aggregate | /10 |
|---|---:|
| SCIENTIFIC SCORE | 8.0 |
| ENGINEERING SCORE | 7.5 |
| STATISTICAL RIGOR SCORE | 5.5 |
| TRADING REALISM SCORE | 2.5 |
| REPRODUCIBILITY SCORE | 7.0 |
| RUNPOD READINESS SCORE | 3.5 |

## 38. Remaining risks

Smoke-critical: no real Linux environment/target filesystem proof, no cross-host identity comparison, no qualified real cache, no fresh owner cost/deadline contract or tested independent stop/evidence workflow. The local Mac fails both conservative hardware admission and heuristic memory planning. The complete staged set has not been transferred remotely.

Research/claim-critical: no completed independent multi-fold evidence; funding settlement and execution/portfolio realism absent; baseline objective fairness and normalized diagnostic units remain open; fixed-universe representativeness and frozen feature semantics limit interpretation. Generic download/legacy paths remain governed by the owner restrictions. API ownership and local hashes are not an adversarial security boundary. The suite is substantial executable evidence, not a claim that every possible defect has been found.

## 39. Exact next command

No RunPod endpoint was supplied, so there is no truthful rsync/SSH destination to execute. The complete local staged hierarchy and content manifest are ready for an owner-authorized transfer; source/runtime files exclude macOS resource-fork files and Git/environment/Claude output directories. No paid SKU or provisioning command is prescribed.

On the **already authorized Linux/x86_64 host**, from the verified `crypto2-source` export, the next gate is exactly:

```bash
bash scripts/closure/verify_linux_external.sh /tmp/phase7-smoke-local/verification
```

First establish that the selected `/tmp/phase7-smoke-local` filesystem is the intended pod-local filesystem, with sufficient disk; do not assume provider mount topology. Use its sibling local cache/model/temp/output/log roots for later work. Compare the six identities against the staged `identity.expected.json` using section 12, revalidate transferred checkpoints/data/sidecar, and retain all Linux evidence. This command performs software/filesystem verification only. **No prepare-only or real fit command is authorized by this report.** The next dependent step is separately authorized one-cache preparation/reload, followed only then by an explicitly approved CPU plumbing smoke with invariant-stop monitoring.

## 40. Final verdict

**NOT_READY_FOR_SMOKE.** The scientific/data/code repairs and local verification are complete; missing external execution evidence is not counted as PASS. Local input-set PASS does not mean a remote transfer occurred. Aggregate IDENTITY remains FAIL until actual Mac/RunPod comparison passes. `LINUX=FAIL` and `FILESYSTEM=FAIL` mean required real-platform qualification is absent, not that Mac fixtures simulate Linux. `ADMISSION=PASS` means the guards correctly enforce/refuse, not that this Mac or any pod is admitted.

Funding remains NOT_MODELLED; tradability is NOT_ESTABLISHED. July unused; August LOCKED_UNUSED. Full grid NOT_AUTHORIZED.

```text
RECOVERY: PASS
MAC_TESTS: PASS
RUFF: PASS
GOLD: PASS
SILVER: PASS
M01: PASS
SIDECAR: PASS
TRUNCATION: PASS
UNIVERSE: PASS
IDENTITY: FAIL
LEDGER: PASS
SELECTION: PASS
ADMISSION: PASS
RESOURCE_ADMISSION: FAIL
RUNPOD_TRANSFER_SET: PASS
LINUX: FAIL
FILESYSTEM: FAIL
CACHE: NOT_QUALIFIED
CPU_POLICY: PASS
LIVE_ORDER_ISOLATION: PASS
AUGUST: LOCKED_UNUSED
PIPELINE: NOT_READY_FOR_SMOKE
TRADABILITY: NOT_ESTABLISHED
FULL_GRID: NOT_AUTHORIZED
```
