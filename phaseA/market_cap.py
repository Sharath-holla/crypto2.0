"""
Market Cap Tier Registry — Phase B extension

Provides:
  1. Static tier assignments for all 29 symbols (stable — BTC has always
     been large cap; SAND has always been small cap over 2020-2026)
  2. CoinGecko live refresh (runs once at startup + every 24h)
     Updates the tier if a coin crosses a cap boundary
  3. Per-candle feature computation:
       cap_tier          : 0=large, 1=mid, 2=small  (int for LightGBM)
       vol_to_mcap_ratio : quote_volume_24h / market_cap_usd
                           large-cap: ~0.001–0.05  small-cap: ~0.05–0.50+
       flow_per_mcap     : |net_taker_volume_24h| / market_cap_usd
                           captures how much directional pressure relative to coin size
       vol_rank_pct      : percentile rank of this symbol's volume vs all symbols
                           at the same timestamp (0=lowest vol, 1=highest)
       flow_vs_peers     : (this symbol net_taker_24) / (median net_taker_24 all symbols)
                           ratio > 1 = this coin getting disproportionate order flow

Why these features unlock the "small-cap pump" pattern:
  - vol_to_mcap_ratio for a small cap during a pump event: 0.20–0.50
    (20–50% of the entire market cap trading in one day — extreme)
  - Same ratio for BTC on the same day: 0.01–0.03 (normal)
  - The base model saw volume_spike but NOT this ratio — it has no way to
    distinguish "BTC volume doubled = mild signal" from
    "SAND volume doubled = potential 30% move"
  - flow_vs_peers detects: this coin is absorbing far more taker buy flow
    than the rest of the market — often precedes a cap-relative breakout

Cap boundaries (USD market cap):
  Large  : > $5B    (BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX)
  Mid    : $500M–$5B (MATIC, LINK, LTC, UNI, ATOM, NEAR, AAVE)
  Small  : < $500M  (FTM, SAND, MANA, AXS, DOT at current cap)

Note: DOT was historically mid/large cap. Assigned mid as a conservative default.
"""

import asyncio
import logging
import time
from typing import Optional

