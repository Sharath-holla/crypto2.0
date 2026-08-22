from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import RESEARCH_CUTOFF, UniverseConfig
from crypto_ai.phase7.registry import SymbolRegistry, build_symbol_registry
from crypto_ai.phase7.universe import SymbolDescriptor

FIXTURE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")


def synthetic_registry(*, observed_at: datetime | None = None) -> SymbolRegistry:
    observed = observed_at or datetime(2026, 6, 30, tzinfo=UTC)
    first = datetime(2019, 1, 1, tzinfo=UTC)
    exchange_info = {
        "symbols": [
            {
                "symbol": symbol,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "onboardDate": int(first.timestamp() * 1_000),
                "status": "TRADING",
            }
            for symbol in FIXTURE_SYMBOLS
        ]
    }
    historical = [
        {
            "symbol": symbol,
            "base_asset": symbol.removesuffix("USDT"),
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
            "first_market_data_time": first,
            "last_market_data_time": RESEARCH_CUTOFF,
            "available_intervals": ["5m", "12h", "1d"],
            "metadata_sources": ["synthetic_fixture"],
        }
        for symbol in FIXTURE_SYMBOLS
    ]
    return build_symbol_registry(
        exchange_info,
        historical,
        observed_at=observed,
        research_cutoff=RESEARCH_CUTOFF,
    )


def synthetic_descriptors(
    *, as_of: datetime = datetime(2022, 1, 1, tzinfo=UTC)
) -> list[SymbolDescriptor]:
    result: list[SymbolDescriptor] = []
    for index, symbol in enumerate(FIXTURE_SYMBOLS):
        result.append(
            SymbolDescriptor(
                symbol=symbol,
                as_of=as_of,
                source_max_time=as_of - timedelta(days=1),
                trailing_quote_volume=1_000_000.0 * (index + 1),
                realized_volatility=0.01 + index * 0.005,
                trade_intensity=1_000.0 * (index + 1),
                funding_variability=0.00001 * (index + 1),
                btc_beta=1.0 if symbol == "BTCUSDT" else 0.5 + index * 0.1,
                btc_correlation=1.0 if symbol == "BTCUSDT" else 0.4 + index * 0.1,
                history_days=1_095.0,
                coverage_ratio=1.0,
            )
        )
    return result


def fixture_universe_config() -> UniverseConfig:
    return UniverseConfig(
        core_target_size=len(FIXTURE_SYMBOLS),
        fixture_mode=True,
        expansion_max_symbols_per_fold=2,
        total_max_symbols_per_fold=len(FIXTURE_SYMBOLS) + 2,
        minimum_history_days=90,
        age_bucket_edges_days=(90, 180, 365),
        selection_lookback_days=30,
    )


def synthetic_candles(
    *,
    rows_per_symbol: int = 720,
    start: datetime = datetime(2021, 12, 25, tzinfo=UTC),
) -> pa.Table:
    rows: list[dict[str, object]] = []
    step = timedelta(minutes=5)
    for symbol_index, symbol in enumerate(FIXTURE_SYMBOLS):
        base = (50_000.0, 4_000.0, 180.0, 0.8)[symbol_index]
        for index in range(rows_per_symbol):
            open_time = start + index * step
            trend = 1.0 + index * (0.00003 + symbol_index * 0.000005)
            cycle = 1.0 + 0.002 * np.sin((index + symbol_index * 5) / 17.0)
            open_price = base * trend * cycle
            close_price = open_price * (1.0 + 0.0005 * np.sin(index / 7.0))
            quote_volume = 1_000_000.0 * (symbol_index + 1) * (1.0 + 0.1 * np.cos(index / 11.0))
            rows.append(
                {
                    "symbol": symbol,
                    "open_time": open_time,
                    "open": open_price,
                    "high": max(open_price, close_price) * 1.001,
                    "low": min(open_price, close_price) * 0.999,
                    "close": close_price,
                    "base_volume": quote_volume / open_price,
                    "quote_volume": quote_volume,
                    "trade_count": 500 + symbol_index * 100 + index % 50,
                    "taker_buy_base_volume": quote_volume * 0.52 / open_price,
                    "taker_buy_quote_volume": quote_volume * 0.52,
                }
            )
    return pa.Table.from_pylist(rows).sort_by([("symbol", "ascending"), ("open_time", "ascending")])
