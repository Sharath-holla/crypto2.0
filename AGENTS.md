# Repository Instructions

## Current phase

Phases 1 through 6, including Phase 5 Hardening, are complete and immutable.
Phase 7 is not authorized.

- Preserve all verified Phase 1 through Phase 4.1 implementations and artifacts.
- Preserve original Phase 5 `walkforward_v1` and hardened
  `walkforward_v1_1` models, predictions, folds, trades, summaries, and
  verification artifacts. Never overwrite them.
- Freeze the Phase 5 prospective holdout at `2026-08-01T00:00:00Z`; do not use
  any row at or beyond it during Phase 5 development or evaluation.
- Start with `BTCUSDT` at `5m`; support `1m` where practical.
- Treat Binance USD-M perpetual futures as the primary research market. Keep Binance Spot as an explicit secondary/cross-market dataset; never merge their Bronze records or source identities.
- Binance is the sole canonical market-data and eventual execution venue. The old Binance-data/CoinSwitch-execution design is superseded.
- CoinSwitch-specific legacy files are deprecated, excluded from the installable package, and retained temporarily only for audit and possible extraction of exchange-independent concepts. Do not run them.
- Preserve the isolated Phase 6 `market_v3_research` features,
  `label_v2_research` targets, fixed probes, BTCUSDT USD-M `12h`/`1d` context,
  MFE/MAE/barrier research, Gold, predictions, reports, and scorecards. Do not
  mutate Feature/Label V1/V2/V2.1, Phase 5, or Phase 6 artifacts.
- Enforce the Phase 6 research cutoff at `2026-07-01T00:00:00Z`; keep all of
  July unused by Phase 6 and keep the August prospective holdout untouched.
- Do not add advanced ML, more instruments, portfolio/risk/leverage logic,
  final TP/SL or Fear engines, sentiment, cloud deployment, Binance execution,
  or live trading. Do not start Phase 7.
- Do not run `main_trader.py`, `pipeline/live_trader.py`, `dashboard.py`, or any command that can access an account or submit an order.

## Engineering rules

- Use current official exchange documentation for API behavior.
- Treat all date ranges as half-open `[start, end)` UTC ranges.
- Preserve exchange decimal strings as exact decimals; do not silently convert prices or volumes to binary floats.
- Keep bronze data immutable. Never silently overwrite or repair an existing raw partition.
- Make ingestion restartable, duplicate-safe, and auditable through checksums and manifests.
- Report missing candles; never synthesize or forward-fill them.
- Keep secrets out of source, logs, tests, and documentation.
- Preserve legacy code unless removal is separately justified and approved.

## Verification

After changes, run the targeted tests, the complete test suite, configured lint checks, and inspect the Git diff. Do not report success with failing checks.
