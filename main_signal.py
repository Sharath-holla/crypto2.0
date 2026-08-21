"""
main_signal.py — Signal Pipeline  (Process 1 of 2)
══════════════════════════════════════════════════════════════════════════════
Responsibilities
  ├─ Connect to Binance via CCXT Pro WebSocket (all tracked symbols)
  ├─ Maintain 250-candle rolling buffers per symbol
  ├─ Run 3-layer inference on every confirmed 15m candle close
  ├─ Advance the AuditLoop for T+4 ground-truth verification
  ├─ Dispatch alerts to Telegram / Discord
  └─ Append every actionable signal to  logs/signals_queue.csv

Does NOT connect to any execution venue or place any orders.
Order execution is handled entirely by  main_trader.py  (Process 2).

Data flow
  Binance WS ──► CryptoListener ──► InferenceEngine ──► SignalQueueWriter
                                  └──► AlertDispatcher  └──► signals_queue.csv
                                  └──► AuditLoop

Configuration : pipeline/config_signal.py
Reads         : models/  (base_model_15m.pkl, cap_calibrator.pkl, mpe_regressor_15m.pkl)
Writes        : logs/signals_queue.csv      ← consumed by main_trader.py
                logs/signals_audit.csv      ← T+4 audit verification log
                logs/signals.log            ← per-signal detail log
                logs/signal_pipeline.log    ← operational / error log

Usage
  python main_signal.py
══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import csv
import logging
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Config (signal pipeline only) ─────────────────────────────────────────────
from pipeline.config_signal import (
    MODEL_PATH, MPE_MODEL_PATH,
    LOG_DIR, LOG_LEVEL,
    SIGNAL_THRESHOLD, STRONG_THRESHOLD,
    SIGNALS_QUEUE_PATH, SIGNALS_QUEUE_HEADER,
)

# ── Pipeline modules (these still import from pipeline.config — do not change) ─
from pipeline.inference import InferenceEngine
from pipeline.alerts    import AlertDispatcher
from pipeline.listener  import CryptoListener
from pipeline.audit     import AuditLoop


# ══════════════════════════════════════════════════════════════════════════════
# Signal Queue Writer
# ══════════════════════════════════════════════════════════════════════════════

class SignalQueueWriter:
    """
    Lightweight drop-in replacement for PaperTrader / LiveTrader.

    The CryptoListener calls record_signal(sig) on whatever object is passed
    as paper_trader=. This class intercepts those calls and appends one CSV
    row per actionable signal instead of placing any orders.

    price_tick() and candle_tick() are no-ops — position monitoring lives in
    main_trader.py (Process 2) which has its own Binance REST connection.
    get_active_symbols() returns [] so the listener's position-monitor loop
    exits immediately and wastes no resources.
    """

    def __init__(self, queue_path: Path) -> None:
        self._path   = queue_path
        self._row_id = self._recover_last_row_id()
        self._log    = logging.getLogger(self.__class__.__name__)
        self._init_csv()
        self._log.info(
            "[queue_writer] Initialised | path=%s | next_row_id=%d",
            queue_path, self._row_id + 1,
        )

    # ── CSV initialisation ─────────────────────────────────────────────────────

    def _recover_last_row_id(self) -> int:
        """
        Read the last row_id already in the CSV so IDs are never reused across
        restarts.  Returns 0 if the file is new or unreadable.
        """
        if not self._path.exists():
            return 0
        try:
            with open(self._path, "r", newline="") as f:
                rows = list(csv.DictReader(f))
            return int(rows[-1]["row_id"]) if rows else 0
        except Exception:
            return 0

    def _init_csv(self) -> None:
        """Create the CSV with headers if it does not exist yet."""
        if not self._path.exists():
            with open(self._path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=SIGNALS_QUEUE_HEADER).writeheader()
            self._log.info("[queue_writer] Created %s", self._path)

    # ── Core write ─────────────────────────────────────────────────────────────

    def record_signal(self, sig: dict) -> None:
        """
        Called by CryptoListener._run_market_return_gate() for every signal.
        "hold" signals are silently discarded; only long / short are written.

        The append is done with a single open/write/close cycle so concurrent
        reads from main_trader.py never see a half-written line.
        """
        if sig.get("signal") == "hold":
            return

        self._row_id += 1
        mpe = sig.get("mpe_target")

        row: dict = {
            "row_id":        self._row_id,
            "written_at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "symbol":        sig.get("symbol",       ""),
            "candle_ts":     str(sig.get("timestamp", "")),
            "signal":        sig.get("signal",       ""),
            "strong":        str(sig.get("strong",   False)),
            "close":         sig.get("close",        ""),
            "mpe_target":    "" if mpe is None else round(float(mpe), 6),
            "p_long":        round(float(sig.get("p_long",        0.0)), 6),
            "p_short":       round(float(sig.get("p_short",       0.0)), 6),
            "p_hold":        round(float(sig.get("p_hold",        0.0)), 6),
            "p_base_long":   round(float(sig.get("p_base_long",   0.0)), 6),
            "p_base_short":  round(float(sig.get("p_base_short",  0.0)), 6),
            "p_cal_long":    round(float(sig.get("p_cal_long",    0.0)), 6),
            "p_cal_short":   round(float(sig.get("p_cal_short",   0.0)), 6),
            "cap_tier":      sig.get("cap_tier",      ""),
            "cap_tier_name": sig.get("cap_tier_name", ""),
            "vol_to_mcap":   round(float(sig.get("vol_to_mcap",   0.0)), 8),
            "flow_vs_peers": round(float(sig.get("flow_vs_peers", 0.0)), 6),
            "market_return": round(float(sig.get("market_return", 0.0)), 6),
            "precision_est": round(float(sig.get("precision_est", 0.5)), 4),
        }

        try:
            with open(self._path, "a", newline="") as f:
                csv.DictWriter(
                    f, fieldnames=SIGNALS_QUEUE_HEADER, extrasaction="ignore"
                ).writerow(row)
            self._log.info(
                "[queue_writer] row_id=%-5d  %-5s  %-15s  "
                "close=%.5f  mpe=%s  p_long=%.3f  p_short=%.3f",
                self._row_id,
                row["signal"].upper(),
                row["symbol"],
                float(row["close"]) if row["close"] != "" else 0.0,
                row["mpe_target"] if row["mpe_target"] != "" else "n/a",
                row["p_long"],
                row["p_short"],
            )
        except Exception as exc:
            self._log.error(
                "[queue_writer] Write failed for row_id=%d (%s): %s",
                self._row_id, row["symbol"], exc,
            )

    # ── Stub interface (required by CryptoListener) ────────────────────────────

    def get_active_symbols(self) -> list:
        """
        Return empty list so the listener's _run_position_monitor() loop
        finds no active symbols and skips Binance REST calls immediately.
        Position monitoring belongs to main_trader.py.
        """
        return []

    def price_tick(self, sym: str, price: float) -> None:
        """No-op. Price ticks are consumed by main_trader.py."""
        pass

    def candle_tick(
        self, sym: str, close: float, high: float, low: float
    ) -> None:
        """No-op. Candle ticks drive time-exits in main_trader.py."""
        pass


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
            logging.FileHandler(LOG_DIR / "signal_pipeline.log"),
        ],
    )
    # Suppress noisy third-party loggers
    for lib in ("ccxt", "aiohttp", "asyncio", "websockets"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════════════════════
# Graceful shutdown
# ══════════════════════════════════════════════════════════════════════════════

def _install_shutdown(loop: asyncio.AbstractEventLoop, listener: CryptoListener) -> None:
    """Register SIGINT / SIGTERM handlers for clean shutdown."""
    async def _shutdown() -> None:
        logging.getLogger(__name__).info(
            "[signal_main] Shutdown signal received — stopping listener..."
        )
        await listener.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))


# ══════════════════════════════════════════════════════════════════════════════
# Banner
# ══════════════════════════════════════════════════════════════════════════════

def _print_banner(logger: logging.Logger) -> None:
    logger.info("=" * 64)
    logger.info("  Signal Pipeline")
    logger.info(f"  Model         : {MODEL_PATH.name}")
    logger.info(f"  Timeframe     : 15m")
    logger.info(f"  Sig threshold : {SIGNAL_THRESHOLD}  |  Strong: {STRONG_THRESHOLD}")
    logger.info(f"  Queue output  : {SIGNALS_QUEUE_PATH}")
    logger.info("=" * 64)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    logger = logging.getLogger(__name__)
    _print_banner(logger)

    # ── 1. Audit loop ──────────────────────────────────────────────────────────
    audit = AuditLoop()
    logger.info("[signal_main] AuditLoop initialised")

    # ── 2. Inference engine (loads all three model layers from disk) ───────────
    logger.info("[signal_main] Loading inference engine (3-layer stack)...")
    engine = InferenceEngine(mpe_model_path=MPE_MODEL_PATH, audit_loop=audit)
    logger.info("[signal_main] Inference engine ready ✓")

    # ── 3. Alert dispatcher (Telegram + Discord, async HTTP) ──────────────────
    dispatcher = AlertDispatcher()
    logger.info("[signal_main] Alert dispatcher ready ✓")

    # ── 4. Signal queue writer ─────────────────────────────────────────────────
    queue_writer = SignalQueueWriter(SIGNALS_QUEUE_PATH)

    # ── 5. Listener (paper_trader= accepts anything with record_signal()) ──────
    #
    # CryptoListener calls:
    #   paper_trader.record_signal(sig)      — written to CSV by queue_writer
    #   paper_trader.get_active_symbols()    — returns [] (no-op in this process)
    #   paper_trader.price_tick(sym, price)  — no-op
    #   paper_trader.candle_tick(sym, c,h,l) — no-op
    
    listener = CryptoListener(
        engine,
        dispatcher,
        audit_loop   = audit,
        paper_trader = queue_writer,
    )

    loop = asyncio.get_event_loop()
    _install_shutdown(loop, listener)

    logger.info("[signal_main] Starting Binance WebSocket listener...")
    try:
        await listener.start()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("[signal_main] Fatal error: %s", exc)
        raise
    finally:
        await listener.stop()
        logger.info("[signal_main] Signal pipeline stopped.")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
