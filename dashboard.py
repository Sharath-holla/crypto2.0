# DEPRECATED: CoinSwitch-specific live dashboard retained only for audit. It can
# access account/order APIs and must not be run under the Binance-only architecture.
"""
Live Trading Dashboard — Enhanced Edition
══════════════════════════════════════════════════════════════════════════════
Serves at http://localhost:8765

All features from config_trader.py and coinswitch_client.py are surfaced:

  HFT Wallet          — HFT/DMA sub-account USDT balance (Bybit V5)
  Standard Wallet     — CoinSwitch standard futures + spot portfolio
  Fund Transfer       — Move USDT in/out of HFT sub-account
  Leverage Panel      — Set per-symbol leverage (buy + sell)
  Instrument Info     — Tick size, lot size, min qty per symbol
  HFT Positions       — Live perpetual futures positions via HFT endpoint
  Order Management    — Cancel single order or cancel-all for symbol
  Open Orders         — Real-time active orders from HFT endpoint
  Order History       — Filled/cancelled order history per symbol
  Config Panel        — All execution params from config_trader.py
  Signal Queue        — Live view of signals_queue.csv
  Equity Curve        — Trade-by-trade chart
  Recent Trades       — Last 20 closed trades with P&L
  Pending Orders      — Limit orders waiting to be filled
  Exit Breakdown      — Doughnut chart of exit reasons

Two data sources:
  LOCAL   logs/positions_state.json
          logs/paper_trades.csv
          logs/equity_curve.csv
          logs/signals_queue.csv
  LIVE    CoinSwitch Pro API  (standard + HFT/DMA endpoints)

NOTE: Add to .env:
  COINSWITCH_API_KEY=xxxx
  COINSWITCH_SECRET_KEY=xxxx
"""

import argparse
import csv
import json
import logging
import os
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import requests
from cryptography.hazmat.primitives.asymmetric import ed25519
from dotenv import load_dotenv

