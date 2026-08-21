"""
Alert Dispatcher — Phase C
Sends signal alerts to Telegram and/or Discord.

Features:
  - Per-symbol cooldown (ALERT_COOLDOWN_S) — no alert spam
  - Two tiers: regular signal and strong signal (different emoji + formatting)
  - Async HTTP via aiohttp — never blocks the WebSocket event loop
  - Graceful degradation: if Telegram fails, tries Discord, logs either way
  - Persistent signal log to logs/signals.log (CSV — importable into Excel)
"""

import asyncio
import csv
import logging
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta, timezone

import aiohttp

from pipeline.config_signal import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    DISCORD_WEBHOOK,
    ALERT_COOLDOWN_S,
    SIGNAL_LOG_PATH,
    EXHAUSTION_THRESHOLD
)

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Async alert dispatcher with per-symbol cooldown tracking.

    Usage
    -----
    dispatcher = AlertDispatcher()
    await dispatcher.send(signal_dict)

    signal_dict keys:  symbol, timestamp, p_long, p_short, p_hold,
                       signal, strong, precision_est
    """

    def __init__(self):
        self._last_alert: dict[str, float] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._tg_lock = asyncio.Lock()
        self._discord_lock = asyncio.Lock()
        self._init_signal_log()

    def _init_signal_log(self):
        """Create CSV signal log with header if it doesn't exist."""
        if not SIGNAL_LOG_PATH.exists():
            with open(SIGNAL_LOG_PATH, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp_utc", "symbol", "signal", "strong",
                    "p_long", "p_hold", "p_short", "precision_est",
                    "market_return", "cap_tier", "cap_tier_name",
                    "vol_to_mcap", "flow_vs_peers","mpe_target", "alerted"
                ])
            logger.info(f"[alerts] Signal log created → {SIGNAL_LOG_PATH}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Cooldown check ─────────────────────────────────────────────────────────

    def _is_cooled_down(self, symbol: str) -> bool:
        last = self._last_alert.get(symbol, {"ts": 0})
        # Handle dict format stored in File 1 vs raw timestamp edge cases
        last_ts = last["ts"] if isinstance(last, dict) else last
        return (time.time() - last_ts) >= ALERT_COOLDOWN_S

    def _mark_alerted(self, symbol: str, direction: str, strong: bool):
        self._last_alert[symbol] = {
            "ts": time.time(),
            "direction": direction,
            "was_strong": strong
        }

    # ── Main entry point ───────────────────────────────────────────────────────

    async def send(self, sig: dict) -> bool:
        """
        Evaluate a signal dict and send alerts if conditions are met.

        Returns True if an alert was dispatched, False if suppressed.
        """
        symbol    = sig["symbol"]
        direction = sig["signal"]
        is_strong = sig["strong"]

        # Only alert on actionable directions
        if direction == "hold":
            # self._log_signal(sig, alerted=False)
            return False

        last = self._last_alert.get(symbol, {"ts": 0, "direction": None, "was_strong": False})
        dir_changed = (direction != last["direction"])
        is_upgrade  = (is_strong and not last["was_strong"])
        is_cooled   = (time.time() - last["ts"]) >= ALERT_COOLDOWN_S

        if dir_changed or is_upgrade or is_cooled:
            msg = self._build_message(sig)
        else:
            # Prevent spam if conditions aren't met
            self._log_signal(sig, alerted=False)
            return False

        # Dispatch concurrently to both channels
        tasks = []
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            tasks.append(self._send_telegram(msg))
        if DISCORD_WEBHOOK:
            tasks.append(self._send_discord(msg, sig))

        if not tasks:
            logger.warning(
                "[alerts] No alert channels configured. "
            )
            self._log_signal(sig, alerted=False)
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = any(r is True for r in results)

        if success:
            self._mark_alerted(symbol, direction, is_strong)
            logger.info(f"[alerts] SENT | {symbol} | {direction.upper()}")

        self._log_signal(sig, alerted=success)
        return success

    # ── Message formatting ─────────────────────────────────────────────────────

    def _build_message(self, sig: dict) -> str:
        direction = sig["signal"]
        strong    = sig["strong"]
        p_long    = sig["p_long"]
        symbol_clean = sig["symbol"].replace("USDT", "/USDT").replace(":USDT", "")

        # Emoji & Label tier with Quant-Tuned Logic
        if direction == "long":
            icon  = "🟢🟢" if strong else "🟢"
            label = "STRONG LONG" if strong else "LONG"
        else: # direction == "short"
            if p_long >= EXHAUSTION_THRESHOLD:
                icon  = "🥷📉"  # Ninja / Contarian trade
                label = "FADE EXHAUSTION (SHORT)"
            else:
                icon  = "🔴🔴" if strong else "🔴"
                label = "STRONG SHORT" if strong else "SHORT"

        try:
            dt_utc = datetime.fromisoformat(str(sig["timestamp"])).replace(tzinfo=timezone.utc)
            dt_ist = dt_utc + timedelta(hours=5, minutes=30)
            utc_str, ist_str = dt_utc.strftime("%Y-%m-%d %H:%M"), dt_ist.strftime("%Y-%m-%d %H:%M")
        except:
            utc_str = ist_str = "N/A"

        cap_label   = sig.get("cap_tier_name", "").upper()
        vol_to_mcap = sig.get("vol_to_mcap")
        flow_peers  = sig.get("flow_vs_peers")
        mpe_target  = sig.get("mpe_target")
        current_price = sig.get("close")


        raw_vol     = sig.get("quote_volume") 
        if raw_vol:
            vol_m  = raw_vol / 1_000_000
            vol_cr = raw_vol / 10_000_000
            raw_vol_line = f"💵 15m Volume = `${vol_m:.2f}M` | `${vol_cr:.2f} Cr`"
        else:
            raw_vol_line = ""
        
        cap_line    = f"📦 Cap tier = `{cap_label}`" if cap_label else ""
        vtm_line    = f"💰 Vol/MCap = `{vol_to_mcap:.6f}`" if vol_to_mcap is not None else ""
        fvp_line    = f"🌊 Flow vs peers = `{flow_peers:.2f}×`" if flow_peers is not None else ""
        mpe_line    = f"🎯 Est. Target = `+{mpe_target:.2f}%`" if mpe_target is not None else ""

        if mpe_target is not None and current_price:
            # Longs go UP, Shorts go DOWN
            if direction == "long":
                target_price = current_price * (1 + (mpe_target / 100))
            elif direction == "short":
                target_price = current_price * (1 - (mpe_target / 100))
            else:
                target_price = current_price

            # Smart formatting: Use more decimals for cheap coins
            if target_price < 1:
                price_str = f"${target_price:.6f}"
            elif target_price < 40:
                price_str = f"${target_price:.4f}"
            else:
                price_str = f"${target_price:.2f}"
                
            mpe_line = f"🎯 Est. Target = `{price_str}` (+{mpe_target:.2f}%)"

        lines = [
            f"{icon} *{label}* — {symbol_clean}",
            f"",
            f"📅 `UTC: {utc_str}`",
            f"🇮🇳 `IST: {ist_str}`",
            f"📊 P(long)  = `{sig['p_long']:.3f}`",
            f"📊 P(short) = `{sig['p_short']:.3f}`",
            f"📊 P(hold)  = `{sig['p_hold']:.3f}`",
            f"⚡ Est. precision = `{sig['precision_est']:.1%}`", # Changed emoji to ⚡ to avoid clash
            f"",
        ]
        
        for extra in [cap_line, vtm_line, raw_vol_line, fvp_line, mpe_line]: 
            if extra:
                lines.append(extra)
                
        lines += [
            f"",
            f"⚡ 15m model | threshold={'strong' if strong else 'standard'}",
        ]
        return "\n".join(lines)

    # ── Telegram ───────────────────────────────────────────────────────────────

    async def _send_telegram(self, message: str) -> bool:
        async with self._tg_lock: # Ensures only 1 message processes at a time
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id":    TELEGRAM_CHAT_ID,
                "text":       message,
                "parse_mode": "Markdown",
            }
            try:
                session = await self._get_session()
                # 1. Open connection, send data, and grab the response
                async with session.post(url, json=payload) as resp:
                    status = resp.status
                    if status != 200:
                        body = await resp.text()
                
                # 2. Connection is now closed. Safe to sleep and enforce the rate limit.
                await asyncio.sleep(1.1)
                
                # 3. Evaluate the result
                if status == 200:
                    return True
                    
                logger.warning(f"[alerts] Telegram error {status}: {body[:200]}")
                return False
                
            except Exception as e:
                logger.warning(f"[alerts] Telegram exception: {e}")
                # Still sleep on failure so a broken network doesn't cause an infinite spam loop
                await asyncio.sleep(1.1) 
                return False

    # ── Discord ────────────────────────────────────────────────────────────────

    async def _send_discord(self, message: str, sig: dict) -> bool:
        async with self._discord_lock:  # <--- Added lock to prevent Discord 429 spam
            direction = sig["signal"]
            strong    = sig["strong"]
            p_long    = sig["p_long"]
            
            # --- Updated Color & Title Logic for Extreme Fades ---
            if direction == "long":
                color = 0x085041 if strong else 0x1D9E75
                title_prefix = "STRONG LONG" if strong else "LONG"
            else: # direction == "short"
                if p_long >= EXHAUSTION_THRESHOLD:
                    color = 0x992DDB # Purple for unusual contrarian trades
                    title_prefix = "🥷 FADE EXHAUSTION (SHORT)"
                else:
                    color = 0x712B13 if strong else 0xD85A30
                    title_prefix = "STRONG SHORT" if strong else "SHORT"

            current_price = sig.get("close")
            mpe_target  = sig.get("mpe_target")

            if direction == "long":
                target_price = current_price * (1 + (mpe_target / 100))
            elif direction == "short":
                target_price = current_price * (1 - (mpe_target / 100))
            else:
                target_price = current_price
            
            if target_price < 1:
                price_str = f"${target_price:.6f}"
            elif target_price < 40:
                price_str = f"${target_price:.4f}"
            else:
                price_str = f"${target_price:.2f}"

            symbol_clean = sig["symbol"].replace(":USDT", "")
            ts_str = str(sig["timestamp"])[:16] if sig["timestamp"] else "N/A"


            embed = {
                "title":       f"{title_prefix} — {symbol_clean}",
                "color":       color,
                "description": f"15m signal | `{ts_str} UTC`",
                "fields": [
                    {"name": "P(long)",         "value": f"`{sig['p_long']:.3f}`",       "inline": True},
                    {"name": "P(short)",        "value": f"`{sig['p_short']:.3f}`",      "inline": True},
                    {"name": "P(hold)",         "value": f"`{sig['p_hold']:.3f}`",       "inline": True},
                    {"name": "Est. precision",  "value": f"`{sig['precision_est']:.1%}`","inline": True},
                    {"name": "Cap tier",        "value": sig.get("cap_tier_name","N/A").upper(), "inline": True},
                    {"name": "Vol/MCap",        "value": f"`{sig['vol_to_mcap']:.4f}`" if sig.get("vol_to_mcap") is not None else "N/A", "inline": True},
                    {"name": "Flow vs peers",   "value": f"`{sig['flow_vs_peers']:.2f}×`" if sig.get("flow_vs_peers") is not None else "N/A", "inline": True},
                    {"name": "Est. Target",     "value": f"`+{sig['mpe_target']:.2f}%`" if sig.get("mpe_target") is not None else "N/A", "inline": True},
                    {"name": "🎯 Take Profit", "value": f"`{price_str}`" if current_price else f"`+{sig['mpe_target']:.2f}%`", "inline": True},
                    {"name": "15m Volume", "value": f"`${sig.get('quote_volume', 0) / 1_000_000:.2f}M` (`{sig.get('quote_volume', 0) / 10_000_000:.2f} Cr`)", "inline": True},
                    {"name": "Threshold tier",  "value": "strong" if strong else "standard", "inline": True},
                ],
                "footer": {"text": "Crypto Futures Signal Bot | Phase B/C/D"},
            }            
            payload = {"embeds": [embed]}
            
            try:
                session = await self._get_session()
                # 1. Open connection, send data, grab status
                async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
                    status = resp.status
                    if status not in (200, 204):
                        body = await resp.text()

                # 2. Connection is closed. Safe to sleep 0.5s to respect Discord limits.
                await asyncio.sleep(0.5)

                # 3. Evaluate the result
                if status in (200, 204):
                    return True
                    
                logger.warning(f"[alerts] Discord error {status}: {body[:200]}")
                return False
                
            except Exception as e:
                logger.warning(f"[alerts] Discord exception: {e}")
                await asyncio.sleep(0.5)  # Always sleep on failure to prevent error loops
                return False

    # ── Signal log ─────────────────────────────────────────────────────────────

    def _log_signal(self, sig: dict, alerted: bool):
        """Append signal to persistent CSV log regardless of alert outcome."""
        try:
            with open(SIGNAL_LOG_PATH, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    str(sig.get("timestamp", ""))[:19],
                    sig.get("symbol", ""),
                    sig.get("signal", ""),
                    sig.get("strong", False),
                    sig.get("p_long", ""),
                    sig.get("p_hold", ""),
                    sig.get("p_short", ""),
                    sig.get("precision_est", ""),
                    sig.get("market_return", ""),
                    sig.get("cap_tier", ""),
                    sig.get("cap_tier_name", ""),
                    sig.get("vol_to_mcap", ""),
                    sig.get("flow_vs_peers", ""),
                    sig.get("mpe_target", ""),
                    alerted,
                ])
        except Exception as e:
            logger.warning(f"[alerts] Failed to write signal log: {e}")