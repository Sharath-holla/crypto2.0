"""
Phase B — Real-Time WebSocket Listener

Architecture
────────────
  One asyncio task per symbol, all sharing a single CCXT Pro exchange instance.
  Each task maintains a rolling deque of BUFFER_SIZE closed candles.

  On every confirmed candle close:
    1. Update rolling buffer for this symbol
    2. Register that this symbol has a closed candle at timestamp T
    3. If >= MARKET_RETURN_WAIT_FRAC of symbols are closed at T:
         a. Compute market_return = mean(return_1) across closed symbols
         b. Run inference on EVERY symbol that is closed at T
         c. Dispatch alerts for signals that exceed threshold

  Candle close detection
  ──────────────────────
  CCXT Pro's watch_ohlcv yields a list of candles. The candle at index [-1]
  is the CURRENT (still open) candle. The candle at index [-2] just closed.
  We detect a new close by tracking the last seen open_time per symbol:
  when watch_ohlcv returns a candle with open_time > last_seen_open_time,
  the PREVIOUS candle is now confirmed closed.

  Memory management
  ─────────────────
  Each symbol holds a deque(maxlen=BUFFER_SIZE). A deque with maxlen
  automatically discards the oldest element when a new one is appended —
  memory is capped at BUFFER_SIZE × (bytes per row) × n_symbols.
  With 250 candles × ~200 bytes × 20 symbols ≈ 1 MB. Trivial on OCI.

  market_return gate
  ──────────────────
  market_return = equal-weight mean of return_1 across all symbols at the
  same 15m timestamp. In live mode we cannot compute this until enough
  symbols have closed their candle at that timestamp.
  MARKET_RETURN_WAIT_FRAC (default 0.80) = wait for 80% before proceeding.
  Symbols that close late get market_return from the partial set — acceptable.

  Async compatibility note
  ────────────────────────
  The trader passed as paper_trader may be PaperTrader (sync methods) or
  LiveTrader (async methods). All calls to price_tick / candle_tick /
  record_signal are routed through _call(), which detects whether the
  returned value is a coroutine and awaits it only when necessary.
  This keeps the listener compatible with both traders without any changes
  to their interfaces.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.config_signal import (
    BUFFER_SIZE, 
    EXCHANGE_ID, 
    MARKET_TYPE, 
    SYMBOLS,
    TIMEFRAME,
    MARKET_RETURN_WAIT_FRAC    
)

logger = logging.getLogger(__name__)

# OHLCV column order returned by CCXT
_OHLCV_COLS = ["timestamp", "open", "high", "low", "close", "volume"]

# Extra columns we need but CCXT does not include in watch_ohlcv.
_EXTRA_COLS = ["quote_volume", "taker_buy_quote", "trades"]


async def _call(result):
    """
    Await result if it is a coroutine, otherwise return it directly.

    Usage:
        await _call(trader.price_tick(sym, price))

    This lets the listener work with both synchronous (PaperTrader) and
    asynchronous (LiveTrader) method implementations without any branching
    at every call site.
    """
    if asyncio.iscoroutine(result):
        return await result
    return result


class CryptoListener:
    """
    Async CCXT Pro WebSocket listener for real-time 15m candle signals.

    Parameters
    ----------
    engine    : InferenceEngine
    dispatcher: AlertDispatcher
    """

    def __init__(self, engine, dispatcher, audit_loop=None, paper_trader=None):
        self.engine     = engine
        self.dispatcher = dispatcher
        self.audit_loop = audit_loop
        self.paper_trader = paper_trader   # PaperTrader or LiveTrader instance
        self.exchange     = None
        # Reverse mapping sym_key → exchange symbol — populated in start()
        self._sym_to_exchange: dict[str, str] = {}

        # Rolling candle buffers: symbol → deque of dicts
        self._buffers: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=BUFFER_SIZE)
        )

        # Track the last open_time we saw per symbol to detect new candles
        self._last_open_ms: dict[str, int] = {}

        # market_return gate: closed_at_ts[T] = {symbol: return_1}
        self._closed_at_ts: dict[int, dict[str, float]] = defaultdict(dict)

        # Pending inference: symbols waiting for market_return gate to open
        self._pending: dict[int, list[str]] = defaultdict(list)

    # ══════════════════════════════════════════════════════════════════════════
    # Startup
    # ══════════════════════════════════════════════════════════════════════════

    async def start(self):
        """Bootstrap REST history then launch all WebSocket tasks."""
        import ccxt.pro as ccxt

        logger.info(f"[listener] Connecting to {EXCHANGE_ID} ({MARKET_TYPE})...")
        self.exchange = getattr(ccxt, EXCHANGE_ID)({
            "enableRateLimit": True,
            "options": {"defaultType": MARKET_TYPE},
        })
        await self.exchange.load_markets()
        logger.info(f"[listener] Markets loaded | {len(SYMBOLS)} symbols")
        self._sym_to_exchange = {self._sym_key(s): s for s in SYMBOLS}

        # Bootstrap each symbol's rolling buffer with REST history
        logger.info("[listener] Bootstrapping rolling buffers from REST...")
        for sym in SYMBOLS:
            await self._bootstrap(sym)
            await asyncio.sleep(0.5)

        logger.info("[listener] Bootstrap complete — starting WebSocket streams")

        # Launch one watch task per symbol + one market_return gate task
        watch_tasks = [self._watch_symbol(sym) for sym in SYMBOLS]
        watch_tasks.append(self._run_market_return_gate())
        if self.paper_trader is not None:
            watch_tasks.append(self._run_position_monitor())
        await asyncio.gather(*watch_tasks, return_exceptions=True)

    async def stop(self):
        if self.exchange:
            await self.exchange.close()
        await self.dispatcher.close()
        logger.info("[listener] Shutdown complete")

    # ══════════════════════════════════════════════════════════════════════════
    # REST Bootstrap
    # ══════════════════════════════════════════════════════════════════════════

    async def _bootstrap(self, symbol: str):
        """
        Fetch BUFFER_SIZE historical candles from REST to warm up the buffer.
        This ensures features like ema50 and volatility_regime are valid
        from the very first WebSocket candle, not after a 100-candle warmup.
        """
        from pipeline.config_signal import TIMEFRAME, BUFFER_SIZE

        sym_key = self._sym_key(symbol)
        try:
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol, timeframe=TIMEFRAME, limit=BUFFER_SIZE
            )
            if not ohlcv:
                logger.warning(f"[bootstrap] {sym_key}: no data returned")
                return

            for bar in ohlcv[:-1]:   # exclude the last (open/live) candle
                row = self._bar_to_dict(bar, sym_key, has_taker=False)
                self._buffers[sym_key].append(row)

            # Try to fetch taker data from Binance klines endpoint (best-effort)
            await self._bootstrap_taker_columns(symbol, sym_key, ohlcv[:-1])

            # Record last seen open_time
            if ohlcv:
                self._last_open_ms[sym_key] = ohlcv[-1][0]

            logger.info(
                f"[bootstrap] {sym_key}: {len(self._buffers[sym_key])} candles loaded"
            )
        except Exception as e:
            logger.warning(f"[bootstrap] {sym_key}: failed — {e}")

    async def _bootstrap_taker_columns(
        self, symbol: str, sym_key: str, ohlcv: list
    ):
        """
        Binance futures /fapi/v1/klines includes taker_buy_quote at index [10].
        Attempt to backfill taker columns in the already-loaded buffer rows.
        This is best-effort — if it fails, taker columns remain 0.0.

        Note: for non-Binance exchanges (Bybit/OKX) taker data requires a
        separate endpoint. The pipeline works without taker data but loses
        CVD / buy_pressure features — those become 0 until the buffer fills
        via WebSocket (which does carry taker data via fetch_trades).
        """
        if EXCHANGE_ID != "binance":
            return
        try:
            since_ms = ohlcv[0][0]
            limit    = len(ohlcv)
            raw = await self.exchange.fapiPublicGetKlines({
                "symbol":    sym_key,
                "interval":  TIMEFRAME,
                "startTime": since_ms,
                "limit":     limit,
            })
            buf_list = list(self._buffers[sym_key])
            for i, r in enumerate(raw):
                if i >= len(buf_list):
                    break
                buf_list[i]["quote_volume"]    = float(r[7])
                buf_list[i]["trades"]          = int(r[8])
                buf_list[i]["taker_buy_quote"] = float(r[10])
            self._buffers[sym_key] = deque(buf_list, maxlen=self._buffers[sym_key].maxlen)
        except Exception as e:
            logger.debug(f"[bootstrap] {sym_key}: taker backfill skipped — {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # WebSocket watch loop (one per symbol)
    # ══════════════════════════════════════════════════════════════════════════

    async def _watch_symbol(self, symbol: str):
        """
        Continuously stream 15m candles for one symbol.
        On every confirmed candle close → update buffer → register with gate.
        """

        sym_key = self._sym_key(symbol)
        logger.info(f"[ws] Starting stream: {sym_key}")
        active_candle = None
        retry_delay   = 1.0

        while True:
            try:
                candles = await self.exchange.watch_ohlcv(symbol, timeframe=TIMEFRAME)
                retry_delay = 1.0   # reset on success

                if not candles:
                    continue

                latest_bar     = candles[-1]
                latest_open_ms = candles[-1][0]
                prev_open_ms   = self._last_open_ms.get(sym_key, 0)

                if latest_open_ms > prev_open_ms and prev_open_ms > 0:
                    # The candle that WAS open at prev_open_ms is now CLOSED.
                    closed_bar = active_candle if active_candle else latest_bar
                    for bar in reversed(candles):
                        if bar[0] == prev_open_ms:
                            closed_bar = bar
                            break

                    if closed_bar is None and len(candles) >= 2:
                        closed_bar = candles[-2]   # fallback: second-to-last

                    if closed_bar:
                        row = self._bar_to_dict(closed_bar, sym_key, has_taker=False)

                        # Attempt to get taker data for this specific candle
                        taker = await self._fetch_single_taker(symbol, sym_key, closed_bar[0])
                        if taker:
                            row.update(taker)

                        self._buffers[sym_key].append(row)

                        # Register this closed candle with the market_return gate
                        closed_ts_ms = closed_bar[0]
                        return_1     = self._compute_return_1(sym_key, closed_bar[4])
                        self._closed_at_ts[closed_ts_ms][sym_key] = return_1
                        self._pending[closed_ts_ms].append(sym_key)

                        logger.debug(
                            f"[ws] {sym_key} candle closed | "
                            f"ts={datetime.fromtimestamp(closed_ts_ms/1000, tz=timezone.utc)} | "
                            f"close={closed_bar[4]:.4f} | "
                            f"buffer={len(self._buffers[sym_key])}"
                        )

                self._last_open_ms[sym_key] = latest_open_ms
                active_candle = latest_bar

            except Exception as e:
                logger.warning(
                    f"[ws] {sym_key}: stream error — {e}. "
                    f"Reconnecting in {retry_delay:.0f}s..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)   # exponential backoff

    async def _fetch_single_taker(
        self, symbol: str, sym_key: str, open_ms: int
    ) -> Optional[dict]:
        """
        Fetch taker buy/sell volume for a single just-closed candle.
        Lightweight REST call — one per candle close per symbol.
        Returns None if the exchange doesn't support it.
        """
        if EXCHANGE_ID != "binance":
            return None
        try:
            raw = await self.exchange.fapiPublicGetKlines({
                "symbol":    sym_key,
                "interval":  TIMEFRAME,
                "startTime": open_ms,
                "limit":     1,
            })
            if raw:
                r = raw[0]
                return {
                    "quote_volume":    float(r[7]),
                    "trades":          int(r[8]),
                    "taker_buy_quote": float(r[10]),
                }
        except Exception as e:
            logger.debug(f"[taker] {sym_key}: fetch failed — {e}")
        return None

    # ══════════════════════════════════════════════════════════════════════════
    # market_return gate + inference trigger
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_market_return_gate(self):
        """
        Phase D additions:
        - Cross-symbol data collection for vol_rank_pct / flow_vs_peers
        - audit_loop.tick() call for T+4 verification advancement
        - FIX: candle_tick now awaited via _call() to support LiveTrader
        """
        n_symbols_total = len(SYMBOLS)
        threshold_n     = max(1, int(n_symbols_total * MARKET_RETURN_WAIT_FRAC))
        DEADLINE_S      = 2 * 15 * 60

        first_seen: dict = {}

        while True:
            await asyncio.sleep(1)

            now          = time.time()
            completed_ts = []

            for ts_ms, sym_returns in list(self._closed_at_ts.items()):
                n_closed = len(sym_returns)

                if ts_ms not in first_seen:
                    first_seen[ts_ms] = now

                age_s     = now - first_seen[ts_ms]
                deadline  = age_s > DEADLINE_S
                gate_open = n_closed >= threshold_n or deadline

                if not gate_open:
                    continue

                # ── Compute market_return ──────────────────────────────────────
                market_return = float(np.mean(list(sym_returns.values())))

                # ── Build cross-symbol volume snapshot ─────────────────────────
                all_quote_volumes: dict = {}
                all_net_taker:     dict = {}

                pending_syms = self._pending.get(ts_ms, [])
                for sk in pending_syms:
                    buf = self._buffers.get(sk)
                    if buf and len(buf) >= 1:
                        last_row = list(buf)[-1]
                        all_quote_volumes[sk] = float(last_row.get("quote_volume", 0.0))
                        tbq = float(last_row.get("taker_buy_quote", 0.0))
                        qvl = float(last_row.get("quote_volume",    0.0))
                        all_net_taker[sk] = tbq - (qvl - tbq)   # = 2*tbq - qvol

                cross_symbol_data = {
                    "all_quote_volumes": all_quote_volumes,
                    "all_net_taker":     all_net_taker,
                }

                # ── Run inference + audit / trader ticks ───────────────────────
                pending_syms = self._pending.pop(ts_ms, [])

                for sym_key in pending_syms:
                    buf = self._buffers[sym_key]
                    if len(buf) < 120:
                        continue
                    df = pd.DataFrame(list(buf))
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

                    # Advance audit loop T+4 counter (every symbol, every candle)
                    if hasattr(self, "audit_loop") and self.audit_loop is not None:
                        last_row  = list(buf)[-1]
                        close_val = float(last_row.get("close", 0.0))
                        high_val  = float(last_row.get("high",  close_val))
                        low_val   = float(last_row.get("low",   close_val))
                        self.audit_loop.tick(sym_key, close_val, high_val, low_val)

                    # FIX: candle_tick is async in LiveTrader — use _call() so
                    # this works with both PaperTrader (sync) and LiveTrader (async).
                    if self.paper_trader is not None:
                        last_row  = list(buf)[-1]
                        close_val = float(last_row.get("close", 0.0))
                        high_val  = float(last_row.get("high",  close_val))
                        low_val   = float(last_row.get("low",   close_val))
                        await _call(
                            self.paper_trader.candle_tick(sym_key, close_val, high_val, low_val)
                        )

                    # ── Inference ──────────────────────────────────────────────
                    try:
                        sig = self.engine.predict(
                            sym_key,
                            df,
                            market_return,
                            cross_symbol_data=cross_symbol_data,
                        )
                    except Exception as e:
                        logger.error(f"[gate] Inference crashed for {sym_key}: {repr(e)}")
                        continue

                    if sig is None:
                        continue

                    asyncio.create_task(self.dispatcher.send(sig))

                    # Open position in paper/live trader (same signal, same price)
                    if self.paper_trader is not None:
                        await _call(self.paper_trader.record_signal(sig))

                completed_ts.append(ts_ms)

            for ts_ms in completed_ts:
                self._closed_at_ts.pop(ts_ms, None)
                first_seen.pop(ts_ms, None)

            expired = [t for t, s in first_seen.items() if (now - s) > DEADLINE_S * 3]
            for t in expired:
                first_seen.pop(t, None)
                self._closed_at_ts.pop(t, None)
                self._pending.pop(t, None)

    # ══════════════════════════════════════════════════════════════════════════
    # Fast position monitor — runs every 1.5 s
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_position_monitor(self):
        """
        Fetch live prices every 1.5 s for symbols with pending orders or open
        positions, then call paper_trader.price_tick() for each.

        FIX: price_tick is async in LiveTrader — wrapped with _call() so this
        works with both PaperTrader (sync) and LiveTrader (async).

        Uses fetch_tickers() (one REST call for all active symbols) to stay
        within Binance rate limits even with many concurrent positions.
        """
        POLL_INTERVAL = 1.5

        # Wait for exchange to be initialised (start() sets self.exchange)
        while self.exchange is None:
            await asyncio.sleep(1)

        logger.info("[monitor] Fast position monitor started")

        while True:
            await asyncio.sleep(POLL_INTERVAL)

            if self.paper_trader is None:
                continue

            active = self.paper_trader.get_active_symbols()
            if not active:
                continue

            # Map sym_keys → exchange symbols (BTC/USDT:USDT etc.)
            exchange_syms = [
                self._sym_to_exchange[sk]
                for sk in active
                if sk in self._sym_to_exchange
            ]
            if not exchange_syms:
                continue

            try:
                # fetch_tickers: one call returns last price for all requested symbols
                tickers = await self.exchange.fetch_tickers(exchange_syms)
                for sym_key in active:
                    ex_sym = self._sym_to_exchange.get(sym_key)
                    if ex_sym is None or ex_sym not in tickers:
                        continue
                    last = tickers[ex_sym].get("last") or tickers[ex_sym].get("close")
                    if last is None:
                        continue
                    # FIX: price_tick is async in LiveTrader — must be awaited
                    await _call(self.paper_trader.price_tick(sym_key, float(last)))
            except Exception as e:
                logger.debug(f"[monitor] Price fetch failed: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _sym_key(symbol: str) -> str:
        """Convert 'BTC/USDT:USDT' → 'BTCUSDT' for use as dict key + feature col."""
        return symbol.replace("/", "").replace(":USDT", "").replace("USDT", "USDT")

    @staticmethod
    def _bar_to_dict(bar: list, sym_key: str, has_taker: bool = False) -> dict:
        """Convert a raw CCXT OHLCV bar list to a dict row."""
        return {
            "timestamp":       bar[0],
            "open":            float(bar[1]),
            "high":            float(bar[2]),
            "low":             float(bar[3]),
            "close":           float(bar[4]),
            "volume":          float(bar[5]),
            "quote_volume":    0.0,
            "taker_buy_quote": 0.0,
            "trades":          0,
        }

    def _compute_return_1(self, sym_key: str, current_close: float) -> float:
        """Compute return_1 = close[t] / close[t-1] - 1 from rolling buffer."""
        buf = self._buffers[sym_key]
        if len(buf) < 2:
            return 0.0
        prev_close = list(buf)[-2]["close"]
        if prev_close == 0:
            return 0.0
        return (current_close / prev_close) - 1.0