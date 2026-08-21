"""
inference_dl.py — DLInferenceEngine (drop-in replacement for InferenceEngine)
══════════════════════════════════════════════════════════════════════════════
Public interface is IDENTICAL to inference.py's InferenceEngine:

    engine = DLInferenceEngine()
    signal = engine.predict(sym_key, df, market_return, cross_symbol_data)

No changes needed in listener.py, main_signal.py, or anywhere else.

Internal pipeline per candle close:
  1. Run engineer_features_extended() on the rolling buffer
  2. Extract the last seq_len rows as the input window
  3. Per-window z-score + recency decay
  4. MC Dropout forward pass through HFTMultiScaleTransformer ensemble
     (N=20 stochastic passes per model, averaged across ensemble)
  5. Uncertainty gate: suppress signal if winner-class std > threshold
  6. Apply tier-based thresholds + vol gate + flow gate
  7. Return the same signal dict format expected by AlertDispatcher

Graceful degradation:
  - Funding rate missing → fr_* features zeroed (model still runs)
  - OI missing → oi_* features zeroed (model still runs)
  - Cross-symbol data missing → neutral defaults used
══════════════════════════════════════════════════════════════════════════════
"""

import bisect
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch

from pipeline.config_signal import (
    TIER_THRESHOLDS, FLOW_VS_PEERS_LIMIT, EXHAUSTION_THRESHOLD,
)
from .config_dl import (
    DL_MODEL_PATH, DL_ENSEMBLE_DIR, DL_FEATURE_PATH,
    SEQ, DL_MODEL, DL_TRAIN, DL_WF, DEVICE,
)
from ...Training_package.features_extended import engineer_features_extended, NON_FEATURE_COLS
from .dataset_dl import normalize_window, apply_recency_decay
from .model_dl import HFTMultiScaleTransformer

logger = logging.getLogger(__name__)

_SIGNAL_MARGIN:  float = 0.03
_THRESHOLD_MIN:  float = 0.48
_THRESHOLD_MAX:  float = 0.58


def _classify_cap_tier(vol_to_mcap: float) -> tuple:
    if vol_to_mcap < 0.00005:
        return 0, "large"
    if vol_to_mcap < 0.001:
        return 1, "mid"
    return 2, "small"


