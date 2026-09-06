# Current Exact State

Evidence cutoff: project-hold artifacts and read-only GCP/Git checks on 2026-09-06.

| Item | Authoritative state |
| --- | --- |
| PROJECT | **ON HOLD** |
| Current phase | Phase 7A `CORE20_PRIMARY` |
| VM | **TERMINATED**; automatic restart false; zero workers implied by termination |
| Discovery | **507/507 COMPLETE** |
| Acquisition | **COMPLETE** |
| Data checkpoint | **VALID**, SHA-256 `d7bb7e99dda07ec62cd493a3c06951d6dae230f340c065b9bd42bd2423a99c0f` |
| Data manifest | SHA-256 `e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0` |
| Candle checkpoints | 60/60 validated (Core20 × 5m/12h/1d) |
| Gold | **7/7 COMPLETE**, persistent disk only |
| Gold partitions | 138 |
| Gold rows | 50,352,548 |
| Gold dataset | `gold-phase7-0cbf2910e8d96c9d19826598` |
| Gold checkpoint SHA | **UNKNOWN while VM stopped; revalidate before reuse** |
| Fold 1 | `STARTED_NOT_COMPLETE` |
| Fold-1 reports | 0/48 |
| Serialized models | 0 |
| Completed folds | 0/16 |
| Fold 2 | NOT STARTED |
| August | `LOCKED_UNUSED`; `used=false`; `evaluation_authorized=false` |
| July | UNUSED |
| Qualified model | NONE / qualification not yet evaluable |
| Paper trading | NOT STARTED |
| Live trading | NOT STARTED |
| Phase 8 | NOT STARTED |
| Open blocker | `FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING` |

Run identity: `phase7a-core20-primary-93f987736b1a79d26b773957`. Immutable discovery lineage:
`phase7-cc550337f1f4ee4654124bf6`. Last validated scientific source commit: `be3a164`; source
fingerprint: `ad1aac9508b0b15e9230e06122f4d7fcdf56bf1baab75a9de1a49f1c2894e67d`.

Gold path:
`/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/`.
Expected checkpoint:
`/home/nssharath123/crypto2.0/local_artifacts/phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/gold.json`.
