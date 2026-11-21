# Phase 7A constrained-memory implementation and execution — 17 November 2026

**The constrained profile is implemented. Real execution is blocked by Runpod placement capacity; no model or real cache was started.**

The owner explicitly authorized completing this profile and automatically proceeding through the gates to ONE canonical Fold-0 `architecture-G0-A6-60m-raw` CPU LightGBM smoke. No additional approval was requested between stages. The authorizations remain recorded; no second model/grid, acquisition, Silver/Gold/sidecar changes, July use or August access occurred.

## Implemented execution profile and safeguards

`PHASE7_RESOURCE_PROFILE=constrained_48gb` is separate from default `standard_smoke`. Standard admission remains **>=64 GiB effective RAM**, eight effective CPUs and 150 decimal GB local disk. The constrained profile has a **45 GiB minimum** (50 decimal GB is 46.57 GiB), eight effective CPUs and the same 150 GB disk/quota minimum. This permits only the measured preparation/probe workflow, not an unqualified full fit. Explicit owner profile authorization and a fresh source/identity/session budget binding are required. Normal approval bindings retain the original 64 GiB floor.

The independent local process-tree watcher samples at 250 ms and survives native dataset construction. It records timestamp/stage/profile, process-tree RSS, raw host MemTotal/MemAvailable, effective total/available RAM, cgroup limit/current/ratio, and free disk in `memory_timeline.jsonl`. WARNING starts at 75%, HIGH at 82%; the stage halts at **>=88% cgroup usage OR <8 GiB effective headroom**, whichever is stricter. Guard telemetry failure/staleness also fails closed. A resource stop signals the outside-Pod provider controller and writes minimal persistent evidence. Samples cannot mathematically guarantee protection from an arbitrary instantaneous allocation; the guard uses substantial absolute reserve and never intentionally runs to kernel OOM.

The short probe uses the full exact qualified TRAIN/Validation float64 matrices, ordered A6 columns, targets, weights, thread budget, CPU backend and canonical fit/observer construction. Only its boosting limit changes to **five**. It has `MEMORY_QUALIFICATION_ONLY` status, no canonical model/result/ledger entry and no TEST metrics. Probe admission requires **peak <82% cgroup usage AND minimum >=10 GiB effective headroom** over its reload/construction/fitting stage. These are stricter than the runtime guard. Full fitting additionally verifies the probe's exact session contract, cache manifest, shapes/dtypes, target/weight hashes, native parameters and threads. A failed probe must report `48GB_HOST_INSUFFICIENT`; since no Pod was placed here, that conclusion was **not** claimed.

A fresh process separates the short probe from the full fit. For full fitting the original maximum **500** rounds, **.02** learning rate and **50**-round early stopping remain unchanged. Effective model threads default to allowed CPU count minus one (eight on nine vCPU), one model worker. The observer's existing deterministic bounded Validation diagnostics, prediction-thread pinning, thresholds and native early-stopping logic are unchanged. No TEST metric is exposed during fitting.

## Allocation-lifetime audit

Existing prepared cache arrays are float64 read-only NumPy memory maps; Arrow IPC tables are memory mapped. Feature conversion already preallocates its final matrix and converts one column at a time. The update uses the existing blocked finiteness checker instead of allocating a whole-matrix boolean temporary. After a successful durable cache write, constrained preparation releases its in-memory matrices before reopening the independently verified mapped payload. For the one-spec case, the source-only sidecar table is released after its derived fold context exists. These changes preserve every matrix value, row, feature order, target, weight and split.

Zero/mean/Ridge baseline work already follows the LightGBM fit; it is not retained alongside active fitting, so it was not reordered or mathematically changed. Observer prediction arrays already follow the approved bounded sample contract; no new row subsampling was introduced. Read-only reload qualification deletes verification-only bundle/weight references and garbage-collects between its two loads. Qualified-cache retention remains early and capacity-conditional, never an emergency low-wallet multi-GB copy.

The unit fixtures compare constrained versus standard predictions, best iteration and native model serialization **exactly**. Negative tests cover unchanged standard admission, unknown profiles, constrained minimum, ratio/headroom boundaries, unavailable/stale guard, absent/wrong probe, changed targets/weights/threads/parameters/cache manifest and forced termination of an owned local dummy child. These are artificial non-market fixtures, not measurements of real Fold-0 memory.

## Deployment attempts and genuine blocker

