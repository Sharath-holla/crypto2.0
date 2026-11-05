"""CHANGED BY CLAUDE (2026-11-05, Phase 7C finding N-01): Ridge baseline must survive NaN features."""

from __future__ import annotations

import numpy as np

from crypto_ai.phase7.hardening import HardeningConfig, score_baselines


def test_ridge_baseline_is_finite_when_features_contain_nan() -> None:
    rng = np.random.default_rng(0)
    train_x = rng.normal(size=(400, 5))
    train_y = train_x[:, 0] * 1e-3 + rng.normal(scale=1e-4, size=400)
    train_x[10, 2] = np.nan  # one missing value must not poison the whole solve
    validation_x = rng.normal(size=(100, 5))
    validation_x[3, 1] = np.nan
    validation_y = rng.normal(scale=1e-3, size=100)
    out = score_baselines(
        train_x,
        train_y,
        validation_x,
        validation_y,
        np.zeros(100),
        np.ones(100, dtype=bool),
        config=HardeningConfig(),
    )
    assert np.isfinite(out["ridge"]["rmse"])
    assert np.isfinite(out["ridge"]["mae"])


def test_ridge_baseline_unchanged_for_clean_features() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(300, 4))
    y = x @ np.array([1e-3, 0.0, 0.0, 2e-3]) + rng.normal(scale=1e-5, size=300)
    out = score_baselines(
        x, y, x[:50], y[:50], np.zeros(50), np.ones(50, dtype=bool), config=HardeningConfig()
    )
    assert out["ridge"]["rmse"] < out["zero_return"]["rmse"]