from pipeline.config_trader import (
    LOG_DIR, BASE_URL, HFT_BASE_URL, 
    BASE_DIR, BASE_URL, HFT_BASE_URL
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

CS_API_KEY      = os.getenv("COINSWITCH_API_KEY",    "")
CS_SECRET       = os.getenv("COINSWITCH_SECRET_KEY", "")
EXCHANGE        = "EXCHANGE_2"

# ── All config params (mirrored from config_trader.py) ────────────────────────
CONFIG_PARAMS = {
    "LEVERAGE":              10.0,
    "RISK_PCT":              0.02,
    "SL_PCT":                0.03,
    "DEFAULT_TP_PCT":        0.025,
    "RR_RATIO":              1.67,
    "MAX_HOLD_BARS":         20,
    "MAX_CONCURRENT":        5,
    "MAX_MARGIN_PCT":        0.20,
    "LIQUIDATION_THRESHOLD": 0.50,
    "ENTRY_OFFSET_PCT":      0.002,
    "MAX_PENDING_BARS":      1,
    "TIMEFRAME":             "15m",
    "PRICE_POLL_INTERVAL":   1.5,
    "CANDLE_TICK_BUFFER_S":  5.0,
}


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _cs_sign(method: str, path: str, params: Optional[dict] = None) -> dict:
    epoch_ms = str(int(time.time() * 1000))
    endpoint = path
    if method == "GET" and params:
        sep      = "&" if urllib.parse.urlparse(path).query else "?"
        endpoint = path + sep + urllib.parse.urlencode(params)
        endpoint = urllib.parse.unquote_plus(endpoint)
    message          = method + endpoint + epoch_ms
    secret_key_bytes = bytes.fromhex(CS_SECRET)
    private_key      = ed25519.Ed25519PrivateKey.from_private_bytes(secret_key_bytes)
    sig_bytes        = private_key.sign(message.encode("utf-8"))
    return {
        "Content-Type":     "application/json",
        "X-AUTH-APIKEY":    CS_API_KEY,
        "X-AUTH-SIGNATURE": sig_bytes.hex(),
        "X-AUTH-EPOCH":     epoch_ms,
    }


def _cs_get(path: str, params: Optional[dict] = None, hft: bool = False) -> dict:
    if not CS_API_KEY or not CS_SECRET:
        return {"error": "API keys not set"}
    base = HFT_BASE_URL if hft else BASE_URL
    try:
        resp = requests.get(base + path, headers=_cs_sign("GET", path, params),
                            params=params, timeout=8)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _cs_post(path: str, payload: dict, hft: bool = False) -> dict:
    if not CS_API_KEY or not CS_SECRET:
        return {"error": "API keys not set"}
    base = HFT_BASE_URL if hft else BASE_URL
    try:
        resp = requests.post(base + path, headers=_cs_sign("POST", path),
                             json=payload, timeout=8)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── Local data readers ─────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Local data API ─────────────────────────────────────────────────────────────

def _local_data() -> dict:
    trades = _read_csv(LOG_DIR / "paper_trades.csv")
    equity = _read_csv(LOG_DIR / "equity_curve.csv")
    state  = _read_json(LOG_DIR / "positions_state.json")

    total    = len(trades)
    wins     = sum(1 for t in trades if float(t.get("pnl_usd", 0)) >= 0)
    losses   = total - wins
    win_rate = (wins / total * 100) if total > 0 else 0

    total_pnl      = sum(float(t.get("pnl_usd", 0)) for t in trades)
    current_equity = float(equity[-1]["equity"]) if equity else state.get("equity", 0.0)
    initial_equity = float(equity[0]["equity"])  if equity else current_equity
    total_return   = ((current_equity - initial_equity) / initial_equity * 100) \
                     if initial_equity else 0.0
    max_dd         = max((float(e.get("max_drawdown_pct", 0)) for e in equity), default=0.0)

    reasons = {}
    for t in trades:
        r = t.get("exit_reason", "unknown")
        reasons[r] = reasons.get(r, 0) + 1

    # Signals queue (last 30 rows)
    signals = _read_csv(LOG_DIR / "signals_queue.csv")
    recent_signals = signals[-30:][::-1] if signals else []

    return {
        "mode":    state.get("mode", "PAPER"),
        "summary": {
            "current_equity":   round(current_equity, 2),
            "initial_capital":  round(initial_equity, 2),
            "total_return_pct": round(total_return, 2),
            "total_pnl_usd":    round(total_pnl, 2),
            "total_trades":     total,
            "wins":             wins,
            "losses":           losses,
            "win_rate":         round(win_rate, 1),
            "max_drawdown_pct": round(max_dd, 2),
            "pending_count":    len(state.get("pending_orders", [])),
            "open_count":       len(state.get("open_positions", [])),
        },
        "equity_curve":   [{"t": e["timestamp"][:16], "eq": float(e["equity"])} for e in equity],
        "recent_trades":  trades[-20:][::-1],
        "pending_orders": state.get("pending_orders", []),
        "open_positions": state.get("open_positions", []),
        "exit_reasons":   reasons,
        "recent_signals": recent_signals,
    }


# ── Exchange data (standard + HFT) ────────────────────────────────────────────

def _exchange_data() -> dict:
    # Standard CoinSwitch: futures wallet + spot portfolio
    std_wallet  = _cs_get("/trade/api/v2/futures/wallet_balance")
    spot_port   = _cs_get("/trade/api/v2/user/portfolio")
    server_time = _cs_get("/trade/api/v2/time")

    # HFT/DMA: unified wallet balance
    hft_wallet = _cs_get("/v5/account/wallet-balance",
                         params={"accountType": "UNIFIED"}, hft=True)
    # HFT positions
    hft_pos    = _cs_get("/v5/position/list",
                         params={"category": "linear"}, hft=True)

    # Parse standard wallet
    std_data    = std_wallet.get("data", {}) or {}
    std_balance = 0.0
    std_avail   = 0.0
    for field in ("totalBalance", "balance", "wallet_balance"):
        raw = std_data.get(field)
        if raw not in (None, "", "0", 0):
            try:
                v = float(raw)
                if v > 0:
                    std_balance = v
                    break
            except (ValueError, TypeError):
                continue
    for field in ("availableBalance", "available"):
        raw = std_data.get(field)
        if raw not in (None, "", "0", 0):
            try:
                v = float(raw)
                if v > 0:
                    std_avail = v
                    break
            except (ValueError, TypeError):
                continue
    if std_avail == 0.0:
        std_avail = std_balance

    # Parse HFT wallet (Bybit V5 UNIFIED)
    hft_balance = 0.0
    hft_avail   = 0.0
    try:
        coin_list = hft_wallet.get("result", {}).get("list", [])
        if coin_list:
            for coin in coin_list[0].get("coin", []):
                if coin.get("coin") == "USDT":
                    hft_balance = float(coin.get("walletBalance", 0) or 0)
                    hft_avail   = float(coin.get("availableToWithdraw", 0) or 0)
                    break
    except Exception:
        pass

    # Parse HFT positions
    hft_positions = []
    try:
        for p in hft_pos.get("result", {}).get("list", []):
            size = float(p.get("size", 0) or 0)
            if size > 0:
                hft_positions.append({
                    "symbol":         p.get("symbol", ""),
                    "side":           p.get("side", ""),
                    "size":           size,
                    "avg_price":      float(p.get("avgPrice", 0) or 0),
                    "unrealised_pnl": float(p.get("unrealisedPnl", 0) or 0),
                    "leverage":       p.get("leverage", ""),
                    "liq_price":      p.get("liqPrice", ""),
                    "mark_price":     float(p.get("markPrice", 0) or 0),
                })
    except Exception:
        pass

    # Spot portfolio
    spot_assets = []
    try:
        for asset in (spot_port.get("data", {}) or {}).get("holdings", []):
            spot_assets.append({
                "symbol": asset.get("coinName", ""),
                "qty":    float(asset.get("holdingQty", 0) or 0),
                "value":  float(asset.get("holdingValue", 0) or 0),
            })
    except Exception:
        pass

    return {
        "std_balance":    round(std_balance, 2),
        "std_avail":      round(std_avail, 2),
        "std_margin":     round(max(std_balance - std_avail, 0), 2),
        "hft_balance":    round(hft_balance, 2),
        "hft_avail":      round(hft_avail, 2),
        "hft_margin":     round(max(hft_balance - hft_avail, 0), 2),
        "hft_positions":  hft_positions[:15],
        "spot_assets":    spot_assets[:20],
        "server_time":    server_time.get("data", {}).get("serverTime", ""),
        "error":          std_wallet.get("error") or hft_wallet.get("error"),
    }


# ── HFT action endpoints ───────────────────────────────────────────────────────

def _hft_open_orders(symbol: str) -> dict:
    return _cs_get("/v5/order/realtime",
                   params={"category": "linear", "symbol": symbol.upper()}, hft=True)


def _hft_order_history(symbol: str) -> dict:
    return _cs_get("/v5/order/history",
                   params={"category": "linear", "symbol": symbol.upper()}, hft=True)


def _hft_instruments(symbol: Optional[str] = None) -> dict:
    params: dict = {"category": "linear"}
    if symbol:
        params["symbol"] = symbol.upper()
    return _cs_get("/v5/market/instruments-info", params=params, hft=True)


def _do_fund_transfer(amount: float, direction: str) -> dict:
    return _cs_post("/dma/api/v1/funds/transfer",
                    {"exchange": EXCHANGE, "amount": amount, "type": direction},
                    hft=True)


def _do_set_leverage(symbol: str, leverage: int) -> dict:
    return _cs_post("/v5/position/set-leverage", {
        "category":     "linear",
        "symbol":        symbol.upper(),
        "buyLeverage":  str(leverage),
        "sellLeverage": str(leverage),
    }, hft=True)


def _do_cancel_order(symbol: str, order_id: str) -> dict:
    return _cs_post("/v5/order/cancel",
                    {"category": "linear", "symbol": symbol.upper(), "orderId": order_id},
                    hft=True)


def _do_cancel_all(symbol: str) -> dict:
    return _cs_post("/v5/order/cancel-all",
                    {"category": "linear", "symbol": symbol.upper()},
                    hft=True)


# ── HTML ───────────────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CoinSwitch HFT Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg0:#080c12;--bg1:#0d1320;--bg2:#131b2c;--bg3:#192235;
  --border:#1e2d44;--border2:#243452;
  --text:#d4dce8;--text2:#7a8fa8;--text3:#3d5470;
  --green:#1fd47a;--green-bg:#0a2418;
  --red:#f4545a;--red-bg:#25090a;
  --blue:#38aaff;--blue-bg:#08182a;
  --amber:#f0a030;--amber-bg:#221500;
  --purple:#9b7cf8;--purple-bg:#15103a;
  --teal:#25c8c0;--teal-bg:#051f1e;
  --mono:'IBM Plex Mono',monospace;
  --sans:'IBM Plex Sans',sans-serif;
}
body{font-family:var(--sans);background:var(--bg0);color:var(--text);font-size:13px;min-height:100vh}

