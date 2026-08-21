# Crypto Trading AI

The repository has completed Phases 1 through 6, including the verified Phase
5.1 hardening protocol and isolated Phase 6 higher-timeframe/target research.
Binance USD-M futures are primary; Spot remains an isolated secondary dataset.
All completed work is public-data and offline research only:
there is no account access, order execution, leverage, or live trading.

The files at the repository root and under `pipeline/`, `phaseA/`, `data/`, and `extra/` are a preserved legacy prototype. CoinSwitch-specific execution modules in that tree are deprecated by ADR-017, are not part of the installable package or test path, and must not be run. They remain temporarily for audit and careful extraction of exchange-independent concepts; they are not the future Binance adapter.

## Install

```powershell
uv sync --extra dev
```

## Test

```powershell
uv run pytest
uv run ruff check src tests
```

## Download a small BTC sample

The range is half-open and must include a timezone. This example downloads one hour of closed USD-M 5-minute candles using the primary-market configuration.

```powershell
uv run crypto-ai download --config configs/data/binance.toml --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z
```

Use `--interval 1m` for USD-M futures 1-minute candles. Use `--market spot` only when intentionally creating the secondary Spot dataset. No API key is required for either Binance public endpoint.

The canonical target architecture uses Binance for market intelligence and a
possible later execution phase. Phase 4 does not authorize account access or
order submission. See `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and
`docs/COINSWITCH_DEPRECATION.md`.

## Validate and inspect

```powershell
uv run crypto-ai validate <parquet-path-from-manifest> --interval 5m
uv run crypto-ai inspect <parquet-path-from-manifest> --limit 5
```

The downloader prints the manifest path and final status. `validate` prints a JSON quality report and exits with code `2` when errors are present. See `docs/RUNBOOK.md` for recovery behavior and `docs/BINANCE_HISTORICAL_DATA.md` for the verified API contract.

## Dataset quality report

```powershell
uv run crypto-ai quality-report `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml `
  --output-root data/quality
```

## Promote passing data to Silver

```powershell
uv run crypto-ai promote-silver `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml
```

Failed datasets are referenced under `data/quarantine/`; Bronze files are never modified. See `docs/DATA_QUALITY.md` for the implemented checks and exact promotion rules.

## Build Gold and train Phase 3 baselines

```powershell
uv run crypto-ai build-dataset --config configs/datasets/btcusdt_5m_july_2026.toml

uv run crypto-ai train `
  --dataset-manifest data/gold/training_sets/gold-19425b0820c974247b73fbe0/manifest.json `
  --config configs/models/lightgbm_v1.toml

uv run crypto-ai evaluate `
  --experiment local_artifacts/experiments/experiment-5f0f09b3ee131bddba69a0b1/experiment.json
```

These commands create predictive research metrics, not trading PnL. See `docs/LABELS.md`, `docs/FEATURES.md`, `docs/MODELING.md`, and `docs/EXPERIMENTS.md` for definitions and the honest July baseline result.

## Phase 4 research

```powershell
uv run crypto-ai build-dataset-v2 `
  --config configs/datasets/btcusdt_5m_phase4_july_2026.toml

uv run crypto-ai train-v2 `
  --dataset-manifest data/gold/market_intelligence/gold-v2-f59110b7f683d2fe4342c8d6/manifest.json `
  --config configs/models/main_model_v2.toml
```

See `docs/BINANCE_MARKET_DATA_RESEARCH.md`, `docs/BACKTESTING.md`, and
`docs/EXPERIMENTS.md`. The real July run found no net-cost-qualified Main Model
V2 trades; this is a safe no-trade research result, not a deployment signal.

## Phase 4.1 multi-year hardening

Phase 4.1 preserves all Phase 3 and Phase 4 artifacts and adds the versioned
`market_v2_1` research path. Official Binance public archives are the bulk
source; REST is restricted to recent increments, metadata, and independently
verified gap correction. The fixed research cutoff is `2026-08-01T00:00:00Z`.

