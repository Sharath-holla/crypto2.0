# Authorized Phase 7A smoke attempt — 17 November 2026

**Stopped at the mandatory host-selection gate. No new Pod or training was started.**

The owner authorized the complete gated sequence for one canonical Fold-0 `architecture-G0-A6-60m-raw` CPU smoke, including conditional preparation/training approvals. No additional permission was requested. Execution stopped because the frozen selector could not establish a qualifying available EU-SE-1 host, as required by the owner's instruction to stop on any failed mandatory gate.

The read-only selector ran at **2026-11-17T08:26:41Z (1:56:41 PM IST)**. It queried GPU stock in Sweden and CPU catalogs at 8/16/32 vCPU, the existing volume/Pod and live wallet. It returned `NO_QUALIFIED_LIVE_CATALOG_CANDIDATE`.

| EU-SE-1 catalog candidate | Compute quote / hour | Catalog minimum system RAM | vCPU minimum | Admission |
| --- | ---: | ---: | ---: | --- |
| NVIDIA A40 | $0.59 | 50 decimal GB (46.57 GiB) | 9 | Not established: RAM floor |
| NVIDIA RTX A6000 | $0.69 | 50 decimal GB (46.57 GiB) | 9 | Not established: RAM floor |

Required effective RAM is **68,719,476,736 bytes (64 GiB)**, with at least eight effective CPUs and 150,000,000,000 bytes of local/container disk. No queried CPU flavor supplied an admitted EU-SE-1 candidate. A catalog minimum is not a maximum: these results do not prove that every machine has only 50 GB. They do mean that the frozen selector has not admitted a qualifying host. No larger allocation was independently established; no insufficient host was deployed merely to continue, no RAM floor lowered, and no other region/volume/data migration substituted. Runpod documents catalog `minRam` as the minimum system RAM across matching machines, distinct from VRAM ([GPU catalog semantics](https://docs.runpod.io/api-reference-v2/catalog/get-a-gpu-type)). A later fresh query or verified qualifying allocation is needed before deployment.

The owner-funded session budget/deadline would be derived from the live wallet and dynamically reserved floor only after a qualifying host quote. Since selection failed, no session contract was activated, no Pod was created, and no stop controller was armed. The authorization remains recorded; this attempt did not spend a new training allowance.

Provider readback at **2026-11-17T08:28:50Z** listed one Pod only, `3hv6n675gud1wu`, state **EXITED**. Volume `kz9axr9t9v` remains 50 GB STANDARD in EU-SE-1. No compute remains running. The old Pod's 50 GB container disk also fails the new 150 GB requirement, so it was not restarted.

Latest queried wallet: **$17.7784630858**. Account running spend: **$0.005/hour**, consistent with retained storage; no new compute charges were incurred. Identified historical Pod plus volume billing from November 14 totals **$1.213347386335954**; billing can lag and is not a fresh allowance. Retained network storage continues billing while compute is stopped ([official storage pricing](https://docs.runpod.io/pods/pricing)). No payment/top-up or volume deletion occurred.

The exact source and separate kit archive hashes were rechecked locally:

- Scientific commit: `1b6a027b180979981eb76a4d6cbdec22510960df`.
- Source: `crypto2-source-1b6a027b1809.tar.gz`, SHA-256 `f1737c335d98cca4832251dc674b46fa17d6f53cfa434b42c1f0bf55a84c26d9`.
- Operator kit: `crypto2-preemption-operator-kit-20261117.tar.gz`, SHA-256 `de0a465043ee20454af2fcdea678dc1836cd38c8cb873bc4d72051a667ed0a3f`.

No source code, scientific design or existing results were modified. Uploaded inputs were preserved; their historical 2,777-file / 10,998,003,736-byte inventory was not represented as a new remote integrity PASS. Linux, local filesystem, remote six identities, cache qualification and model fitting did not run.

| Requested status | Observed result |
| --- | --- |
| POD | None deployed; existing `3hv6n675gud1wu` |
| HOST | No admitted candidate |
| RATE | New compute $0/hour; observed retained-storage account spend $0.005/hour |
| WALLET_START | $17.7784630858, predeployment observation |
| LINUX | NOT_RUN |
| FILESYSTEM | NOT_RUN |
| IDENTITIES | NOT_RUN remotely; frozen source/kit archive hashes PASS locally |
| RESOURCE_ADMISSION | STOPPED_AT_HOST_SELECTION_GATE |
| CACHE | NOT_PREPARED |
| CACHE_PERSISTED | NO new cache |
| MODEL | NOT_STARTED |
| ROUNDS | 0 / 500 |
| BEST_ITERATION | N/A |
| STOP_REASON | NO_QUALIFIED_LIVE_CATALOG_CANDIDATE |
| CHECKPOINT | NOT_REQUIRED |
| PROVIDER | EXITED — all listed Pods |
| WALLET_END | $17.7784630858 latest queried; storage continues billing |
| AUGUST | LOCKED_UNUSED |
| TRADABILITY | NOT_ESTABLISHED |
| FULL_GRID | NOT_AUTHORIZED |

Machine-readable evidence: [live catalog](evidence_authorized_smoke_20261117/live_selection.json), [provider/billing readback](evidence_authorized_smoke_20261117/provider_readback.json), and [final status](evidence_authorized_smoke_20261117/final_status.json).