/* Nav */
.nav{display:flex;align-items:center;gap:0;padding:0 20px;background:var(--bg1);border-bottom:1px solid var(--border);height:44px;position:sticky;top:0;z-index:100}
.nav-logo{font-family:var(--mono);font-size:14px;font-weight:500;color:var(--blue);letter-spacing:-.5px;margin-right:24px;white-space:nowrap}
.nav-tabs{display:flex;gap:0;height:44px}
.tab{padding:0 16px;height:44px;display:flex;align-items:center;font-size:12px;font-weight:500;color:var(--text2);cursor:pointer;border-bottom:2px solid transparent;transition:color .15s,border-color .15s;white-space:nowrap}
.tab:hover{color:var(--text)}
.tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
.paper-dot{width:7px;height:7px;border-radius:50%;background:var(--amber)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.mode-badge{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:3px;font-weight:500}
.mode-live{background:var(--green-bg);color:var(--green)}
.mode-paper{background:var(--amber-bg);color:var(--amber)}
#refresh-ts{font-family:var(--mono);font-size:10px;color:var(--text3)}

/* Page sections */
.page{display:none;padding:16px 20px}
.page.active{display:block}

/* Wallet row */
.wallet-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-bottom:16px}
.wallet-card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 14px}
.wallet-card .wlbl{font-size:10px;font-family:var(--mono);color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.wallet-card .wval{font-family:var(--mono);font-size:18px;font-weight:500}
.wallet-card .wsub{font-size:10px;color:var(--text3);margin-top:2px;font-family:var(--mono)}

/* Summary grid */
.grid-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:16px}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 14px}
.scard .slbl{font-size:10px;font-family:var(--mono);color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.scard .sval{font-family:var(--mono);font-size:18px;font-weight:500}
.scard .ssub{font-size:10px;color:var(--text3);margin-top:2px}

/* Chips */
.chip{display:inline-flex;align-items:center;padding:1px 7px;border-radius:3px;font-size:10px;font-weight:500;font-family:var(--mono)}
.long{background:var(--green-bg);color:var(--green)}.short{background:var(--red-bg);color:var(--red)}
.tp{background:var(--blue-bg);color:var(--blue)}.sl{background:var(--red-bg);color:var(--red)}
.time{background:var(--amber-bg);color:var(--amber)}.liquidation{background:var(--purple-bg);color:var(--purple)}
.chip.buy{background:var(--green-bg);color:var(--green)}.chip.sell{background:var(--red-bg);color:var(--red)}

/* Section headings */
.sec-hd{display:flex;align-items:center;gap:8px;margin-bottom:10px;margin-top:4px}
.sec-hd .title{font-size:11px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.5px;color:var(--text2);font-weight:500}
.cnt-badge{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:1px 8px;font-size:10px;font-family:var(--mono);color:var(--text2)}

/* Tables */
.tbl-wrap{overflow-x:auto;border-radius:6px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:6px 10px;background:var(--bg2);color:var(--text3);font-weight:500;font-family:var(--mono);font-size:10px;letter-spacing:.3px;border-bottom:1px solid var(--border)}
td{padding:6px 10px;border-bottom:1px solid var(--border2);font-family:var(--mono);font-size:11px}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg2)}
.green{color:var(--green)}.red{color:var(--red)}.muted{color:var(--text3)}.blue{color:var(--blue)}.amber{color:var(--amber)}

/* Pending cards */
.pending-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.pcard{background:var(--bg2);border:1px dashed var(--border2);border-radius:6px;padding:10px 12px}
.pcard .sym{font-family:var(--mono);font-weight:500;font-size:12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}
.pcard .row{font-size:10px;font-family:var(--mono);color:var(--text3);margin-top:3px;display:flex;justify-content:space-between}
.pcard .row span{color:var(--text2)}
.progress{background:var(--bg0);border-radius:2px;height:2px;margin-top:8px}
.pbar{height:2px;border-radius:2px;transition:width .3s}

