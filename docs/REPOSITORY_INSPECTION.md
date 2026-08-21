# Repository Inspection

Inspection date: 2026-08-19

The supplied archive contained a legacy prototype but no Git history, package metadata, dependency declaration, tests, documentation, historical downloader, or `AGENTS.md`. All Python files were parsed and their imports, definitions, API calls, configuration, storage behavior, and external dependencies were inventoried. No notebook or database code was present.

## GOOD - KEEP

- `pipeline/listener.py`: preserves useful live-market concepts such as confirmed-candle handling, bounded per-symbol buffers, asynchronous streams, exchange rate limiting through CCXT, and taker-volume enrichment. It is a future live-data reference, not the Phase 1 historical downloader.
- `pipeline/coinswitch_client.py`: historically kept standard CoinSwitch and HFT/DMA domains separate and contained useful adapter-boundary ideas. ADR-017 now deprecates the entire venue-specific client; it is retained temporarily, not supported.
- `pipeline/audit.py` and `pipeline/alerts.py`: contain useful audit-log and non-blocking alert concepts for later phases.
- `phaseA/features.py`, `phaseA/labels.py`, `pipeline/inference.py`, and `extra/model_dl.py`: contain reusable research ideas. They remain preserved for later evaluation; none is imported by the Phase 1 package.
- `main_signal.py` and `main_trader.py`: document an intended process boundary between signal creation and execution. Only the exchange-independent boundary concept is worth retaining; the CoinSwitch execution implementation is deprecated.

## CHANGE - MODIFY BEFORE FUTURE USE

- The existing Binance path is a 15-minute USD-M futures live/bootstrap integration, not a historical pipeline. It converts exchange decimals to `float`, uses a CCXT exchange-specific method (`fapiPublicGetKlines`), lacks deterministic pagination/manifests, and cannot produce immutable raw data.
- `pipeline/listener.py` broadly catches exceptions and reconnects indefinitely. It needs typed failure categories, stale-data detection, bounded operational policies, and current API verification before production use.
- `pipeline/config_signal.py` and `pipeline/config_trader.py` use module-level mutable configuration and filesystem side effects during import. They contain large hard-coded symbol lists and mix environment loading with runtime policy.
- `pipeline/config_trader.py` contains live leverage and risk constants. `pipeline/live_trader.py` also defines fallback leverage/risk values when imports fail. This is unsafe for production and must remain disabled until the risk and execution phases.
- CoinSwitch endpoints, signing, identifiers, credentials, account calls, and order behavior are deprecated and must not be revalidated or reused. Any future execution research must begin from current official Binance documentation after explicit Phase 4 authorization.
- CSV files are used as a cross-process queue and state store without a durable transaction/locking design. This is not suitable for production execution state.
- `data/inference.py` and `pipeline/inference.py` are near-duplicate implementations; `extra/config_signal.py` also overlaps `pipeline/config_signal.py`. They must be reconciled later, after tests establish intended behavior.
- The legacy code depends on undeclared packages including CCXT Pro, pandas, NumPy, scikit-learn, PyTorch, aiohttp, cryptography, python-dotenv, and numba.

## REMOVE

- `.DS_Store` and all `__pycache__/`/`.pyc` files are generated platform artifacts. They are ignored by Git and can be deleted safely; they were left physically untouched to preserve the supplied archive exactly.
- `.vscode/settings.json` is a developer-local environment preference rather than project behavior; it is preserved locally but ignored.
- `*.egg-info/` is generated packaging metadata and is ignored rather than versioned.
- Empty `logs/` and `models/` runtime directories do not need tracked placeholders.
- No source file was deleted. Apparent duplicates require behavioral tests before removal.

## MISSING

The archive lacked every core Phase 1 component:

- installable package metadata and dependency management;
- repository instructions, README, architecture, decisions, state, runbook, and data dictionary;
- current Binance historical-data contract documentation;
- a Spot/USD-M historical kline adapter with deterministic pagination and safe retries;
- exact canonical candle types and Arrow schema;
- immutable bronze Parquet layout, atomic writes, checksums, and manifests;
- resumable partition discovery and duplicate-conflict detection;
- instrument metadata snapshots;
- structured ingestion logs;
- validation for schema/nulls, timestamps, intervals/gaps, OHLC, and volumes;
- unit, schema, data-quality, mocked API, and integration tests.

The new `src/crypto_ai/` implementation supplies these missing Phase 1 components without importing or activating the legacy trading system.