import aiohttp
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Static cap tier assignments ────────────────────────────────────────────────
# Tier: 0=large, 1=mid, 2=small
# CoinGecko IDs used for live refresh
SYMBOL_META: dict[str, dict] = {
    "BTCUSDT":      {"tier": 0, "cg_id": "bitcoin",                 "mcap_usd": 1_900_000_000_000},
    "ETHUSDT":      {"tier": 0, "cg_id": "ethereum",                "mcap_usd":   320_000_000_000},
    "BNBUSDT":      {"tier": 0, "cg_id": "binancecoin",             "mcap_usd":    90_000_000_000},
    "SOLUSDT":      {"tier": 0, "cg_id": "solana",                  "mcap_usd":    75_000_000_000},
    "XRPUSDT":      {"tier": 0, "cg_id": "ripple",                  "mcap_usd":    65_000_000_000},
    "ADAUSDT":      {"tier": 0, "cg_id": "cardano",                 "mcap_usd":    35_000_000_000},
    "AVAXUSDT":     {"tier": 0, "cg_id": "avalanche-2",             "mcap_usd":    14_000_000_000},
    "DOGEUSDT":     {"tier": 0, "cg_id": "dogecoin",                "mcap_usd":    40_000_000_000},
    
    "DOTUSDT":      {"tier": 1, "cg_id": "polkadot",                "mcap_usd":     8_000_000_000},
    "LINKUSDT":     {"tier": 1, "cg_id": "chainlink",               "mcap_usd":     8_500_000_000},
    "LTCUSDT":      {"tier": 1, "cg_id": "litecoin",                "mcap_usd":     6_000_000_000},
    "UNIUSDT":      {"tier": 1, "cg_id": "uniswap",                 "mcap_usd":     5_500_000_000},
    "1000PEPEUSDT": {"tier": 1, "cg_id": "pepe",                    "mcap_usd":     4_500_000_000},
    "POLUSDT":      {"tier": 1, "cg_id": "polygon-ecosystem-token", "mcap_usd":     3_500_000_000},
    "ATOMUSDT":     {"tier": 1, "cg_id": "cosmos",                  "mcap_usd":     2_800_000_000},
    "NEARUSDT":     {"tier": 1, "cg_id": "near",                    "mcap_usd":     2_500_000_000},
    "AAVEUSDT":     {"tier": 1, "cg_id": "aave",                    "mcap_usd":     2_200_000_000},
    
    "VIRTUALUSDT":  {"tier": 2, "cg_id": "virtual-protocol",        "mcap_usd":       800_000_000},
    "FTMUSDT":      {"tier": 2, "cg_id": "fantom",                  "mcap_usd":       700_000_000},
    "SANDUSDT":     {"tier": 2, "cg_id": "the-sandbox",             "mcap_usd":       600_000_000},
    "MANAUSDT":     {"tier": 2, "cg_id": "decentraland",            "mcap_usd":       550_000_000},
    "AXSUSDT":      {"tier": 2, "cg_id": "axie-infinity",           "mcap_usd":       450_000_000},
    "ZECUSDT":      {"tier": 2, "cg_id": "zcash",                   "mcap_usd":       400_000_000},
    "FARTCOINUSDT": {"tier": 2, "cg_id": "fartcoin",                "mcap_usd":       350_000_000},
    "PIPPINUSDT":   {"tier": 2, "cg_id": "pippin",                  "mcap_usd":       150_000_000},
    "FHEUSDT":      {"tier": 2, "cg_id": "fhenix",                  "mcap_usd":       100_000_000},
    "XPINUSDT":     {"tier": 2, "cg_id": "xpin",                    "mcap_usd":        50_000_000},
    "RIVERUSDT":    {"tier": 2, "cg_id": "river",                   "mcap_usd":        50_000_000},
    "BEATUSDT":     {"tier": 2, "cg_id": "beat",                    "mcap_usd":        50_000_000},
    "KITEUSDT":     {"tier": 2, "cg_id": "kite",                    "mcap_usd":        50_000_000},
    "SIRENUSDT":    {"tier": 2, "cg_id": "siren",                   "mcap_usd":        50_000_000},
    "ARIAUSDT":     {"tier": 2, "cg_id": "aria",                    "mcap_usd":        50_000_000},
    "TRIAUSDT":     {"tier": 2, "cg_id": "tria",                    "mcap_usd":        50_000_000},
    "MAGMAUSDT":    {"tier": 2, "cg_id": "magma",                   "mcap_usd":        50_000_000},
    "STABLEUSDT":   {"tier": 2, "cg_id": "stable",                  "mcap_usd":        50_000_000},
    "NIGHTUSDT":    {"tier": 2, "cg_id": "night",                   "mcap_usd":        50_000_000},
    "GIGGLEUSDT":   {"tier": 2, "cg_id": "giggle",                  "mcap_usd":        50_000_000},
    "PRLUSDT":      {"tier": 2, "cg_id": "prl",                     "mcap_usd":        50_000_000},
    "UAIUSDT":      {"tier": 2, "cg_id": "uai",                     "mcap_usd":        50_000_000},
    "HUSDT":        {"tier": 2, "cg_id": "h",                       "mcap_usd":        50_000_000},
    "CLOUSDT":      {"tier": 2, "cg_id": "clo",                     "mcap_usd":        50_000_000},
    "TRUSTUSDT":    {"tier": 2, "cg_id": "trust",                   "mcap_usd":        50_000_000},
}

TIER_NAMES = {0: "large-cap", 1: "mid-cap", 2: "small-cap"}

# Refresh interval for live CoinGecko data
_REFRESH_INTERVAL_S = 24 * 3600   # every 24h
_last_refresh_ts: float = 0.0


# ── Live market cap refresh ────────────────────────────────────────────────────

async def refresh_market_caps(session: Optional[aiohttp.ClientSession] = None) -> None:
    """
    Fetch current market caps from CoinGecko and update SYMBOL_META in-place.
    Uses the free CoinGecko API (no key required, rate limit: 10–30 req/min).
    Silently skips on network errors — static values are the fallback.

    Called once at startup and then every 24h by a background task.
    """
    global _last_refresh_ts

    cg_ids = [m["cg_id"] for m in SYMBOL_META.values()]
    ids_param = ",".join(cg_ids)
    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids_param}&vs_currencies=usd&include_market_cap=true"
    )

    own_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        own_session = True

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.warning(f"[mcap] CoinGecko returned {resp.status} — using static values")
                return
            data = await resp.json()

        updated = 0
        for sym, meta in SYMBOL_META.items():
            cg_id = meta["cg_id"]
            if cg_id not in data:
                continue
            new_mcap = data[cg_id].get("usd_market_cap", meta["mcap_usd"])
            meta["mcap_usd"] = float(new_mcap)

            # Re-tier based on updated market cap
            if new_mcap >= 5_000_000_000:
                new_tier = 0
            elif new_mcap >= 500_000_000:
                new_tier = 1
            else:
                new_tier = 2

            if new_tier != meta["tier"]:
                logger.info(
                    f"[mcap] {sym} tier changed: "
                    f"{TIER_NAMES[meta['tier']]} → {TIER_NAMES[new_tier]} "
                    f"(mcap=${new_mcap/1e9:.2f}B)"
                )
                meta["tier"] = new_tier
            updated += 1

        _last_refresh_ts = time.time()
        logger.info(f"[mcap] Market caps refreshed | {updated} symbols updated")

    except Exception as e:
        logger.warning(f"[mcap] CoinGecko refresh failed: {e} — using static values")
    finally:
        if own_session:
            await session.close()