class DLInferenceEngine:
    """
    Drop-in replacement for InferenceEngine using the trained Transformer.
    Uses MC Dropout ensemble inference with an uncertainty gate to suppress
    signals when the model is confused (e.g. choppy / sideways markets).
    """

    def __init__(
        self,
        model_path:    Optional[Path]         = None,
        ensemble_dir:  Optional[Path]         = None,
        audit_loop                            = None,
        use_ensemble:  bool                   = True,
        device:        Optional[torch.device] = None,
        mc_samples:    int                    = DL_TRAIN["mc_samples"],
        unc_threshold: float                  = DL_TRAIN["uncertainty_threshold"],
    ):
        self._audit_loop    = audit_loop
        self._device        = device or DEVICE
        self._models:       list = []
        self._feature_cols: list = []
        self._n_features:   int  = 0
        self._seq_len:      int  = SEQ["seq_len"]
        self._mc_samples    = mc_samples
        self._unc_threshold = unc_threshold

        self._load_models(
            model_path   or DL_MODEL_PATH,
            ensemble_dir or DL_ENSEMBLE_DIR,
            use_ensemble,
        )

    def _build_model(self, n_features: int) -> HFTMultiScaleTransformer:
        return HFTMultiScaleTransformer(
            n_features=n_features, seq_len=self._seq_len,
        ).to(self._device)

    def _load_models(self, model_path: Path, ensemble_dir: Path,
                     use_ensemble: bool):
        if DL_FEATURE_PATH.exists():
            with open(DL_FEATURE_PATH, "rb") as f:
                self._feature_cols = pickle.load(f)
            logger.info(f"[dl_engine] Feature cols loaded: {len(self._feature_cols)}")
        else:
            raise FileNotFoundError(f"Feature cols not found: {DL_FEATURE_PATH}")

        if use_ensemble and ensemble_dir.exists():
            ckpts = sorted(ensemble_dir.glob("fold_*.pt"))
            if ckpts:
                fold_data = []
                for ckpt in ckpts:
                    d = torch.load(ckpt, map_location=self._device,
                                   weights_only=False)
                    fold_data.append((d.get("val_loss", float("inf")), ckpt, d))
                fold_data.sort(key=lambda x: x[0])

                for _, ckpt, d in fold_data[:DL_WF["ensemble_top_k"]]:
                    n_feat = d.get("n_features", len(self._feature_cols))
                    m = self._build_model(n_feat)
                    m.load_state_dict(d["model_state"])
                    m.eval()
                    self._models.append(m)
                    if not self._n_features:
                        self._n_features = n_feat

                logger.info(
                    f"[dl_engine] Ensemble: {len(self._models)} models | "
                    f"n_features={self._n_features} | "
                    f"mc_samples={self._mc_samples}"
                )
                return

        if not model_path.exists():
            raise FileNotFoundError(f"[dl_engine] Model not found: {model_path}")

        d = torch.load(model_path, map_location=self._device, weights_only=False)
        self._n_features = d.get("n_features", len(self._feature_cols))
        m = self._build_model(self._n_features)
        m.load_state_dict(d["model_state"])
        m.eval()
        self._models.append(m)
        logger.info(f"[dl_engine] Single model | n_features={self._n_features}")

    # ── Public interface ──────────────────────────────────────────────────────

    def predict(
        self,
        sym_key:           str,
        df:                pd.DataFrame,
        market_return:     float,
        cross_symbol_data: Optional[dict] = None,
    ) -> Optional[dict]:
        try:
            return self._predict_inner(sym_key, df, market_return, cross_symbol_data)
        except Exception as exc:
            logger.error(f"[dl_engine] predict crashed for {sym_key}: {repr(exc)}",
                         exc_info=True)
            return None

    # ── Internal pipeline ─────────────────────────────────────────────────────

    def _predict_inner(self, sym_key, df, market_return, cross_symbol_data):
        if len(df) < self._seq_len + 50:
            return None

        df = df.copy()
        if "symbol" not in df.columns:
            df.insert(0, "symbol", sym_key)

        feat_df = engineer_features_extended(df, timeframe="15m")
        feat_df = feat_df.dropna(subset=["close"])

        if len(feat_df) < self._seq_len:
            return None

        feat_df["market_return"] = market_return
        if cross_symbol_data is not None:
            self._inject_cross_symbol(feat_df, sym_key, cross_symbol_data)

        for c in [c for c in self._feature_cols if c not in feat_df.columns]:
            feat_df[c] = 0.0

        window = feat_df[self._feature_cols].values[-self._seq_len:].astype(np.float32)
        window = np.nan_to_num(window, nan=0.0, posinf=0.0, neginf=0.0)
        window = normalize_window(window)
        window = apply_recency_decay(window, SEQ["recency_decay"])

        X = torch.from_numpy(window).unsqueeze(0).to(self._device)

        # MC Dropout ensemble
        all_probas, all_unc = [], []
        with torch.no_grad():
            for m in self._models:
                mean_p, unc, _ = m.predict_mc(X, n_samples=self._mc_samples)
                all_probas.append(mean_p)
                all_unc.append(unc)

        avg_proba = torch.stack(all_probas).mean(0).squeeze(0)
        uncertainty = float(torch.stack(all_unc).mean(0).squeeze(0))

        p_short, p_hold, p_long = (float(avg_proba[0]),
                                   float(avg_proba[1]),
                                   float(avg_proba[2]))

        # Uncertainty gate
        if uncertainty > self._unc_threshold:
            logger.debug(f"[dl_engine] {sym_key}: suppressed unc={uncertainty:.3f}")
            return None

        last_row    = feat_df.iloc[-1]
        ts          = last_row.get("timestamp", df.index[-1])
        vol_to_mcap = self._estimate_vol_to_mcap(last_row)
        tier, tier_name = _classify_cap_tier(vol_to_mcap)
        thresh      = self._resolve_thresholds(tier)

        vol_ok    = vol_to_mcap >= thresh.get("min_vol_to_mcap", 0.0)
        flow_vs_peers = float(last_row.get("flow_vs_peers", 0.0))
        flow_ok   = flow_vs_peers > FLOW_VS_PEERS_LIMIT

        long_margin  = p_long  - p_short
        short_margin = p_short - p_long

        if (p_short >= thresh["signal"] and short_margin >= _SIGNAL_MARGIN
                and vol_ok and flow_ok):
            direction     = "short"
            is_strong     = p_short >= thresh["strong"]
            precision_est = self._precision_from_audit("short")
        elif (p_long >= thresh["signal"] and long_margin >= _SIGNAL_MARGIN
              and vol_ok and flow_ok):
            direction     = "long"
            is_strong     = p_long >= thresh["strong"]
            precision_est = self._precision_from_audit("long")
        else:
            return None   # HOLD → listener.py skips None

        signal = {
            "symbol":        sym_key,
            "timestamp":     ts,
            "signal":        direction,
            "strong":        is_strong,
            "p_long":        p_long,
            "p_short":       p_short,
            "p_hold":        p_hold,
            "p_base_long":   p_long,
            "p_base_short":  p_short,
            "p_cal_long":    p_long,
            "p_cal_short":   p_short,
            "precision_est": precision_est,
            "market_return": float(market_return),
            "cap_tier":      tier,
            "cap_tier_name": tier_name,
            "vol_to_mcap":   float(vol_to_mcap),
            "flow_vs_peers": float(flow_vs_peers),
            "mpe_target":    None,
            "close":         float(last_row.get("close", 0.0)),
            "uncertainty":   uncertainty,
        }

        if self._audit_loop is not None:
            self._audit_loop.record_prediction(signal)

        logger.debug(
            f"[dl_engine] {sym_key} | {direction.upper()} "
            f"{'★' if is_strong else ''} | "
            f"p_long={p_long:.3f} p_short={p_short:.3f} | "
            f"unc={uncertainty:.3f} | tier={tier_name}"
        )
        return signal

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _inject_cross_symbol(feat_df: pd.DataFrame, sym_key: str,
                              cross_symbol_data: dict):
        all_qvol  = cross_symbol_data.get("all_quote_volumes", {})
        all_taker = cross_symbol_data.get("all_net_taker", {})

        this_qvol  = all_qvol.get(sym_key, 0.0)
        peer_qvols = sorted(all_qvol.values())
        if peer_qvols:
            rank = bisect.bisect_left(peer_qvols, this_qvol) / max(1, len(peer_qvols) - 1)
            feat_df["vol_rank_pct"] = rank

        this_taker  = all_taker.get(sym_key, 0.0)
        peer_takers = list(all_taker.values())
        if peer_takers:
            mean_t = np.mean(peer_takers)
            std_t  = np.std(peer_takers) or 1.0
            feat_df["flow_vs_peers"] = float(
                np.clip((this_taker - mean_t) / std_t, -3, 3)
            )

    @staticmethod
    def _estimate_vol_to_mcap(row) -> float:
        close = float(row.get("close", 1.0)) or 1.0
        vol   = float(row.get("quote_volume", 0.0))
        oi_c  = float(row.get("oi_contracts", 0.0))
        if oi_c > 0:
            return vol / (close * oi_c)
        if vol > 5e8:
            return 0.00001
        if vol > 5e7:
            return 0.0001
        return 0.002

    def _resolve_thresholds(self, tier: int) -> dict:
        base = TIER_THRESHOLDS.get(tier, TIER_THRESHOLDS[1]).copy()
        if self._audit_loop is not None:
            delta = self._audit_loop.get_threshold_delta()
            base["signal"] = float(
                np.clip(base["signal"] + delta, _THRESHOLD_MIN, _THRESHOLD_MAX))
            base["strong"] = float(
                np.clip(base["strong"] + delta,
                        base["signal"] + 0.02, _THRESHOLD_MAX))
        return base

    def _precision_from_audit(self, direction: str) -> float:
        _BASELINE = {"long": 0.533, "short": 0.431}
        if self._audit_loop is None:
            return _BASELINE.get(direction, 0.50)
        try:
            prec = self._audit_loop.get_rolling_precision()
            if prec is not None and not np.isnan(prec):
                return float(prec)
        except Exception:
            pass
        return _BASELINE.get(direction, 0.50)