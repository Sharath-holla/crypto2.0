"""
Audit Loop — Phase D Self-Correction Mechanism

Implements the three-part verification and feedback system:

  1. Prediction Recording
     On every non-hold signal, write one row to signals_audit.csv:
       sig_id, timestamp, symbol, signal, close_at_signal, predicted_mpe,
       p_long, p_short, cap_tier, verified=False
     (actual columns left blank — filled in at T+4)

  2. T+4 Ground-Truth Verification
     The listener calls audit_loop.tick(symbol, close) on every candle close.
     When a signal is 4 candles old, the audit loop fills in:
       actual_high_4c, actual_low_4c, actual_mpe,
       hit (bool) — did price reach ≥ 75% of predicted MPE?
       precision_contribution (1 if correct direction, else 0)
     verified=True is set and the row is updated in the CSV.

  3. Adaptive Threshold Feedback
     After verifying each signal, the rolling precision over the last
     PRECISION_WINDOW verified signals is re-computed.
     The threshold delta (get_threshold_delta()) maps precision to an
     adjustment signal that the InferenceEngine applies:

       precision > 0.62  →  delta = −0.03  (aggressive: lower threshold, capture more alpha)
       precision > 0.55  →  delta = −0.015
       0.48 – 0.55       →  delta =  0.0   (neutral, on-target)
       precision < 0.48  →  delta = +0.02  (defensive)
       precision < 0.40  →  delta = +0.04  (very defensive)

  4. Feature Correlation Report (run on-demand or weekly)
     correlate_features() computes Spearman rank correlation between each
     input feature in the audit log and the binary hit outcome.
     This identifies which features are most predictive in the current regime.

Audit CSV columns
─────────────────
  sig_id              : UUID for each signal
  timestamp           : UTC ISO timestamp of the signal candle
  symbol              : e.g. "BTCUSDT"
  signal              : "long" | "short"
  strong              : bool
  close_at_signal     : close price at signal time
  predicted_mpe       : predicted max excursion % (from Layer 3, or NaN)
  p_long              : blended P(long)
  p_short             : blended P(short)
  p_base_long         : raw base model P(long) — for layer attribution analysis
  cap_tier            : 0/1/2
  cap_tier_name       : "large-cap" / "mid-cap" / "small-cap"
  vol_to_mcap         : vol_to_mcap_ratio at signal time
  flow_vs_peers       : flow_vs_peers at signal time
  verified            : False → True when T+4 closes
  actual_high_4c      : highest close in the 4 candles after signal
  actual_low_4c       : lowest close in the 4 candles after signal
  actual_mpe          : realized max excursion % (same sign convention as predicted)
  hit                 : bool — did actual_mpe >= 0.75 × predicted_mpe?
  precision_correct   : bool — was the direction correct? (long: high > entry, short: low < entry)
  candles_elapsed     : counter used internally; not meaningful after verification
"""

import csv
import logging
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.config_signal import (LOG_DIR)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
PRECISION_WINDOW = 50    # rolling window for precision calculation
VERIFICATION_DELAY = 4   # candles before T+4 check fires
HIT_RATIO = 0.75         # fraction of predicted MPE that counts as a "hit"

# Minimum verified signals before the adaptive delta is trusted
MIN_VERIFIED_FOR_ADAPTATION = 20

# Adaptive delta schedule (precision → threshold shift)
# These are piecewise-constant; chosen conservatively to avoid overcorrection.
_DELTA_SCHEDULE = [
    (0.62, -0.030),   # precision > 0.62 → aggressive
    (0.55, -0.015),   # precision 0.55–0.62 → mildly aggressive
    (0.48,  0.000),   # precision 0.48–0.55 → neutral
    (0.40,  0.020),   # precision 0.40–0.48 → defensive
    (0.00,  0.040),   # precision < 0.40 → very defensive
]

_AUDIT_HEADER = [
    "sig_id", "timestamp", "symbol", "signal", "strong",
    "close_at_signal", "predicted_mpe",
    "p_long", "p_short", "p_base_long",
    "cap_tier", "cap_tier_name", "vol_to_mcap", "flow_vs_peers",
    "verified",
    "actual_high_4c", "actual_low_4c", "actual_mpe",
    "hit", "precision_correct", "candles_elapsed",
]


