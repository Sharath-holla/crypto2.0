"""
model_dl.py — HFTMultiScaleTransformer with Uncertainty Estimation
══════════════════════════════════════════════════════════════════════════════
Architecture:

  Input  (B, S, F)          B=batch, S=seq_len=193, F=n_features
      │
      ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  MultiScaleConvEncoder  (3 parallel causal dilated branches)    │
  │                                                                 │
  │  Scale 1 [d=1,2,4]   → RF ~15 candles  (microstructure)        │
  │  Scale 2 [d=4,8,16]  → RF ~60 candles  (momentum)              │
  │  Scale 3 [d=16,32,64]→ RF ~192 candles (regime / daily cycle)  │
  │                                                                 │
  │  FusionGate: learned per-position scale weights (softmax)       │
  │  Output: (B, S, conv_channels)                                  │
  └──────────────────────────┬──────────────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Linear projection + LayerNorm + GELU                           │
  │  conv_channels → d_model                                        │
  └──────────────────────────┬──────────────────────────────────────┘
                             │ (B, S, d_model)
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  ALiBi Positional Encoding                                      │
  │  Sinusoidal PE + per-head recency bias in attention             │
  └──────────────────────────┬──────────────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  ALiBi Transformer Encoder × num_layers (6)                     │
  │  Pre-norm + stochastic depth regularisation                     │
  └──────────────────────────┬──────────────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Dual Pooling: concat(last_token, mean_pool) → (B, 2×d_model)  │
  └──────────────────────────┬──────────────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Classification Head  → (B, 3) logits                          │
  │  Uncertainty Head     → (B, 1) uncertainty logit               │
  └─────────────────────────────────────────────────────────────────┘

Loss: PunishmentFocalLoss — asymmetric punishment matrix multiplied by
      focal weights (γ=2) to focus training on hard / misclassified samples.

Inference: MC Dropout — N forward passes with dropout active, average
      softmax + measure std of winner class → uncertainty gate.

PATCH NOTES
───────────
Fix #5 — Residual connections in MultiScaleConvEncoder.forward:
  The original implementation updated `residual = out` after every conv layer,
  so each layer's skip connection pointed to the PREVIOUS layer's output rather
  than the branch input. This turned the three-layer stack into a running
  accumulation (out_3 = layer3(out_2) + out_2 = layer3(out_2) + layer2(out_1)
  + out_1 = ...) rather than proper ResNet-style skip connections.
  The fix keeps `residual` fixed at `proj(x_t)` throughout the branch so every
  conv layer receives a direct skip from the projected branch input.
══════════════════════════════════════════════════════════════════════════════
"""

import math
import random
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config_dl import DL_MODEL, PUNISHMENT_MATRIX, DL_TRAIN


# ─────────────────────────────────────────────────────────────────────────────
# Causal dilated Conv1D
# ─────────────────────────────────────────────────────────────────────────────

