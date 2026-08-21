"""
train_dl.py — Purged walk-forward cross-validation training pipeline
══════════════════════════════════════════════════════════════════════════════
Walk-forward fold structure (n_splits=8):
  Each fold trains on all data BEFORE the val fold, with a gap_bars buffer.
  Val windows are NON-OVERLAPPING: each fold covers a fresh segment of time.

Per-fold training:
  - AdamW with linear warmup + cosine annealing with warm restarts
  - PunishmentFocalLoss (punishment matrix × focal γ=2)
  - UncertaintyAuxLoss (trains uncertainty head to predict its own errors)
  - AMP (automatic mixed precision) on CUDA — ~2× throughput, no accuracy cost
  - Early stopping on val PunishmentFocalLoss
  - Best fold checkpoint saved to DL_ENSEMBLE_DIR/fold_{i}.pt

Post-training:
  - Load top-k fold checkpoints by val loss
  - Evaluate ensemble (MC Dropout) on held-out test set
  - Report: triple-barrier accuracy + ±2%/10c precision + uncertainty stats

PATCH NOTES
───────────
Fix #4 — Walk-forward fold overlap: original step between consecutive val
  windows was fold_size // n_splits, meaning adjacent folds shared ~87.5% of
  their validation data (nearly identical CV sets).  The fix caps fold_size
  at n_cv // (n_splits + 1) so n_splits non-overlapping val windows fit in the
  CV portion without gaps, giving independent signal per fold.

Fix #8 — Mixed precision training (AMP): FoldTrainer now wraps the forward
  pass in torch.cuda.amp.autocast and uses GradScaler for the backward pass
  when running on CUDA.  Throughput improvement is typically 1.5–2× with no
  change in convergence behaviour.  AMP is a no-op on CPU and MPS devices.
══════════════════════════════════════════════════════════════════════════════
"""

import logging
import math
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix

from .config_dl import (
    DL_MODEL, DL_TRAIN, DL_WF, SEQ, DEVICE,
    DL_ENSEMBLE_DIR, DL_MODEL_PATH, DL_TRAIN_LOG,
)
from .dataset_dl import (
    CandleSequenceDataset, make_loader, prepare_datasets,
)
from .model_dl import (
    HFTMultiScaleTransformer, PunishmentFocalLoss, UncertaintyAuxLoss,
)
from .labels_dual import compute_fixed_precision

logger = logging.getLogger(__name__)
_CLASS_NAMES = ["SHORT", "HOLD", "LONG"]

# Weight for the auxiliary uncertainty loss term
_AUX_LOSS_WEIGHT = 0.10


# ─────────────────────────────────────────────────────────────────────────────
# LR schedule: linear warmup + cosine annealing
# ─────────────────────────────────────────────────────────────────────────────

class WarmupCosineScheduler(torch.optim.lr_scheduler.LambdaLR):
    def __init__(self, optimizer, warmup_steps: int, total_steps: int,
                 min_lr: float, base_lr: float):
        self.warmup_steps = warmup_steps
        self.total_steps  = total_steps
        self.min_lr       = min_lr
        self.base_lr      = base_lr

        def lr_lambda(step: int) -> float:
            if step < warmup_steps:
                return step / max(1, warmup_steps)
            progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
            cosine   = 0.5 * (1.0 + math.cos(math.pi * progress))
            return (min_lr + cosine * (base_lr - min_lr)) / base_lr

        super().__init__(optimizer, lr_lambda)


