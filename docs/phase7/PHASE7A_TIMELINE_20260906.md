# Crypto 2.0 — Phase 7A Timeline Through Project Hold

All timestamps are UTC. `UNKNOWN` means the surviving accessible evidence does not support an exact timestamp.

| Time | Event | Outcome |
| --- | --- | --- |
| UNKNOWN | Phase 7 discovery completed | 507/507 Binance USD-M symbols discovered with durable per-symbol evidence. |
| 2026-09-04T04:44:36.816513Z | Canonical Phase 7 backup created | Run `phase7-cc550337f1f4ee4654124bf6` preserved to GCS; large regenerable raw/Silver data were intentionally excluded and manifests retained. |
| 2026-09-04T13:46:55Z | Optimizer commit `8cdd0b1` | Phase 7 training execution optimization preserved. |
| 2026-09-04T18:21:40Z | Phase 7A runner commit `bee3771` | Separate cost-capped CORE20 PRIMARY configuration, supervisor, worker, feasibility gate, and watchdog added. |
| 2026-09-04T18:49:53Z | Core20 materialization commit `812f41a` | Phase 7A universe work scoped to the deterministic Core20. |
| 2026-09-05T02:19:15Z | Acquisition-resume commit `35f20d6` | Completed symbol acquisitions became reusable on resume. |
| UNKNOWN | Derivative archive blocker diagnosed | Missing official Binance derivative archive files were treated explicitly rather than synthesized. |
| 2026-09-05T09:07:14Z | Commit `0894e6c` | General missing-archive handling preserved; no synthetic candles or index rows introduced. |
| UNKNOWN | BCHUSDT HTF diagnosis | Discovery-window 1d evidence had contaminated strict full-range acquisition coverage; BCHUSDT appeared to begin at 2021-10-03 despite official history from 2020-01-01. |
| 2026-09-05T11:33:54Z | Commit `88af25f` | Discovery evidence and full-range HTF acquisition identity were separated; interior gaps remained fail-closed. |
| 2026-09-05T20:12:16.441969Z | HNTUSDT Gold worker failure | 2025 Gold requested rows after HNTUSDT's validated May 2024 lifecycle end. Guest guard preserved evidence and shut down safely. Gold remained 5/7. |
| 2026-09-05T20:12:33.891561Z | Durable GCS incident status | `overnight_fold1_status.json` recorded BLOCKED, zero workers, Fold 1 not started, and August LOCKED_UNUSED. |
| 2026-09-06T04:59:35Z | Commit `be3a164` | General post-delisting lifecycle intersection fix committed with regression coverage; no HNT-specific bypass. |
| 2026-09-06T05:39:48.813655Z | 2025 Gold chunk validation | PASS: 1,997,280 feature rows and 7,989,120 target rows for 19 active symbols; zero HNTUSDT post-lifecycle rows. |
| UNKNOWN | Gold finalization completed | Gold reached 7/7, 138 partitions, 50,352,548 rows, dataset `gold-phase7-0cbf2910e8d96c9d19826598`; validation found no August rows. |
| 2026-09-06T05:55:06.785Z | Four-hour Fold-1-only runtime authority created | Fold 2 explicitly unauthorized. |
| UNKNOWN | Fold-1 launcher defects diagnosed | `/usr/bin/time` was missing on one launch path, and a systemd service used an incorrect Python invocation. Both were operational, not scientific, failures. |
| UNKNOWN | Corrected Fold-1 worker launched | Direct environment Python invocation used; stale one-shot deadlines were not reused. |
| 2026-09-06T09:06Z–11:42Z | Earlier Fold-1 attempt | Owner manually stopped VM. Gold remained valid; no report/model was produced. |
| 2026-09-06T12:15:39Z | Final VM boot | Existing VM only; no resource resize or replacement. |
| 2026-09-06T12:32:41Z | Direct Fold-1 worker started | One logical worker entered real Fold-1 pipeline preparation. |
| 2026-09-06T12:33:23.222339Z | Productive authority began | Graceful deadline set to 16:18:23.222339Z; hard deadline to 16:33:23.222339Z. |
| 2026-09-06T16:19:14Z | Graceful guest termination event | Fold-1 preparation had produced 0/48 reports and zero serialized models; checkpoint state was preserved. |
| 2026-09-06T16:19:37.995Z | VM stopped | Compute Engine control plane recorded TERMINATED. |
| 2026-09-06T17:51:28.5058664Z | Project hold assessment | VM remained terminated; auto-resume metadata and automatic restart were disabled; no monitoring automation remained. |

## Hold conclusion

The project was voluntarily paused because the pre-model Fold-1 preparation stage repeatedly consumed hours without a reusable matrix checkpoint or sufficiently granular timing. This is an open engineering/cost blocker, **not a model failure**: no Fold-1 model completed and model qualification has not begun.