/* Position cards */
.pos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.poscard{background:var(--bg2);border-radius:6px;padding:10px 12px}
.poscard.positive{border:1px solid #0a3d1f}.poscard.negative{border:1px solid #2d0708}.poscard.neutral{border:1px solid var(--border)}
.poscard .sym{font-family:var(--mono);font-weight:500;font-size:12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center}
.poscard .pnl{font-family:var(--mono);font-size:15px;font-weight:500;margin-bottom:4px}
.poscard .row{font-size:10px;font-family:var(--mono);color:var(--text3);display:flex;justify-content:space-between;margin-top:3px}
.poscard .row span{color:var(--text2)}
.levels{display:flex;gap:6px;margin-top:6px;font-size:10px}
.tp-badge{background:var(--blue-bg);color:var(--blue);padding:2px 6px;border-radius:3px;font-family:var(--mono);font-size:10px}
.sl-badge{background:var(--red-bg);color:var(--red);padding:2px 6px;border-radius:3px;font-family:var(--mono);font-size:10px}
.bar-progress{background:var(--bg0);border-radius:2px;height:2px;margin-top:6px}
.bar-fill{height:2px;border-radius:2px;background:var(--blue)}

/* Action panels */
.action-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-bottom:16px}
.action-card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:14px}
.action-card h3{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text2);margin-bottom:12px}
.field{margin-bottom:8px}
.field label{display:block;font-size:10px;font-family:var(--mono);color:var(--text3);margin-bottom:3px;text-transform:uppercase;letter-spacing:.3px}
.field input,.field select{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:6px 8px;color:var(--text);font-family:var(--mono);font-size:12px;outline:none}
.field input:focus,.field select:focus{border-color:var(--blue)}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:6px 14px;border-radius:4px;font-family:var(--mono);font-size:11px;font-weight:500;cursor:pointer;border:none;transition:opacity .15s}
.btn:hover{opacity:.85}.btn:active{opacity:.7}
.btn-blue{background:var(--blue);color:#000}.btn-red{background:var(--red);color:#fff}
.btn-green{background:var(--green);color:#000}.btn-amber{background:var(--amber);color:#000}
.btn-ghost{background:var(--bg3);color:var(--text);border:1px solid var(--border)}
.action-result{margin-top:8px;font-family:var(--mono);font-size:10px;color:var(--text3);background:var(--bg3);border-radius:4px;padding:6px 8px;min-height:28px;word-break:break-all;display:none}

/* Config grid */
.cfg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
.cfg-card{background:var(--bg2);border:1px solid var(--border);border-radius:5px;padding:8px 12px}
.cfg-card .ck{font-family:var(--mono);font-size:10px;color:var(--text3);margin-bottom:2px}
.cfg-card .cv{font-family:var(--mono);font-size:14px;font-weight:500;color:var(--teal)}

/* Signals table */
.sig-long{color:var(--green)}.sig-short{color:var(--red)}.sig-strong{color:var(--amber)}

/* Charts */
canvas{width:100%!important}
.chart-wrap{position:relative;margin-bottom:16px}

/* Two-col */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}

/* HFT position table tag */
.hft-tag{font-family:var(--mono);font-size:9px;padding:1px 5px;border-radius:2px;background:var(--purple-bg);color:var(--purple)}

/* Error */
.err-box{background:var(--red-bg);border:1px solid var(--red);border-radius:5px;padding:8px 12px;font-family:var(--mono);font-size:11px;color:var(--red);margin-bottom:12px}

/* Divider */
.divider{border:none;border-top:1px solid var(--border);margin:14px 0}
</style>
</head>
<body>

<nav class="nav">
  <span class="nav-logo">⬡ CS·HFT</span>
  <div class="nav-tabs">
    <div class="tab active" onclick="goTab('overview')">Overview</div>
    <div class="tab" onclick="goTab('positions')">Positions</div>
    <div class="tab" onclick="goTab('orders')">Orders</div>
    <div class="tab" onclick="goTab('actions')">Actions</div>
    <div class="tab" onclick="goTab('signals')">Signals</div>
    <div class="tab" onclick="goTab('config')">Config</div>
  </div>
  <div class="nav-right">
    <div id="mode-dot" class="live-dot"></div>
    <span id="mode-badge" class="mode-badge mode-live">LIVE</span>
    <span id="refresh-ts">—</span>
  </div>
</nav>

<!-- ══════════════════════════════════════════════════════ OVERVIEW ══ -->
<div class="page active" id="page-overview">

  <div id="err-box" style="display:none" class="err-box"></div>

  <!-- Wallet row: standard + HFT side by side -->
  <div class="wallet-row" id="wallet-row">
    <div class="wallet-card"><div class="wlbl">Loading...</div></div>
  </div>

  <!-- Strategy summary -->
  <div class="grid-4" id="summary-grid"></div>

  <!-- Equity + exit charts -->
  <div class="grid-2">
    <div>
      <div class="sec-hd"><span class="title">Equity curve</span></div>
      <div class="chart-wrap" style="height:150px"><canvas id="equityChart" role="img" aria-label="Equity curve over closed trades"></canvas></div>
    </div>
    <div>
      <div class="sec-hd"><span class="title">Exit breakdown</span></div>
      <div class="chart-wrap" style="height:150px"><canvas id="exitChart" role="img" aria-label="Exit reason breakdown"></canvas></div>
    </div>
  </div>

  <!-- Pending orders -->
  <div class="sec-hd"><span class="title">Pending orders</span><span class="cnt-badge" id="pending-count">0</span></div>
  <div class="pending-grid" id="pending-grid"><span class="muted">No pending orders</span></div>

  <hr class="divider">

  <!-- Recent trades -->
  <div class="sec-hd"><span class="title">Recent closed trades</span></div>
  <div class="tbl-wrap">
    <table><thead><tr>
      <th>Symbol</th><th>Dir</th><th>Limit</th><th>Fill</th><th>Exit</th>
      <th>Reason</th><th>PnL</th><th>ROM%</th><th>Held</th><th>Cap tier</th>
    </tr></thead>
    <tbody id="trade-tbody"></tbody></table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════ POSITIONS ══ -->
<div class="page" id="page-positions">

  <!-- HFT live positions (Bybit V5) -->
  <div class="sec-hd">
    <span class="title">HFT/DMA live positions</span>
    <span class="hft-tag">dma.coinswitch.co</span>
    <span class="cnt-badge" id="hft-pos-count">0</span>
  </div>
  <div class="tbl-wrap" style="margin-bottom:16px">
    <table><thead><tr>
      <th>Symbol</th><th>Side</th><th>Size</th><th>Avg price</th>
      <th>Mark price</th><th>Unrealised PnL</th><th>Leverage</th><th>Liq price</th>
    </tr></thead>
    <tbody id="hft-pos-tbody"></tbody></table>
  </div>

  <!-- Strategy open positions -->
  <div class="sec-hd"><span class="title">Strategy open positions</span><span class="cnt-badge" id="open-count">0</span></div>
  <div class="pos-grid" id="pos-grid"><span class="muted">No open positions</span></div>

  <hr class="divider">

  <!-- Spot portfolio -->
  <div class="sec-hd"><span class="title">Spot portfolio</span></div>
  <div class="tbl-wrap">
    <table><thead><tr><th>Asset</th><th>Qty</th><th>Value (USDT)</th></tr></thead>
    <tbody id="spot-tbody"></tbody></table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════ ORDERS ══ -->
<div class="page" id="page-orders">

  <!-- Symbol selector for HFT order queries -->
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap">
    <select id="sym-select" style="background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:6px 10px;color:var(--text);font-family:var(--mono);font-size:12px;outline:none">
      <option value="">— select symbol —</option>
    </select>
    <button class="btn btn-blue" onclick="loadOrdersForSym()">Load orders</button>
    <button class="btn btn-ghost" onclick="loadOrderHistory()">Order history</button>
    <button class="btn btn-ghost" onclick="loadInstrumentInfo()">Instrument info</button>
  </div>
  <div id="orders-err" style="display:none" class="err-box"></div>

  <!-- Real-time active orders -->
  <div class="sec-hd"><span class="title">Active orders (realtime)</span><span class="cnt-badge" id="active-order-count">0</span></div>
  <div class="tbl-wrap" style="margin-bottom:16px">
    <table><thead><tr>
      <th>Symbol</th><th>Side</th><th>Type</th><th>Price</th><th>Qty</th>
      <th>Filled qty</th><th>Status</th><th>Order ID</th><th>Actions</th>
    </tr></thead>
    <tbody id="active-orders-tbody"></tbody></table>
  </div>

  <!-- Order history -->
  <div class="sec-hd"><span class="title">Order history</span></div>
  <div class="tbl-wrap" style="margin-bottom:16px">
    <table><thead><tr>
      <th>Symbol</th><th>Side</th><th>Type</th><th>Price</th><th>Avg fill</th>
      <th>Qty</th><th>Status</th><th>Order ID</th>
    </tr></thead>
    <tbody id="history-orders-tbody"></tbody></table>
  </div>

  <!-- Instrument info -->
  <div class="sec-hd"><span class="title">Instrument info</span></div>
  <div class="tbl-wrap">
    <table><thead><tr>
      <th>Symbol</th><th>Tick size</th><th>Qty step</th><th>Min order qty</th><th>Status</th>
    </tr></thead>
    <tbody id="instrument-tbody"></tbody></table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════ ACTIONS ══ -->
<div class="page" id="page-actions">
  <div class="action-grid">

    <!-- Fund transfer -->
    <div class="action-card">
      <h3>Fund transfer (HFT sub-account)</h3>
      <div class="field"><label>Amount (USDT)</label><input type="number" id="ft-amount" placeholder="e.g. 100" min="0" step="0.01"></div>
      <div class="field"><label>Direction</label>
        <select id="ft-dir">
          <option value="in">IN — deposit into HFT</option>
          <option value="out">OUT — withdraw from HFT</option>
        </select>
      </div>
      <button class="btn btn-green" onclick="doFundTransfer()">Transfer funds</button>
      <div class="action-result" id="ft-result"></div>
    </div>

    <!-- Set leverage -->
    <div class="action-card">
      <h3>Set leverage (per symbol)</h3>
      <div class="field"><label>Symbol</label><input type="text" id="lev-sym" placeholder="e.g. BTCUSDT" style="text-transform:uppercase"></div>
      <div class="field"><label>Leverage (1 – 100×)</label><input type="number" id="lev-val" placeholder="10" min="1" max="100" value="10"></div>
      <button class="btn btn-blue" onclick="doSetLeverage()">Set leverage</button>
      <div class="action-result" id="lev-result"></div>
    </div>

    <!-- Cancel single order -->
    <div class="action-card">
      <h3>Cancel order</h3>
      <div class="field"><label>Symbol</label><input type="text" id="co-sym" placeholder="e.g. BTCUSDT" style="text-transform:uppercase"></div>
      <div class="field"><label>Order ID</label><input type="text" id="co-id" placeholder="exchange order ID"></div>
      <button class="btn btn-red" onclick="doCancelOrder()">Cancel order</button>
      <div class="action-result" id="co-result"></div>
    </div>

    <!-- Cancel all orders -->
    <div class="action-card">
      <h3>Cancel all orders (symbol)</h3>
      <div class="field"><label>Symbol</label><input type="text" id="ca-sym" placeholder="e.g. BTCUSDT" style="text-transform:uppercase"></div>
      <button class="btn btn-red" onclick="doCancelAll()">Cancel all orders</button>
      <div class="action-result" id="ca-result"></div>
    </div>

  </div>
</div>

<!-- ══════════════════════════════════════════════════════ SIGNALS ══ -->
<div class="page" id="page-signals">
  <div class="sec-hd"><span class="title">Signal queue (last 30)</span><span class="cnt-badge" id="sig-count">0</span></div>
  <div class="tbl-wrap">
    <table><thead><tr>
      <th>Row ID</th><th>Written at</th><th>Symbol</th><th>Candle ts</th>
      <th>Signal</th><th>Strong</th><th>Close</th><th>MPE target</th>
      <th>P long</th><th>P short</th><th>P hold</th>
      <th>Cap tier</th><th>Precision est</th>
    </tr></thead>
    <tbody id="signals-tbody"></tbody></table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════ CONFIG ══ -->
<div class="page" id="page-config">
  <div class="sec-hd"><span class="title">Execution config (config_trader.py)</span></div>
  <div class="cfg-grid" id="cfg-grid"></div>

  <hr class="divider">

  <div class="sec-hd"><span class="title">API endpoints</span></div>
  <div class="tbl-wrap">
    <table><thead><tr><th>Name</th><th>Method</th><th>Host</th><th>Path</th></tr></thead>
    <tbody id="ep-tbody"></tbody></table>
  </div>

  <hr class="divider">

  <div class="sec-hd"><span class="title">Tracked symbols (<span id="sym-count">0</span>)</span></div>
  <div id="sym-chips" style="display:flex;flex-wrap:wrap;gap:4px"></div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let equityChart=null, exitChart=null;
const SYMBOLS=[
  "BTC/USDT:USDT","ETH/USDT:USDT","BNB/USDT:USDT","SOL/USDT:USDT",
  "XRP/USDT:USDT","ADA/USDT:USDT","AVAX/USDT:USDT","DOGE/USDT:USDT",
  "DOT/USDT:USDT","LINK/USDT:USDT","LTC/USDT:USDT","XPIN/USDT:USDT",
  "UNI/USDT:USDT","ATOM/USDT:USDT","NEAR/USDT:USDT","FTM/USDT:USDT",
  "SAND/USDT:USDT","MANA/USDT:USDT","AAVE/USDT:USDT","AXS/USDT:USDT",
  "RIVER/USDT:USDT","BEAT/USDT:USDT","PIPPIN/USDT:USDT","KITE/USDT:USDT",
  "SIREN/USDT:USDT","ZEC/USDT:USDT","ARIA/USDT:USDT","TRIA/USDT:USDT",
  "POL/USDT:USDT","MAGMA/USDT:USDT","STABLE/USDT:USDT","NIGHT/USDT:USDT",
  "GIGGLE/USDT:USDT","PRL/USDT:USDT","FARTCOIN/USDT:USDT","UAI/USDT:USDT",
  "H/USDT:USDT","VIRTUAL/USDT:USDT","CLO/USDT:USDT","FHE/USDT:USDT",
  "TRUST/USDT:USDT","1000PEPE/USDT:USDT","RAVE/USDT:USDT","FIGHT/USDT:USDT",
  "BAN/USDT:USDT","BOB/USDT:USDT","VELVET/USDT:USDT","BLESS/USDT:USDT",
  "APR/USDT:USDT","CYS/USDT:USDT","COAI/USDT:USDT","KGEN/USDT:USDT",
  "BANANAS31/USDT:USDT","4/USDT:USDT","XPL/USDT:USDT","EDGE/USDT:USDT",
  "ZAMA/USDT:USDT","TRUMP/USDT:USDT","XAU/USDT:USDT","VVV/USDT:USDT",
  "F/USDT:USDT","STRK/USDT:USDT","M/USDT:USDT","HANA/USDT:USDT",
  "TIA/USDT:USDT","MERL/USDT:USDT","LIGHT/USDT:USDT"
];

// Populate symbol dropdowns
const sel=document.getElementById('sym-select');
SYMBOLS.forEach(s=>{
  const sym=s.replace('/USDT:USDT','').replace('/USDT','')+'USDT';
  const o=document.createElement('option');
  o.value=sym;o.textContent=sym;sel.appendChild(o);
});

// ── Helpers ────────────────────────────────────────────────────────────────
function fmt(n,d=2){return parseFloat(n||0).toFixed(d);}
function sign(n){return n>=0?'+':'';}
function col(n){return n>=0?'var(--green)':'var(--red)';}
function mono(s){return`<span style="font-family:var(--mono)">${s}</span>`;}

// ── Tab navigation ─────────────────────────────────────────────────────────
function goTab(id){
  document.querySelectorAll('.tab').forEach((t,i)=>{
    const ids=['overview','positions','orders','actions','signals','config'];
    t.classList.toggle('active',ids[i]===id);
  });
  document.querySelectorAll('.page').forEach(p=>{
    p.classList.toggle('active',p.id==='page-'+id);
  });
}

// ── Render functions ───────────────────────────────────────────────────────
function renderMode(mode){
  const dot=document.getElementById('mode-dot');
  const badge=document.getElementById('mode-badge');
  if(mode==='LIVE'){dot.className='live-dot';badge.className='mode-badge mode-live';badge.textContent='LIVE';}
  else{dot.className='paper-dot';badge.className='mode-badge mode-paper';badge.textContent='PAPER';}
}

function renderWallet(ex){
  const eb=document.getElementById('err-box');
  if(ex.error){eb.style.display='block';eb.textContent='Exchange: '+ex.error;}
  else{eb.style.display='none';}
  document.getElementById('wallet-row').innerHTML=`
    <div class="wallet-card"><div class="wlbl">STD futures balance</div><div class="wval">$${ex.std_balance.toLocaleString('en',{minimumFractionDigits:2})}</div><div class="wsub">avail $${ex.std_avail.toLocaleString('en',{minimumFractionDigits:2})}</div></div>
    <div class="wallet-card"><div class="wlbl">STD margin used</div><div class="wval" style="color:var(--amber)">$${ex.std_margin.toLocaleString('en',{minimumFractionDigits:2})}</div></div>
    <div class="wallet-card" style="border-color:var(--purple)"><div class="wlbl">HFT/DMA balance <span class="hft-tag">unified</span></div><div class="wval" style="color:var(--purple)">$${ex.hft_balance.toLocaleString('en',{minimumFractionDigits:2})}</div><div class="wsub">avail $${ex.hft_avail.toLocaleString('en',{minimumFractionDigits:2})}</div></div>
    <div class="wallet-card" style="border-color:var(--purple)"><div class="wlbl">HFT margin used</div><div class="wval" style="color:var(--amber)">$${ex.hft_margin.toLocaleString('en',{minimumFractionDigits:2})}</div></div>
  `;
}

function renderSummary(s){
  const rc=s.total_return_pct>=0?'var(--green)':'var(--red)';
  const dc=s.max_drawdown_pct>15?'var(--red)':s.max_drawdown_pct>8?'var(--amber)':'var(--text3)';
  document.getElementById('summary-grid').innerHTML=`
    <div class="scard"><div class="slbl">Strategy equity</div><div class="sval">$${s.current_equity.toLocaleString('en',{minimumFractionDigits:2})}</div></div>
    <div class="scard"><div class="slbl">Total return</div><div class="sval" style="color:${rc}">${sign(s.total_return_pct)}${fmt(s.total_return_pct)}%</div></div>
    <div class="scard"><div class="slbl">Win rate</div><div class="sval">${fmt(s.win_rate,1)}%<span class="muted" style="font-size:12px;margin-left:6px">${s.wins}W/${s.losses}L</span></div></div>
    <div class="scard"><div class="slbl">Max drawdown</div><div class="sval" style="color:${dc}">${fmt(s.max_drawdown_pct)}%</div></div>
    <div class="scard"><div class="slbl">Total trades</div><div class="sval">${s.total_trades}</div></div>
    <div class="scard"><div class="slbl">Total P&L</div><div class="sval" style="color:${col(s.total_pnl_usd)}">${sign(s.total_pnl_usd)}$${Math.abs(s.total_pnl_usd).toFixed(2)}</div></div>
    <div class="scard"><div class="slbl">Pending orders</div><div class="sval" style="color:var(--blue)">${s.pending_count}</div></div>
    <div class="scard"><div class="slbl">Open positions</div><div class="sval" style="color:var(--purple)">${s.open_count}</div></div>
  `;
}

function renderEquity(curve){
  const ctx=document.getElementById('equityChart').getContext('2d');
  if(equityChart)equityChart.destroy();
  equityChart=new Chart(ctx,{
    type:'line',
    data:{labels:curve.map(p=>p.t),datasets:[{label:'Equity',data:curve.map(p=>p.eq),
      borderColor:'#38aaff',borderWidth:1.5,backgroundColor:'rgba(56,170,255,0.05)',
      fill:true,pointRadius:0,tension:0.3}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{ticks:{maxTicksLimit:6,font:{size:9,family:"'IBM Plex Mono',monospace"},color:'#3d5470'},grid:{color:'rgba(255,255,255,0.02)'}},
        y:{ticks:{font:{size:9,family:"'IBM Plex Mono',monospace"},color:'#3d5470',callback:v=>'$'+v.toLocaleString()},grid:{color:'rgba(255,255,255,0.02)'}}
      }}
  });
}

function renderExits(r){
  const ctx=document.getElementById('exitChart').getContext('2d');
  if(exitChart)exitChart.destroy();
  const labels=Object.keys(r),data=Object.values(r);
  const clr={'tp':'#38aaff','sl':'#f4545a','time':'#f0a030','liquidation':'#9b7cf8'};
  exitChart=new Chart(ctx,{type:'doughnut',
    data:{labels,datasets:[{data,backgroundColor:labels.map(l=>clr[l]||'#3d5470'),borderWidth:0}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'right',labels:{font:{size:9,family:"'IBM Plex Mono',monospace"},color:'#7a8fa8',boxWidth:8,padding:6}}}}
  });
}

