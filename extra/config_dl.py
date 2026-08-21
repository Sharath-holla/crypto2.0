"""
config_dl.py — Deep Learning model configuration
══════════════════════════════════════════════════════════════════════════════
Extends pipeline/config_signal.py. All training, model, and sequence settings
live here. Does NOT duplicate anything already in config_signal.py.

Data directory: transformer/data/  (parquet files downloaded from Binance)
Model/log dirs: shared with the rest of the project (models/, logs/)

PATCH NOTES
───────────
Fix #7 — label_smoothing reduced from 0.05 → 0.01.
  The focal-loss term already handles the "downweight easy examples" problem
  that label smoothing is normally meant to address. At 0.05, smoothing was
  spreading probability mass toward the wrong-direction classes that the
  punishment matrix is specifically trying to penalise (4×). Reducing to 0.01
  keeps a tiny regularisation effect without fighting the punishment signal.
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import torch
from pathlib import Path
from pipeline.config_signal import MODEL_DIR, LOG_DIR, WF, BARRIER

# ══════════════════════════════════════════════════════════════════════════════
# Sequence / window settings
# ══════════════════════════════════════════════════════════════════════════════

SEQ = {
    "interval":        "15m",
    "input_days":      2,              # How many past days feed into the model
    "candles_per_day": 96,             # 15m candles per calendar day
    # seq_len = input_days × candles_per_day + 1 (present candle)
    # 2 × 96 + 1 = 193 candles per sequence
    "seq_len":         193,
    "recency_decay":   0.997,
    # Per-candle exponential decay: present=1.0, 100 candles ago≈0.74
    # Applied AFTER per-window z-score normalisation
}

# ══════════════════════════════════════════════════════════════════════════════
# Model architecture  (HFTMultiScaleTransformer)
# ══════════════════════════════════════════════════════════════════════════════

DL_MODEL = {
    # Multi-scale Conv1D front-end (3 parallel branches)
    "conv_channels":   64,
    "conv_kernel":     3,
    # dilations per branch:
    #   Scale 1 [1,2,4]   → RF 15 candles  (microstructure)
    #   Scale 2 [4,8,16]  → RF 60 candles  (momentum)
    #   Scale 3 [16,32,64]→ RF 192 candles (regime)

    # Transformer encoder
    "d_model":         256,
    "nhead":           8,              # head_dim = 32
    "num_layers":      6,              # upgraded from 4
    "dim_feedforward": 512,
    "dropout":         0.12,
    "stoch_depth_p":   0.05,          # stochastic depth drop prob per layer

    # Output
    "num_classes":     3,             # 0=SHORT, 1=HOLD, 2=LONG
}

# ══════════════════════════════════════════════════════════════════════════════
# Punishment loss — asymmetric cross-entropy weights
# ══════════════════════════════════════════════════════════════════════════════
#
# Matrix layout: [true_class_row][predicted_class_col]
# Label mapping: 0=SHORT, 1=HOLD, 2=LONG
#
# Design rationale:
#   - Wrong direction (LONG→SHORT or SHORT→LONG) = most dangerous → 4.0×
#   - Missing a move (predicting HOLD when a winner exists)       → 2.5×
#   - False alarm (predicting direction when it is HOLD)          → 2.0×
#   - Correct prediction                                          → 1.0×

PUNISHMENT_MATRIX = [
    #  pred:SHORT  pred:HOLD  pred:LONG
    [1.0,          2.5,       4.0],   # true: SHORT
    [2.0,          1.0,       2.0],   # true: HOLD
    [4.0,          2.5,       1.0],   # true: LONG
]

# ══════════════════════════════════════════════════════════════════════════════
# Training hyper-parameters
# ══════════════════════════════════════════════════════════════════════════════

DL_TRAIN = {
    # ── M3 MPS tuning (24 GB unified memory) ────────────────────────────────
    # batch_size=128: M3's unified memory bandwidth saturates around 128.
    # 128 × 193 × 52 × 4 B = ~52 MB per batch — well within headroom.
    # AMP is disabled on MPS (use_amp = device.type == 'cuda'), so fp32 is used.
    "batch_size":        128,
    "lr":                3e-4,
    "weight_decay":      1e-4,
    "betas":             (0.9, 0.999),   # AdamW betas
    "epochs":            150,
    "patience":          20,             # Early stopping on val loss
    "grad_clip":         1.0,
    "warmup_steps":      1000,           # Linear warmup before cosine annealing
    "min_lr":            1e-6,           # Cosine annealing floor
    # FIX #7: reduced from 0.05 — focal loss already handles easy-example
    # downweighting; high smoothing fights the punishment matrix (4× wrong-dir).
    "label_smoothing":   0.01,
    # Focal loss settings (added to PunishmentLoss)
    "focal_gamma":       2.0,            # Focus on hard examples
    "focal_weight":      0.40,           # Weight of focal term vs punishment term
    # MC Dropout uncertainty estimation
    "mc_samples":        20,             # Forward passes at inference time
    "uncertainty_threshold": 0.08,       # Suppress signal if winner-class std > this
}

# ══════════════════════════════════════════════════════════════════════════════
# Purged walk-forward CV  (extends WF from config_signal.py)
# ══════════════════════════════════════════════════════════════════════════════

DL_WF = {
    **WF,                              # inherit gap_bars=24, val_ratio=0.15
    "n_splits":        8,              # upgraded from 6
    "ensemble_top_k":  4,              # use the 4 best folds for ensemble inference
    "min_train_samples": 50_000,       # with 5 years × 28 symbols, folds are large
}

# ══════════════════════════════════════════════════════════════════════════════
# Data fetcher settings
# ══════════════════════════════════════════════════════════════════════════════

FETCH = {
    "lookback_days":    1825,          # 5 years of training data (365 × 5)
    "base_url_futures": "https://fapi.binance.com",
    "base_url_spot":    "https://api.binance.com",
    "req_delay_s":      0.08,          # Kept for legacy calls (rate limiter now manages timing)
    "retries":          5,
    "oi_interval":      "15m",         # OI history interval (last 30 days only via API)
    "n_workers":        4,             # Concurrent download threads
    # Capacity: 28 symbols × 5 years × 96 candles = ~4.9M rows (~3.5 hours to train)
}

# ══════════════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════════════

# Data: parquet files sit inside the transformer package itself
DL_DATA_DIR = Path(__file__).parent / "data"

# Model artefacts: shared with the rest of the project
DL_MODEL_PATH   = MODEL_DIR / "dl_base_model.pt"
DL_ENSEMBLE_DIR = MODEL_DIR / "dl_ensemble"
DL_SCALER_PATH  = MODEL_DIR / "dl_scaler.pkl"
DL_FEATURE_PATH = MODEL_DIR / "dl_feature_cols.pkl"
DL_TRAIN_LOG    = LOG_DIR   / "dl_training.csv"
# Memory-mapped feature arrays (written once, read on-demand per batch)
DL_MEMMAP_DIR   = Path(__file__).parent / "data" / "mmap"

for _p in (DL_ENSEMBLE_DIR, DL_DATA_DIR, DL_MEMMAP_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# Memory mode — choose based on your system RAM
# ══════════════════════════════════════════════════════════════════════════════
#
# RAM budget by symbol count (peak, including all 8 walk-forward fold copies):
#
#   8 GB  system → LOW_MEMORY_MODE=True  →  5–8 symbols  (tight, uses swap)
#  16 GB  system → LOW_MEMORY_MODE=True  → 10 symbols    ✓ comfortable
#  24 GB  system → LOW_MEMORY_MODE=False → 20 symbols    ✓ comfortable  ← YOU ARE HERE
#  32 GB+ system → LOW_MEMORY_MODE=False → 28 symbols    ✓ ideal
#
# M3 unified memory note:
#   On Apple Silicon, CPU and GPU share the same 24 GB pool.
#   The model (~13 MB) and active batch (~52 MB at batch=128) are negligible.
#   Peak usage at fold-list construction: ~14.5 GB → leaves ~9.5 GB headroom.

LOW_MEMORY_MODE = False   # 24 GB RAM — False is correct here

# ── Symbol lists ─────────────────────────────────────────────────────────────

# 10 symbols: for 8–16 GB systems
DL_SAFE_SYMBOLS_10 = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT",  "SOLUSDT",  "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT",  "LINKUSDT",
]

# 20 symbols: for 24 GB systems (Apple M3 / similar)  ← ACTIVE
# All symbols have 5+ years of Binance Futures history and high liquidity.
DL_SYMBOLS_20 = [
    "BTCUSDT",  "ETHUSDT",  "BNBUSDT",  "SOLUSDT",  "XRPUSDT",
    "ADAUSDT",  "AVAXUSDT", "DOGEUSDT", "DOTUSDT",  "LINKUSDT",
    "LTCUSDT",  "UNIUSDT",  "ATOMUSDT", "NEARUSDT", "FTMUSDT",
    "MATICUSDT","AAVEUSDT", "AXSUSDT",  "ETCUSDT",  "XLMUSDT",
]

# 28 symbols: for 32+ GB systems
DL_FULL_SYMBOLS_28 = [
    "BTCUSDT",  "ETHUSDT",  "BNBUSDT",   "SOLUSDT",  "XRPUSDT",
    "ADAUSDT",  "AVAXUSDT", "DOGEUSDT",  "DOTUSDT",  "LINKUSDT",
    "LTCUSDT",  "UNIUSDT",  "ATOMUSDT",  "NEARUSDT", "FTMUSDT",
    "MATICUSDT","SANDUSDT", "AAVEUSDT",  "AXSUSDT",  "FILUSDT",
    "ETCUSDT",  "XLMUSDT",  "ALGOUSDT",  "VETUSDT",  "ICPUSDT",
    "THETAUSDT","TRXUSDT",  "EOSUSDT",
]

# ── Active symbol set ─────────────────────────────────────────────────────────
if LOW_MEMORY_MODE:
    DL_DEFAULT_SYMBOLS = DL_SAFE_SYMBOLS_10
else:
    DL_DEFAULT_SYMBOLS = DL_SYMBOLS_20   # 24 GB — use 20 symbols

# ══════════════════════════════════════════════════════════════════════════════
# Device auto-selection
# ══════════════════════════════════════════════════════════════════════════════

def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

DEVICE = get_device()
