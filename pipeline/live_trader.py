# DEPRECATED: CoinSwitch-specific legacy prototype. ADR-017 supersedes this
# execution architecture. Do not import or run this module.
"""
Live Trader — Real Order Execution via CoinSwitch Pro HFT/DMA API

All order operations route through the HFT/DMA sub-account
(https://dma.coinswitch.co, Bybit V5 REST dialect).

Public interface (identical to PaperTrader):
  record_signal(sig)            — places real limit entry order via HFT
  price_tick(sym, price)        — checks fill + TP/SL on every 1.5 s tick
  candle_tick(sym, c, h, l)     — time exit + pending order timeout
  get_active_symbols()          — symbols needing fast monitoring
  get_summary()                 — portfolio stats

Order lifecycle
───────────────
  1. Signal fires
       → set_hft_leverage(symbol, LEVERAGE)   if not yet set this session
       → place_hft_order (Limit) at close ± ENTRY_OFFSET_PCT
       → store pending: {orderId, limit_price, direction, ...}

  2. price_tick() every 1.5 s
       → get_hft_order() to check orderStatus
       → on "Filled":
           → fetch avgPrice from HFT order
           → place_hft_order (Limit, reduceOnly) for TP
           → place_hft_order (Market, triggerPrice, reduceOnly) for SL
           → transition PENDING → OPEN

  3. price_tick() on open position
       → get_hft_order() to check TP / SL orderStatus
       → on either "Filled":
           → cancel_all_hft_orders(symbol)   — remove the other leg
           → close position locally, write CSV

  4. candle_tick()
       → increment bar counters
       → on timeout (MAX_HOLD_BARS): cancel_all_hft_orders, place Market close

  5. Crash recovery
       → restore_state() reads positions_state.json on startup
       → HFT order status is re-checked via get_hft_order()

HFT order status values (Bybit V5)
  Active   : "New" | "PartiallyFilled"
  Terminal : "Filled" | "Cancelled" | "Rejected" | "Deactivated"

State files (dashboard reads these)
  logs/paper_trades.csv        — closed trades (full history)
  logs/equity_curve.csv        — equity after every closed trade
  logs/positions_state.json    — live: pending + open + HFT order IDs
"""

import csv
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from pipeline.coinswitch_client import CoinSwitchClient, to_cs_symbol

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
try:
    from pipeline.config_trader import (
        LEVERAGE, RISK_PCT, SL_PCT, DEFAULT_TP_PCT, LOG_DIR,
        MAX_HOLD_BARS, MAX_CONCURRENT, MAX_MARGIN_PCT, LIQUIDATION_THRESHOLD,
    )
    ENTRY_OFFSET_PCT = getattr(
        __import__("pipeline.config", fromlist=["ENTRY_OFFSET_PCT"]),
        "ENTRY_OFFSET_PCT", 0.002,
    )
    MAX_PENDING_BARS = getattr(
        __import__("pipeline.config", fromlist=["MAX_PENDING_BARS"]),
        "MAX_PENDING_BARS", 1,
    )
except ImportError:
    LEVERAGE = 10.0; RISK_PCT = 0.02; SL_PCT = 0.015; DEFAULT_TP_PCT = 0.025
    MAX_HOLD_BARS = 20; MAX_CONCURRENT = 5; MAX_MARGIN_PCT = 0.20
    LIQUIDATION_THRESHOLD = 0.50; ENTRY_OFFSET_PCT = 0.002; MAX_PENDING_BARS = 1

# ── HFT order status constants ─────────────────────────────────────────────────
_HFT_FILLED    = {"Filled"}
_HFT_PARTIAL   = {"PartiallyFilled"}
_HFT_ACTIVE    = {"New", "PartiallyFilled"}
_HFT_TERMINAL  = {"Filled", "Cancelled", "Rejected", "Deactivated"}
_HFT_CANCELLED = {"Cancelled", "Rejected", "Deactivated"}

# ── CSV headers ────────────────────────────────────────────────────────────────
_TRADE_HEADER = [
    "trade_id", "symbol", "direction", "strong",
    "signal_close", "limit_price", "fill_price",
    "entry_time", "exit_time", "exit_price", "exit_reason",
    "notional_usd", "margin_usd", "leverage",
    "tp_price", "sl_price",
    "pnl_usd", "pnl_pct", "return_on_margin",
    "equity_before", "equity_after",
    "bars_pending", "bars_held",
    "entry_order_id", "tp_order_id", "sl_order_id",
    "cap_tier", "cap_tier_name", "vol_to_mcap", "flow_vs_peers",
    "p_long", "p_short", "mpe_predicted",
]
_EQUITY_HEADER = [
    "trade_id", "timestamp", "equity", "trade_pnl",
    "total_trades", "wins", "losses", "win_rate", "max_drawdown_pct",
]


# ── Order state containers ─────────────────────────────────────────────────────

