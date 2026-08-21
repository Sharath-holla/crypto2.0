# DEPRECATED: CoinSwitch-specific legacy prototype. ADR-017 supersedes this
# execution architecture. Do not run, configure credentials, or submit orders.
"""
main_trader.py — Trading Engine  (Process 2 of 2)
══════════════════════════════════════════════════════════════════════════════
Responsibilities
  ├─ Poll  logs/signals_queue.csv  for new signals (every 1 s)
  ├─ Call  LiveTrader.record_signal()  to place limit-entry orders on CoinSwitch
  ├─ Monitor pending orders + open positions every 1.5 s (Binance REST prices)
  └─ Fire  LiveTrader.candle_tick()  on every 15m boundary (Binance REST OHLCV)

Does NOT run any ML models, connect to Telegram/Discord, or use WebSockets.

Data flow
  signals_queue.csv ──► SignalQueueReader ──► LiveTrader.record_signal()
  Binance REST  ──► _price_monitor()       ──► LiveTrader.price_tick()
  15m timer     ──► _candle_tick_sched()   ──► LiveTrader.candle_tick()

Configuration : pipeline/config_trader.py
Reads         : logs/signals_queue.csv            ← written by main_signal.py
                logs/trader_queue_state.json      ← own resume pointer
                logs/positions_state.json         ← crash-recovery positions
Writes        : logs/paper_trades.csv             ← closed trade history
                logs/equity_curve.csv             ← equity after each trade
                logs/positions_state.json         ← live open position state
                logs/trader_queue_state.json      ← last consumed row_id
                logs/trader.log                   ← operational log

Environment variables required
  COINSWITCH_API_KEY
  COINSWITCH_SECRET_KEY

Usage
  python main_trader.py [--capital 10000]
══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Config (trader pipeline only) ─────────────────────────────────────────────
from pipeline.config_trader import (
    LOG_DIR, LOG_LEVEL,
    SIGNALS_QUEUE_PATH, SIGNALS_QUEUE_HEADER, TRADER_QUEUE_STATE_PATH,
    EXCHANGE_ID, MARKET_TYPE, TIMEFRAME, CANDLE_SECONDS, SYMBOLS,
    PRICE_POLL_INTERVAL, CANDLE_TICK_BUFFER_S,
)

# ── Execution modules ──────────────────────────────────────────────────────────
from pipeline.coinswitch_client import CoinSwitchClient
from pipeline.live_trader       import LiveTrader


# ══════════════════════════════════════════════════════════════════════════════
# Signal Queue Reader
# ══════════════════════════════════════════════════════════════════════════════

class SignalQueueReader:
    """
    Polls signals_queue.csv written by main_signal.py.

    Tracking strategy
    ─────────────────
    The reader stores the last processed row_id in trader_queue_state.json.
    On every poll it opens the CSV, skips rows with row_id ≤ last_row_id,
    and returns only truly new rows.  This approach is:
      • Safe across restarts (no signals are re-processed or skipped)
      • File-lock-free (append-only writes by the signal process never race
        with sequential reads here because we open/close for each read)
      • Robust to partial writes (DictReader skips malformed trailing lines)
    """

    def __init__(self, queue_path: Path, state_path: Path) -> None:
        self._queue_path  = queue_path
        self._state_path  = state_path
        self._last_row_id = self._load_state()
        self._log         = logging.getLogger(self.__class__.__name__)
        self._log.info(
            "[queue_reader] Initialised | queue=%s | resuming from row_id=%d",
            queue_path, self._last_row_id,
        )

    # ── State persistence ──────────────────────────────────────────────────────

    def _load_state(self) -> int:
        """Return the last-consumed row_id from disk, or 0 on first run."""
        if not self._state_path.exists():
            return 0
        try:
            data = json.loads(self._state_path.read_text())
            return int(data.get("last_row_id", 0))
        except Exception:
            return 0

    def _save_state(self) -> None:
        """Persist the current last_row_id so restarts resume correctly."""
        try:
            self._state_path.write_text(
                json.dumps({
                    "last_row_id": self._last_row_id,
                    "updated_at":  datetime.now(timezone.utc).isoformat(),
                },
                indent=2)
            )
        except Exception as exc:
            self._log.warning("[queue_reader] State save failed: %s", exc)

    # ── Poll ───────────────────────────────────────────────────────────────────

    def read_new(self) -> list[dict]:
        """
        Return all rows with row_id > last_row_id and update the pointer.
        Returns an empty list if the queue file does not exist yet.
        """
        if not self._queue_path.exists():
            return []

        new_rows: list[dict] = []
        try:
            with open(self._queue_path, "r", newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        rid = int(row.get("row_id", 0))
                    except (ValueError, TypeError):
                        continue
                    if rid > self._last_row_id:
                        new_rows.append(row)
                        self._last_row_id = rid   # keep advancing during this read
        except Exception as exc:
            self._log.error("[queue_reader] CSV read error: %s", exc)
            return []

        if new_rows:
            self._save_state()
            self._log.debug(
                "[queue_reader] %d new row(s) found | last_row_id now %d",
                len(new_rows), self._last_row_id,
            )
        return new_rows

    # ── Row → signal dict ──────────────────────────────────────────────────────

    @staticmethod
    def row_to_signal(row: dict) -> dict:
        """
        Convert a CSV row dict back to the signal dict format expected by
        LiveTrader.record_signal().  All numeric fields are safely parsed;
        empty / "None" mpe_target is restored to Python None.
        """
        def _f(key: str, default: float = 0.0) -> float:
            v = row.get(key, "")
            if v in ("", "None", "nan", "NaN"):
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        def _b(key: str) -> bool:
            return str(row.get(key, "")).strip().lower() in ("true", "1", "yes")

        mpe_raw = row.get("mpe_target", "")
        mpe     = None if mpe_raw in ("", "None", "nan", "NaN") else _f("mpe_target")

        return {
            # Core identity
            "symbol":        row.get("symbol",       ""),
            "timestamp":     row.get("candle_ts",    ""),
            "signal":        row.get("signal",       ""),
            "strong":        _b("strong"),
            # Price at signal close — used by LiveTrader for limit entry offset
            "close":         _f("close"),
            # Layer-3 MPE target — used as TP distance; None falls back to DEFAULT_TP_PCT
            "mpe_target":    mpe,
            # Blended probabilities — stored in LivePosition for audit / CSV
            "p_long":        _f("p_long"),
            "p_short":       _f("p_short"),
            "p_hold":        _f("p_hold"),
            # Cap-tier features — stored in LivePosition / trade CSV
            "cap_tier":      row.get("cap_tier",      ""),
            "cap_tier_name": row.get("cap_tier_name", ""),
            "vol_to_mcap":   _f("vol_to_mcap"),
            "flow_vs_peers": _f("flow_vs_peers"),
            # Context fields
            "market_return": _f("market_return"),
            "precision_est": _f("precision_est", 0.5),
        }


# ══════════════════════════════════════════════════════════════════════════════
# Background coroutines
# ══════════════════════════════════════════════════════════════════════════════

async def _signal_poller(trader: LiveTrader, reader: SignalQueueReader) -> None:
    """
    Poll signals_queue.csv every second.
    For each new row call trader.record_signal() to place a limit-entry order.

    Duplicate-symbol guard: LiveTrader already rejects a new signal if there is
    a pending or open position on that symbol (MAX_CONCURRENT / dedup logic).
    No extra filtering needed here.
    """
    log = logging.getLogger("signal_poller")
    log.info("[poller] Watching %s", reader._queue_path)

    while True:
        await asyncio.sleep(1.0)
        for row in reader.read_new():
            sig = SignalQueueReader.row_to_signal(row)
            direction = sig.get("signal", "")
            if direction not in ("long", "short"):
                continue

            log.info(
                "[poller] New signal  row_id=%-5s  %-5s  %-15s  "
                "close=%s  mpe=%s",
                row.get("row_id", "?"),
                direction.upper(),
                sig["symbol"],
                sig["close"],
                sig.get("mpe_target") or "n/a",
            )
            try:
                await trader.record_signal(sig)
            except Exception as exc:
                log.error(
                    "[poller] record_signal failed for %s: %s",
                    sig["symbol"], exc,
                )


async def _price_monitor(
    trader: LiveTrader,
    exchange,
    sym_map: dict[str, str],
) -> None:
    """
    Fetch live last prices every PRICE_POLL_INTERVAL seconds for every symbol
    that has a pending order or open position, then call trader.price_tick().

    Uses fetch_tickers() — one REST call for all active symbols at once —
    to stay within Binance rate limits even with many concurrent positions.
    """
    log = logging.getLogger("price_monitor")
    log.info("[price_monitor] Started (poll=%.1fs)", PRICE_POLL_INTERVAL)

    while True:
        await asyncio.sleep(PRICE_POLL_INTERVAL)

        active: list[str] = trader.get_active_symbols()
        if not active:
            continue

        # Translate sym_keys to exchange symbols (BTC/USDT:USDT etc.)
        ex_syms = [sym_map[sk] for sk in active if sk in sym_map]
        if not ex_syms:
            continue

        try:
            tickers = await exchange.fetch_tickers(ex_syms)
            for sk in active:
                ex_sym = sym_map.get(sk)
                if not ex_sym or ex_sym not in tickers:
                    continue
                last = (
                    tickers[ex_sym].get("last")
                    or tickers[ex_sym].get("close")
                )
                if last is None:
                    continue
                await trader.price_tick(sk, float(last))
        except Exception as exc:
            log.debug("[price_monitor] fetch_tickers failed: %s", exc)


async def _candle_tick_scheduler(
    trader: LiveTrader,
    exchange,
    sym_map: dict[str, str],
) -> None:
    """
    Fire LiveTrader.candle_tick() on every 15m candle-close boundary for all
    symbols with a pending order or open position.

    Timing
    ──────
    Sleeps until the next epoch-aligned 15m boundary + CANDLE_TICK_BUFFER_S
    (default 5 s) to allow the exchange candle to settle before we fetch OHLCV.

    Real H / L
    ──────────
    Fetches the last 3 candles via REST and uses index [-2] (the just-closed
    candle) so candle_tick() receives accurate high/low for intra-candle SL
    checks and time-based exits.  If the fetch fails, zeros are passed — the
    LiveTrader bar counter still increments and time-exits still fire.
    """
    log = logging.getLogger("candle_scheduler")
    log.info("[candle_sched] Started")

    while True:
        # ── Align to next 15m candle boundary ─────────────────────────────────
        now    = time.time()
        wait_s = CANDLE_SECONDS - (now % CANDLE_SECONDS) + CANDLE_TICK_BUFFER_S
        await asyncio.sleep(wait_s)

        active: list[str] = trader.get_active_symbols()
        if not active:
            continue

        log.info("[candle_sched] Candle tick for %d active symbol(s)", len(active))

        for sk in list(active):
            ex_sym = sym_map.get(sk)

            if not ex_sym:
                # Symbol not in our map — tick with zeros so bar counter increments
                await trader.candle_tick(sk, 0.0, 0.0, 0.0)
                continue

            try:
                # index -1 = still-open candle; index -2 = just-closed candle
                ohlcv = await exchange.fetch_ohlcv(
                    ex_sym, timeframe=TIMEFRAME, limit=3
                )
                if len(ohlcv) >= 2:
                    bar   = ohlcv[-2]
                    close = float(bar[4])
                    high  = float(bar[2])
                    low   = float(bar[3])
                else:
                    close = high = low = 0.0
            except Exception as exc:
                log.debug(
                    "[candle_sched] OHLCV fetch failed for %s: %s", sk, exc
                )
                close = high = low = 0.0

            try:
                await trader.candle_tick(sk, close, high, low)
            except Exception as exc:
                log.error(
                    "[candle_sched] candle_tick raised for %s: %s", sk, exc
                )


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging() -> None:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt   = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "trader.log"),
        ],
    )
    for lib in ("ccxt", "aiohttp", "asyncio", "websockets"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════════════════════
# Graceful shutdown
# ══════════════════════════════════════════════════════════════════════════════

def _install_shutdown(
    loop: asyncio.AbstractEventLoop,
    cs_client: CoinSwitchClient,
    exchange,
) -> None:
    """Register SIGINT / SIGTERM for clean teardown of both HTTP clients."""
    async def _shutdown() -> None:
        log = logging.getLogger(__name__)
        log.info("[trader_main] Shutdown signal received — closing clients...")
        await cs_client.close()
        await exchange.close()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trading Engine — Process 2 (reads signals_queue.csv, executes orders)"
    )
    parser.add_argument(
        "--capital", type=float, default=10_000.0,
        help="Starting capital in USDT (default: 10 000). "
             "Overridden by live wallet balance after sync.",
    )
    args = parser.parse_args()

    logger = logging.getLogger(__name__)
    logger.info("=" * 64)
    logger.info("  Trading Engine -")
    logger.info(f"  Signal queue : {SIGNALS_QUEUE_PATH}")
    logger.info(f"  Capital      : loading.... (syncing)")
    logger.info("=" * 64)

    # ── API key validation ─────────────────────────────────────────────────────
    api_key    = os.getenv("COINSWITCH_API_KEY",    "")
    secret_key = os.getenv("COINSWITCH_SECRET_KEY", "")
    if not api_key or not secret_key:
        logger.error(
            "[trader_main] COINSWITCH_API_KEY and COINSWITCH_SECRET_KEY "
            "must be set in your .env file."
        )
        sys.exit(1)

    # ── CoinSwitch client ──────────────────────────────────────────────────────
    cs_client = CoinSwitchClient(api_key, secret_key)

    logger.info("[trader_main] Validating CoinSwitch API keys...")
    val = await cs_client.validate_keys()
    if "error" in val:
        logger.error("[trader_main] Key validation failed: %s", val)
        await cs_client.close()
        sys.exit(1)
    logger.info("[trader_main] CoinSwitch API keys valid ✓")

    # ── Live trader ────────────────────────────────────────────────────────────
    trader = LiveTrader(cs_client=cs_client, initial_capital=args.capital)

    actual_balance = await trader.sync_balance()
    if actual_balance > 0:
        logger.info("[trader_main] HFT wallet balance: %.4f USDT", actual_balance)

    # Load exchange tick-size / lot-size rules for all symbols up-front
    logger.info("[trader_main] Loading instrument rules from CoinSwitch HFT...")
    await trader.load_instrument_rules()

    # Restore any pending orders / open positions from the last run
    logger.info("[trader_main] Restoring position state from disk...")
    await trader.restore_state()

    # ── Binance REST exchange (price + candle monitoring) ──────────────────────
    #
    # We use ccxt.async_support (REST-only) — NOT ccxt.pro (WebSocket).
    # The signal process already holds the WebSocket connection; using REST here
    # keeps the two processes fully independent and avoids connection conflicts.
    import ccxt.async_support as ccxt_async

    exchange = getattr(ccxt_async, EXCHANGE_ID)({
        "enableRateLimit": True,
        "options":         {"defaultType": MARKET_TYPE},
    })
    await exchange.load_markets()
    logger.info("[trader_main] Binance REST markets loaded ✓")

    # Build sym_key ("BTCUSDT") → exchange symbol ("BTC/USDT:USDT") lookup
    sym_map: dict[str, str] = {
        s.replace("/", "").replace(":USDT", "").replace("USDT", "USDT"): s
        for s in SYMBOLS
    }

    # ── Signal queue reader ────────────────────────────────────────────────────
    reader = SignalQueueReader(SIGNALS_QUEUE_PATH, TRADER_QUEUE_STATE_PATH)

    # ── Shutdown handler ───────────────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    _install_shutdown(loop, cs_client, exchange)

    # ── Launch all three concurrent loops ──────────────────────────────────────
    #
    # Loop 1 — _signal_poller     : polls CSV every 1 s → record_signal()
    # Loop 2 — _price_monitor     : polls Binance REST every 1.5 s → price_tick()
    # Loop 3 — _candle_tick_sched : fires every 15m boundary → candle_tick()
    #
    # return_exceptions=True prevents one crashed loop from killing the others.
    logger.info("[trader_main] Starting order execution loops...")
    try:
        results = await asyncio.gather(
            _signal_poller(trader, reader),
            _price_monitor(trader, exchange, sym_map),
            _candle_tick_scheduler(trader, exchange, sym_map),
            return_exceptions=True,
        )
        # Log any loop that exited with an exception
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "[trader_main] Loop %d exited with exception: %s", i, result
                )
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("[trader_main] Fatal error: %s", exc)
    finally:
        await exchange.close()
        await cs_client.close()
        logger.info("[trader_main] Trading engine stopped.")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
