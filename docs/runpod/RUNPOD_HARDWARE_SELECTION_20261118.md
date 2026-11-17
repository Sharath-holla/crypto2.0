# Live hardware selection

Choose by effective host resources and same-region total cost, not GPU prestige. Existing volume: `kz9axr9t9v`, STANDARD 50 GB, **EU-SE-1**. A cheaper host elsewhere cannot attach it; no duplicate dataset migration is authorized.

Run `scripts/closure/runpod_select_host_phase7.py --output <snapshot.json>` tomorrow. It performs only authenticated catalog/Pod/volume/wallet reads. It queries Secure GPU candidates and 8/16/32-vCPU CPU flavors; sorts by actual catalog rate; rejects absent regional availability or advertised allocation below 64 GiB/8 CPU. Catalog RAM uses decimal GB and is converted to bytes: **64 GB is not 64 GiB**. A catalog minimum is not proof of an individual host's actual allocation. Re-query/quote a larger allocation if available; no Pod may be admitted from marketing alone.

Preparation-time authenticated snapshot is in `../reviews/evidence_runpod_preparation_20261117/live_selection.json`. That historical snapshot listed only **RTX A6000, $0.69/hour, 50 GB minimum RAM, 9 vCPU** in EU-SE-1. CPU flavors queried have no EU-SE-1 availability. The A6000's listed minimum allocation is below the floor. **That snapshot did not establish a qualified host for launch; it is not a current quote.** Do not substitute the old zero-GPU Pod or assume its full physical host RAM is usable. Refresh tomorrow; a quoted >=64 GiB A6000 allocation could be reconsidered only with actual proof.

Reference fallback order, conditional on actual allocation and EU-SE-1 availability:

| Reference type | User's reference compute $/h | Reference host RAM / CPU | 1 h all-in* | 2 h | 4 h |
| --- | ---: | --- | ---: | ---: | ---: |
| RTX 3090 | .50 | 125 GB / 16 | .53264 | 1.06528 | 2.13056 |
| L40 | .82 | 94 GB / 8 | .85264 | 1.70528 | 3.41056 |
| L40S | 1.09 | 94 GB / 16 | 1.12264 | 2.24528 | 4.49056 |
| RTX 6000 Ada | 1.09 | 167 GB / 10 | 1.12264 | 2.24528 | 4.49056 |
| Live A6000 minimum — **insufficient RAM** | .69 | 50 GB / 9 | .72264 | 1.44528 | 2.89056 |

*Planning illustration only: 200 GB local container disk at $0.10/GB/month plus existing 50 GB network volume at $0.07/GB/month, 720-hour planning month. No runtime promise, taxes/additional storage excluded, public reference prices are not live allocation quotes. The API selector also writes current candidate scenarios. Owner approval must use the actual deployment quote and a conservative all-in rate including applicable charges; do not silently enlarge the cap.

[Official Pod pricing](https://docs.runpod.io/pods/pricing) documents storage rates, per-second compute billing and live deployment pricing. [Official storage types](https://docs.runpod.io/pods/storage/types) distinguishes local container disk (erased on stop) from independently retained network volumes. Public reference prices in the table came from the owner's task; authenticated regional availability takes precedence.

Before launch record selected type/count, rate, allocated RAM/vCPU, image/digest, region, requested local disk and owner session contract. Inside the container record Pod ID, deployment time, uname/architecture, physical RAM, cgroup RAM/current/available, host CPU, sched affinity, cgroup CPU quota, effective CPU count, mount type/source/options, provider disk quota, df total/free, and actual `/workspace` network-volume binding.

Admission: Linux x86_64; >=68,719,476,736 bytes effective RAM; >=8 effective CPUs; >=150,000,000,000 bytes true local capacity **and** provider quota. Recommend 200 GB local disk when quoted/approved; at least 32 GiB currently available RAM and 25 GiB free disk are additional operating guards, not peak-memory guarantees. Prior ~25.836 GiB is a heuristic. Filesystem qualification must pass on the actual local cache/output mount, not `/workspace` FUSE. Reject NFS/FUSE/CIFS and unqualified mounts for the high-churn working directories in this kit.

CPU-only LightGBM; GPU_NOT_QUALIFIED. One model worker may use all canonical effective allowed CPU threads. Do not automatically choose a 5090 with insufficient RAM, or H100/H200/B200/B300 when cheaper safe hosts exist. If no qualifying same-region host is available, stop selection and report rather than deploy something unsuitable.

Preemption/restart additionally requires the same recorded LightGBM model thread budget and locked numerical environment. The new host may have more effective CPUs but must cap this model at the prior recorded thread count. Re-query all prices and wallet before a separately authorized session. Native mid-fit continuation is not qualified; retained-cache recovery starts one new attempt at round zero.
