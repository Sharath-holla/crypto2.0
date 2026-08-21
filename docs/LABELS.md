# Phase 3 Labels

Label name: `forward_return_60m`  
Label version: `1.0.0`  
Primary target: `future_return_60m`

## Timestamp semantics

For a prediction candle with row index `i`:

- `prediction_candle_open_time` is the candle's inclusive open timestamp.
- `feature_time` is the next exact interval boundary, when the completed candle is available to a model.
- `entry_time` is the next candle open and equals `feature_time` under the Phase 3 reference convention.
- `label_end_time` is the candle open exactly 60 minutes after `entry_time`.

For five-minute candles the 60-minute horizon contains 12 intervals. The next-open entry adds one more offset, so:

```text
entry row  = i + 1
target row = i + 1 + 12 = i + 13

future_return_60m[i] = open[i + 13] / open[i + 1] - 1
```

Concrete example:

```text
prediction candle: 09:55–10:00
feature_time:       10:00
entry_time:         10:00, using the 10:00 candle open as a label reference
label_end_time:     11:00, using the 11:00 candle open as a label reference
```

The prices are label references, not claims that a real order can execute perfectly at those prices. Spread, fees, latency, slippage, funding, and position accounting belong to Phase 4.

## Gap and terminal-row behavior

Every expected candle open from the entry through the target must exist at the configured interval. A missing timestamp anywhere in that sequence invalidates the sample with `gap_in_horizon`; the engine never jumps across the gap.

For five-minute data, the final 13 prediction candles lack the required `i + 13` target and are reported as `insufficient_future`. Invalid labels are not filled, carried backward, or assumed to be zero. Gold construction excludes them and records reason counts.

## Precision and versioning

Entry and future reference prices remain Arrow `decimal128(38,18)` in Gold. The simple-return target is calculated from exact `Decimal` prices and converted once to `float64` for model consumption.

Label metadata records the name, version, horizon, entry/future reference rules, return type, gap behavior, and deterministic configuration hash. Changing any definition produces a different Gold dataset version.

The configurable one-basis-point `near_zero_threshold_bps` is used only for target-distribution reporting. It is not a trading-cost estimate or classification claim.

## Phase 6 Label V2 research family

`label_v2_research-1.0.0` is separate from immutable Label V1. It defines
gap-safe next-open forward returns at 15m, 30m, 1h, 2h, and 4h; long/short
MFE/MAE evaluation labels at each horizon; and two volatility-normalized 1h
TP-before-SL research labels. Every target stores its own `label_end_time`.

MFE, MAE, barrier outcomes, entry/future references, and target timestamps are
never feature inputs. A 5-minute TP/SL overlap is resolved with validated
1-minute data only when ordering is unambiguous; otherwise it remains
`AMBIGUOUS`. See `PHASE6_TARGET_RESEARCH.md` for definitions and evidence.
