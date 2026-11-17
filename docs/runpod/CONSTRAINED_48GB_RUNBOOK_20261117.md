# Constrained Phase 7A execution

Owner authorization is recorded in the 17 November 2026 request. Only one canonical Fold-0 `architecture-G0-A6-60m-raw` CPU smoke is permitted after every mandatory gate; staged approval artifacts may be activated without further prompts. No second model/grid, new acquisition, Silver/Gold/sidecar changes or July/August access.

The standard profile remains >=64 GiB effective RAM. Explicit `PHASE7_RESOURCE_PROFILE=constrained_48gb` requires >=45 GiB effective RAM (50 decimal GB is 46.57 GiB), >=8 effective CPUs, >=150 GB true local/container capacity and quota (200 GB requested). Read actual cgroup limit/current, host total/available, effective CPU quota/affinity and local mount. Finite usable cgroup memory accounting is required. The lower admission floor alone never authorizes fitting.

Continuous independent process-tree guard: sample every 250 ms, append `evidence/memory_timeline.jsonl`, and heartbeat locally. Fail closed on stale/missing guard. WARNING >=75%, HIGH >=82%; halt at >=88% cgroup use OR <8 GiB effective available headroom. Guard exceptions also halt the stage, signal the outside-Pod controller and retain minimal persistent evidence. This is sampled protection with an 8 GiB margin, not a guarantee against arbitrary instantaneous allocation or kernel/provider failures. The wallet controller remains independent and stops provider compute on resource failure.

After bootstrap/transfer/identity/Linux/filesystem/resource gates, activate `OWNER_CONSTRAINED_PREPARE_TEMPLATE_20261117.json` with the session USD/deadline and exact new identities. Prepare one cache, then run the existing double read-only reload and capacity-conditional early persistent-cache retention. Release verification-only arrays before the next process begins.

After reload PASS, activate a separate `OWNER_CONSTRAINED_PROBE_TEMPLATE_20261117.json`, mode train but operation MEMORY_QUALIFICATION_ONLY. Run:

```bash
bash "$KIT/scripts/closure/runpod_memory_probe_phase7.sh" --execute --approval /crypto2-session/owner-memory-probe-approved.json
```

The probe loads the exact qualified full-row cache, same 109 float64 columns/targets/weights/splits, same CPU threads, native scientific parameters and observer setup; only its boost count becomes five. It writes no canonical model/report/ledger and scores no TEST. Require sampled peak <82% cgroup usage AND >=10 GiB minimum effective headroom across the entire probe/reload stage. Otherwise report `48GB_HOST_INSUFFICIENT`, stop, and never run the full fit. Five rounds expose construction/initial histogram allocations but do not bound the 500-round peak.

After probe PASS, activate `OWNER_CONSTRAINED_TRAIN_TEMPLATE_20261117.json` and run the normal train wrapper. Admission binds the probe's session contract, exact cache manifest, float64 shapes, target/weight hashes, canonical parameters and threads before fitting. A fresh process releases probe-only state. The original 500-round maximum, .02 learning rate and 50-round early stopping are unchanged. Model threads use effective CPU minus one by default (8 on a 9-vCPU host). Continue guard/observer/wallet monitoring throughout fitting and baseline/report publication. Preserve the existing bounded diagnostic sampling contract; no TEST metrics appear during fit.

Native partial checkpointing and $1 floor/$1.75 dynamic-trigger shutdown remain enabled. Mid-fit continuation remains NOT QUALIFIED. Persist cache early if capacity permits; otherwise future restart requires exact cache re-preparation. Export final or failure evidence, stop provider compute and verify EXITED. Never delete the network volume.

Allocation audit: existing cache arrays are read-only float64 memmaps, Arrow IPC tables are memory mapped, baseline Ridge executes after fitting, and observer predictions use existing bounded deterministic samples. New changes release preparation matrices before loading their verified persisted copies; release the no-longer-needed sidecar source after the one-spec fold context is derived; and use the existing bounded finiteness checker during matrix construction. Contents/order/row membership, baseline math and model parameters are unchanged. Tests compare native model strings and predictions exactly with the standard path on tiny artificial fixtures.

Use the new `runpod_source_manifest.json` and separate operator kit. Earlier 1b6a027/7a64ee0 exports do not implement this profile. All source, dependency, source-inventory and six-identity gates still apply. Base approval artifacts remain pending until populated with the actual owner-authorized session facts; the frozen source does not include account API credentials.
