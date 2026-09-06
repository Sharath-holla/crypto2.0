# Targets and Labels

## Current contract

Phase 7A uses `multiasset_targets_v2` with horizons **15, 30, 60, and 120 minutes** and two target
representations: `raw_future_return` and `normalized_future_return`. The normalized value divides
raw return by `max(abs(feature-time daily_volatility), 1e-8)`; model predictions are multiplied by
the stored ex-ante scale before raw-return metrics/economics. Future volatility is forbidden.

## Exact timing

For a 5m source candle `i`:

```text
source opens at open[i]
source completes / feature_time = open[i+1]
configured full latency = one additional completed 5m bar
entry_time = open[i+2]
label_end_time = entry_time + horizon
```

The return is based on the entry open and the open at `label_end_time`. MFE/MAE long and short use
the future high/low path beginning at the same entry. Each label stores `feature_time`,
`entry_time`, `label_end_time`, horizon, raw/normalized return, ex-ante scale, and path excursions.

Labels require an unbroken sequence of future 5m candles through the endpoint. A gap, delisting,
missing entry/end/path row, or `label_end_time >= 2026-07-01T00:00:00Z` invalidates that row; no
history is fabricated. The superseded `multiasset_targets_v1` remains available only for audit and
is excluded from new Phase 7 economics.

## NO_TRADE and barriers

`NO_TRADE` is not a target class in v2. It is the downstream result when a calibrated prediction
does not clear the TRAIN-frozen cost tier plus Cal-B-selected threshold, or when a threshold is
unavailable. Phase 6/Phase 7.2 contain MFE/MAE and competing-risk/barrier research contracts, but no
final production TP/SL/barrier values are selected for Phase 7A:

**UNKNOWN — DO NOT INVENT.**