async def run_refresh_loop(session: aiohttp.ClientSession) -> None:
    """Background coroutine — refreshes market caps every 24 hours."""
    while True:
        await refresh_market_caps(session)
        await asyncio.sleep(_REFRESH_INTERVAL_S)


# ── Per-candle cap feature computation ────────────────────────────────────────

def compute_cap_features(
    symbol:              str,
    quote_volume:        float,   # this candle's quote volume (USD)
    net_taker_volume:    float,   # taker_buy_quote - taker_sell_quote
    cvd_24:              float,   # cumulative volume delta over 24 bars
    all_quote_volumes:   dict[str, float],   # {symbol: quote_volume} at this timestamp
    all_net_taker:       dict[str, float],   # {symbol: net_taker_volume} at this timestamp
) -> dict:
    """
    Compute cap-normalised order flow features for one symbol at one timestamp.

    Parameters
    ----------
    symbol            : e.g. "BTCUSDT"
    quote_volume      : this candle's USD trading volume
    net_taker_volume  : taker_buy - taker_sell (positive = buying pressure)
    cvd_24            : 24-bar cumulative volume delta from feature engineering
    all_quote_volumes : mapping of ALL symbols' quote_volume at same timestamp
    all_net_taker     : mapping of ALL symbols' net_taker_volume at same timestamp

    Returns dict with:
      cap_tier          int   0/1/2
      vol_to_mcap_ratio float quote_volume / market_cap
      flow_per_mcap     float |net_taker_volume| / market_cap
      cvd_to_mcap       float cvd_24 / market_cap  (24-bar directional pressure)
      vol_rank_pct      float 0–1  percentile of this symbol's volume vs peers
      flow_vs_peers     float this symbol's net_taker / median(all net_taker)
      cap_tier_name     str   "large-cap" / "mid-cap" / "small-cap"
    """
    sym_key = symbol.replace("/", "").replace(":USDT", "")
    meta    = SYMBOL_META.get(sym_key, {"tier": 1, "mcap_usd": 1_000_000_000})
    tier    = meta["tier"]
    mcap    = max(meta["mcap_usd"], 1e6)   # floor at $1M to avoid div-by-zero

    # Normalised volume and flow
    vol_to_mcap   = quote_volume      / mcap
    flow_per_mcap = abs(net_taker_volume) / mcap
    cvd_to_mcap   = cvd_24            / mcap

    # Cross-symbol ranking (requires peer data)
    all_vols = list(all_quote_volumes.values())
    if len(all_vols) >= 2:
        rank = np.searchsorted(np.sort(all_vols), quote_volume) / len(all_vols)
        vol_rank_pct = float(np.clip(rank, 0.0, 1.0))
    else:
        vol_rank_pct = 0.5

    peer_taker = [v for k, v in all_net_taker.items() if k != sym_key]
    if peer_taker:
        median_peer = float(np.median(np.abs(peer_taker))) or 1.0
        flow_vs_peers = abs(net_taker_volume) / median_peer
    else:
        flow_vs_peers = 1.0

    return {
        "cap_tier":          tier,
        "vol_to_mcap_ratio": float(np.clip(vol_to_mcap,   0.0, 10.0)),
        "flow_per_mcap":     float(np.clip(flow_per_mcap, 0.0, 5.0)),
        "cvd_to_mcap":       float(np.clip(cvd_to_mcap,  -5.0, 5.0)),
        "vol_rank_pct":      vol_rank_pct,
        "flow_vs_peers":     float(np.clip(flow_vs_peers, 0.0, 20.0)),
        "cap_tier_name":     TIER_NAMES[tier],
    }


def get_tier_thresholds(tier: int) -> dict:
    """
    Per-tier signal thresholds.

    Rationale:
      Large-cap signals need higher P(long) because the base model already
      sees many large-cap examples and the precision curve is flatter.
      Small-cap signals can use a slightly lower threshold because a genuine
      order-flow imbalance relative to market cap is a stronger signal —
      but we require a higher vol_to_mcap_ratio to confirm it's real.

    These are starting defaults. Tune using signals.log after 2–4 weeks live.
    """
    return {
        0: {"signal": 0.510, "strong": 0.540, "exhausted": 0.670, "min_vol_to_mcap": 0.001},  # large
        1: {"signal": 0.510, "strong": 0.540, "exhausted": 0.670, "min_vol_to_mcap": 0.005},  # mid
        2: {"signal": 0.510, "strong": 0.540, "exhausted": 0.670, "min_vol_to_mcap": 0.015},  # small
    }[tier]
