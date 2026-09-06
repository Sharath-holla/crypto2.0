# Configuration Reference

## Full Phase 7 versus Phase 7A

`configs/phase7/research_v1.toml` defines the canonical full experiment with Gold root
`data/gold/phase7` and configuration hash `cc550337f1f4ee4654124bf6` in the frozen baseline.
It contains CORE and EXPANDING views, 48 primary A6 specs, six A0–A5 ablations, and four HTF
controls.

`configs/phase7/research_core20_primary_v1.toml` is the separate Phase 7A identity
`93f987736b1a79d26b773957`, with name `phase7a-core20-primary-v1` and Gold root
`data/gold/phase7a_core20_primary_v1`. The Phase 7A runner limits execution to CORE and the 48
primary A6 specs; it does not edit the canonical full config.

## Important fields

| Section/field | Frozen value and purpose |
| --- | --- |
| `phase7.mode` | `cloud`; heavy stages also require `PHASE7_ALLOW_CLOUD_RESEARCH=1` |
| data range | `data_start=2020-01-01`, exclusive `research_cutoff=2026-07-01` |
| holdout | starts 2026-08-01; `LOCKED_UNUSED`, used/evaluation-authorized false; complete July buffer |
| venue/data | 5m decision interval; required 5m/12h/1d; funding/mark/index; Binance/quality configs |
| paths | data, artifact, Gold, checkpoint roots; optional cloud root from environment |
| universe | target 20; cutoff 2022-01-01; expansion at fold TRAIN end; +10/30 total cap |
| eligibility | 365-day history; age edges 365/730/1460; coverage 0.995, warning 0.999; 90-day selection window |
| anchors/contract | BTCUSDT/ETHUSDT; USDT; PERPETUAL; required 5m/12h/1d |
| feature windows | correlation/liquidity/7d volatility 2016 rows; daily 288; include 12h/1d/derivatives |
| negative controls | disabled |
| targets | 15/30/60/120m; one full 5m latency bar; raw + volatility-normalized; floor `1e-8` |
| models | G0/C0/P0/H0; 4 clusters; symbol-ID and balanced-weight comparisons enabled |
| per-coin gates | TRAIN 20,000; Validation 2,000; Cal-A 2,000 rows |
| LightGBM | learning rate .02; 500 estimators; 31 leaves; depth -1; child 100; subsample/columns .9; L1 .1; L2 1; early stop 50; seed 42 |
| resources | max workers 4; model threads 4; batch 250,000; memory guard 8 GiB; GPU false |
| schedule | 24m TRAIN, 3m Validation, 3m Calibration, 3m TEST, 3m step, rolling, minimum segment 500 |
| leakage | actual-label purge plus 120-minute embargo |
| calibration | identity/linear; 10 reliability buckets; minimum 100 samples |
| costs | fixed stress 1/1.25/1.5/2×; thresholds 2/4/6/8/10 bps; 30 Cal-B trades |
| tiers | 4 bps taker/side; high 1 spread +1 slippage/side; medium 2+2; lower 4+4 |

Pydantic uses `extra="forbid"` and frozen models. Validators require the exact horizons,
architectures, intervals, derivative families, cutoffs, July gap, anchor symbols, and an embargo at
least the longest horizon. Do not “fix” a validation error by weakening these rules. Any scientific
change requires a new experiment/config/baseline identity and owner approval.