class CausalConv1d(nn.Module):
    """Causal dilated 1D convolution: output[t] only sees input[0..t]."""

    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int, dilation: int = 1):
        super().__init__()
        self.pad  = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(in_channels, out_channels, kernel_size,
                              dilation=dilation, padding=0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.pad(x, (self.pad, 0))   # left pad only → causal
        return self.conv(x)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-scale Conv1D encoder (3 parallel branches)
# ─────────────────────────────────────────────────────────────────────────────

class MultiScaleConvEncoder(nn.Module):
    """
    Three parallel causal dilated Conv1D branches capture different
    temporal horizons simultaneously.

    Branch dilations:
      Scale 1: [1, 2, 4]    → receptive field ~15 candles (microstructure)
      Scale 2: [4, 8, 16]   → receptive field ~60 candles (momentum)
      Scale 3: [16, 32, 64] → receptive field ~192 candles (regime)

    A learnable FusionGate computes per-position softmax weights
    over the three branch outputs and returns a weighted sum.

    Residual connections: each conv layer inside a branch receives a fixed
    skip from the projected branch input (ResNet-style). The skip anchor does
    NOT move forward after each layer — see FIX #5 in patch notes.
    """

    _DILATION_SETS = [
        [1,  2,  4],    # scale 1: microstructure
        [4,  8,  16],   # scale 2: momentum
        [16, 32, 64],   # scale 3: regime
    ]

    def __init__(self, in_channels: int, hidden_channels: int,
                 kernel_size: int = 3):
        super().__init__()

        self.branches    = nn.ModuleList()
        self.input_projs = nn.ModuleList()

        for dilations in self._DILATION_SETS:
            layers = nn.ModuleList()
            ch_in  = in_channels
            for d in dilations:
                layers.append(nn.Sequential(
                    CausalConv1d(ch_in, hidden_channels, kernel_size, d),
                    nn.GroupNorm(min(8, hidden_channels), hidden_channels),
                    nn.GELU(),
                ))
                ch_in = hidden_channels
            self.branches.append(layers)
            # Project input dim to hidden for residual connections
            self.input_projs.append(
                nn.Conv1d(in_channels, hidden_channels, 1)
                if in_channels != hidden_channels else nn.Identity()
            )

        n_scales = len(self._DILATION_SETS)
        # FusionGate: per-position learned scale weights
        self.fusion_gate = nn.Sequential(
            nn.Linear(hidden_channels * n_scales, n_scales),
            nn.Softmax(dim=-1),
        )
        self.out_channels = hidden_channels

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, S, F) → transpose to (B, F, S) for Conv1D
        x_t = x.transpose(1, 2)

        branch_outs = []
        for branch_layers, proj in zip(self.branches, self.input_projs):
            # FIX #5: residual is fixed at the projected branch input and is
            # NOT updated to `out` after each layer.  Every conv layer in the
            # branch receives a direct skip connection from proj(x_t), which is
            # the standard ResNet identity shortcut.  The original code set
            # `residual = out` inside the loop, turning the stack into a
            # running accumulation rather than a true skip connection.
            residual = proj(x_t)   # fixed skip anchor — always from branch input
            out      = x_t
            for layer in branch_layers:
                out = layer(out) + residual   # residual stays as proj(x_t)
            branch_outs.append(out.transpose(1, 2))   # → (B, S, hidden)

        # Fusion: weighted sum guided by concatenated branch outputs
        concat = torch.cat(branch_outs, dim=-1)        # (B, S, 3*hidden)
        gate   = self.fusion_gate(concat)               # (B, S, 3)

        fused = sum(gate[..., i:i+1] * bo
                    for i, bo in enumerate(branch_outs))
        return fused    # (B, S, hidden_channels)


# ─────────────────────────────────────────────────────────────────────────────
# ALiBi positional encoding
# ─────────────────────────────────────────────────────────────────────────────