function renderPending(orders){
  document.getElementById('pending-count').textContent=orders.length;
  const el=document.getElementById('pending-grid');
  if(!orders.length){el.innerHTML='<span class="muted">Waiting for signals...</span>';return;}
  el.innerHTML=orders.map(o=>{
    const cls=o.direction==='long'?'long':'short';
    const lbl=o.direction==='long'?'LIMIT BUY':'LIMIT SELL';
    const pct=Math.min(100,Math.round(o.bars_elapsed/o.max_pending_bars*100));
    const diff=((o.limit_price/o.signal_close-1)*100).toFixed(2);
    return `<div class="pcard">
      <div class="sym">${o.symbol.replace('USDT','')} <span class="chip ${cls}">${lbl}</span></div>
      <div class="row"><span>Signal close</span><span>$${parseFloat(o.signal_close).toFixed(5)}</span></div>
      <div class="row"><span>Limit price</span><span style="font-weight:500">$${parseFloat(o.limit_price).toFixed(5)}</span></div>
      <div class="row"><span>Offset</span><span>${diff}%</span></div>
      <div class="row"><span>Notional</span><span>$${parseFloat(o.notional_usd).toLocaleString()}</span></div>
      <div class="row"><span>Expires</span><span style="color:${pct>66?'var(--red)':'var(--text2)'}">bar ${o.bars_elapsed}/${o.max_pending_bars}</span></div>
      ${o.cs_order_id?`<div class="row"><span>Order ID</span><span>${o.cs_order_id.slice(0,14)}…</span></div>`:''}
      <div class="progress"><div class="pbar" style="width:${pct}%;background:${pct>66?'var(--red)':'var(--blue)'}"></div></div>
    </div>`;
  }).join('');
}

