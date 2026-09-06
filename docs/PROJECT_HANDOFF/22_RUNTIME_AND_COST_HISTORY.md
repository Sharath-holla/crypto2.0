# Runtime and Cost History

| Session | Productive compute / overhead | Outcome |
| --- | --- | --- |
| Initial Phase 7A acquisition/Gold window | Runtime authority showed 69,239.939018 s cumulative elapsed; not all productive | Gold 5/7; stopped on HNT lifecycle defect |
| Post-lifecycle 2025 chunk | 2,126.012797 s | Validated general fix; later Gold reached 7/7 |
| Corrected Fold-1 launch window | 6,846.423 s explicitly classified failed-launch overhead | No report/model; launcher/session problems |
| Earlier real Fold-1 preparation attempts | Approximately 2h35m inferred, not individually recoverable | Manual VM stop; 0/48 |
| Final Fold-1-only attempt | Worker 12:32:41Z; authority 12:33:23.222339Z; ~3h45m42s productive; 1,064.222339 s preflight | Graceful budget stop; 0/48; VM terminated |
| All real Fold-1 pipeline attempts | Approximately **6h21m** | Preparation repeated; no cumulative durable spec progress |

The authoritative full ledger is `docs/phase7/PHASE7A_RUNTIME_COST_LEDGER.md`; timestamps are in
`PHASE7A_TIMELINE_20260906.md`. Unknown boundaries stay unknown.

Earlier synthetic/local workload estimates modeled estimator counts and optimized fitting but did
not reproduce the real multi-million-row Fold-1 preparation path, disk behavior, or missing
pre-estimator checkpoint. They therefore underestimated wall-clock time to the first report and
must not be used as a 16-fold budget promise.

GCP billing export was not queried. Billing-verified compute cost is unavailable, and no owner-
reported currency amount is preserved in the hold evidence. Do not invent one. Stopped VM compute
is inactive, but its 250 GB persistent disk and GCS objects can continue storage charges.