class ALiBiPositionalEncoding(nn.Module):
    """
    Sinusoidal PE for absolute position + ALiBi bias for relative recency.

    ALiBi (Press et al. 2022): add a per-head slope × relative distance
    directly to the pre-softmax attention logits.
      bias[h, q, k] = -slopes[h] × max(0, q - k)
    Recent keys get near-zero penalty → naturally higher attention.
    """

    def __init__(self, d_model: int, seq_len: int,
                 num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.num_heads = num_heads

        # Sinusoidal PE
        pe  = torch.zeros(1, seq_len, d_model)
        pos = torch.arange(seq_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float()
                        * (-math.log(10000.0) / d_model))
        pe[0, :, 0::2] = torch.sin(pos * div)
        pe[0, :, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe)

        # ALiBi slopes: geometric sequence
        slopes = torch.tensor(
            [2 ** (-8.0 * i / num_heads) for i in range(1, num_heads + 1)],
            dtype=torch.float32,
        )
        self.register_buffer("slopes", slopes)

        # Relative distance matrix: causal
        idx  = torch.arange(seq_len)
        dist = (idx.unsqueeze(0) - idx.unsqueeze(1)).clamp(min=0).float()
        self.register_buffer("dist", dist)

        self.dropout = nn.Dropout(dropout)

    def get_alibi_bias(self, seq_len: int) -> torch.Tensor:
        return -self.slopes.view(-1, 1, 1) * self.dist[:seq_len, :seq_len]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


# ─────────────────────────────────────────────────────────────────────────────
# Custom Transformer encoder layer with ALiBi + stochastic depth
# ─────────────────────────────────────────────────────────────────────────────

class ALiBiEncoderLayer(nn.Module):
    """
    Pre-norm Transformer encoder layer with ALiBi bias injection
    and stochastic depth (LayerDrop) for regularisation.
    """

    def __init__(self, d_model: int, nhead: int,
                 dim_feedforward: int, dropout: float = 0.1,
                 stoch_depth_p: float = 0.05):
        super().__init__()
        self.attn = nn.MultiheadAttention(
            d_model, nhead, dropout=dropout, batch_first=True
        )
        self.ff = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )
        self.norm1         = nn.LayerNorm(d_model)
        self.norm2         = nn.LayerNorm(d_model)
        self.drop          = nn.Dropout(dropout)
        self.nhead         = nhead
        self.stoch_depth_p = stoch_depth_p

    def _stoch_depth_scale(self) -> float:
        """
        Stochastic depth: during training randomly drop the entire residual
        update for this layer. At inference always apply.
        Expected scale = 1 - p (unbiased estimate used at eval time).
        """
        if self.training and self.stoch_depth_p > 0:
            if random.random() < self.stoch_depth_p:
                return 0.0
        return 1.0

    def forward(self, x: torch.Tensor,
                alibi_bias: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, S, _ = x.shape
        scale   = self._stoch_depth_scale()

        # Pre-norm + self-attention
        residual  = x
        x         = self.norm1(x)
        attn_mask = None
        if alibi_bias is not None:
            attn_mask = (alibi_bias.unsqueeze(0)
                         .expand(B, -1, -1, -1)
                         .reshape(B * self.nhead, S, S))
        attn_out, _ = self.attn(x, x, x, attn_mask=attn_mask)
        x = residual + scale * self.drop(attn_out)

        # Pre-norm + feed-forward
        residual = x
        x        = residual + scale * self.ff(self.norm2(x))
        return x


# ─────────────────────────────────────────────────────────────────────────────
# Punishment Focal Loss
# ─────────────────────────────────────────────────────────────────────────────

class PunishmentFocalLoss(nn.Module):
    """
    Asymmetric weighted cross-entropy combined with focal loss.

    Total loss = punishment_CE + focal_weight × focal_CE

    Punishment term: each sample's CE is multiplied by
      punishment_matrix[true_class, predicted_class]
      Wrong-direction errors (LONG→SHORT) incur 4× penalty.

    Focal term: (1 - p_correct)^γ × CE
      Downweights easy examples (clear HOLDs that the model already
      predicts correctly with high confidence), forcing attention onto
      the hard LONG/SHORT signals that matter for trading.
    """

    def __init__(
        self,
        matrix:          list  = PUNISHMENT_MATRIX,
        label_smoothing: float = DL_TRAIN["label_smoothing"],
        gamma:           float = DL_TRAIN["focal_gamma"],
        focal_weight:    float = DL_TRAIN["focal_weight"],
    ):
        super().__init__()
        pm = torch.tensor(matrix, dtype=torch.float32)
        self.register_buffer("pm", pm)
        self.label_smoothing = label_smoothing
        self.gamma           = gamma
        self.focal_weight    = focal_weight

    def forward(self, logits: torch.Tensor,
                targets: torch.Tensor) -> torch.Tensor:
        """
        logits:  (B, 3)
        targets: (B,) long tensor with values in {0, 1, 2}
        """
        # Per-sample CE (no reduction)
        ce = F.cross_entropy(logits, targets,
                             label_smoothing=self.label_smoothing,
                             reduction="none")    # (B,)

        with torch.no_grad():
            preds       = logits.argmax(dim=1)
            multipliers = self.pm[targets, preds]

            # Focal weights based on P(true class)
            proba   = F.softmax(logits, dim=-1)
            p_true  = proba.gather(1, targets.unsqueeze(1)).squeeze(1)
            focal_w = (1.0 - p_true).pow(self.gamma)

        punishment_loss = (ce * multipliers).mean()
        focal_loss      = (ce * focal_w).mean()

        return punishment_loss + self.focal_weight * focal_loss


# ─────────────────────────────────────────────────────────────────────────────
# Uncertainty auxiliary loss
# ─────────────────────────────────────────────────────────────────────────────

class UncertaintyAuxLoss(nn.Module):
    """
    Train the uncertainty head to predict whether the main head is wrong.

    Target = 1 if main head prediction is incorrect, 0 if correct.
    This teaches the uncertainty head to identify its own failure modes.
    """

    def forward(self, uncertainty_logit: torch.Tensor,
                logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            preds   = logits.argmax(dim=1)
            is_wrong = (preds != targets).float()   # 1=wrong, 0=correct
        return F.binary_cross_entropy_with_logits(
            uncertainty_logit.squeeze(-1), is_wrong
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main model
# ─────────────────────────────────────────────────────────────────────────────

class HFTMultiScaleTransformer(nn.Module):
    """
    Multi-scale Temporal Transformer with MC Dropout uncertainty estimation.

    forward() returns (logits, uncertainty_logit):
      logits:           (B, num_classes)  — raw class logits
      uncertainty_logit:(B, 1)            — uncertainty score logit

    At inference use predict_mc() which runs N stochastic forward passes
    and returns (mean_proba, uncertainty_score) with dropout active.
    """

    def __init__(
        self,
        n_features:      int,
        seq_len:         int,
        conv_channels:   int   = DL_MODEL["conv_channels"],
        conv_kernel:     int   = DL_MODEL["conv_kernel"],
        d_model:         int   = DL_MODEL["d_model"],
        nhead:           int   = DL_MODEL["nhead"],
        num_layers:      int   = DL_MODEL["num_layers"],
        dim_feedforward: int   = DL_MODEL["dim_feedforward"],
        dropout:         float = DL_MODEL["dropout"],
        stoch_depth_p:   float = DL_MODEL["stoch_depth_p"],
        num_classes:     int   = DL_MODEL["num_classes"],
    ):
        super().__init__()
        assert d_model % nhead == 0, "d_model must be divisible by nhead"

        self.seq_len    = seq_len
        self.d_model    = d_model
        self.n_features = n_features

        # Multi-scale Conv1D encoder
        self.conv_enc = MultiScaleConvEncoder(n_features, conv_channels, conv_kernel)

        # Project conv_channels → d_model
        self.input_proj = nn.Sequential(
            nn.Linear(conv_channels, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
        )

        # ALiBi positional encoding
        self.pos_enc = ALiBiPositionalEncoding(d_model, seq_len, nhead, dropout)

        # Transformer encoder stack
        self.layers = nn.ModuleList([
            ALiBiEncoderLayer(d_model, nhead, dim_feedforward,
                              dropout, stoch_depth_p)
            for _ in range(num_layers)
        ])
        self.final_norm = nn.LayerNorm(d_model)

        # Dual pooling: last_token ++ mean_pool → 2×d_model
        pool_dim = 2 * d_model

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(pool_dim, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, num_classes),
        )

        # Uncertainty head (trained to predict own correctness)
        self.uncertainty_head = nn.Sequential(
            nn.Linear(pool_dim, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, 1),
        )

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out",
                                        nonlinearity="relu")

    def _encode(self, x: torch.Tensor) -> torch.Tensor:
        """Shared encoder: Conv → Project → PE → Transformer → pool."""
        x = self.conv_enc(x)          # (B, S, conv_channels)
        x = self.input_proj(x)        # (B, S, d_model)
        x = self.pos_enc(x)           # (B, S, d_model)

        alibi = self.pos_enc.get_alibi_bias(x.size(1))  # (nhead, S, S)
        for layer in self.layers:
            x = layer(x, alibi_bias=alibi)

        x = self.final_norm(x)        # (B, S, d_model)

        last_tok  = x[:, -1, :]       # (B, d_model)
        mean_pool = x.mean(dim=1)     # (B, d_model)
        return torch.cat([last_tok, mean_pool], dim=1)   # (B, 2×d_model)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        x: (B, seq_len, n_features)
        Returns: (logits (B, num_classes), uncertainty_logit (B, 1))
        """
        pooled            = self._encode(x)
        logits            = self.classifier(pooled)
        uncertainty_logit = self.uncertainty_head(pooled)
        return logits, uncertainty_logit

    @torch.no_grad()
    def predict_mc(
        self,
        x:            torch.Tensor,
        n_samples:    int   = DL_TRAIN["mc_samples"],
        unc_threshold: float = DL_TRAIN["uncertainty_threshold"],
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Monte Carlo Dropout inference.

        Runs N stochastic forward passes with dropout active, then:
          mean_proba     : average softmax across samples → (B, 3)
          uncertainty    : std of winner-class probability  → (B,)
          suppress_mask  : bool tensor, True = uncertain → suppress signal

        Usage:
            model.eval()  # still needed to disable BN stats tracking
            mean_proba, uncertainty, suppress = model.predict_mc(X)
        """
        # Enable dropout even during eval by setting to train mode
        # (we use no_grad so gradients are still disabled)
        was_training = self.training
        self.train()

        all_probas = []
        for _ in range(n_samples):
            logits, _ = self.forward(x)
            all_probas.append(torch.softmax(logits, dim=-1))

        if not was_training:
            self.eval()

        stacked    = torch.stack(all_probas, dim=0)  # (N, B, 3)
        mean_proba = stacked.mean(dim=0)             # (B, 3)
        std_proba  = stacked.std(dim=0)              # (B, 3)

        # Uncertainty = std of the winner class probability
        winner_idx  = mean_proba.argmax(dim=-1)      # (B,)
        uncertainty = std_proba.gather(
            1, winner_idx.unsqueeze(1)
        ).squeeze(1)                                 # (B,)

        suppress_mask = uncertainty > unc_threshold  # (B,) bool
        return mean_proba, uncertainty, suppress_mask

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