class PendingOrder:
    __slots__ = ("order_id", "cs_order_id", "symbol", "cs_symbol", "direction",
                 "strong", "signal_close", "limit_price", "notional", "margin",
                 "tp_pct", "sig", "placed_at", "bars_elapsed")

    def __init__(self, symbol, cs_symbol, direction, strong, signal_close,
                 limit_price, notional, margin, tp_pct, sig, cs_order_id):
        self.order_id     = str(uuid.uuid4())[:10]
        self.cs_order_id  = cs_order_id   # HFT orderId (Bybit V5)
        self.symbol       = symbol
        self.cs_symbol    = cs_symbol
        self.direction    = direction
        self.strong       = strong
        self.signal_close = signal_close
        self.limit_price  = limit_price
        self.notional     = notional
        self.margin       = margin
        self.tp_pct       = tp_pct
        self.sig          = sig
        self.placed_at    = datetime.now(timezone.utc)
        self.bars_elapsed = 0


class LivePosition:
    __slots__ = ("trade_id", "symbol", "cs_symbol", "direction", "strong",
                 "signal_close", "limit_price", "fill_price", "entry_time",
                 "notional", "margin", "tp_price", "sl_price",
                 "tp_order_id", "sl_order_id", "entry_order_id",
                 "equity_before", "bars_pending", "bars_held",
                 "last_price", "unrealised_pnl",
                 "cap_tier", "cap_tier_name", "vol_to_mcap", "flow_vs_peers",
                 "p_long", "p_short", "mpe_predicted")

    def __init__(self, order: PendingOrder, fill_price: float,
                 fill_time: datetime, tp_price: float, sl_price: float,
                 tp_order_id: str, sl_order_id: str, equity_before: float):
        sig = order.sig
        self.trade_id       = str(uuid.uuid4())[:10]
        self.symbol         = order.symbol
        self.cs_symbol      = order.cs_symbol
        self.direction      = order.direction
        self.strong         = order.strong
        self.signal_close   = order.signal_close
        self.limit_price    = order.limit_price
        self.fill_price     = fill_price
        self.entry_time     = fill_time
        self.notional       = order.notional
        self.margin         = order.margin
        self.tp_price       = tp_price
        self.sl_price       = sl_price
        self.tp_order_id    = tp_order_id
        self.sl_order_id    = sl_order_id
        self.entry_order_id = order.cs_order_id
        self.equity_before  = equity_before
        self.bars_pending   = order.bars_elapsed
        self.bars_held      = 0
        self.last_price     = fill_price
        self.unrealised_pnl = 0.0
        self.cap_tier       = sig.get("cap_tier", "")
        self.cap_tier_name  = sig.get("cap_tier_name", "")
        self.vol_to_mcap    = sig.get("vol_to_mcap", "")
        self.flow_vs_peers  = sig.get("flow_vs_peers", "")
        self.p_long         = sig.get("p_long", "")
        self.p_short        = sig.get("p_short", "")
        self.mpe_predicted  = sig.get("mpe_target", "")

    def update_unrealised(self, price: float) -> float:
        pct = (price - self.fill_price) / self.fill_price
        if self.direction == "short": pct = -pct
        self.last_price     = price
        self.unrealised_pnl = pct * self.notional
        return self.unrealised_pnl


# ── Main engine ────────────────────────────────────────────────────────────────

