# Git History and Important Commits

Dates below are commit-author dates. This is a curated chronology, not every commit.

| Commit | Date | Purpose and impact |
| --- | --- | --- |
| `a10d239` | 2026-08-21 | Prepared Phase 7 Google Cloud migration |
| `9467886` | 2026-08-22 | Added Phase 7 multi-asset registry/universe/features/targets/models architecture |
| `dd978b9` | 2026-08-22 | Added guarded context/OI foundation; kept it out of Phase 7 training |
| `ed20a08` | 2026-08-25 | Phase 7.1 hardening and future-safe contracts |
| `063e843` | 2026-08-29 | Phase 7.2 research/1m contract foundation; disabled from baseline |
| `a8ccec7` | 2026-08-29 | Made configuration identity cross-platform |
| `48f2322`, `d0f27b5` | 2026-08-29/30 | Corrected onboard and exact interval archive bounds |
| `86cece5`, `6d72c72` | 2026-08-30 | Corrected zero-volume aggregation and separated liquidity from corruption |
| `564f1fb`, `b4a130e` | 2026-08-30/31 | Evidence-gated archive/REST reconciliation, including missing-row repair from official REST |
| `b89f12c` | 2026-08-30 | Represented unrecoverable candles as causal unusable segments |
| `4742733` | 2026-08-30 | Runtime observability without scientific changes |
| `b45c4ec`, `ea32ec5`, `7dd008f`, `e4a496b` | 2026-08-31–09-02 | Cost-aware supervisor, budget stop/recovery, logical-worker counting |
| `8f04065` | 2026-09-02 | Durable discovery completion and explicit bad-source exclusions |
| `7c8e79f`, `070a240` | 2026-09-04 | Fail training defects/coverage/weight errors loudly instead of misclassifying ineligibility |
| `3f319c3`, `158486f` | 2026-09-04 | Vectorized pair statistics and hardened numerical equivalence/shape behavior |
| `8cdd0b1` | 2026-09-04 | Optimized matrix reuse, estimator scheduling/threading, H0 reuse, Arrow I/O |
| `bee3771` | 2026-09-04 | Added separate cost-capped Phase 7A Core20-primary runner/controls |
| `812f41a` | 2026-09-05 | Scoped Phase 7A universe materialization to Core20 |
| `35f20d6` | 2026-09-05 | Reused validated completed acquisitions on resume |
| `0894e6c` | 2026-09-05 | Handled genuinely missing official derivative archives without synthesis |
| `88af25f` | 2026-09-05 | Separated discovery HTF evidence from full-range coverage identity |
| `be3a164` | 2026-09-06 | Corrected general post-delisting Gold lifecycle intersection |
| `b641e8b` | 2026-09-06 | Frozen Phase 7A hold state, timeline, ledger, architecture and resume runbook |

`be3a164f3fe283885dff1e3a201dbac2dfc303af` is the last validated scientific/operational source
commit and has source fingerprint `ad1aac9508b0b15e9230e06122f4d7fcdf56bf1baab75a9de1a49f1c2894e67d`.
`b641e8b914a27f6b9a00ae4be7a2cbd75a02d9ed` is the pre-handoff frozen baseline and is tagged
`phase7a-hold-20260906`. The new tag `crypto2.0-handoff-20260906` identifies the complete handoff
commit; see `HANDOFF_MANIFEST.json` and `git show` rather than assuming an older hash is HEAD.
