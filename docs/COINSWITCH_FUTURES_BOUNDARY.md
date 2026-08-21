# Superseded CoinSwitch Futures Boundary

## Status

**Superseded by ADR-017 on 2026-08-19.**

This file is retained as an explicit historical marker because the earlier architecture selected Binance USD-M for research data and CoinSwitch for eventual execution. That target is no longer valid. Binance is now the sole canonical market-data and eventual execution venue.

No future feature, dataset, backtest, account, reconciliation, paper-trading, or live-execution design may depend on CoinSwitch. Older CoinSwitch API observations in the original inspection are not a supported contract and must not be used for implementation.

## Legacy-code disposition

The root and `pipeline/` CoinSwitch modules are outside the installable `crypto_ai` package and test suite. They are deprecated and prohibited from use. They remain temporarily because the supplied checkout has no tracked Git baseline and because a later, separately authorized cleanup may extract generic domain concepts before removing exchange-specific code.

See `COINSWITCH_DEPRECATION.md` for the file-by-file classification and `ARCHITECTURE.md` for the canonical Binance-only target.
