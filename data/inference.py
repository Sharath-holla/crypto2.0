"""
Inference Engine — Phase D (Three-Layer Cascading Stack)

Architecture
────────────
  Layer 1 — Base Classifier   : LightGBM on 15m OHLCV + taker flow
                                 → P_base [p_short, p_hold, p_long]

  Layer 2 — Cap Calibrator    : shallow LightGBM on P_base + cap features
                                 → P_cal  [p_short, p_hold, p_long]

  Blending (Hold Bias fix):
      P_final = P_base × BLEND_BASE  +  P_cal × BLEND_CAL
      default: 0.70 / 0.30

  Layer 3 — MPE Regressor     : fires ONLY on confirmed signals
                                 → predicted max price excursion % (4-candle horizon)

Dynamic thresholds:
  Tier 0 Large  : signal ≥ 0.44 | strong ≥ 0.52
  Tier 1 Mid    : signal ≥ 0.42 | strong ≥ 0.50
  Tier 2 Small  : signal ≥ 0.38 | strong ≥ 0.46
  + adaptive delta from AuditLoop rolling precision feedback

Signal margin:
  P(winner) − P(loser) ≥ 0.03 to suppress borderline noise

Vol gate:
  vol_to_mcap ≥ min_vol_to_mcap[tier] to suppress thin-volume small-cap signals
"""

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pipeline.config_signal import (
    EXHAUSTION_THRESHOLD, 
    TIER_THRESHOLDS, 
    FLOW_VS_PEERS_LIMIT, 
    MODEL_PATH, 
    CAP_CALIBRATOR_PATH
)

logger = logging.getLogger(__name__)

# ── Blending weights ──────────────────────────────────────────────────────────
BLEND_BASE: float = 0.70
BLEND_CAL:  float = 0.30

# ── Dynamic per-tier thresholds (spec §II, lower than raw base thresholds) ────
# These operate on the BLENDED probability, which is recalibrated and smoother.
# tune after 2–4 weeks of audit log data.

# Margin: P(winner) − P(loser) must exceed this
_SIGNAL_MARGIN: float = 0.03

# Adaptive threshold clamps (audit loop cannot push thresholds out of these bounds)
_THRESHOLD_MIN: float = 0.48
_THRESHOLD_MAX: float = 0.58