class LiveTrader:
    """
    Live trading engine using the CoinSwitch HFT/DMA API.
    Same public interface as PaperTrader.
    """

    def __init__(self, cs_client: CoinSwitchClient,
                 initial_capital: Optional[float] = None,
                 log_dir: Optional[Path] = None):
        self._cs = cs_client
        self._instrument_rules: dict[str, dict] = {}

        if log_dir is None:
            log_dir = LOG_DIR

        self._equity          = float(initial_capital or 0.0)
        self._initial_capital = float(initial_capital or 0.0)
        self._peak_equity     = float(initial_capital or 0.0)
        self._cum_pnl         = float(0.0)

        self._total_trades    = 0
        self._wins            = 0
        self._losses          = 0
        self._max_drawdown    = 0.0

        self._pending: dict[str, PendingOrder] = {}
        self._open:    dict[str, LivePosition] = {}
        self._leverage_set: set[str]           = set()

        self._trade_log  = log_dir / "paper_trades.csv"
        self._equity_log = log_dir / "equity_curve.csv"
        self._state_path = log_dir / "positions_state.json"

        self._init_csvs()
        logger.info(
            "[live] LiveTrader initialised (HFT mode) | "
            "leverage=%sx | risk=%.0f%%/trade | "
            "entry_offset=%.1f%% | SL=%.1f%%",
            LEVERAGE, RISK_PCT * 100, ENTRY_OFFSET_PCT * 100, SL_PCT * 100,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Startup: fetch real balance
    # ══════════════════════════════════════════════════════════════════════════

    async def sync_balance(self) -> float:
        """
        Fetch actual balance. Tries HFT wallet first, then standard futures wallet.
        """
        # ── 1. HFT/DMA wallet (USDT) ─────────────────────────────────────────
        try:
            hft_resp = await self._cs.get_hft_balance()
            acct_list = hft_resp.get("result", {}).get("list", [])
            
            if acct_list:
                # Loop through coins to find USDT
                for coin_data in acct_list[0].get("coin", []):
                    if coin_data.get("coin", "").upper() == "USDT":
                        # Extract both balance and PNL
                        balance = float(coin_data.get("walletBalance") or 0)
                        pnl = float(coin_data.get("cumRealisedPnl") or 0)

                        if balance > 0.0:
                            self._equity          = balance
                            self._initial_capital = self._initial_capital or balance
                            self._peak_equity     = max(self._peak_equity, balance)
                            # Optional: if you have a pnl attribute, update it here
                            self._cum_pnl = pnl 

                            logger.info("[live] HFT wallet synced | Bal: %.4f USDT | PNL: %.4f", balance, pnl)
                            return balance
                            
        except Exception as e:
            logger.debug("[live] HFT balance fetch failed: %s", e)

        # ── 2. Standard futures wallet fallback ──────────────────────────────
        # REMOVED: 'if balance > 0:' because we only get here if HFT failed or was 0
        try:
            resp = await self._cs.get_futures_wallet()
            data = resp.get("data", {})
            found_balance = 0.0

            if isinstance(data, dict):
                for field in ("totalBalance", "availableBalance", "balance", "available"):
                    val = data.get(field)
                    if val not in (None, "", "0", 0):
                        found_balance = float(val)
                        break

            elif isinstance(data, list):
                for coin in data:
                    # Support for multiple currency identifiers
                    symbol = str(coin.get("name", coin.get("currency", ""))).upper()
                    if symbol in ("USDT", "INR", "INDIAN RUPEE"):
                        found_balance = float(coin.get("main_balance", coin.get("balance", 0)) or 0)
                        break

            if found_balance > 0:
                self._equity          = found_balance
                self._initial_capital = self._initial_capital or found_balance
                self._peak_equity     = max(self._peak_equity, found_balance)
                logger.info("[live] Standard wallet balance synced | %.2f", found_balance)
                return found_balance

        except Exception as e:
            logger.warning("[live] Standard wallet balance sync failed: %s", e)

        logger.warning("[live] All balance sync attempts returned 0. Using last known equity: %.2f", self._equity)
        return self._equity

    # ══════════════════════════════════════════════════════════════════════════
    # HFT sub-account initialisation
    # ══════════════════════════════════════════════════════════════════════════

    async def initialize_hft(self, transfer_amount: float = 1.0) -> bool:
        """
        Transfer funds to the HFT/DMA sub-account to activate it.
        Call this once before the first order if the sub-account is new.
        """
        resp = await self._cs.initialize_hft_subaccount(transfer_amount)
        if "error" in resp:
            logger.error("[live] HFT sub-account init failed: %s", resp)
            return False
        logger.info("[live] HFT sub-account initialised | %.4f USDT transferred", transfer_amount)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # Instrument rules — tick size & qty step per symbol
    # ══════════════════════════════════════════════════════════════════════════

    async def load_instrument_rules(self) -> None:
        """
        Fetch tick size and qty step for ALL linear instruments from the HFT API
        and cache them in self._instrument_rules.

        Call once at startup after sync_balance():
            await trader.load_instrument_rules()

        Populates self._instrument_rules[symbol] = {
            "tickSize":    "0.10",   # priceFilter.tickSize
            "qtyStep":     "0.001",  # lotSizeFilter.qtyStep
            "minOrderQty": "0.001",  # lotSizeFilter.minOrderQty
        }

        Bybit V5 response shape:
          result.list[i].symbol
          result.list[i].priceFilter.tickSize
          result.list[i].lotSizeFilter.qtyStep
          result.list[i].lotSizeFilter.minOrderQty
        """
        try:
            resp        = await self._cs.get_hft_instrument_info()   # no symbol = all
            instruments = resp.get("result", {}).get("list", [])
            loaded      = 0
            for inst in instruments:
                symbol = inst.get("symbol", "")
                if not symbol:
                    continue
                tick_size = inst.get("priceFilter",   {}).get("tickSize",    "")
                qty_step  = inst.get("lotSizeFilter", {}).get("qtyStep",     "")
                min_qty   = inst.get("lotSizeFilter", {}).get("minOrderQty", "")
                if tick_size and qty_step:
                    self._instrument_rules[symbol] = {
                        "tickSize":    tick_size,
                        "qtyStep":     qty_step,
                        "minOrderQty": min_qty,
                    }
                    loaded += 1
            logger.info("[live] Instrument rules loaded for %d symbols", loaded)
        except Exception as e:
            logger.warning("[live] load_instrument_rules failed: %s", e)

    async def _ensure_symbol_rules(self, cs_symbol: str) -> None:
        """
        Lazy-load instrument rules for a single symbol if not yet cached.
        Called automatically from record_signal() before the first order on a
        new symbol so formatting is always correct even if load_instrument_rules()
        was not called at startup.
        """
        if cs_symbol in self._instrument_rules:
            return
        try:
            resp        = await self._cs.get_hft_instrument_info(symbol=cs_symbol)
            instruments = resp.get("result", {}).get("list", [])
            for inst in instruments:
                symbol = inst.get("symbol", "")
                if not symbol:
                    continue
                tick_size = inst.get("priceFilter",   {}).get("tickSize",    "")
                qty_step  = inst.get("lotSizeFilter", {}).get("qtyStep",     "")
                min_qty   = inst.get("lotSizeFilter", {}).get("minOrderQty", "")
                if tick_size and qty_step:
                    self._instrument_rules[symbol] = {
                        "tickSize":    tick_size,
                        "qtyStep":     qty_step,
                        "minOrderQty": min_qty,
                    }
                    logger.info(
                        "[live] Rules for %s: tickSize=%s qtyStep=%s",
                        symbol, tick_size, qty_step,
                    )
        except Exception as e:
            logger.warning("[live] _ensure_symbol_rules(%s) failed: %s", cs_symbol, e)

    # ══════════════════════════════════════════════════════════════════════════
    # Crash recovery — restore state from positions_state.json
    # ══════════════════════════════════════════════════════════════════════════

    async def restore_state(self) -> None:
        """
        Restore pending/open positions from positions_state.json after a
        crash or restart.  HFT order status is re-verified via get_hft_order().
        """
        if not self._state_path.exists():
            logger.info("[live] No state file found — starting fresh.")
            return

        try:
            with open(self._state_path) as f:
                state = json.load(f)
        except Exception as e:
            logger.warning("[live] Could not read state file: %s", e)
            return

        saved_equity = state.get("equity", 0.0)
        if saved_equity > 0 and self._equity == 0.0:
            self._equity      = saved_equity
            self._peak_equity = saved_equity

        restored_pending = 0
        for p in state.get("pending_orders", []):
            sym    = p.get("symbol", "")
            cs_sym = to_cs_symbol(sym)
            if not sym or sym in self._pending:
                continue

            cs_oid = p.get("cs_order_id", "")
            if cs_oid:
                order_data = await self._cs.get_hft_order(cs_sym, cs_oid)
                status     = order_data.get("orderStatus", "")
                if status in _HFT_TERMINAL:
                    logger.info(
                        "[live] Restore: pending %s in terminal state %s — skipping",
                        cs_oid, status,
                    )
                    continue

            fake_sig: dict = {}
            order = PendingOrder(
                symbol       = sym,
                cs_symbol    = cs_sym,
                direction    = p.get("direction", "long"),
                strong       = False,
                signal_close = p.get("signal_close", 0.0),
                limit_price  = p.get("limit_price", 0.0),
                notional     = p.get("notional_usd", 0.0),
                margin       = p.get("margin_usd", 0.0),
                tp_pct       = DEFAULT_TP_PCT,
                sig          = fake_sig,
                cs_order_id  = cs_oid,
            )
            order.bars_elapsed     = p.get("bars_elapsed", 0)
            self._pending[sym]     = order
            restored_pending      += 1

        restored_open = 0
        for o in state.get("open_positions", []):
            sym    = o.get("symbol", "")
            cs_sym = to_cs_symbol(sym)
            if not sym or sym in self._open:
                continue

            fake_sig: dict = {}
            fill  = o.get("fill_price", 0.0)
            tp    = o.get("tp_price", 0.0)
            sl    = o.get("sl_price", 0.0)
            notnl = o.get("notional_usd", 0.0)
            mrgn  = o.get("margin_usd", 0.0)

            stub = PendingOrder(
                symbol       = sym,
                cs_symbol    = cs_sym,
                direction    = o.get("direction", "long"),
                strong       = False,
                signal_close = fill,
                limit_price  = fill,
                notional     = notnl,
                margin       = mrgn,
                tp_pct       = DEFAULT_TP_PCT,
                sig          = fake_sig,
                cs_order_id  = "",
            )
            entry_time_str = o.get("entry_time", "")
            entry_time = datetime.fromisoformat(entry_time_str) \
                if entry_time_str else datetime.now(timezone.utc)

            pos = LivePosition(
                order        = stub,
                fill_price   = fill,
                fill_time    = entry_time,
                tp_price     = tp,
                sl_price     = sl,
                tp_order_id  = o.get("tp_order_id", ""),
                sl_order_id  = o.get("sl_order_id", ""),
                equity_before= self._equity,
            )
            pos.bars_held   = o.get("bars_held", 0)
            self._open[sym] = pos
            restored_open  += 1

        logger.info(
            "[live] State restored: %d pending order(s), %d open position(s)",
            restored_pending, restored_open,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Public API (matches PaperTrader interface)
    # ══════════════════════════════════════════════════════════════════════════

    async def record_signal(self, sig: dict) -> bool:
        """
        Called when a non-hold signal fires.
        Sets HFT leverage (once per symbol per session), then places a
        limit entry order via the HFT/DMA API.
        Returns True if an order was placed.
        """
        symbol    = sig.get("symbol", "")
        direction = sig.get("signal", "hold")
        close_px  = float(sig.get("close", 0.0))
        cs_symbol = to_cs_symbol(symbol)

        if direction == "hold" or close_px <= 0:
            return False
        if symbol in self._pending or symbol in self._open:
            return False
        if len(self._pending) + len(self._open) >= MAX_CONCURRENT:
            logger.info("[live] Capacity full — skipping %s", symbol)
            return False

        # ── Position sizing ───────────────────────────────────────────────────
        risk_amount = self._equity * RISK_PCT
        notional    = risk_amount / SL_PCT
        margin      = notional / LEVERAGE
        max_margin  = self._equity * MAX_MARGIN_PCT
        if margin > max_margin:
            margin   = max_margin
            notional = margin * LEVERAGE
        if margin > self._equity * 0.95:
            logger.warning("[live] Insufficient equity — skipping %s", symbol)
            return False

        # ── Limit price ───────────────────────────────────────────────────────
        if direction == "long":
            limit_price = close_px * (1.0 - ENTRY_OFFSET_PCT)
            hft_side    = "Buy"
        else:
            limit_price = close_px * (1.0 + ENTRY_OFFSET_PCT)
            hft_side    = "Sell"

        # ── TP percentage ─────────────────────────────────────────────────────
        mpe    = sig.get("mpe_target")
        tp_pct = (mpe / 100.0) \
            if (mpe and isinstance(mpe, (int, float)) and mpe > 0) \
            else DEFAULT_TP_PCT

        # ── Set HFT leverage once per symbol per session ──────────────────────
        if cs_symbol not in self._leverage_set:
            self._leverage_set.add(cs_symbol)   # claim slot before await (prevents race)
            lev_resp = await self._cs.set_hft_leverage(cs_symbol, int(LEVERAGE))
            if "error" in lev_resp:
                self._leverage_set.discard(cs_symbol)   # roll back so next signal retries
                logger.warning("[live] Could not set HFT leverage for %s: %s",
                               cs_symbol, lev_resp)
            else:
                logger.info("[live] HFT leverage set %s → %dx", cs_symbol, int(LEVERAGE))

        # Ensure tick size / qty step rules are loaded for this symbol before
        # any formatting call (lazy-loads from HFT API if not yet cached)
        await self._ensure_symbol_rules(cs_symbol)

        quantity_str = self._format_quantity(notional / limit_price, cs_symbol)
        price_str = self._format_price(limit_price, cs_symbol)

        # ── SAFETY CATCH: Prevent sending 0 qty to exchange ───────────────────
        if float(quantity_str) <= 0:
            logger.warning("[live] Qty rounded to 0 for %s (notional %.2f too small). Skipping.", 
                           symbol, notional)
            return False
        
        logger.info(
            "[live] %s Quantity=%s | Price=%s | ", symbol, quantity_str, price_str
        )

        # Convert back to float so our local tracking perfectly matches the exchange
        actual_limit_price = float(price_str)

        # ── Place limit entry order via HFT ───────────────────────────────────
        resp = await self._cs.place_hft_order(
            symbol     = cs_symbol,
            side       = hft_side,
            order_type = "Limit",
            qty        = quantity_str,
            price      = price_str,
        )
        
        if "error" in resp:
            logger.error("[live] HFT entry order failed %s: %s", symbol, resp)
            return False

        # HFT response: result.orderId  (Bybit V5 format)
        cs_order_id = resp.get("result", {}).get("orderId", "")
        
        # ── SAFETY CATCH: Ensure we actually got an ID back ───────────────────
        if not cs_order_id:
             logger.error("[live] HFT entry order returned no orderId %s: %s", symbol, resp)
             return False

        order = PendingOrder(
            symbol       = symbol,
            cs_symbol    = cs_symbol,
            direction    = direction,
            strong       = bool(sig.get("strong", False)),
            signal_close = close_px,
            limit_price  = actual_limit_price,  # <── Use the rounded price here
            notional     = notional,
            margin       = margin,
            tp_pct       = tp_pct,
            sig          = sig,
            cs_order_id  = cs_order_id,
        )
        self._pending[symbol] = order
        self._save_state()

        logger.info(
            "[live] HFT ORDER PLACED %s %s | close=%.5f | limit=%.5f | "
            "qty=%s | notional=%.2f | orderId=%s",
            direction.upper(), symbol, close_px, actual_limit_price,
            quantity_str, notional, cs_order_id,
        )
        return True

    async def price_tick(self, sym_key: str, price: float) -> None:
        """
        FAST PATH — called every ~1.5 s.
        Checks pending order fill status, then TP/SL on open positions.
        """
        now = datetime.now(timezone.utc)

        # ── Pending: check if entry order was filled ──────────────────────────
        order = self._pending.get(sym_key)
        if order is not None:
            filled = await self._check_hft_order_filled(
                order.cs_order_id, order.cs_symbol, price,
                order.limit_price, order.direction,
            )
            if filled:
                await self._on_entry_filled(order, order.limit_price, now)
            return

        # ── Open: check if TP or SL order was filled ─────────────────────────
        pos = self._open.get(sym_key)
        if pos is None:
            return

        pos.update_unrealised(price)

        tp_hit = await self._check_hft_order_filled(
            pos.tp_order_id, pos.cs_symbol, price, pos.tp_price,
            direction="tp", is_reduce=True,
        )
        if tp_hit:
            await self._cancel_and_close(pos, pos.tp_price, "tp", now)
            return

        sl_hit = await self._check_hft_order_filled(
            pos.sl_order_id, pos.cs_symbol, price, pos.sl_price,
            direction="sl", is_reduce=True,
        )
        if sl_hit:
            await self._cancel_and_close(pos, pos.sl_price, "sl", now)
            return

        # Liquidation safety net
        if pos.unrealised_pnl < -pos.margin * LIQUIDATION_THRESHOLD:
            logger.warning("[live] LIQUIDATION GATE hit for %s — closing", sym_key)
            await self._cancel_and_close(pos, price, "liquidation", now)

        self._save_state()

    async def candle_tick(self, sym_key: str, close: float,
                          high: float, low: float) -> None:
        """
        SLOW PATH — every candle close.
        Handles pending timeout + time-based exit.
        """
        now = datetime.now(timezone.utc)

        order = self._pending.get(sym_key)
        if order is not None:
            order.bars_elapsed += 1
            if order.bars_elapsed >= MAX_PENDING_BARS:
                logger.info(
                    "[live] ORDER CANCELLED (timeout) %s %s | limit=%.5f",
                    order.direction.upper(), sym_key, order.limit_price,
                )
                # Cancel via HFT API — requires symbol + orderId
                await self._cs.cancel_hft_order(order.cs_symbol, order_id=order.cs_order_id)
                del self._pending[sym_key]
                self._save_state()
            return

        pos = self._open.get(sym_key)
        if pos is None:
            return
        pos.bars_held += 1
        if pos.bars_held >= MAX_HOLD_BARS:
            logger.info("[live] TIME EXIT %s after %d bars", sym_key, pos.bars_held)
            await self._cancel_and_close(pos, close, "time", now, use_market=True)

    def get_active_symbols(self) -> list[str]:
        return list(self._pending.keys()) + list(self._open.keys())

    def get_summary(self) -> dict:
        total    = self._total_trades
        win_rate = (self._wins / total) if total > 0 else 0.0
        ret      = (self._equity - self._initial_capital) / max(self._initial_capital, 1)
        return {
            "equity":           round(self._equity, 2),
            "initial_capital":  round(self._initial_capital, 2),
            "total_return_pct": round(ret * 100, 2),
            "total_trades":     total,
            "wins":             self._wins,
            "losses":           self._losses,
            "win_rate":         round(win_rate * 100, 1),
            "max_drawdown_pct": round(self._max_drawdown * 100, 2),
            "pending_count":    len(self._pending),
            "open_count":       len(self._open),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════════════

    async def _check_hft_order_filled(
        self, order_id: str, cs_symbol: str, current_price: float,
        target_price: float, direction: str, is_reduce: bool = False,
    ) -> bool:
        """
        Returns True if the HFT order is in a filled state.
        Falls back to price-level check if the API call fails (resilience).

        direction: "long" | "short" (entry orders) or "tp" | "sl" (reduce orders)
        """
        if not order_id:
            return False

        try:
            order_data = await self._cs.get_hft_order(cs_symbol, order_id)
            status     = order_data.get("orderStatus", "")

            if status in _HFT_FILLED:
                return True
            if status in _HFT_CANCELLED:
                logger.info("[live] HFT order %s terminal state: %s", order_id, status)
                return False
            # "New" / "PartiallyFilled" → still active, check price fallback below
        except Exception as e:
            logger.debug("[live] HFT order status fetch failed %s: %s", order_id, e)

        # Price fallback
        if not is_reduce:
            if direction == "long"  and current_price <= target_price: return True
            if direction == "short" and current_price >= target_price: return True
        else:
            if direction == "tp":
                pos = next(
                    (p for p in self._open.values() if p.tp_order_id == order_id), None
                )
                if pos:
                    if pos.direction == "long"  and current_price >= pos.tp_price: return True
                    if pos.direction == "short" and current_price <= pos.tp_price: return True
            elif direction == "sl":
                pos = next(
                    (p for p in self._open.values() if p.sl_order_id == order_id), None
                )
                if pos:
                    if pos.direction == "long"  and current_price <= pos.sl_price: return True
                    if pos.direction == "short" and current_price >= pos.sl_price: return True
        return False

    async def _on_entry_filled(self, order: PendingOrder,
                               fill_price: float, fill_time: datetime) -> None:
        """
        Entry order filled → fetch actual avgPrice from HFT, place TP and SL
        via HFT API, transition PENDING → OPEN.
        """
        # ── Fetch actual average fill price from HFT ──────────────────────────
        if order.cs_order_id:
            try:
                order_data = await self._cs.get_hft_order(order.cs_symbol, order.cs_order_id)
                avg_px     = float(order_data.get("avgPrice", 0) or 0)
                if avg_px > 0:
                    logger.debug(
                        "[live] HFT fill price %s: %.6f (limit was %.6f)",
                        order.cs_order_id, avg_px, order.limit_price,
                    )
                    fill_price = avg_px
            except Exception as e:
                logger.debug("[live] Could not fetch HFT fill price %s: %s — using limit",
                             order.cs_order_id, e)

        cs = order.cs_symbol

        if order.direction == "long":
            tp_price = fill_price * (1.0 + order.tp_pct)
            sl_price = fill_price * (1.0 - SL_PCT)
            tp_side  = "Sell"
            sl_side  = "Sell"
            sl_trigger_dir = 2     # fall below → stop-loss for long
            # Limit execution price sits 0.2% below the trigger so it fills
            # even with a fast-moving candle (still far better than market slippage)
            sl_limit_price = sl_price * (1.0 - 0.002)
        else:
            tp_price = fill_price * (1.0 - order.tp_pct)
            sl_price = fill_price * (1.0 + SL_PCT)
            tp_side  = "Buy"
            sl_side  = "Buy"
            sl_trigger_dir = 1     # rise above → stop-loss for short
            # Limit execution price sits 0.2% above the trigger
            sl_limit_price = sl_price * (1.0 + 0.002)

        quantity = self._format_quantity(order.notional / fill_price, cs)

        # ── TP: Limit reduce-only order ───────────────────────────────────────
        tp_resp = await self._cs.place_hft_order(
            symbol      = cs,
            side        = tp_side,
            order_type  = "Limit",
            qty         = quantity,
            price       = self._format_price(tp_price, cs),
            tif         = "GTC",
            reduce_only = True,
        )
        tp_order_id = tp_resp.get("result", {}).get("orderId", "")

        # ── SL: stop-limit order (Limit order triggered at sl_price) ─────────
        # order_type="Limit" + trigger_price + stop_order_type="Stop" is the
        # Bybit V5 stop-limit pattern. sl_limit_price is the guaranteed execution
        # price once triggered — set slightly beyond the trigger to ensure fill.
        sl_resp = await self._cs.place_hft_order(
            symbol            = cs,
            side              = sl_side,
            order_type        = "Limit",
            qty               = quantity,
            price             = self._format_price(sl_limit_price, cs),
            trigger_price     = self._format_price(sl_price, cs),
            trigger_direction = sl_trigger_dir,
            stop_order_type   = "Stop",
            reduce_only       = True,
        )
        sl_order_id = sl_resp.get("result", {}).get("orderId", "")

        pos = LivePosition(
            order        = order,
            fill_price   = fill_price,
            fill_time    = fill_time,
            tp_price     = tp_price,
            sl_price     = sl_price,
            tp_order_id  = tp_order_id,
            sl_order_id  = sl_order_id,
            equity_before= self._equity,
        )
        del self._pending[order.symbol]
        self._open[order.symbol] = pos

        logger.info(
            "[live] HFT FILLED %s %s | fill=%.5f | "
            "tp=%.5f (id=%s) | sl=%.5f (id=%s)",
            order.direction.upper(), order.symbol, fill_price,
            tp_price, tp_order_id, sl_price, sl_order_id,
        )
        self._save_state()

    async def _cancel_and_close(self, pos: LivePosition, exit_price: float,
                                exit_reason: str, exit_time: datetime,
                                use_market: bool = False) -> None:
        """Cancel all HFT TP/SL orders for the symbol, then record closure."""
        try:
            await self._cs.cancel_all_hft_orders(pos.cs_symbol)
        except Exception as e:
            logger.warning("[live] cancel_all_hft_orders failed for %s: %s",
                           pos.cs_symbol, e)

        if use_market:
            close_side = "Sell" if pos.direction == "long" else "Buy"
            qty        = self._format_quantity(pos.notional / exit_price, pos.cs_symbol)
            await self._cs.place_hft_order(
                symbol      = pos.cs_symbol,
                side        = close_side,
                order_type  = "Market",
                qty         = qty,
                reduce_only = True,
            )

        self._record_close(pos, exit_price, exit_reason, exit_time)

    def _record_close(self, pos: LivePosition, exit_price: float,
                      exit_reason: str, exit_time: datetime) -> None:
        pct_move = (exit_price - pos.fill_price) / pos.fill_price
        if pos.direction == "short": pct_move = -pct_move

        pnl_usd      = pct_move * pos.notional
        rom          = pnl_usd / pos.margin
        self._equity = max(self._equity + pnl_usd, 0.0)

        if self._equity > self._peak_equity:
            self._peak_equity = self._equity
        dd = (self._peak_equity - self._equity) / max(self._peak_equity, 1e-9)
        self._max_drawdown = max(self._max_drawdown, dd)

        self._total_trades += 1
        if pnl_usd >= 0: self._wins   += 1
        else:            self._losses += 1

        win_rate = self._wins / self._total_trades
        logger.info(
    "[live] CLOSED %s %s | reason=%s | "
    "fill=%.5f → exit=%.5f | pnl=%+.2f (%+.1f%% levered) | "
    "equity=%.2f | W%d/L%d (%.0f%%)",
    pos.direction.upper(), 
    pos.symbol, 
    exit_reason,
    pos.fill_price, 
    exit_price,
    pnl_usd, 
    pct_move * LEVERAGE * 100,
    self._equity, 
    self._wins, 
    self._losses, 
    win_rate
)

        self._append_trade({
            "trade_id":         pos.trade_id,
            "symbol":           pos.symbol,
            "direction":        pos.direction,
            "strong":           pos.strong,
            "signal_close":     round(pos.signal_close, 6),
            "limit_price":      round(pos.limit_price, 6),
            "fill_price":       round(pos.fill_price, 6),
            "entry_time":       pos.entry_time.isoformat() if pos.entry_time else "",
            "exit_time":        exit_time.isoformat(),
            "exit_price":       round(exit_price, 6),
            "exit_reason":      exit_reason,
            "notional_usd":     round(pos.notional, 2),
            "margin_usd":       round(pos.margin, 2),
            "leverage":         LEVERAGE,
            "tp_price":         round(pos.tp_price, 6),
            "sl_price":         round(pos.sl_price, 6),
            "pnl_usd":          round(pnl_usd, 4),
            "pnl_pct":          round(pct_move * 100, 4),
            "return_on_margin": round(rom * 100, 4),
            "equity_before":    round(pos.equity_before, 2),
            "equity_after":     round(self._equity, 2),
            "bars_pending":     pos.bars_pending,
            "bars_held":        pos.bars_held,
            "entry_order_id":   pos.entry_order_id,
            "tp_order_id":      pos.tp_order_id,
            "sl_order_id":      pos.sl_order_id,
            "cap_tier":         pos.cap_tier,
            "cap_tier_name":    pos.cap_tier_name,
            "vol_to_mcap":      pos.vol_to_mcap,
            "flow_vs_peers":    pos.flow_vs_peers,
            "p_long":           pos.p_long,
            "p_short":          pos.p_short,
            "mpe_predicted":    pos.mpe_predicted,
        })
        self._append_equity({
            "trade_id":         pos.trade_id,
            "timestamp":        exit_time.isoformat(),
            "equity":           round(self._equity, 2),
            "trade_pnl":        round(pnl_usd, 4),
            "total_trades":     self._total_trades,
            "wins":             self._wins,
            "losses":           self._losses,
            "win_rate":         round(win_rate * 100, 2),
            "max_drawdown_pct": round(self._max_drawdown * 100, 2),
        })
        del self._open[pos.symbol]
        self._save_state()

    # ── Precision helpers ──────────────────────────────────────────────────────

    def _format_price(self, price: float, cs_symbol: str) -> str:
        """Round price to the exchange's exact tick size using ROUND_HALF_UP."""
        rules = self._instrument_rules.get(cs_symbol)
        if not rules or float(rules["tickSize"]) == 0:
            return f"{price:.6f}" # Fallback if rules aren't loaded

        tick_size = Decimal(rules["tickSize"])
        d_price = Decimal(str(price))
        
        # Round to nearest tick
        rounded = (d_price / tick_size).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_size
        
        # Format string to match the decimal places of the tick size
        decimals = abs(tick_size.as_tuple().exponent)
        return f"{rounded:.{decimals}f}"
    
    def _format_quantity(self, qty: float, cs_symbol: str) -> str:
        """Round quantity DOWN to the exchange's exact lot size step."""
        rules = self._instrument_rules.get(cs_symbol)
        if not rules or float(rules["qtyStep"]) == 0:
            return f"{qty:.4f}" # Fallback

        qty_step = Decimal(rules["qtyStep"])
        d_qty = Decimal(str(qty))
        
        # Round DOWN to nearest step (never round up for qty, or you might exceed balance)
        rounded = (d_qty / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
        
        decimals = abs(qty_step.as_tuple().exponent)
        return f"{rounded:.{decimals}f}"
    # ── State persistence ──────────────────────────────────────────────────────

    def _save_state(self) -> None:
        pending_list = [
            {
                "symbol":           sym,
                "direction":        o.direction,
                "signal_close":     round(o.signal_close, 6),
                "limit_price":      round(o.limit_price, 6),
                "notional_usd":     round(o.notional, 2),
                "margin_usd":       round(o.margin, 2),
                "bars_elapsed":     o.bars_elapsed,
                "max_pending_bars": MAX_PENDING_BARS,
                "placed_at":        o.placed_at.isoformat(),
                "cs_order_id":      o.cs_order_id,
            }
            for sym, o in self._pending.items()
        ]
        open_list = []
        for sym, p in self._open.items():
            tp_d = round((p.tp_price / p.fill_price - 1) * 100, 3) \
                   if p.direction == "long" \
                   else round((1 - p.tp_price / p.fill_price) * 100, 3)
            sl_d = round((1 - p.sl_price / p.fill_price) * 100, 3) \
                   if p.direction == "long" \
                   else round((p.sl_price / p.fill_price - 1) * 100, 3)
            open_list.append({
                "symbol":             sym,
                "direction":          p.direction,
                "fill_price":         round(p.fill_price, 6),
                "last_price":         round(p.last_price, 6),
                "tp_price":           round(p.tp_price, 6),
                "sl_price":           round(p.sl_price, 6),
                "tp_dist_pct":        tp_d,
                "sl_dist_pct":        sl_d,
                "notional_usd":       round(p.notional, 2),
                "margin_usd":         round(p.margin, 2),
                "unrealised_pnl_usd": round(p.unrealised_pnl, 2),
                "bars_held":          p.bars_held,
                "max_hold_bars":      MAX_HOLD_BARS,
                "entry_time":         p.entry_time.isoformat() if p.entry_time else "",
                "entry_order_id":     p.entry_order_id,
                "tp_order_id":        p.tp_order_id,
                "sl_order_id":        p.sl_order_id,
            })
        try:
            with open(self._state_path, "w") as f:
                json.dump({
                    "equity":         round(self._equity, 2),
                    "pending_orders": pending_list,
                    "open_positions": open_list,
                    "last_updated":   datetime.now(timezone.utc).isoformat(),
                    "mode":           "LIVE_HFT",
                }, f, indent=2)
        except Exception as e:
            logger.debug("[live] State save failed: %s", e)

    # ── CSV helpers ────────────────────────────────────────────────────────────

    def _init_csvs(self):
        if not self._trade_log.exists():
            with open(self._trade_log, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_TRADE_HEADER).writeheader()
        if not self._equity_log.exists():
            with open(self._equity_log, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_EQUITY_HEADER).writeheader()
            self._append_equity({
                "trade_id":         "START",
                "timestamp":        datetime.now(timezone.utc).isoformat(),
                "equity":           round(self._equity, 2),
                "trade_pnl":        0,
                "total_trades":     0,
                "wins":             0,
                "losses":           0,
                "win_rate":         0,
                "max_drawdown_pct": 0,
            })

    def _append_trade(self, row: dict):
        try:
            with open(self._trade_log, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=_TRADE_HEADER,
                               extrasaction="ignore").writerow(row)
        except Exception as e:
            logger.warning("[live] Trade log write failed: %s", e)

    def _append_equity(self, row: dict):
        try:
            with open(self._equity_log, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=_EQUITY_HEADER,
                               extrasaction="ignore").writerow(row)
        except Exception as e:
            logger.warning("[live] Equity log write failed: %s", e)