class AuditLoop:
    """
    Persistent signal audit loop with T+4 verification and adaptive feedback.

    Parameters
    ----------
    audit_path : Path to signals_audit.csv
                 Default: LOG_DIR / "signals_audit.csv"

    Usage
    -----
    audit = AuditLoop()
    # Called by InferenceEngine after each non-hold signal:
    audit.record_prediction(signal_dict)
    # Called by the listener on every candle close, for every symbol:
    audit.tick(sym_key, close, high, low)
    # Called by InferenceEngine to get adaptive threshold adjustment:
    delta = audit.get_threshold_delta()
    """

    def __init__(self, audit_path: Optional[Path] = None):
        self._path = audit_path or (LOG_DIR / "signals_audit.csv")
        self._init_csv()

        # In-memory pending signals: sig_id → row dict with mutable candles_elapsed
        # We track all unverified signals here.
        self._pending: dict[str, dict] = {}

        # Per-symbol buffer for T+4 price tracking:
        # sym_key → deque of (close, high, low) tuples, newest last
        self._price_buf: dict[str, deque] = defaultdict(lambda: deque(maxlen=VERIFICATION_DELAY + 2))

        # Signals waiting for T+4 closes per symbol:
        # sym_key → [sig_id, ...]  (oldest first)
        self._waiting: dict[str, list] = defaultdict(list)

        # Rolling precision (deque of 1/0 for last PRECISION_WINDOW verified signals)
        self._precision_buf: deque = deque(maxlen=PRECISION_WINDOW)
        self._n_verified: int = 0

        # Adaptive delta (cached; recomputed after each verification)
        self._threshold_delta: float = 0.0

        # Reload unverified rows from disk on startup
        self._reload_pending()

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    def record_prediction(self, sig: dict) -> str:
        """
        Write a new signal to the audit CSV and register it for T+4 verification.
        Returns the sig_id assigned to this prediction.
        """
        sig_id = str(uuid.uuid4())[:12]
        row = {
            "sig_id":          sig_id,
            "timestamp":       str(sig.get("timestamp", ""))[:19],
            "symbol":          sig.get("symbol", ""),
            "signal":          sig.get("signal", ""),
            "strong":          sig.get("strong", False),
            "close_at_signal": sig.get("close", ""),
            "predicted_mpe":   sig.get("mpe_target", ""),
            "p_long":          sig.get("p_long", ""),
            "p_short":         sig.get("p_short", ""),
            "p_base_long":     sig.get("p_base_long", ""),
            "cap_tier":        sig.get("cap_tier", ""),
            "cap_tier_name":   sig.get("cap_tier_name", ""),
            "vol_to_mcap":     sig.get("vol_to_mcap", ""),
            "flow_vs_peers":   sig.get("flow_vs_peers", ""),
            "verified":        False,
            "actual_high_4c":  "",
            "actual_low_4c":   "",
            "actual_mpe":      "",
            "hit":             "",
            "precision_correct": "",
            "candles_elapsed": 0,
        }
        self._append_row(row)
        self._pending[sig_id] = row
        sym = row["symbol"]
        self._waiting[sym].append(sig_id)
        logger.debug(f"[audit] Recorded | {sym} | {row['signal']} | id={sig_id}")
        return sig_id

    def tick(self, sym_key: str, close: float, high: float, low: float) -> None:
        """
        Called on every candle close for a symbol.
        Updates price buffer and increments elapsed counter for pending signals.
        Triggers verification when VERIFICATION_DELAY candles have elapsed.
        """
        self._price_buf[sym_key].append((close, high, low))

        pending_ids = self._waiting.get(sym_key, [])
        verified_ids = []

        for sig_id in list(pending_ids):
            row = self._pending.get(sig_id)
            if row is None:
                verified_ids.append(sig_id)
                continue
            row["candles_elapsed"] = int(row.get("candles_elapsed", 0)) + 1
            if row["candles_elapsed"] >= VERIFICATION_DELAY:
                self._verify(sig_id, row)
                verified_ids.append(sig_id)

        for sig_id in verified_ids:
            if sig_id in pending_ids:
                pending_ids.remove(sig_id)

    def get_threshold_delta(self) -> float:
        """
        Return the current adaptive threshold adjustment.
        InferenceEngine adds this to the static per-tier thresholds.
        Returns 0.0 until MIN_VERIFIED_FOR_ADAPTATION signals are verified.
        """
        return self._threshold_delta

    def get_rolling_precision(self) -> Optional[float]:
        """Return rolling precision over last PRECISION_WINDOW verified signals."""
        if len(self._precision_buf) < 5:
            return None
        return float(np.mean(list(self._precision_buf)))

    # ══════════════════════════════════════════════════════════════════════════
    # T+4 verification
    # ══════════════════════════════════════════════════════════════════════════

    def _verify(self, sig_id: str, row: dict) -> None:
        """
        Fill in ground truth for a pending signal using the accumulated price buffer.
        """
        sym           = row["symbol"]
        signal        = row["signal"]
        close_entry   = float(row.get("close_at_signal") or 0)
        predicted_mpe = row.get("predicted_mpe")

        price_history = list(self._price_buf[sym])

        if len(price_history) < VERIFICATION_DELAY:
            logger.debug(f"[audit] {sig_id}: price buffer too short, skipping")
            return

        # Use the last VERIFICATION_DELAY closes/highs/lows
        recent = price_history[-VERIFICATION_DELAY:]
        closes = [c for c, h, l in recent]
        highs  = [h for c, h, l in recent]
        lows   = [l for c, h, l in recent]

        actual_high = max(highs) if highs else (close_entry or 0)
        actual_low  = min(lows)  if lows  else (close_entry or 0)

        # Compute actual MPE
        actual_mpe = None
        precision_correct = False
        if close_entry and close_entry > 0:
            if signal == "long":
                actual_mpe        = (actual_high / close_entry - 1.0) * 100.0
                precision_correct = actual_high > close_entry
            elif signal == "short":
                actual_mpe        = (close_entry / actual_low - 1.0) * 100.0 if actual_low > 0 else 0.0
                precision_correct = actual_low < close_entry

        # Hit: actual_mpe reached at least HIT_RATIO × predicted_mpe
        hit = False
        if (
            predicted_mpe not in ("", None)
            and actual_mpe is not None
        ):
            try:
                hit = float(actual_mpe) >= HIT_RATIO * float(predicted_mpe)
            except (ValueError, TypeError):
                hit = False
        elif actual_mpe is not None:
            # No MPE prediction — use direction correctness as hit proxy
            hit = precision_correct

        # Update row in-memory
        row.update({
            "verified":        True,
            "actual_high_4c":  round(actual_high, 6),
            "actual_low_4c":   round(actual_low,  6),
            "actual_mpe":      round(actual_mpe, 4) if actual_mpe is not None else "",
            "hit":             hit,
            "precision_correct": precision_correct,
        })

        # Rewrite to CSV
        self._update_csv_row(sig_id, row)

        # Update rolling precision
        self._precision_buf.append(1 if precision_correct else 0)
        self._n_verified += 1

        # Recompute adaptive delta
        self._recompute_delta()

        # Remove from pending
        self._pending.pop(sig_id, None)

        logger.info(
            f"[audit] VERIFIED | {sym} {signal.upper()} | "
            f"entry={close_entry:.4f} | high={actual_high:.4f} low={actual_low:.4f} | "
            f"mpe_pred={predicted_mpe or 'n/a'} actual={actual_mpe:.2f}% | "
            f"hit={hit} correct={precision_correct} | "
            f"rolling_precision={self.get_rolling_precision():.3f}"
            if self.get_rolling_precision() is not None else
            f"[audit] VERIFIED | {sym} {signal.upper()} | correct={precision_correct}"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Adaptive feedback
    # ══════════════════════════════════════════════════════════════════════════

    def _recompute_delta(self) -> None:
        """
        Map rolling precision → threshold delta using the piecewise schedule.
        Only activates after MIN_VERIFIED_FOR_ADAPTATION verified signals.
        """
        if self._n_verified < MIN_VERIFIED_FOR_ADAPTATION:
            return

        precision = self.get_rolling_precision()
        if precision is None:
            return

        delta = 0.0
        for threshold, shift in _DELTA_SCHEDULE:
            if precision >= threshold:
                delta = shift
                break

        if abs(delta - self._threshold_delta) >= 0.005:
            logger.info(
                f"[audit] Adaptive threshold delta: "
                f"{self._threshold_delta:+.3f} → {delta:+.3f} "
                f"(rolling_precision={precision:.3f} over last {len(self._precision_buf)} signals)"
            )
        self._threshold_delta = delta

    # ══════════════════════════════════════════════════════════════════════════
    # Feature correlation analysis (weekly / on-demand)
    # ══════════════════════════════════════════════════════════════════════════

    def correlate_features(self) -> Optional[pd.DataFrame]:
        """
        Compute Spearman rank correlation between numeric audit columns and
        precision_correct outcome.  Identifies which features are most
        predictive in the current regime.

        Returns a sorted DataFrame or None if insufficient verified rows.
        """
        df = self._load_audit_df()
        verified = df[df["verified"] == True]

        if len(verified) < MIN_VERIFIED_FOR_ADAPTATION:
            logger.info(
                f"[audit] Insufficient verified rows for correlation "
                f"({len(verified)} < {MIN_VERIFIED_FOR_ADAPTATION})"
            )
            return None

        numeric_cols = [
            "p_long", "p_short", "p_base_long",
            "vol_to_mcap", "flow_vs_peers",
            "cap_tier", "predicted_mpe", "actual_mpe",
        ]
        available = [c for c in numeric_cols if c in verified.columns]
        target    = pd.to_numeric(verified["precision_correct"], errors="coerce")

        rows = []
        for col in available:
            series = pd.to_numeric(verified[col], errors="coerce")
            valid  = series.notna() & target.notna()
            if valid.sum() < 10:
                continue
            corr = series[valid].corr(target[valid], method="spearman")
            rows.append({"feature": col, "spearman_corr": round(corr, 4), "n": valid.sum()})

        if not rows:
            return None

        result = (
            pd.DataFrame(rows)
            .sort_values("spearman_corr", key=abs, ascending=False)
            .reset_index(drop=True)
        )
        out_path = LOG_DIR / "audit_feature_correlation.csv"
        result.to_csv(out_path, index=False)
        logger.info(f"[audit] Feature correlation saved → {out_path}")
        logger.info(f"\n{result.to_string(index=False)}")
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # CSV helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _init_csv(self):
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_AUDIT_HEADER)
                writer.writeheader()
            logger.info(f"[audit] Audit log created → {self._path}")

    def _append_row(self, row: dict):
        with open(self._path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_AUDIT_HEADER, extrasaction="ignore")
            writer.writerow(row)

    def _update_csv_row(self, sig_id: str, row: dict):
        """
        Rewrite the CSV with the verified row updated in-place.
        Efficient for small logs (<50k rows); for larger logs, switch to SQLite.
        """
        try:
            df = self._load_audit_df()
            mask = df["sig_id"] == sig_id
            if not mask.any():
                # sig_id not found — append as new (handles restart edge case)
                self._append_row(row)
                return

            for key, val in row.items():
                if key in df.columns:
                    df.loc[mask, key] = val

            df.to_csv(self._path, index=False)
        except Exception as exc:
            logger.warning(f"[audit] CSV update failed for {sig_id}: {exc}")
            # Fallback: append a corrected row rather than lose the verification
            self._append_row({**row, "sig_id": sig_id + "_v"})

    def _load_audit_df(self) -> pd.DataFrame:
        try:
            return pd.read_csv(self._path, dtype=str)
        except Exception:
            return pd.DataFrame(columns=_AUDIT_HEADER)

    def _reload_pending(self):
        """
        On startup, reload unverified rows from disk into _pending and _waiting.
        Allows the audit loop to survive process restarts mid-session.
        """
        df = self._load_audit_df()
        unverified = df[df["verified"].isin(["False", "false", "0", ""])]
        for _, row in unverified.iterrows():
            row_dict = row.to_dict()
            sig_id   = row_dict.get("sig_id", "")
            sym      = row_dict.get("symbol", "")
            if sig_id and sym:
                row_dict["candles_elapsed"] = int(row_dict.get("candles_elapsed") or 0)
                self._pending[sig_id]       = row_dict
                self._waiting[sym].append(sig_id)

        # Reload rolling precision from verified rows
        verified = df[df["verified"].isin(["True", "true", "1"])]
        recent   = verified.tail(PRECISION_WINDOW)
        for _, row in recent.iterrows():
            pc = row.get("precision_correct", "")
            if pc in ("True", "true", "1"):
                self._precision_buf.append(1)
            elif pc in ("False", "false", "0"):
                self._precision_buf.append(0)
        self._n_verified   = len(verified)
        self._recompute_delta()

        if self._pending:
            logger.info(
                f"[audit] Reloaded {len(self._pending)} unverified signals from disk"
            )
