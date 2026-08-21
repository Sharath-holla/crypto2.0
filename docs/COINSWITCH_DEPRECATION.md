# CoinSwitch Deprecation Inventory

## Decision

ADR-017 replaces the Binance-data/CoinSwitch-execution target with a Binance-only data and eventual execution architecture. This inventory records the disposition of every meaningful CoinSwitch reference found during the architecture revision. No listed module was imported, run, or validated.

## GOOD BUT UNUSED

- `pipeline/listener.py`: generic confirmed-candle, bounded-buffer, reconnect, and rate-limit concepts. It is a live-data reference only and needs a verified Binance adapter and production failure policy before use.
- `pipeline/audit.py` and `pipeline/alerts.py`: exchange-independent audit and non-blocking alert ideas.
- `main_signal.py`: the signal/execution process boundary is conceptually useful, but its legacy queue contract is not production-ready.

These files are not authorized Phase 4 implementations.

## SHARED LOGIC

- `main_trader.py` and `pipeline/live_trader.py` contain concepts such as signal intake, order lifecycle, position state, fill handling, exits, and reconciliation.
- `dashboard.py` contains generic monitoring concepts such as positions, orders, equity, recent trades, and operational status.

The concepts may eventually map to exchange-independent objects such as `OrderRequest`, `Order`, `Fill`, `Position`, `AccountState`, `RiskState`, and `ExecutionResult`. Their current implementations are entangled with CoinSwitch endpoints and unsafe legacy configuration, so the code itself is not shared infrastructure.

## NEEDS REFACTORING

- `main_trader.py`: mixes Binance price observation, CoinSwitch execution, CSV queues, mutable state, and live account behavior.
- `pipeline/live_trader.py`: mixes exchange calls, strategy exits, leverage, sizing, risk constants, local state, and PnL.
- `dashboard.py`: directly exposes CoinSwitch credentials and account/order endpoints alongside local monitoring.
- `pipeline/config_trader.py`: mixes CoinSwitch endpoints, credentials, risk/leverage policy, file paths, and Binance monitoring settings at import time.

If any generic behavior is reused, it must first move behind tested exchange-independent domain/service interfaces. A future Binance adapter must be written from current official Binance documentation rather than by translating endpoint strings mechanically.

## SAFE TO REMOVE

The following CoinSwitch-specific material is safe to remove after generic concepts are extracted or explicitly rejected:

- `pipeline/coinswitch_client.py` in full: signing, base URLs, identifiers, payload dialect, and endpoints are venue-specific.
- CoinSwitch endpoint and credential sections of `pipeline/config_trader.py`.
- CoinSwitch account/order panels and API routes in `dashboard.py`.
- CoinSwitch imports, environment variables, key validation, instrument loading, and client construction in `main_trader.py`.
- CoinSwitch request paths and API calls in `pipeline/live_trader.py`.

They are retained temporarily rather than deleted because there is no tracked Git baseline from which to recover them and this task authorizes an architecture update, not a destructive legacy rewrite.

## Documentation references

- Canonical documents (`AGENTS.md`, `README.md`, `MASTER_SPEC.md`, `ARCHITECTURE.md`, `PROJECT_STATE.md`) now describe Binance-only architecture.
- ADR-007 retains its original reason as historical context but is explicitly superseded in part by ADR-017.
- `COINSWITCH_FUTURES_BOUNDARY.md` is retained only as a superseded-history marker.
- `REPOSITORY_INSPECTION.md` records what the archive contained at inspection time and now points to this deprecation decision.

## Prohibited use

Do not run `main_trader.py`, `pipeline/live_trader.py`, or `dashboard.py`. Do not configure CoinSwitch credentials. Do not use the legacy client for account access, leverage changes, order submission, cancellation, or position monitoring.
