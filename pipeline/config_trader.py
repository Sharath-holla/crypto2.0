# DEPRECATED: CoinSwitch-specific legacy configuration. ADR-017 supersedes this
# architecture. Do not load it for account access or execution.
"""
Trading Engine Configuration — config_trader.py
══════════════════════════════════════════════════════════════════════════════
Used exclusively by  main_trader.py  (Process 2).

Covers:
  • All CoinSwitch Pro API endpoints (standard + HFT/DMA)
  • Order-execution parameters (leverage, risk, SL, TP, sizing)
  • Signal queue input path (produced by main_signal.py)
  • Trader position-state & queue-reader state file paths
  • Binance REST settings used for price_tick / candle_tick monitoring
  • Logging

Does NOT contain any model weights, inference settings, or alert tokens.
Those live in config_signal.py.
══════════════════════════════════════════════════════════════════════════════
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent.parent   # project root
LOG_DIR  = BASE_DIR / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# CoinSwitch Pro API — Base URLs
# ══════════════════════════════════════════════════════════════════════════════
#
# Two distinct base URLs serve different sub-systems:
#
#   BASE_URL     — Standard CoinSwitch REST (key validation, wallet queries)
#   HFT_BASE_URL — HFT/DMA sub-account (all order operations, Bybit V5 dialect)
#
# Authentication is identical for both: Ed25519, same header set.

BASE_URL     = "https://coinswitch.co"
HFT_BASE_URL = "https://dma.coinswitch.co"

# ── CoinSwitch identifier ──────────────────────────────────────────────────────
# Required in fund-transfer payloads; only supported futures exchange.
EXCHANGE = "EXCHANGE_2"

# ══════════════════════════════════════════════════════════════════════════════
# Standard CoinSwitch endpoints  (https://coinswitch.co)
# ══════════════════════════════════════════════════════════════════════════════

# GET — Validate API key pair; call once at startup before placing orders
EP_VALIDATE_KEYS  = "/trade/api/v2/validate/keys"

# GET — CoinSwitch server time (ms epoch); useful for clock-skew checks
EP_SERVER_TIME    = "/trade/api/v2/time"

# GET — CoinSwitch server ping
EP_SERVER_PING = "/trade/api/v2/ping"

# GET — Futures wallet USDT balance (standard REST view)
EP_FUTURES_WALLET = "/trade/api/v2/futures/wallet_balance"

# GET — Spot portfolio (fallback balance source)
EP_SPOT_PORTFOLIO = "/trade/api/v2/user/portfolio"

# ══════════════════════════════════════════════════════════════════════════════
# HFT/DMA endpoints  (https://dma.coinswitch.co — Bybit V5 REST dialect)
# ══════════════════════════════════════════════════════════════════════════════

# POST — Move funds into / out of the HFT sub-account
#        Body: { "exchange": EXCHANGE, "amount": float, "type": "in"|"out" }
EP_HFT_FUND_TRANSFER    = "/dma/api/v1/funds/transfer"

# POST — Set leverage for a symbol (must be called before first order)
#        Body: { "category": "linear", "symbol": str,
#                "buyLeverage": str, "sellLeverage": str }
EP_HFT_SET_LEVERAGE     = "/v5/position/set-leverage"

# POST — Place any order type (Limit / Market / Stop-Limit / Stop-Market)
#        Body: { "category": "linear", "symbol", "side", "orderType",
#                "qty", "price"?, "timeInForce", "positionIdx",
#                "reduceOnly", "triggerPrice"?, "triggerBy"?,
#                "triggerDirection"?, "stopOrderType"?, "orderLinkId"? }
EP_HFT_ORDER_CREATE     = "/v5/order/create"

# POST — Cancel a single active order by orderId or orderLinkId
#        Body: { "category": "linear", "symbol", "orderId"? | "orderLinkId"? }
EP_HFT_ORDER_CANCEL     = "/v5/order/cancel"

# POST — Cancel ALL open orders for a symbol at once
#        Body: { "category": "linear", "symbol" }
EP_HFT_ORDER_CANCEL_ALL = "/v5/order/cancel-all"

# GET  — Active (open / partially-filled) orders; filter by symbol / orderId
#        Params: category=linear & symbol & orderId? → result.list[]
EP_HFT_ORDER_REALTIME   = "/v5/order/realtime"

# GET  — Filled / cancelled order history
#        Params: category=linear & symbol & orderId? → result.list[]
EP_HFT_ORDER_HISTORY    = "/v5/order/history"

# GET  — Open perpetual futures positions
#        Params: category=linear & symbol? → result.list[]
#        Key fields: symbol, side (Buy/Sell), size, avgPrice, unrealisedPnl, leverage
EP_HFT_POSITION_LIST    = "/v5/position/list"

# GET  — HFT/DMA unified account USDT wallet balance
#        Params: accountType=UNIFIED → result.list[0].coin[]
EP_HFT_WALLET_BALANCE   = "/v5/account/wallet-balance"

# GET  — Instrument info: tick-size / lot-size / min-qty for all or one symbol
#        Params: category=linear & symbol? → result.list[]
#        Key fields per instrument:
#          symbol, priceFilter.tickSize, lotSizeFilter.qtyStep, lotSizeFilter.minOrderQty
EP_HFT_INSTRUMENTS_INFO = "/v5/market/instruments-info"

# ══════════════════════════════════════════════════════════════════════════════
# Order-execution parameters
# ══════════════════════════════════════════════════════════════════════════════

LEVERAGE               = 5.0    # futures leverage multiplier
RISK_PCT               = 0.1   # fraction of equity risked per trade
SL_PCT                 = 0.05  # stop-loss distance from fill price (1.5%)
DEFAULT_TP_PCT         = 0.025  # fallback TP if Layer-3 MPE unavailable (1.67 RR)
RR_RATIO               = 1.67   # min reward:risk for fallback TP calculation
MAX_HOLD_BARS          = 20     # force-close after N candles (= barrier time_bars)
MAX_CONCURRENT         = 5      # max simultaneous open positions
MAX_MARGIN_PCT         = 0.20   # one position cannot exceed 20% of equity as margin
LIQUIDATION_THRESHOLD  = 0.50   # liquidate if unrealised loss > 50% of margin

# ── Entry & pending-order settings ────────────────────────────────────────────
# Limit entry is placed at close ± ENTRY_OFFSET_PCT to improve fill probability
ENTRY_OFFSET_PCT = 0.002   # 0.2% offset from signal-close price

# Cancel pending limit entry if it hasn't filled within this many 15m candles
MAX_PENDING_BARS = 1

# ══════════════════════════════════════════════════════════════════════════════
# Signal Queue CSV  (produced by main_signal.py, consumed here)
# ══════════════════════════════════════════════════════════════════════════════

SIGNALS_QUEUE_PATH = LOG_DIR / "signals_queue.csv"

# Column list must stay in sync with config_signal.py SIGNALS_QUEUE_HEADER
SIGNALS_QUEUE_HEADER = [
    "row_id",
    "written_at",
    "symbol",
    "candle_ts",
    "signal",        # "long" | "short"
    "strong",        # "True" | "False"
    "close",         # close price at signal time
    "mpe_target",    # Layer-3 MPE %; empty if not available
    "p_long",
    "p_short",
    "p_hold",
    "p_base_long",
    "p_base_short",
    "p_cal_long",
    "p_cal_short",
    "cap_tier",
    "cap_tier_name",
    "vol_to_mcap",
    "flow_vs_peers",
    "market_return",
    "precision_est",
]

# ── Trader queue reader state ──────────────────────────────────────────────────
# Stores the last processed row_id so the reader survives restarts without
# re-processing old signals.
TRADER_QUEUE_STATE_PATH = LOG_DIR / "trader_queue_state.json"

# ══════════════════════════════════════════════════════════════════════════════
# Binance REST — used by main_trader.py for price_tick & candle_tick
# ══════════════════════════════════════════════════════════════════════════════
#
# The trader process does NOT open a WebSocket to Binance. Instead it uses
# lightweight REST calls:
#   • fetch_tickers()  — every 1.5 s for active symbols  → price_tick()
#   • fetch_ohlcv()    — every 15m boundary               → candle_tick()

EXCHANGE_ID    = "binance"
MARKET_TYPE    = "future"
TIMEFRAME      = "15m"
CANDLE_SECONDS = 15 * 60    # 900 s — used to compute time to next candle close

# Polling intervals (seconds)
PRICE_POLL_INTERVAL  = 1.5   # fast loop: price_tick
CANDLE_TICK_BUFFER_S = 5.0   # extra wait after boundary to ensure candle is settled

# ══════════════════════════════════════════════════════════════════════════════
# Tracked symbols  (required to build the sym_key → exchange-symbol map)
# ══════════════════════════════════════════════════════════════════════════════

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT", "SOL/USDT:USDT",
    "XRP/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT", "DOGE/USDT:USDT",
    "DOT/USDT:USDT", "LINK/USDT:USDT", "LTC/USDT:USDT", "XPIN/USDT:USDT",
    "UNI/USDT:USDT", "ATOM/USDT:USDT", "NEAR/USDT:USDT", "FTM/USDT:USDT",
    "SAND/USDT:USDT", "MANA/USDT:USDT", "AAVE/USDT:USDT", "AXS/USDT:USDT",
    "RIVER/USDT:USDT", "BEAT/USDT:USDT", "PIPPIN/USDT:USDT", "KITE/USDT:USDT",
    "SIREN/USDT:USDT", "ZEC/USDT:USDT", "ARIA/USDT:USDT", "TRIA/USDT:USDT",
    "POL/USDT:USDT", "MAGMA/USDT:USDT", "STABLE/USDT:USDT", "NIGHT/USDT:USDT",
    "GIGGLE/USDT:USDT", "PRL/USDT:USDT", "FARTCOIN/USDT:USDT", "UAI/USDT:USDT",
    "H/USDT:USDT", "VIRTUAL/USDT:USDT", "CLO/USDT:USDT", "FHE/USDT:USDT",
    "TRUST/USDT:USDT", "1000PEPE/USDT:USDT", "RAVE/USDT:USDT", "FIGHT/USDT:USDT",
    "BAN/USDT:USDT", "BOB/USDT:USDT", "VELVET/USDT:USDT", "BLESS/USDT:USDT",
    "APR/USDT:USDT", "CYS/USDT:USDT", "COAI/USDT:USDT", "KGEN/USDT:USDT",
    "BANANAS31/USDT:USDT", "4/USDT:USDT", "XPL/USDT:USDT", "EDGE/USDT:USDT",
    "ZAMA/USDT:USDT", "TRUMP/USDT:USDT", "XAU/USDT:USDT", "VVV/USDT:USDT",
    "F/USDT:USDT", "STRK/USDT:USDT", "M/USDT:USDT", "HANA/USDT:USDT",
    "TIA/USDT:USDT", "MERL/USDT:USDT", "LIGHT/USDT:USDT",
]

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOG_LEVEL = "DEBUG"