class InferenceEngine:
    """
    Three-layer inference engine.

    Parameters
    ----------
    mpe_model_path : optional Path to the MPE regressor artifact
                     (models/mpe_regressor_15m.pkl)
    audit_loop     : optional AuditLoop instance; when supplied the engine
                     records every prediction for T+4 verification and reads
                     back adaptive threshold deltas.

    Usage
    -----
    engine = InferenceEngine()
    signal = engine.predict("BTCUSDT", candle_df, market_return)
    """

    def __init__(
        self,
        mpe_model_path: Optional[Path] = None,
        audit_loop=None,
    ):
        self._base_model:    object        = None
        self._base_scaler:   object        = None
        self._base_features: list[str]     = []
        self._cal_model:     object        = None
        self._cal_features:  list[str]     = []
        self._mpe_model:     object        = None
        self._mpe_features:  list[str]     = []
        self._audit_loop                   = audit_loop
        self._mpe_path                     = mpe_model_path

        self._load_models()

    # ══════════════════════════════════════════════════════════════════════════
    # Model loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_models(self):
        # ── Base model (required) ──────────────────────────────────────────
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"[engine] Base model not found: {MODEL_PATH}")
        with open(MODEL_PATH, "rb") as f:
            art = pickle.load(f)
        self._base_model    = art["model"]
        self._base_scaler   = art.get("scaler")            # may be None if unscaled
        self._base_features = art.get("feature_cols")
        logger.info(
            f"[engine] Base model loaded | "
            f"features={len(self._base_features)} | "
            f"scaler={'yes' if self._base_scaler else 'no'}"
        )

        # ── Cap calibrator (optional — degrades gracefully) ────────────────
        if CAP_CALIBRATOR_PATH and CAP_CALIBRATOR_PATH.exists():
            with open(CAP_CALIBRATOR_PATH, "rb") as f:
                art = pickle.load(f)
            self._cal_model    = art["model"]
            self._cal_features = art["features"]
            self._cal_type     = art.get("calibrator_type", "direction")
            logger.info(
                f"[engine] Cap calibrator loaded (Layer 2 active) | "
                f"type={self._cal_type}"
            )
        else:
            self._cal_type = None
            logger.warning(
                "[engine] Cap calibrator not found — "
                "running base model only (blend becomes 1.0/0.0)"
            )

        # ── MPE regressor (optional) ──────────────────────────────────────
        if self._mpe_path and self._mpe_path.exists():
            with open(self._mpe_path, "rb") as f:
                art = pickle.load(f)
            self._mpe_model    = art["model"]
            self._mpe_features = art["feature_cols"]
            logger.info("[engine] MPE regressor loaded (Layer 3 active)")
        else:
            logger.info("[engine] MPE regressor not found — Layer 3 disabled")

    # ══════════════════════════════════════════════════════════════════════════
    # Public interface
    # ══════════════════════════════════════════════════════════════════════════

    def predict(
        self,
        sym_key:           str,
        df:                pd.DataFrame,
        market_return:     float,
        cross_symbol_data: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Run full three-layer inference for one symbol at the latest closed candle.

        Parameters
        ----------
        sym_key           : normalised symbol, e.g. "BTCUSDT"
        df                : rolling candle buffer as DataFrame
                            (timestamp column is already datetime[UTC])
        market_return     : equal-weight mean of return_1 across all closed
                            symbols at this timestamp (computed by the gate)
        cross_symbol_data : optional dict:
                              "all_quote_volumes": {sym_key: float}
                              "all_net_taker":     {sym_key: float}
                            Used for vol_rank_pct and flow_vs_peers.
                            Falls back to neutral defaults when absent.

        Returns
        -------
        Signal dict (all fields required by AlertDispatcher) or None.
        None is returned when:
          - buffer is too short (< 120 rows)
          - signal == "hold"
          - vol gate fails
        """
        try:
            return self._predict_inner(sym_key, df, market_return, cross_symbol_data)
        except Exception as exc:
            logger.error(
                f"[engine] predict crashed for {sym_key}: {repr(exc)}",
                exc_info=True,
            )
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # Internal pipeline
    # ══════════════════════════════════════════════════════════════════════════

    def _predict_inner(
        self,
        sym_key:           str,
        df:                pd.DataFrame,
        market_return:     float,
        cross_symbol_data: Optional[dict],
    ) -> Optional[dict]:
        from phaseA.features import engineer_features
        from phaseA.market_cap import compute_cap_features

        if len(df) < 120:
            logger.debug(f"[engine] {sym_key}: buffer too short ({len(df)}), skipping")
            return None

        # ── 1. Feature engineering ─────────────────────────────────────────
        df = df.copy()
        df["symbol"] = sym_key
        # Inject pre-computed market_return (gate already aggregated it)
        df["market_return"] = market_return

        df_feat = engineer_features(df, "15m")
        if len(df_feat) < 2:
            return None
        last = df_feat.iloc[-1]
        ts   = last.get("timestamp", pd.Timestamp.utcnow())

        # ── 2. Layer 1: Base model ─────────────────────────────────────────
        X_row = {feat: last.get(feat, 0.0) for feat in self._base_features}
        X     = pd.DataFrame([X_row])[self._base_features].fillna(0.0)

        if self._base_scaler is not None:
            X_arr = pd.DataFrame(
                self._base_scaler.transform(X),
                columns=self._base_features,
            )
        else:
            X_arr = X[self._base_features]

        p_base = self._base_model.predict_proba(X_arr)[0]   # [p_short, p_hold, p_long]

        # ── 3. Cap features ────────────────────────────────────────────────
        quote_vol = float(last.get("quote_volume",    0.0))
        net_taker = float(last.get("net_taker_volume", 0.0))
        cvd_24    = float(last.get("cvd_24",           0.0))

        all_qvols  = {}
        all_ntaker = {}
        if cross_symbol_data:
            all_qvols  = dict(cross_symbol_data.get("all_quote_volumes", {}))
            all_ntaker = dict(cross_symbol_data.get("all_net_taker",     {}))
        all_qvols.setdefault( sym_key, quote_vol)
        all_ntaker.setdefault(sym_key, net_taker)

        cap_feats = compute_cap_features(
            symbol            = sym_key,
            quote_volume      = quote_vol,
            net_taker_volume  = net_taker,
            cvd_24            = cvd_24,
            all_quote_volumes = all_qvols,
            all_net_taker     = all_ntaker,
        )
        tier = cap_feats["cap_tier"]

        # ── 4. Layer 2: Cap calibrator ─────────────────────────────────────
        if self._cal_model is not None:
            cal_row = {
                "p_long":              float(p_base[2]),
                "p_short":             float(p_base[0]),
                "p_long_minus_short":  float(p_base[2] - p_base[0]),
                "cap_tier":            cap_feats["cap_tier"],
                "vol_to_mcap_ratio":   cap_feats["vol_to_mcap_ratio"],
                "flow_per_mcap":       cap_feats["flow_per_mcap"],
                "cvd_to_mcap":         cap_feats["cvd_to_mcap"],
                "vol_rank_pct":        cap_feats["vol_rank_pct"],
                "flow_vs_peers":       cap_feats["flow_vs_peers"],
            }
            X_cal = pd.DataFrame([cal_row])[self._cal_features].fillna(0.0)
            p_cal_raw = float(self._cal_model.predict_proba(X_cal)[0, 1])

            if self._cal_type == "quality":
                # Quality calibrator: p_cal_raw = P(base model is correct)
                # At 0.5 (uncertain) → no change. Above 0.5 → amplify winner.
                # Below 0.5 → dampen winner (push toward hold).
                # quality_delta ∈ [-BLEND_CAL, +BLEND_CAL]
                quality_delta = (p_cal_raw - 0.5) * 2.0 * BLEND_CAL

                p_final = p_base.copy()
                if p_base[2] >= p_base[0]:   # base model leans long
                    shift = quality_delta * (1.0 - p_base[2])  # how much room to move
                    p_final[2] = float(np.clip(p_base[2] + shift, 0.0, 0.99))
                    p_final[1] = float(np.clip(p_base[1] - abs(shift), 0.01, 1.0))
                else:                         # base model leans short
                    shift = quality_delta * (1.0 - p_base[0])
                    p_final[0] = float(np.clip(p_base[0] + shift, 0.0, 0.99))
                    p_final[1] = float(np.clip(p_base[1] - abs(shift), 0.01, 1.0))

                # p_cal is stored for audit/debug — reconstruct as 3-vector
                p_cal = p_base.copy()
                p_cal[2] = p_cal_raw        # store quality score in p_long slot
                p_cal[0] = 1.0 - p_cal_raw  # complement in p_short slot

            else:
                # Legacy direction calibrator: p_cal_raw = P(long)
                p_cal_long  = p_cal_raw
                p_cal_short = 1.0 - p_cal_long
                p_cal = np.array([p_cal_short, float(p_base[1]), p_cal_long], dtype=np.float32)

                # Blend directional components only; hold stays anchored
                p_final = p_base.copy()
                p_final[0] = p_base[0] * BLEND_BASE + p_cal[0] * BLEND_CAL
                p_final[2] = p_base[2] * BLEND_BASE + p_cal[2] * BLEND_CAL
        else:
            p_cal   = p_base.copy()
            p_final = p_base.copy()

        # Re-normalise after blending (floating-point sum ≈ 1.0 but clip)
        p_total = p_final.sum()
        if p_total > 0:
            p_final /= p_total

        p_short_f, p_hold_f, p_long_f = p_final[0], p_final[1], p_final[2]

        # ── 5. Resolve thresholds (static + adaptive delta) ────────────────
        thresholds    = self._resolve_thresholds(tier)
        sig_thresh    = thresholds["signal"]
        strong_thresh = thresholds["strong"]
        min_vtm       = thresholds["min_vol_to_mcap"]
        exhausted_thresh = thresholds.get("exhausted", EXHAUSTION_THRESHOLD)
        vol_to_mcap   = cap_feats["vol_to_mcap_ratio"]
        vol_ok        = vol_to_mcap >= min_vtm

# ── 6. Signal determination (Quant-Tuned Logic) ────────────────────
        long_margin  = p_long_f  - p_short_f
        short_margin = p_short_f - p_long_f

        # --- NEW: Extract flow and create the 0.3 gate ---
        flow_vs_peers = cap_feats["flow_vs_peers"]
        flow_ok       = flow_vs_peers > FLOW_VS_PEERS_LIMIT

        # # Scenario A: Exhaustion Pump (The Judo Flip)
        # if p_long_f >= exhausted_thresh and vol_ok and flow_ok:
        #     direction     = "short" # Fading the pump
        #     is_strong     = False   # Set to False so alerts.py triggers the 🥷 icon, not the 🔴🔴 icon
        #     precision_est = 0.55    # Assigned custom precision for fade trades
            
        # Scenario B: Standard Market Selling Pressure
        # Note: using sig_thresh here assuming it's synced to 0.53 in your config
        if p_short_f >= sig_thresh and short_margin >= _SIGNAL_MARGIN and vol_ok and flow_ok:
            direction     = "short"
            is_strong     = p_short_f >= strong_thresh
            precision_est = self._precision_from_tier(tier, is_strong, "short")
            
        # Scenario C: The Profitable Long Window (Floor to Ceiling)
        elif sig_thresh <= p_long_f <= strong_thresh and long_margin >= _SIGNAL_MARGIN and vol_ok and flow_ok:
            direction     = "long"
            is_strong     = False # By definition, profitable longs are low-momentum
            precision_est = self._precision_from_tier(tier, is_strong, "long")
            
        # Scenario D: The Noise / Deadzone
        else:
            direction     = "hold"
            is_strong     = False
            precision_est = 0.50

        # ── 7. Layer 3: MPE regressor (non-hold signals only) ──────────────
        mpe_target: Optional[float] = None
        if direction != "hold" and self._mpe_model is not None:
            # Pass p_base instead of p_final to prevent train-serve skew!
            mpe_target = self._predict_mpe(last, cap_feats, p_final)
            if mpe_target is not None and mpe_target < 0.30:
                logger.debug(f"[engine] {sym_key} MPE too low ({mpe_target:.2f}%), downgrading to HOLD")
                direction = "hold"
                is_strong = False

        # ── 8. Assemble signal dict ────────────────────────────────────────
        signal: dict = {
            # Core identity
            "symbol":         sym_key,
            "timestamp":      ts,
            # Signal classification
            "signal":         direction,
            "strong":         is_strong,
            # Blended probabilities (used by AlertDispatcher)
            "p_long":         float(p_long_f),
            "p_short":        float(p_short_f),
            "p_hold":         float(p_hold_f),
            # Raw layer outputs (for audit log analysis)
            "p_base_long":    float(p_base[2]),
            "p_base_short":   float(p_base[0]),
            "p_cal_long":     float(p_cal[2]),
            "p_cal_short":    float(p_cal[0]),
            # Precision estimate (historical calibration table)
            "precision_est":  precision_est,
            # Market context
            "market_return":  float(market_return),
            # Cap features (AlertDispatcher uses these for message formatting)
            "cap_tier":       cap_feats["cap_tier"],
            "cap_tier_name":  cap_feats["cap_tier_name"],
            "vol_to_mcap":    float(vol_to_mcap),
            "flow_vs_peers":  float(cap_feats["flow_vs_peers"]),
            # Layer 3 output
            "mpe_target":     mpe_target,
            # Close price at signal time (needed by audit loop for T+4 check)
            "close":          float(last.get("close", 0.0)),
        }

        # Register with audit loop for T+4 ground-truth verification
        if self._audit_loop is not None and direction != "hold":
            self._audit_loop.record_prediction(signal)

        logger.debug(
            f"[engine] {sym_key} | {direction.upper()} {'★' if is_strong else ''} | "
            f"p_long={p_long_f:.3f} p_short={p_short_f:.3f} | "
            f"tier={cap_feats['cap_tier_name']} | vtm={vol_to_mcap:.4f} | "
            f"mpe={f'{mpe_target:.2f}%' if mpe_target else 'n/a'}"
        )
        return signal

    # ══════════════════════════════════════════════════════════════════════════
    # Layer 3: MPE inference
    # ══════════════════════════════════════════════════════════════════════════

    def _predict_mpe(
        self,
        last_row: dict | pd.Series,
        cap_feats: dict,
        p_final: np.ndarray,
    ) -> Optional[float]:
        """
        Predict max price excursion % over the next 4 candles.
        Returns None if prediction fails (non-fatal — signal is still dispatched).
        """
        try:
            mpe_row: dict = {}
            for feat in self._mpe_features:
                if feat == "p_short":
                    mpe_row[feat] = float(p_final[0])
                elif feat == "p_hold":
                    mpe_row[feat] = float(p_final[1])
                elif feat == "p_long":
                    mpe_row[feat] = float(p_final[2])
                elif feat in cap_feats:
                    mpe_row[feat] = cap_feats[feat]
                else:
                    mpe_row[feat] = float(last_row.get(feat, 0.0))

            X_mpe = pd.DataFrame([mpe_row], columns=self._mpe_features).fillna(0.0)
            return float(self._mpe_model.predict(X_mpe)[0])
        except Exception as exc:
            logger.debug(f"[engine] MPE prediction failed: {exc}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # Threshold resolution
    # ══════════════════════════════════════════════════════════════════════════

    def _resolve_thresholds(self, tier: int) -> dict:
        """
        Merge static per-tier defaults with the adaptive delta from AuditLoop.

        The adaptive delta is a single signed float that shifts all thresholds
        uniformly. Clamped to prevent runaway feedback, with special bounds
        for the Extreme Exhaustion fade.
        """
        base = TIER_THRESHOLDS.get(tier, TIER_THRESHOLDS[1]).copy()

        if self._audit_loop is not None:
            delta = self._audit_loop.get_threshold_delta()
            
            # 1. Shift the FLOOR of the Long window (Standard Signal)
            base["signal"] = float(
                np.clip(base["signal"] + delta, _THRESHOLD_MIN, _THRESHOLD_MAX)
            )
            
            # 2. Shift the CEILING of the Long window (Strong Signal)
            # Ensure it always stays at least slightly above the signal floor
            base["strong"] = float(
                np.clip(base["strong"] + delta, base["signal"] + 0.02, _THRESHOLD_MAX)
            )
            
            # 3. Shift the EXHAUSTION trigger (The Judo Flip)
            # Given a higher clip range so it doesn't get crushed by _THRESHOLD_MAX
            if "exhausted" in base:
                base["exhausted"] = float(
                    np.clip(base["exhausted"] + delta, 0.60, 0.85) 
                )
                
        return base

    # ══════════════════════════════════════════════════════════════════════════
    # Precision estimation table
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _precision_from_tier(tier: int, strong: bool, direction: str) -> float:
        """
        Historical precision estimates from the 600k Out-of-Sample Backtest.
        Used as a display estimate in alerts; NOT used for threshold gating.
        """
        _TABLE = {
            # LONG STRATEGY (Low Momentum Trend Continuation)
            # Actual out-of-sample win rate: 53.3%
            (0, False, "long"):  0.533,
            (0, True,  "long"):  0.533, # We don't execute strong longs anymore, but safely default
            (1, False, "long"):  0.533,
            (1, True,  "long"):  0.533,
            (2, False, "long"):  0.533,
            (2, True,  "long"):  0.533,
            
            # SHORT STRATEGY (Standard Market Selling Pressure)
            # Actual out-of-sample win rate: 43.1% (Profitable with 2:1 R:R)
            (0, False, "short"): 0.431,
            (0, True,  "short"): 0.431,
            (1, False, "short"): 0.431,
            (1, True,  "short"): 0.431,
            (2, False, "short"): 0.431,
            (2, True,  "short"): 0.431,
            
            # NOTE: The "Fade Exhaustion" Short (EXTREME_THRESHOLD) is handled 
            # dynamically in Step 6 of predict_inner and overrides this table.
        }
        return _TABLE.get((tier, strong, direction), 0.50)