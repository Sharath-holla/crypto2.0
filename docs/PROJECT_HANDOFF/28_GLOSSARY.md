# Glossary

| Term | Project meaning |
| --- | --- |
| Bronze | Immutable raw official-source records plus acquisition lineage/checksums |
| Silver | Quality-validated source data promoted without silently repairing Bronze |
| Gold | Partitioned model-ready features, targets, timing and lineage |
| Core20 | Frozen 20-symbol `core_universe_v1` selected causally at 2022-01-01 |
| CORE | Research view containing eligible members of the frozen Core20 |
| EXPANDING | Separately reported view: eligible core plus causally selected newer fold members |
| A6 | Full Phase 7 feature group: 54 native columns plus 22 12h and 33 1d columns (109 total) |
| G0 | One global pooled LightGBM architecture |
| C0 | One LightGBM per TRAIN-only cluster |
| P0 | One LightGBM per coin subject to TRAIN/Validation/Cal-A gates |
| H0 | Global LightGBM plus supported symbol/cluster residual corrections and fallback |
| NO_TRADE | Downstream decision when cost+edge threshold is not cleared or policy is unavailable |
| Cal-A | First chronological half of Calibration; fits identity/linear calibrator |
| Cal-B | Second chronological half; selects fixed cost-aware threshold |
| OOS | Out-of-sample TEST prediction after all identities freeze |
| `label_end_time` | Actual endpoint of a row's future label path; used for purge and exit |
| purge | Remove prior-segment rows whose label ends at/after the next segment begins |
| embargo | Exclude the first 120 minutes of a later segment after purge |
| `feature_time` | Earliest time the completed source information is available; 5m `open[i+1]` |
| `causal_available_from` / `available_from` | Earliest verified official-data time that may support causal eligibility |
| `available_until` | Exclusive verified lifecycle/data end; later rows may not be created |
| `valid_until` | Exclusive freshness boundary for an as-of context value |
| Gold checkpoint | Validated stage record binding Gold manifest/files/hashes/chunks; presence alone is insufficient |
| Fold | One rolling TRAIN/Validation/Calibration/TEST calendar unit |
| Phase 7A | Separate Core20/CORE-only 48-primary-spec cost-controlled experiment |
| August lock | `2026-08-01` prospective holdout: `LOCKED_UNUSED`, used/evaluation-authorized false |