The live constrained selector initially admitted A40 at $0.59/hour and A6000 at $0.69/hour in EU-SE-1, each advertising a 50 decimal GB minimum system-RAM allocation and nine vCPU. Actual in-container qualification would still have been required. The official catalog's availability is not a reservation; Runpod's [deployment guidance](https://docs.runpod.io/api-reference-v2/pods/create-a-pod) anticipates placement refusals and candidate fallback.

| Attempt | Requested host/disk | Outcome |
| --- | --- | --- |
| 09:31 UTC | A40 / 200 GB | HTTP 400; account readback confirmed no new Pod |
| 09:32 UTC diagnostic retry | A40 / 200 GB | HTTP 400 with exact capacity message below |
| 09:34 UTC refresh | Intended A40 / authorized 150 GB minimum | A40 had disappeared from the catalog; no create request sent |
| 09:35 UTC | Cheapest remaining A6000 / 150 GB | HTTP 400 with the same capacity message |

The provider response was:

> There are no longer any instances available with the requested specifications. Please refresh and try again.

No safety gate was bypassed. Neither a newly placed host nor a real resource-probe result exists. The old zero-GPU Pod reported no allocated CPU/RAM and only 70 GB container disk, so it did not independently satisfy the current contract and was left stopped. No network-volume relocation, resize or deletion was attempted.

Fresh readback at **2026-11-17T09:39:31.361579+00:00** listed only `3hv6n675gud1wu`, state **EXITED**; volume `kz9axr9t9v` remains 50 GB STANDARD in EU-SE-1. Wallet was **$17.7736019747**, account spend/hour **$0.005** from retained storage. New compute charges: **$0**. A stopped Pod's displayed historical rate is not running compute billing ([provider state/rate semantics](https://docs.runpod.io/api-reference-v2/pods/update-a-pod)). Persistent storage continues billing; it was preserved.

The attempted cost plans derived a **$15.77** maximum session spend from the live wallet after a $1.75 stopping trigger plus $0.25 extra reserve, additionally respecting the historical cumulative $18 cap. Conservative all-in rate bounds were $0.75/hour for the 200 GB A40 and $0.86/hour for the 150 GB A6000. Intent deadlines were no later than 24 hours after each request. These were **not** an activated billable session contract: no Pod ID was returned, no controller was armed, and no prepare/probe/train approval was activated. No payment, top-up or automatic restart occurred.

## Final frozen source and packages

Final scientific source: **`e2fbe33211d975e3af88e52ce6180c820ce05cbb`**, incorporating constrained execution and raw-host/cgroup telemetry. It supersedes 3675002, 1b6a027 and 7a64ee0 for this workflow; earlier packages are preserved as historical artifacts. The final exact Git-free export passed **1,520 tests**, with zero failures/errors/skips, plus Ruff and formatting. The additional operator suite passed **41 cases**. The final telemetry-only delta from the previously verified constrained source is recorded explicitly.

Source archive: `/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117/crypto2-source-e2fbe33211d9.tar.gz`.

SHA-256: `0b9451abb0553da7438e16fe11193d1d1edebe95cd0abbf861ef740e65cdd0e0`.

Inventory digest: `171f179d5a274ab7412263e57c9db44b71b1f7262f8c6aa86bcfde5fdd858758`. 1,270 committed files / 26,579,362 bytes; 1,271 regular shipping files / 26,811,461 bytes including the source-freeze manifest. Dependencies remain locked by the unchanged `uv.lock` SHA `d0cf77d737384e0d35e6175daf74bfa9716ece8a9f246d1f107beb0a01556d85`. Operator metadata ships separately to avoid a commit-hash self-reference; use the current operator manifest and corresponding kit, not the historical kit.

| Identity | Expected value |
| --- | --- |
| EXPERIMENT_CONTROL_DIGEST | `3534b3baa7e4de24622e6f9d07a13686aabb9acb6bbe611b451025ad73ffadb3` |
| GOLD_MANIFEST_SHA | `a142027722424ead5bbc508537e85bf743b3da68b38c3a99c9aabd3ef0e2e711` |
| PREPARATION_DIGEST | `fa11fc625ea1f7281823b1d1b55644c28b2ab76922c70d60c528d24ca125d587` |
| SCIENTIFIC_SOURCE_DIGEST | `fd33312fbbd1ee388cb59729a9f4d7b14a1c17380d8f3e526d6baa1a1e44bfc2` |
| SELECTION_PROTOCOL_DIGEST | `562dbf8203f476e446cd9968d336fa74b022924c01e5b1c34f3167c065c73826` |
| SIDECAR_SHA | `ea5f25a2a7c009c79a9ecbbe795960234b67074d36d2db7c21424724fabc2048` |

Repository and final export identities match. Gold/sidecar/selection identities are unchanged. Preparation identity changed with the equivalent bounded matrix check; source/control identities changed with the new runtime. No historical identity was forced onto the new source, and no historical result was overwritten.

## Execution procedure when capacity is genuinely available

Use the new separate [constrained runbook](../runpod/CONSTRAINED_48GB_RUNBOOK_20261117.md), source manifest and constrained approval templates. Re-query stock, wallet/rate/billing and derive the authorized <=24-hour session limits. Attach only the existing volume. Verify actual resources and supervised outside-Pod stop control with permission proof and two fresh heartbeats before heavy work. Run bootstrap/transfer/six-identities/Linux/filesystem/resource gates, then activate one prepare approval, prepare, double reload and early retention. Activate the distinct memory-probe approval; only after PASS activate the canonical full-training approval and fit the one model. On any failed gate stop provider compute and confirm EXITED. Native mid-fit continuation remains disabled; no second model or automatic restart after top-up.

The owner's current message authorizes these conditional stages; the blocker here is provider capacity, not a missing owner confirmation. This report does not claim a Linux, real cache, memory-probe or live stop-control PASS.

## Requested final status

| Field | Result |
| --- | --- |
| HOST | T_DEPLOYED — A40 and A6000 placement rejected |
| RATE_USD_HR | No running compute; attempted quotes $0.59 / $0.69 |
| EFFECTIVE_RAM_GIB | NOT_MEASURED |
| EFFECTIVE_CPU | NOT_MEASURED |
| RESOURCE_PROFILE | CONSTRAINED_48GB |
| LINUX | NOT_RUN |
| FILESYSTEM | NOT_RUN |
| IDENTITIES | LOCAL_MATCH; REMOTE_NOT_RUN |
| CACHE | NOT_PREPARED |
| CACHE_PEAK_RAM_GIB | NOT_MEASURED |
| CACHE_RELOAD | NOT_RUN |
| CACHE_PERSISTED | NO new cache |
| MEMORY_PROBE | NOT_RUN |
| PROBE_PEAK_RAM_GIB | NOT_MEASURED |
| PROBE_HEADROOM_GIB | NOT_MEASURED |
| FULL_TRAINING | NOT_STARTED |
| MODEL | NOT_STARTED |
| ROUNDS | 0 / 500 |
| BEST_ITERATION | N/A |
| BEST_VALIDATION_RMSE | N/A |
| STOP_REASON | RUNPOD_PLACEMENT_UNAVAILABLE |
| FULL_TRAINING_PEAK_RAM_GIB | NOT_MEASURED |
| WALLET_START | $17.7736019747 |
| WALLET_END | $17.7687408636 latest observed; storage continues billing |
| WALLET_FLOOR | USD_1.00 |
| LATEST_CHECKPOINT | None from this attempt |
| PROVIDER | EXITED — all listed Pods |
| AUGUST | LOCKED_UNUSED |
| TRADABILITY | NOT_ESTABLISHED |
| FULL_GRID | NOT_AUTHORIZED |

Detailed source/test/deployment/provider receipts are in [evidence_constrained_20261117](evidence_constrained_20261117/). No profitability conclusion is possible from this attempt.

## Final minimum-profile placement check

After the initial placement failures, one additional request used 49 decimal GB minimum RAM (45.64 GiB), eight vCPU and 150 GB local disk, all still meeting the implemented constrained admission floor. The refreshed catalog selected A6000; A40 was absent. Runpod again returned HTTP 400 with the same no-instances-available message at 2026-11-17T10:17:58Z. No Pod was created and no controller/real cache/probe/fit ran. This confirms the refusal also occurred at the authorized resource minimum rather than only at the preferred larger disk/CPU request. Runtime safety thresholds and scientific workload were never lowered.

Latest readback: **2026-11-17T10:19:35.216811+00:00**, only old Pod **EXITED**, preserved 50 GB network volume, wallet **$17.7687408636**, retained-storage account rate **$0.005/hour**. The source and executable operator kit remain unchanged; the kit contains the earlier immutable audit snapshot, and this final report adds the later placement/readback receipts.