function renderOpen(positions){
  document.getElementById('open-count').textContent=positions.length;
  const el=document.getElementById('pos-grid');
  if(!positions.length){el.innerHTML='<span class="muted">No open positions</span>';return;}
  el.innerHTML=positions.map(p=>{
    const pnl=parseFloat(p.unrealised_pnl_usd||0);
    const cls=pnl>0?'positive':pnl<0?'negative':'neutral';
    const dir=p.direction==='long'?'<span class="chip long">LONG</span>':'<span class="chip short">SHORT</span>';
    const bp=Math.round(p.bars_held/p.max_hold_bars*100);
    const last=parseFloat(p.last_price||p.fill_price);
    const mv=((last/parseFloat(p.fill_price)-1)*100*(p.direction==='long'?1:-1));
    return `<div class="poscard ${cls}">
      <div class="sym">${p.symbol.replace('USDT','/USDT')} ${dir}</div>
      <div class="pnl" style="color:${col(pnl)}">${sign(pnl)}$${Math.abs(pnl).toFixed(2)} <span class="muted">(${sign(mv)}${Math.abs(mv).toFixed(2)}%)</span></div>
      <div class="row"><span>Fill</span><span>$${parseFloat(p.fill_price).toFixed(5)}</span></div>
      <div class="row"><span>Last</span><span style="color:${col(mv)}">$${last.toFixed(5)}</span></div>
      <div class="levels"><span class="tp-badge">TP ${p.tp_dist_pct}%</span><span class="sl-badge">SL ${p.sl_dist_pct}%</span></div>
      <div class="row" style="margin-top:4px"><span>Bar ${p.bars_held}/${p.max_hold_bars}</span><span class="muted">${p.entry_time?p.entry_time.slice(11,16)+' UTC':''}</span></div>
      <div class="bar-progress"><div class="bar-fill" style="width:${bp}%"></div></div>
    </div>`;
  }).join('');
}

function renderHftPositions(positions){
  document.getElementById('hft-pos-count').textContent=positions.length;
  const tb=document.getElementById('hft-pos-tbody');
  if(!positions.length){tb.innerHTML='<tr><td colspan="8" class="muted" style="padding:10px">No open HFT positions</td></tr>';return;}
  tb.innerHTML=positions.map(p=>{
    const pnl=parseFloat(p.unrealised_pnl||0);
    const side=p.side==='Buy'?'<span class="chip buy">BUY</span>':'<span class="chip sell">SELL</span>';
    return `<tr>
      <td>${p.symbol}</td><td>${side}</td>
      <td>${p.size}</td>
      <td>$${parseFloat(p.avg_price||0).toFixed(4)}</td>
      <td>$${parseFloat(p.mark_price||0).toFixed(4)}</td>
      <td style="color:${col(pnl)}">${sign(pnl)}$${Math.abs(pnl).toFixed(4)}</td>
      <td>${p.leverage}×</td>
      <td class="muted">${p.liq_price||'-'}</td>
    </tr>`;
  }).join('');
}

function renderSpot(assets){
  const tb=document.getElementById('spot-tbody');
  if(!assets.length){tb.innerHTML='<tr><td colspan="3" class="muted" style="padding:10px">No spot assets</td></tr>';return;}
  tb.innerHTML=assets.map(a=>`<tr>
    <td>${a.symbol}</td><td>${a.qty}</td><td>$${parseFloat(a.value||0).toFixed(2)}</td>
  </tr>`).join('');
}

