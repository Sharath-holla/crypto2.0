# Training and Walk-Forward Methodology

## Calendar geometry

Phase 7A derives 16 rolling folds from `[2020-01-01, 2026-07-01)`:

- 24 calendar months TRAIN;
- 3 months Validation;
- 3 months Calibration, split chronologically in half into Cal-A and Cal-B;
- 3 months TEST;
- 3-month step.

| Fold | TRAIN | Validation | Calibration | TEST |
| --- | --- | --- | --- | --- |
| 0 | 2020-01-01→2022-01-01 | →2022-04-01 | →2022-07-01 | →2022-10-01 |
| 1 | 2020-04-01→2022-04-01 | →2022-07-01 | →2022-10-01 | →2023-01-01 |
| 2 | 2020-07-01→2022-07-01 | →2022-10-01 | →2023-01-01 | →2023-04-01 |
| 3 | 2020-10-01→2022-10-01 | →2023-01-01 | →2023-04-01 | →2023-07-01 |
| 4 | 2021-01-01→2023-01-01 | →2023-04-01 | →2023-07-01 | →2023-10-01 |
| 5 | 2021-04-01→2023-04-01 | →2023-07-01 | →2023-10-01 | →2024-01-01 |
| 6 | 2021-07-01→2023-07-01 | →2023-10-01 | →2024-01-01 | →2024-04-01 |
| 7 | 2021-10-01→2023-10-01 | →2024-01-01 | →2024-04-01 | →2024-07-01 |
| 8 | 2022-01-01→2024-01-01 | →2024-04-01 | →2024-07-01 | →2024-10-01 |
| 9 | 2022-04-01→2024-04-01 | →2024-07-01 | →2024-10-01 | →2025-01-01 |
| 10 | 2022-07-01→2024-07-01 | →2024-10-01 | →2025-01-01 | →2025-04-01 |
| 11 | 2022-10-01→2024-10-01 | →2025-01-01 | →2025-04-01 | →2025-07-01 |
| 12 | 2023-01-01→2025-01-01 | →2025-04-01 | →2025-07-01 | →2025-10-01 |
| 13 | 2023-04-01→2025-04-01 | →2025-07-01 | →2025-10-01 | →2026-01-01 |
| 14 | 2023-07-01→2025-07-01 | →2025-10-01 | →2026-01-01 | →2026-04-01 |
| 15 | 2023-10-01→2025-10-01 | →2026-01-01 | →2026-04-01 | →2026-07-01 |

All boundaries are half-open UTC. Test windows are non-overlapping. Cal-A/Cal-B split at the exact
temporal midpoint (which can be noon for an odd number of days); the safe CLI plan derives and
prints the exact IDs and midpoint timestamps.

## Leakage controls and ownership

There is no random shuffle. TRAIN fits model parameters, preprocessing, symbol weights, clusters,
and liquidity tiers. Validation alone controls early stopping/hybrid structure. Cal-A fits the
calibrator. Purged and embargoed Cal-B selects the threshold. TEST remains inaccessible until the
complete identity freezes and then provides OOS reporting only.

Before each later segment, prior rows are removed unless their **actual stored**
`label_end_time < next_segment.start`; then the next segment's first 120 minutes are embargoed.
Saying “embargo ≥ longest horizon” is incomplete: the implementation checks row-specific target
end times first, including entry latency and path availability. The embargo is an additional
separation, not a substitute for purge.

The exclusive research cutoff is 2026-07-01. July is unused, and the permanent holdout begins
2026-08-01 and remains locked. No fold may derive its endpoint from observed row maxima or cross
the holdout.