# ─────────────────────────────────────────────────────────────────────────────
# Purged walk-forward fold generator
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_folds(
    df:         pd.DataFrame,
    n_splits:   int   = DL_WF["n_splits"],
    val_ratio:  float = DL_WF["val_ratio"],
    gap_bars:   int   = DL_WF["gap_bars"],
    test_ratio: float = 0.10,
) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Generate (train_df, val_df) pairs for purged walk-forward CV.
    The final test set is reserved separately and never yielded here.

    FIX #4 — Non-overlapping val windows:
      fold_size is now capped at n_cv // (n_splits + 1) so that n_splits
      consecutive, non-overlapping val windows fit within the CV portion.

      The original step was fold_size // n_splits, producing ~87.5% overlap
      between consecutive folds (nearly identical validation sets, defeating
      the purpose of walk-forward CV).

      New layout (8 folds, n_cv rows, fold_size = n_cv // 9):
        fold 1 val: rows [0*fs … 1*fs)       train: rows [:−gap]
        fold 2 val: rows [1*fs … 2*fs)       train: rows [:1*fs−gap]
        ...
        fold 8 val: rows [7*fs … 8*fs)       train: rows [:7*fs−gap]
      Each val window covers a unique slice of time.
    """
    n        = len(df)
    n_test   = int(n * test_ratio)
    n_cv     = n - n_test

    # FIX #4: cap fold_size so n_splits non-overlapping windows fit in n_cv.
    # n_splits + 1 ensures at least one fold_size worth of data remains at the
    # front for the minimum training set (fold 1).
    max_fold_size = n_cv // (n_splits + 1)
    fold_size     = min(int(n_cv * val_ratio), max_fold_size)

    folds = []

    for i in range(n_splits):
        # Walk backwards from the end of the CV region; step = fold_size (no overlap)
        val_end   = n_cv - i * fold_size
        val_start = val_end - fold_size
        train_end = val_start - gap_bars

        if val_start <= 0 or train_end < DL_WF["min_train_samples"]:
            logger.warning(f"[wf] Fold {i+1}: insufficient data, skipping")
            continue

        train_df = df.iloc[:train_end].copy()
        val_df   = df.iloc[val_start:val_end].copy()
        folds.append((train_df, val_df))
        logger.info(
            f"[wf] Fold {i+1}: train={len(train_df):,} | "
            f"gap={gap_bars} | val={len(val_df):,}"
        )

    return list(reversed(folds))   # chronological order (oldest val first)


# ─────────────────────────────────────────────────────────────────────────────
# Single-fold trainer
# ─────────────────────────────────────────────────────────────────────────────

class FoldTrainer:
    def __init__(self, model: HFTMultiScaleTransformer, n_features: int,
                 ckpt_path: Path, device: torch.device):
        self.model      = model.to(device)
        self.device     = device
        self.ckpt       = ckpt_path
        self.n_features = n_features

        self.criterion      = PunishmentFocalLoss().to(device)
        self.aux_criterion  = UncertaintyAuxLoss().to(device)

        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr           = DL_TRAIN["lr"],
            weight_decay = DL_TRAIN["weight_decay"],
            betas        = DL_TRAIN["betas"],
        )
        self.best_val_loss = float("inf")
        self.patience_ctr  = 0

        # FIX #8: AMP — GradScaler for CUDA; no-op on CPU / MPS.
        self.use_amp = (device.type == "cuda")
        self.scaler  = torch.cuda.amp.GradScaler(enabled=self.use_amp)

    def _one_epoch(
        self, loader: DataLoader, train: bool
    ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        self.model.train(train)
        total_loss = 0.0
        preds_all, labels_all, fixed_all = [], [], []

        ctx = torch.enable_grad() if train else torch.no_grad()
        with ctx:
            for X, y, y_fixed in loader:
                X, y = X.to(self.device), y.to(self.device)

                if train:
                    self.optimizer.zero_grad(set_to_none=True)

                # FIX #8: wrap forward + loss in autocast for fp16 on CUDA.
                # autocast is a no-op when use_amp=False (CPU / MPS).
                with torch.cuda.amp.autocast(enabled=self.use_amp):
                    logits, unc_logit = self.model(X)
                    main_loss = self.criterion(logits, y)
                    aux_loss  = self.aux_criterion(unc_logit, logits, y)
                    loss      = main_loss + _AUX_LOSS_WEIGHT * aux_loss

                if train:
                    # FIX #8: scaled backward + unscale before grad clip.
                    self.scaler.scale(loss).backward()
                    self.scaler.unscale_(self.optimizer)
                    nn.utils.clip_grad_norm_(self.model.parameters(),
                                             DL_TRAIN["grad_clip"])
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                    if hasattr(self, "scheduler"):
                        self.scheduler.step()

                total_loss += main_loss.item() * X.size(0)
                preds_all.append(logits.argmax(1).cpu().numpy())
                labels_all.append(y.cpu().numpy())
                fixed_all.append(y_fixed.cpu().numpy())

        n = len(loader.dataset)
        return (
            total_loss / n,
            np.concatenate(preds_all),
            np.concatenate(labels_all),
            np.concatenate(fixed_all),
        )

    def fit(self, train_loader: DataLoader, val_loader: DataLoader,
            total_steps: int) -> dict:
        self.scheduler = WarmupCosineScheduler(
            self.optimizer,
            warmup_steps = DL_TRAIN["warmup_steps"],
            total_steps  = total_steps,
            min_lr       = DL_TRAIN["min_lr"],
            base_lr      = DL_TRAIN["lr"],
        )

        history = []
        for epoch in range(1, DL_TRAIN["epochs"] + 1):
            t0 = time.time()
            tr_loss, _, _, _     = self._one_epoch(train_loader, train=True)
            val_loss, vp, vl, vf = self._one_epoch(val_loader,   train=False)
            val_acc  = (vp == vl).mean()
            elapsed  = time.time() - t0
            prec     = compute_fixed_precision(vp, vf)
            lr       = self.optimizer.param_groups[0]["lr"]

            row = {
                "epoch": epoch, "train_loss": tr_loss, "val_loss": val_loss,
                "val_acc": val_acc, "lr": lr,
                "long_prec":  prec["long_precision"],
                "short_prec": prec["short_precision"],
            }
            history.append(row)

            logger.info(
                f"  E{epoch:>4} | tr={tr_loss:.4f} val={val_loss:.4f} "
                f"acc={val_acc:.3f} | "
                f"±2%%prec L={prec['long_precision']:.3f} "
                f"S={prec['short_precision']:.3f} "
                f"| lr={lr:.2e} | {elapsed:.1f}s"
            )

            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.patience_ctr  = 0
                torch.save({
                    "model_state": self.model.state_dict(),
                    "val_loss":    val_loss,
                    "val_acc":     float(val_acc),
                    "epoch":       epoch,
                    "prec":        prec,
                    "n_features":  self.n_features,
                    "seq_len":     SEQ["seq_len"],
                }, self.ckpt)
            else:
                self.patience_ctr += 1

            if self.patience_ctr >= DL_TRAIN["patience"]:
                logger.info(f"  Early stop at epoch {epoch}")
                break

        return {"best_val_loss": self.best_val_loss, "history": history}


# ─────────────────────────────────────────────────────────────────────────────
# Test evaluation
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model: HFTMultiScaleTransformer, loader: DataLoader,
             device: torch.device) -> dict:
    """Evaluate model on a DataLoader, return metrics dict."""
    model.eval()
    use_amp = (device.type == "cuda")
    preds_all, labels_all, fixed_all = [], [], []

    for X, y, y_fixed in loader:
        X = X.to(device)
        with torch.cuda.amp.autocast(enabled=use_amp):
            logits, _ = model(X)
        preds_all.append(logits.argmax(1).cpu().numpy())
        labels_all.append(y.cpu().numpy())
        fixed_all.append(y_fixed.cpu().numpy())

    preds  = np.concatenate(preds_all)
    labels = np.concatenate(labels_all)
    fixed  = np.concatenate(fixed_all)

    report = classification_report(labels, preds, target_names=_CLASS_NAMES,
                                   output_dict=True, zero_division=0)
    cm     = confusion_matrix(labels, preds, labels=[0, 1, 2])
    prec   = compute_fixed_precision(preds, fixed)
    return {"report": report, "confusion_matrix": cm, "precision_fixed": prec}


def _print_metrics(metrics: dict, fold: str = "Test"):
    r  = metrics["report"]
    cm = metrics["confusion_matrix"]
    p  = metrics["precision_fixed"]
    print(f"\n  ─── {fold} metrics ────────────────────────────────")
    print(f"  {'Class':<7} {'P':>6} {'R':>6} {'F1':>6} {'N':>8}")
    for cls in _CLASS_NAMES:
        m = r.get(cls, {})
        print(f"  {cls:<7} {m.get('precision',0):>6.3f} "
              f"{m.get('recall',0):>6.3f} {m.get('f1-score',0):>6.3f} "
              f"{m.get('support',0):>8.0f}")
    print(f"  Accuracy: {r.get('accuracy', 0):.4f}")
    print(f"\n  Confusion matrix [SHORT|HOLD|LONG]:")
    print(f"  {''!s:>8}" + "".join(f"{c:>7}" for c in _CLASS_NAMES))
    for i, c in enumerate(_CLASS_NAMES):
        print(f"  {c:>8}" + "".join(f"{cm[i,j]:>7}" for j in range(3)))
    print(f"\n  ±2%/10c precision:")
    print(f"    LONG  hit rate: {p['long_precision']:.3f}  (n={p['n_long']:,})")
    print(f"    SHORT hit rate: {p['short_precision']:.3f}  (n={p['n_short']:,})")
    print(f"    Overall:        {p['overall']:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble evaluation with MC Dropout
# ─────────────────────────────────────────────────────────────────────────────

def ensemble_predict_mc(
    models: list, loader: DataLoader, device: torch.device,
    n_samples: int = DL_TRAIN["mc_samples"],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Run MC Dropout ensemble inference.
    Each model in `models` runs n_samples stochastic passes.
    Final probability = mean across all (len(models) × n_samples) samples.
    """
    use_amp = (device.type == "cuda")
    preds_all, labels_all, fixed_all, unc_all = [], [], [], []

    with torch.no_grad():
        for X, y, y_fixed in loader:
            X = X.to(device)

            # Collect probabilities from all models × all MC samples
            all_probas = []
            for m in models:
                with torch.cuda.amp.autocast(enabled=use_amp):
                    mean_p, unc, _ = m.predict_mc(X, n_samples=n_samples)
                all_probas.append(mean_p)
                unc_all.append(unc.cpu().numpy())

            avg_proba = torch.stack(all_probas, dim=0).mean(dim=0)  # (B, 3)
            preds_all.append(avg_proba.argmax(dim=-1).cpu().numpy())
            labels_all.append(y.cpu().numpy())
            fixed_all.append(y_fixed.cpu().numpy())

    return (
        np.concatenate(preds_all),
        np.concatenate(labels_all),
        np.concatenate(fixed_all),
        np.concatenate(unc_all),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Full training orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def train(
    labelled_df:  pd.DataFrame,
    feature_cols: Optional[list]       = None,
    device:       torch.device         = DEVICE,
) -> HFTMultiScaleTransformer:
    """
    Run full purged walk-forward training and produce an ensemble checkpoint.

    Steps:
      1. Build datasets (chronological split + purge gap)
      2. Walk-forward CV: train one model per fold (8 folds)
      3. Rank folds by val_loss, save top-k checkpoints (4)
      4. Evaluate ensemble (MC Dropout) on test set
      5. Save best single model to DL_MODEL_PATH

    Returns the best single-fold model.
    """
    import random
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)

    # Prepare datasets — prepare_datasets now enforces ["timestamp","symbol"]
    # sort internally (Fix #1), so labelled_df can arrive in any order.
    train_ds, val_ds, test_ds, feature_cols = prepare_datasets(
        labelled_df,
        feature_cols = feature_cols,
        seq_len      = SEQ["seq_len"],
        decay        = SEQ["recency_decay"],
        val_ratio    = DL_WF["val_ratio"],
        test_ratio   = 0.10,
        gap_bars     = DL_WF["gap_bars"],
    )
    n_features = train_ds.n_features

    print(f"\n{'='*65}")
    print(f"  HFT MULTI-SCALE TRANSFORMER — Walk-Forward Training")
    print(f"  Device: {device} | AMP: {device.type == 'cuda'} | "
          f"Features: {n_features} | seq_len: {SEQ['seq_len']}")
    print(f"  Folds: {DL_WF['n_splits']} | Ensemble top-k: {DL_WF['ensemble_top_k']}")
    print(f"{'='*65}")

    # Walk-forward CV on the train+val portion only
    train_val_df = labelled_df.sort_values(
        ["timestamp", "symbol"]
    ).iloc[:int(len(labelled_df) * 0.90)]

    folds = walk_forward_folds(
        train_val_df,
        n_splits  = DL_WF["n_splits"],
        val_ratio = DL_WF["val_ratio"],
        gap_bars  = DL_WF["gap_bars"],
    )

    fold_results = []

    for fold_i, (fold_train_df, fold_val_df) in enumerate(folds, 1):
        print(f"\n  ── Fold {fold_i}/{len(folds)} ──────────────────────────────────")

        fold_train_ds = CandleSequenceDataset(
            fold_train_df, feature_cols, SEQ["seq_len"], SEQ["recency_decay"])
        fold_val_ds   = CandleSequenceDataset(
            fold_val_df,   feature_cols, SEQ["seq_len"], SEQ["recency_decay"])

        train_loader = make_loader(fold_train_ds, balance=True)
        val_loader   = make_loader(fold_val_ds,   balance=False)

        model = HFTMultiScaleTransformer(
            n_features=n_features, seq_len=SEQ["seq_len"]
        ).to(device)
        print(f"  Parameters: {model.count_parameters():,}")

        ckpt_path   = DL_ENSEMBLE_DIR / f"fold_{fold_i}.pt"
        total_steps = DL_TRAIN["epochs"] * len(train_loader)
        trainer     = FoldTrainer(model, n_features, ckpt_path, device)
        result      = trainer.fit(train_loader, val_loader, total_steps)

        fold_results.append({
            "fold":          fold_i,
            "ckpt_path":     ckpt_path,
            "best_val_loss": result["best_val_loss"],
        })

    # Select top-k folds
    fold_results.sort(key=lambda x: x["best_val_loss"])
    top_k = fold_results[:DL_WF["ensemble_top_k"]]
    best  = top_k[0]

    print(f"\n  Top-{DL_WF['ensemble_top_k']} folds selected:")
    for fr in top_k:
        print(f"    Fold {fr['fold']}: val_loss={fr['best_val_loss']:.4f}")

    # Ensemble evaluation on test set
    test_loader = make_loader(test_ds, balance=False)

    ensemble_models = []
    for fr in top_k:
        m    = HFTMultiScaleTransformer(
            n_features=n_features, seq_len=SEQ["seq_len"]).to(device)
        ckpt = torch.load(fr["ckpt_path"], map_location=device)
        m.load_state_dict(ckpt["model_state"])
        m.eval()
        ensemble_models.append(m)

    te_preds, te_labels, te_fixed, te_unc = ensemble_predict_mc(
        ensemble_models, test_loader, device)
    te_report = classification_report(te_labels, te_preds,
                                      target_names=_CLASS_NAMES,
                                      output_dict=True, zero_division=0)
    te_cm   = confusion_matrix(te_labels, te_preds, labels=[0, 1, 2])
    te_prec = compute_fixed_precision(te_preds, te_fixed)
    _print_metrics(
        {"report": te_report, "confusion_matrix": te_cm,
         "precision_fixed": te_prec}, fold="Ensemble Test (MC Dropout)"
    )

    unc_thresh = DL_TRAIN["uncertainty_threshold"]
    suppressed = (te_unc > unc_thresh).mean() * 100
    print(f"\n  Uncertainty gate @ {unc_thresh}: "
          f"would suppress {suppressed:.1f}% of test signals")

    # Save best single model
    best_model = HFTMultiScaleTransformer(
        n_features=n_features, seq_len=SEQ["seq_len"]).to(device)
    ckpt = torch.load(best["ckpt_path"], map_location=device)
    best_model.load_state_dict(ckpt["model_state"])

    torch.save({
        "model_state":    best_model.state_dict(),
        "feature_cols":   feature_cols,
        "n_features":     n_features,
        "seq_len":        SEQ["seq_len"],
        "model_cfg":      DL_MODEL,
        "val_loss":       best["best_val_loss"],
        "test_precision": te_prec,
        "fold":           best["fold"],
    }, DL_MODEL_PATH)

    print(f"\n  ✅ Best model saved → {DL_MODEL_PATH}")

    # Save training log
    pd.DataFrame(fold_results).to_csv(DL_TRAIN_LOG, index=False)

    return best_model


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Train HFT Multi-Scale DL model")
    parser.add_argument("--data",   type=str, required=True,
                        help="Path to labelled parquet (output of labels_dual.py)")
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    df  = pd.read_parquet(args.data)
    dev = torch.device(args.device) if args.device else DEVICE
    print(f"[train] Loaded {len(df):,} rows | device={dev}")
    train(df, device=dev)