function renderTrades(trades){
  const tb=document.getElementById('trade-tbody');
  if(!trades.length){tb.innerHTML='<tr><td colspan="10" class="muted" style="padding:14px">No closed trades yet</td></tr>';return;}
  tb.innerHTML=trades.map(t=>{
    const pnl=parseFloat(t.pnl_usd),rom=parseFloat(t.return_on_margin);
    const dir=t.direction==='long'?'<span class="chip long">L</span>':'<span class="chip short">S</span>';
    return `<tr>
      <td>${t.symbol.replace('USDT','/USDT')}</td><td>${dir}</td>
      <td class="muted">${parseFloat(t.limit_price||0).toFixed(4)}</td>
      <td>${parseFloat(t.fill_price||t.entry_price||0).toFixed(4)}</td>
      <td>${parseFloat(t.exit_price||0).toFixed(4)}</td>
      <td><span class="chip ${t.exit_reason}">${t.exit_reason}</span></td>
      <td style="color:${col(pnl)}">${sign(pnl)}$${Math.abs(pnl).toFixed(2)}</td>
      <td style="color:${col(rom)}">${sign(rom)}${Math.abs(rom).toFixed(1)}%</td>
      <td class="muted">${t.bars_held||t.candles_held||0}</td>
      <td class="muted">${t.cap_tier_name||''}</td>
    </tr>`;
  }).join('');
}

function renderSignals(signals){
  document.getElementById('sig-count').textContent=signals.length;
  const tb=document.getElementById('signals-tbody');
  if(!signals.length){tb.innerHTML='<tr><td colspan="13" class="muted" style="padding:10px">No signals in queue</td></tr>';return;}
  tb.innerHTML=signals.map(s=>{
    const sigCls=s.signal==='long'?'sig-long':'sig-short';
    const strong=s.strong==='True'?'<span class="chip" style="background:var(--amber-bg);color:var(--amber)">✦ STRONG</span>':'';
    const plong=parseFloat(s.p_long||0);
    const pshort=parseFloat(s.p_short||0);
    return `<tr>
      <td class="muted">${s.row_id||''}</td>
      <td class="muted">${(s.written_at||'').slice(0,16)}</td>
      <td style="font-weight:500">${(s.symbol||'').replace('USDT','')}</td>
      <td class="muted">${(s.candle_ts||'').slice(0,16)}</td>
      <td class="${sigCls}" style="font-weight:500">${(s.signal||'').toUpperCase()} ${strong}</td>
      <td>${s.strong==='True'?'<span class="amber">YES</span>':'<span class="muted">no</span>'}</td>
      <td>$${parseFloat(s.close||0).toFixed(5)}</td>
      <td class="blue">${s.mpe_target||'—'}</td>
      <td style="color:${plong>0.5?'var(--green)':'var(--text2)'}">${parseFloat(s.p_long||0).toFixed(3)}</td>
      <td style="color:${pshort>0.5?'var(--red)':'var(--text2)'}">${parseFloat(s.p_short||0).toFixed(3)}</td>
      <td class="muted">${parseFloat(s.p_hold||0).toFixed(3)}</td>
      <td class="muted">${s.cap_tier_name||s.cap_tier||''}</td>
      <td class="muted">${parseFloat(s.precision_est||0).toFixed(3)}</td>
    </tr>`;
  }).join('');
}

function renderConfig(){
  const cfg={
    "LEVERAGE":"10×","RISK_PCT":"15%","SL_PCT":"1.5%","DEFAULT_TP_PCT":"2.5%",
    "RR_RATIO":"1.67","MAX_HOLD_BARS":"20 bars","MAX_CONCURRENT":"5 pos",
    "MAX_MARGIN_PCT":"20%","LIQUIDATION_THRESHOLD":"50%",
    "ENTRY_OFFSET_PCT":"0.2%","MAX_PENDING_BARS":"1 bar",
    "TIMEFRAME":"15m","PRICE_POLL":"1.5s","CANDLE_BUFFER":"5s"
  };
  document.getElementById('cfg-grid').innerHTML=Object.entries(cfg).map(([k,v])=>`
    <div class="cfg-card"><div class="ck">${k}</div><div class="cv">${v}</div></div>
  `).join('');

  const eps=[
    ['VALIDATE_KEYS','GET','coinswitch.co','/trade/api/v2/validate/keys'],
    ['SERVER_TIME','GET','coinswitch.co','/trade/api/v2/time'],
    ['SERVER_PING','GET','coinswitch.co','/trade/api/v2/ping'],
    ['FUTURES_WALLET','GET','coinswitch.co','/trade/api/v2/futures/wallet_balance'],
    ['SPOT_PORTFOLIO','GET','coinswitch.co','/trade/api/v2/user/portfolio'],
    ['HFT_FUND_TRANSFER','POST','dma.coinswitch.co','/dma/api/v1/funds/transfer'],
    ['HFT_SET_LEVERAGE','POST','dma.coinswitch.co','/v5/position/set-leverage'],
    ['HFT_ORDER_CREATE','POST','dma.coinswitch.co','/v5/order/create'],
    ['HFT_ORDER_CANCEL','POST','dma.coinswitch.co','/v5/order/cancel'],
    ['HFT_ORDER_CANCEL_ALL','POST','dma.coinswitch.co','/v5/order/cancel-all'],
    ['HFT_ORDER_REALTIME','GET','dma.coinswitch.co','/v5/order/realtime'],
    ['HFT_ORDER_HISTORY','GET','dma.coinswitch.co','/v5/order/history'],
    ['HFT_POSITION_LIST','GET','dma.coinswitch.co','/v5/position/list'],
    ['HFT_WALLET_BALANCE','GET','dma.coinswitch.co','/v5/account/wallet-balance'],
    ['HFT_INSTRUMENTS_INFO','GET','dma.coinswitch.co','/v5/market/instruments-info'],
  ];
  document.getElementById('ep-tbody').innerHTML=eps.map(([name,method,host,path])=>`<tr>
    <td style="color:var(--teal)">${name}</td>
    <td><span class="chip ${method==='GET'?'buy':'sell'}">${method}</span></td>
    <td class="muted">${host}</td>
    <td style="color:var(--text2)">${path}</td>
  </tr>`).join('');

  const symDiv=document.getElementById('sym-chips');
  document.getElementById('sym-count').textContent=SYMBOLS.length;
  symDiv.innerHTML=SYMBOLS.map(s=>{
    const base=s.replace('/USDT:USDT','').replace('/USDT','');
    return `<span style="background:var(--bg2);border:1px solid var(--border);border-radius:3px;padding:2px 8px;font-family:var(--mono);font-size:10px;color:var(--text2)">${base}</span>`;
  }).join('');
}

// ── Order panel actions ────────────────────────────────────────────────────
async function loadOrdersForSym(){
  const sym=document.getElementById('sym-select').value;
  if(!sym)return;
  const resp=await fetch('/api/hft_orders?symbol='+sym).then(r=>r.json());
  const orders=resp.result?.list||[];
  document.getElementById('active-order-count').textContent=orders.length;
  const tb=document.getElementById('active-orders-tbody');
  if(!orders.length){tb.innerHTML='<tr><td colspan="9" class="muted" style="padding:10px">No active orders</td></tr>';return;}
  tb.innerHTML=orders.map(o=>{
    const side=o.side==='Buy'?'<span class="chip buy">BUY</span>':'<span class="chip sell">SELL</span>';
    return `<tr>
      <td>${o.symbol}</td><td>${side}</td><td class="muted">${o.orderType}</td>
      <td>$${o.price||'-'}</td><td>${o.qty}</td><td>${o.cumExecQty||0}</td>
      <td class="muted">${o.orderStatus}</td>
      <td class="muted" style="font-size:10px">${(o.orderId||'').slice(0,14)}…</td>
      <td><button class="btn btn-red" style="padding:3px 8px;font-size:10px" onclick="quickCancel('${o.symbol}','${o.orderId}')">Cancel</button></td>
    </tr>`;
  }).join('');
}