```powershell
uv run crypto-ai download-archive --start 2020-01-01T00:00:00Z --end 2026-08-01T00:00:00Z --symbol BTCUSDT --interval 5m --market usdm
uv run crypto-ai promote-silver --manifest <bronze-manifest>
uv run crypto-ai build-dataset-v2-1 --config configs/datasets/market_v2_1_core.toml
uv run crypto-ai build-dataset-v2-1 --config configs/datasets/market_v2_1_derivatives.toml
uv run crypto-ai train-v2-1 --core-dataset-manifest <core-gold-manifest> --derivatives-dataset-manifest <derivatives-gold-manifest> --config configs/models/main_model_v2_1.toml
uv run crypto-ai backtest-v2-1 --experiment <experiment.json> --config configs/backtests/foundation_v2_1.toml --funding-manifest <funding-manifest> --execution-1m-silver-manifest <one-minute-silver-manifest>
```

Feature V2.1 uses precise kline taker-flow terminology. Taker-buy volume is
aggressive executed flow inside a candle; it is not historical order-book depth
or complete market buying/selling pressure. Open interest remains an optional,
short-retention experiment and cannot truncate the multi-year core family.
Phase 4.1 remains public-data, bar-based research: it contains no private
account, leverage, position, or order operation.

The completed multi-year run produced core Gold
`gold-v2-1-a3d74d086a912070ee63a5ec`, derivatives Gold
`gold-v2-1-445fe8d3e2f5c2cb9e5ac6d1`, experiment
`main-model-v2-1-55f7b64298b70d529a1c5e39`, and backtest
`backtest-v2-1-1ab164e8a1409ebbad40b155`. The evidence is **NO RELIABLE EDGE**:
added groups did not beat the core baseline reliably, and the positive
base-cost backtest contains only five trades. Phase 5 freezes
`2026-08-01T00:00:00Z` as an untouched prospective holdout.

## Phase 5 walk-forward validation

```powershell
uv run crypto-ai walk-forward --config configs/walkforward/btc_primary_v1.toml --plan
uv run crypto-ai walk-forward --config configs/walkforward/btc_primary_v1.toml --resume
uv run crypto-ai walk-forward --config configs/walkforward/btc_derivatives_v1.toml --resume
```

The primary L0/L5 and matched derivatives D0/D2 candidates retain fixed
Phase 4.1 schemas and model parameters. Test data is unavailable until training,
validation-only early stopping, calibration, and threshold selection are
frozen. Results are **RETROSPECTIVE WALK-FORWARD OOS**, never prospective
holdout results. See `docs/WALK_FORWARD.md`.

The completed runs contain 17 primary and 16 derivatives folds. All four
candidates are `INCONCLUSIVE`; base-cost expectancy is negative for L0, L5,
D0, and D2. The combined decision is **NO QUALIFIED MODEL** and the prospective
holdout remains unopened. See `docs/PHASE5_RESULT.md` for the full evidence.

## Phase 5.1 hardening

Phase 5.1 preserves every historical Phase 5 artifact and reuses the 66 frozen
LightGBM model bundles plus saved TEST raw predictions. It introduces no model,
feature, label, hyperparameter, asset, account behavior, or order path.

```powershell
uv run crypto-ai harden-walk-forward --config configs/walkforward/btc_primary_v1_1.toml --resume
uv run crypto-ai harden-walk-forward --config configs/walkforward/btc_derivatives_v1_1.toml --resume
```

The unchanged outer Calibration window is split chronologically. Cal-A fits
identity/linear calibration; purged and embargoed Cal-B selects the unchanged
edge threshold. Fixed-policy cost stress freezes the exact 1x trade list and is
the primary qualification input; adaptive-policy stress is a separate
secondary diagnostic. The prospective holdout remains locked and unused.

The future multi-asset, expected-return distribution, MFE/MAE, dynamic TP/SL,
fear/euphoria, liquidity, risk, position sizing, leverage, portfolio, and
trade-management design is documentation-only in
`docs/FUTURE_TRADING_SYSTEM.md`. No next phase is authorized.

## Phase 6 higher-timeframe and target research

```powershell
uv run crypto-ai phase6-research --config configs/phase6/research_v1.toml
```

Phase 6 uses a conservative `2026-07-01T00:00:00Z` cutoff, adds direct
BTCUSDT USD-M 12h/daily context through completed-candle joins, and evaluates
separate `market_v3_research` features and `label_v2_research` targets. The
final immutable experiment is `phase6-btc-a6d0815c4adf041bf4107755`; model
status remains **NO QUALIFIED MODEL** and the August holdout remains unused.
See `docs/PHASE6_FEATURE_RESEARCH.md` and
`docs/PHASE6_TARGET_RESEARCH.md`. Phase 7 has not started and is not
authorized.
