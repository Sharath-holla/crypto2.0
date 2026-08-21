"""
Signal Pipeline Configuration — config_signal.py
══════════════════════════════════════════════════════════════════════════════
Used exclusively by  main_signal.py  (Process 1).

Covers:
  • Model architecture & training hyper-parameters
  • Three-layer inference settings
  • Audit loop settings
  • Binance WebSocket listener settings
  • Symbol universe
  • Telegram / Discord alert settings
  • Signal queue output path (consumed by main_trader.py)
  • Logging

Does NOT contain any exchange account endpoints or order-execution settings.
Those live in config_trader.py.
══════════════════════════════════════════════════════════════════════════════
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR  = Path(__file__).parent.parent   # project root  (one level above pipeline/)
DATA_DIR  = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
LOG_DIR   = BASE_DIR / "logs"

for _d in (DATA_DIR, MODEL_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# Per-timeframe feature sets
# ══════════════════════════════════════════════════════════════════════════════

FEATURES: dict[str, list[str]] = {
    "15m": [
        "return_1", "return_3", "return_6",
        "ema20", "ema_diff",
        "atr_14", "atr_ratio", "vol_adj_return_1",
        "taker_sell_quote", "net_taker_volume",
        "cvd_24", "cvd_ratio_24", "buy_pressure",
        "volume_spike", "avg_trade_size", "trade_size_spike", "volume_change",
        "momentum_3", "momentum_4", "vol_adj_momentum_4",
        "vwap_24", "vwap_dev",
        "volatility_24", "volatility_regime",
        "volume_ma20", "liquidity_shock",
        "range_position",
    ],
    "1h": [
        "return_1", "return_3", "return_6", "return_12", "return_24",
        "ema20", "ema50", "ema_diff", "ema_slope",
        "atr_14", "atr_ratio", "vol_adj_return_1", "vol_adj_return_6",
        "taker_sell_quote", "net_taker_volume",
        "cvd_24", "cvd_ratio_24", "buy_pressure",
        "volume_spike", "avg_trade_size", "trade_size_spike", "volume_change",
        "momentum_3", "momentum_4", "vol_adj_momentum_4",
        "momentum_6", "price_acceleration",
        "vwap_24", "vwap_dev",
        "volatility_24", "volatility_regime",
        "volume_ma20", "liquidity_shock",
        "market_return", "daily_return",
        "range_position", "dist_from_high", "range_expansion",
        "efficiency_ratio", "trend_strength",
    ],
    "4h": [
        "return_1", "return_3", "return_6", "return_12", "return_24",
        "ema20", "ema50", "ema_diff", "ema_slope",
        "atr_14", "atr_ratio",
        "vol_adj_return_1", "vol_adj_return_6", "vol_adj_return_12",
        "cvd_24", "cvd_ratio_24",
        "volume_spike", "volume_change",
        "momentum_4", "vol_adj_momentum_4",
        "momentum_6", "price_acceleration",
        "vwap_24", "vwap_dev",
        "volatility_24", "volatility_regime",
        "volume_ma20", "liquidity_shock",
        "rolling_sharpe",
        "market_return", "daily_return",
        "range_position", "dist_from_high", "dist_from_low", "range_expansion",
        "efficiency_ratio", "trend_strength",
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
# Triple Barrier configuration
# ══════════════════════════════════════════════════════════════════════════════

BARRIER: dict[str, dict] = {
    "15m": {"upper_mult": 1.0, "lower_mult": 1.5, "time_bars": 20},
    "1h":  {"upper_mult": 1.0, "lower_mult": 1.5, "time_bars": 12},
    "4h":  {"upper_mult": 0.8, "lower_mult": 1.2, "time_bars":  6},
}

# ══════════════════════════════════════════════════════════════════════════════
# Purged Walk-Forward CV
# ══════════════════════════════════════════════════════════════════════════════

WF: dict = {
    "n_splits":  6,
    "gap_bars":  24,
    "val_ratio": 0.15,
}



# ══════════════════════════════════════════════════════════════════════════════
# Inference settings
# ══════════════════════════════════════════════════════════════════════════════

# Dynamic tiered thresholds (per cap tier)
# Keys: 0=large-cap, 1=mid-cap, 2=small-cap
TIER_THRESHOLDS = {
    0: {"signal": 0.510, "strong": 0.540, "exhausted": 0.670, "min_vol_to_mcap": 0.00001},
    1: {"signal": 0.510, "strong": 0.540, "exhausted": 0.670, "min_vol_to_mcap": 0.00005},
    2: {"signal": 0.520, "strong": 0.600, "exhausted": 0.900, "min_vol_to_mcap": 0.00100},
}

# Blended P(winner) − P(loser) must exceed this to suppress borderline signals
SIGNAL_MARGIN = 0.05

USE_PER_TIER_THRESHOLDS = True

# ── Flat fallback thresholds (legacy imports) ──────────────────────────────────
SIGNAL_THRESHOLD     = 0.51
STRONG_THRESHOLD     = 0.54
SHORT_THRESHOLD      = 0.53
EXHAUSTION_THRESHOLD = 0.90

# ══════════════════════════════════════════════════════════════════════════════
# Audit loop
# ══════════════════════════════════════════════════════════════════════════════

AUDIT_LOG_PATH            = LOG_DIR / "signals_audit.csv"
AUDIT_PRECISION_WINDOW    = 50    # rolling window (last N verified signals)
AUDIT_VERIFICATION_DELAY  = 4    # candles to wait before T+4 ground-truth check
AUDIT_HIT_RATIO           = 0.75  # fraction of MPE that counts as a "hit"
AUDIT_MIN_VERIFIED        = 20    # min verified signals before delta is trusted

# ══════════════════════════════════════════════════════════════════════════════
# Model paths
# ══════════════════════════════════════════════════════════════════════════════

ACTIVE_TIMEFRAME    = "15m"
MODEL_PATH          = MODEL_DIR / "base_model_15m.pkl"
CAP_CALIBRATOR_PATH = MODEL_DIR / "cap_calibrator.pkl"

# ══════════════════════════════════════════════════════════════════════════════
# Binance WebSocket listener settings
# ══════════════════════════════════════════════════════════════════════════════

EXCHANGE_ID   = "binance"
MARKET_TYPE   = "future"       # perpetual futures
TIMEFRAME     = "15m"
CANDLE_SECONDS = 15 * 60      # 900 s — used for candle-close detection

# Rolling buffer per symbol. Must be >= max feature lookback (250 safe minimum).
BUFFER_SIZE   = 250

# Wait for this fraction of symbols to close before running inference
MARKET_RETURN_WAIT_FRAC = 0.8

# Cross-symbol data collection for vol_rank_pct / flow_vs_peers features
COLLECT_CROSS_SYMBOL_DATA = True

# ── Trade gate ─────────────────────────────────────────────────────────────────
FLOW_VS_PEERS_LIMIT = 0.3

# ══════════════════════════════════════════════════════════════════════════════
# Tracked symbols
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
# Alert dispatcher (Telegram / Discord)
# ══════════════════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK")

# Minimum seconds between alerts for the SAME symbol (prevents spam)
ALERT_COOLDOWN_S = 4 * CANDLE_SECONDS   # 1 hour = 4 × 15m candles

# ══════════════════════════════════════════════════════════════════════════════
# Signal Queue CSV  (written here, read by main_trader.py)
# ══════════════════════════════════════════════════════════════════════════════

SIGNALS_QUEUE_PATH = LOG_DIR / "signals_queue.csv"

# Column order must stay in sync with config_trader.py
SIGNALS_QUEUE_HEADER = [
    "row_id",        # auto-increment integer, never resets across restarts
    "written_at",    # ISO-8601 UTC when written
    "symbol",        # e.g. "BTCUSDT"
    "candle_ts",     # ISO-8601 candle open timestamp
    "signal",        # "long" | "short"
    "strong",        # "True" | "False"
    "close",         # close price at signal time (used for entry offset)
    "mpe_target",    # Layer-3 MPE % (used as TP distance); empty if Layer 3 off
    "p_long",        # blended P(long)
    "p_short",       # blended P(short)
    "p_hold",        # blended P(hold)
    "p_base_long",   # raw Layer-1 P(long)
    "p_base_short",  # raw Layer-1 P(short)
    "p_cal_long",    # Layer-2 calibrated P(long)
    "p_cal_short",   # Layer-2 calibrated P(short)
    "cap_tier",      # 0 | 1 | 2
    "cap_tier_name", # "large" | "mid" | "small"
    "vol_to_mcap",   # volume-to-market-cap ratio
    "flow_vs_peers", # normalised flow vs peer group
    "market_return", # equal-weight market return at candle close
    "precision_est", # historical out-of-sample precision estimate
]

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOG_LEVEL       = "INFO"
SIGNAL_LOG_PATH = LOG_DIR / "signals.log"