async function loadOrderHistory(){
  const sym=document.getElementById('sym-select').value;
  if(!sym)return;
  const resp=await fetch('/api/hft_order_history?symbol='+sym).then(r=>r.json());
  const orders=resp.result?.list||[];
  const tb=document.getElementById('history-orders-tbody');
  if(!orders.length){tb.innerHTML='<tr><td colspan="8" class="muted" style="padding:10px">No order history</td></tr>';return;}
  tb.innerHTML=orders.map(o=>{
    const side=o.side==='Buy'?'<span class="chip buy">BUY</span>':'<span class="chip sell">SELL</span>';
    return `<tr>
      <td>${o.symbol}</td><td>${side}</td><td class="muted">${o.orderType}</td>
      <td>${o.price||'-'}</td><td>${o.avgPrice||'-'}</td><td>${o.qty}</td>
      <td class="muted">${o.orderStatus}</td>
      <td class="muted" style="font-size:10px">${(o.orderId||'').slice(0,14)}…</td>
    </tr>`;
  }).join('');
}

async function loadInstrumentInfo(){
  const sym=document.getElementById('sym-select').value;
  const url='/api/hft_instruments'+(sym?'?symbol='+sym:'');
  const resp=await fetch(url).then(r=>r.json());
  const insts=(resp.result?.list||[]).slice(0,30);
  const tb=document.getElementById('instrument-tbody');
  if(!insts.length){tb.innerHTML='<tr><td colspan="5" class="muted" style="padding:10px">No data</td></tr>';return;}
  tb.innerHTML=insts.map(i=>`<tr>
    <td style="font-weight:500">${i.symbol}</td>
    <td class="blue">${i.priceFilter?.tickSize||'-'}</td>
    <td class="blue">${i.lotSizeFilter?.qtyStep||'-'}</td>
    <td class="blue">${i.lotSizeFilter?.minOrderQty||'-'}</td>
    <td class="muted">${i.status||'-'}</td>
  </tr>`).join('');
}

async function quickCancel(symbol,orderId){
  const resp=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action:'cancel_order',symbol,order_id:orderId})}).then(r=>r.json());
  alert(JSON.stringify(resp,null,2));
  loadOrdersForSym();
}

// ── Action panel helpers ───────────────────────────────────────────────────
async function callAction(payload,resultId){
  const el=document.getElementById(resultId);
  el.style.display='block';el.textContent='Sending…';el.style.color='var(--text3)';
  try{
    const r=await fetch('/api/action',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
    const ok=!r.error&&(r.retCode===0||r.retCode===undefined);
    el.style.color=ok?'var(--green)':'var(--red)';
    el.textContent=JSON.stringify(r,null,2);
  }catch(e){el.style.color='var(--red)';el.textContent='Error: '+e.message;}
}

function doFundTransfer(){
  const amount=parseFloat(document.getElementById('ft-amount').value);
  const dir=document.getElementById('ft-dir').value;
  if(!amount||amount<=0)return alert('Enter a valid amount');
  callAction({action:'fund_transfer',amount,direction:dir},'ft-result');
}
function doSetLeverage(){
  const sym=document.getElementById('lev-sym').value.trim().toUpperCase();
  const lev=parseInt(document.getElementById('lev-val').value);
  if(!sym)return alert('Enter symbol');
  callAction({action:'set_leverage',symbol:sym,leverage:lev},'lev-result');
}
function doCancelOrder(){
  const sym=document.getElementById('co-sym').value.trim().toUpperCase();
  const id=document.getElementById('co-id').value.trim();
  if(!sym||!id)return alert('Enter symbol and order ID');
  callAction({action:'cancel_order',symbol:sym,order_id:id},'co-result');
}
function doCancelAll(){
  const sym=document.getElementById('ca-sym').value.trim().toUpperCase();
  if(!sym)return alert('Enter symbol');
  if(!confirm(`Cancel ALL orders for ${sym}?`))return;
  callAction({action:'cancel_all',symbol:sym},'ca-result');
}

// ── Main refresh ───────────────────────────────────────────────────────────
async function refresh(){
  try{
    const [ld,ex]=await Promise.all([
      fetch('/api/data').then(r=>r.json()),
      fetch('/api/exchange').then(r=>r.json()),
    ]);
    renderMode(ld.mode||'PAPER');
    renderWallet(ex);
    renderSummary(ld.summary);
    renderEquity(ld.equity_curve);
    renderExits(ld.exit_reasons);
    renderPending(ld.pending_orders);
    renderOpen(ld.open_positions);
    renderHftPositions(ex.hft_positions||[]);
    renderSpot(ex.spot_assets||[]);
    renderTrades(ld.recent_trades);
    renderSignals(ld.recent_signals||[]);
    document.getElementById('refresh-ts').textContent=
      new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('refresh-ts').textContent='Error: '+e.message;
  }
}

renderConfig();
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        qp   = dict(urllib.parse.parse_qsl(path.query))
        ep   = path.path

        if ep in ("/", "/index.html"):
            self._respond(200, "text/html; charset=utf-8", _HTML.encode())
        elif ep == "/api/data":
            self._json(_local_data())
        elif ep == "/api/exchange":
            self._json(_exchange_data())
        elif ep == "/api/hft_orders":
            sym = qp.get("symbol", "")
            self._json(_hft_open_orders(sym) if sym else {"error": "symbol required"})
        elif ep == "/api/hft_order_history":
            sym = qp.get("symbol", "")
            self._json(_hft_order_history(sym) if sym else {"error": "symbol required"})
        elif ep == "/api/hft_instruments":
            self._json(_hft_instruments(qp.get("symbol")))
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/api/action":
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            action  = payload.get("action", "")
            result  = {}

            if action == "fund_transfer":
                result = _do_fund_transfer(float(payload["amount"]), payload["direction"])
            elif action == "set_leverage":
                result = _do_set_leverage(payload["symbol"], int(payload["leverage"]))
            elif action == "cancel_order":
                result = _do_cancel_order(payload["symbol"], payload["order_id"])
            elif action == "cancel_all":
                result = _do_cancel_all(payload["symbol"])
            else:
                result = {"error": f"Unknown action: {action}"}

            self._json(result)
        else:
            self.send_response(404); self.end_headers()

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self._respond(200, "application/json", body)

    def _respond(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global LOG_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",    type=int,  default=8765)
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR)
    args = parser.parse_args()
    LOG_DIR = args.log_dir

    if not CS_API_KEY or not CS_SECRET:
        logger.warning(
            "COINSWITCH_API_KEY / COINSWITCH_SECRET_KEY not found in environment. "
            "Add them to your .env file."
        )

    server = HTTPServer(("localhost", args.port), Handler)
    logger.info(f"Dashboard: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
