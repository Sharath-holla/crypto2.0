# Repository Instructions

## Current phase

Phases 1 through 6, including Phase 5 Hardening, are complete and immutable.
Phase 7 local implementation is authorized and complete; the real cloud
research run is pending and must be started manually on the existing VM.

- Preserve all verified Phase 1 through Phase 4.1 implementations and artifacts.
- Preserve original Phase 5 `walkforward_v1` and hardened
  `walkforward_v1_1` models, predictions, folds, trades, summaries, and
  verification artifacts. Never overwrite them.
- Freeze the Phase 5 prospective holdout at `2026-08-01T00:00:00Z`; do not use
  any row at or beyond it during Phase 5 development or evaluation.
- For Phase 7, the prospective holdout status is permanently `LOCKED_UNUSED`:
  `prospective_holdout_used=false` and
  `prospective_holdout_evaluation_authorized=false`. July 2026 is a separate
  fully unused buffer after the exclusive July 1 research cutoff.
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
- Phase 7 is limited to the checked-in 15-30 symbol USD-M pilot framework,
  historical registry, data/feature/target build, G0/C0/P0/H0 LightGBM
  benchmarks, retrospective walk-forward validation, and research economics.
- Do not run heavy multi-symbol acquisition/training on the laptop. The cloud
  pipeline requires `PHASE7_ALLOW_CLOUD_RESEARCH=1` and manual execution on the
  existing training VM. Do not start, resize, or modify cloud resources from
  ordinary local development tasks.
- The small `crypto_ai.context` foundation may collect public Alternative.me
  Fear & Greed and Binance USD-M open interest only through the separate
  explicit context-network guard. Both feature families remain disabled from
  Phase 7 training; historical Fear & Greed is knowledge-time unverified and OI
  is recent/forward-only. Do not implement CryptoPanic, Arkham, or Reddit.
- Do not add portfolio/risk/leverage logic, final TP/SL or dynamic Fear engines,
  other sentiment, cloud services/deployment, Binance execution, or live trading.
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
