"""Equivalence tests: vectorized ``_pair_stats`` vs the original loop reference.

The production implementation must be numerically equivalent to the reference
within a justified float64 tolerance (single-pass window sums vs NumPy's
two-pass var/cov; relative error scales with window length and stays far below
1e-9 for the fixtures used here) and must place NaN exactly where the
reference does.
"""

from __future__ import annotations

import numpy as np
import pytest

from crypto_ai.phase7.features import _pair_stats, _pair_stats_reference


def _assert_equivalent(values: np.ndarray, anchor: np.ndarray, window: int) -> None:
    corr_fast, beta_fast = _pair_stats(values, anchor, window)
    corr_ref, beta_ref = _pair_stats_reference(values, anchor, window)
    # Exact NaN placement.
    np.testing.assert_array_equal(np.isfinite(corr_fast), np.isfinite(corr_ref))
    np.testing.assert_array_equal(np.isfinite(beta_fast), np.isfinite(beta_ref))
    # Numeric closeness where both are defined. The fast path uses
    # extended-precision (longdouble) window sums while the reference uses
    # NumPy's two-pass var/cov/corrcoef; observed worst-case difference on
    # these adversarial multi-scale fixtures is <1e-11. Windows with
    # near-zero variance are recomputed with the exact reference algorithm
    # and match bit-for-bit. 1e-9 is far below any scientific use threshold.
    finite = np.isfinite(corr_fast) & np.isfinite(corr_ref)
    np.testing.assert_allclose(corr_fast[finite], corr_ref[finite], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(beta_fast[finite], beta_ref[finite], rtol=1e-9, atol=1e-9)
    # Shapes and leading NaN warmup identical.
    assert corr_fast.shape == values.shape
    assert corr_fast[: window - 1].size == 0 or not np.isfinite(corr_fast[: window - 1]).any()


@pytest.mark.parametrize(
    "rows,window",
    [
        (5_000, 100),
        (40_000, 2_016),
        (2_016, 2_016),
        (2_017, 2_016),
        (1_000, 12),
    ],
)
def test_normal_correlated_series(rows: int, window: int) -> None:
    rng = np.random.default_rng(7)
    x = np.cumsum(rng.normal(0.0, 0.001, rows))
    y = 0.8 * x + rng.normal(0.0, 0.0005, rows)
    _assert_equivalent(x, y, window)


def test_short_series_all_nan() -> None:
    rng = np.random.default_rng(11)
    x = np.cumsum(rng.normal(0.0, 0.001, 500))
    y = np.cumsum(rng.normal(0.0, 0.001, 500))
    corr, beta = _pair_stats(x, y, 2_016)
    assert not np.isfinite(corr).any()
    assert not np.isfinite(beta).any()


def test_constant_values_series() -> None:
    rng = np.random.default_rng(13)
    x = np.full(3_000, 1.25)
    y = np.cumsum(rng.normal(0.0, 0.001, 3_000))
    _assert_equivalent(x, y, 100)


def test_constant_anchor_series() -> None:
    rng = np.random.default_rng(17)
    x = np.cumsum(rng.normal(0.0, 0.001, 3_000))
    y = np.full(3_000, -0.5)
    _assert_equivalent(x, y, 100)


def test_zero_variance_anchor_block() -> None:
    rng = np.random.default_rng(19)
    x = np.cumsum(rng.normal(0.0, 0.001, 4_000))
    y = np.cumsum(rng.normal(0.0, 0.001, 4_000))
    y[1_000:1_500] = 7.0  # constant block longer than the window
    _assert_equivalent(x, y, 100)


def test_sprinkled_nans() -> None:
    rng = np.random.default_rng(23)
    x = np.cumsum(rng.normal(0.0, 0.001, 5_000))
    y = 0.8 * x + rng.normal(0.0, 0.0005, 5_000)
    for arr in (x, y):
        picks = rng.choice(len(arr), size=250, replace=False)
        arr[picks] = np.nan
    _assert_equivalent(x, y, 100)


def test_contiguous_nan_gap_mid_and_edges() -> None:
    rng = np.random.default_rng(29)
    x = np.cumsum(rng.normal(0.0, 0.001, 8_000))
    y = 0.8 * x + rng.normal(0.0, 0.0005, 8_000)
    x[2_000:4_000] = np.nan  # gap spanning many windows
    y[6_500:6_800] = np.nan  # partial-gap region
    _assert_equivalent(x, y, 100)


def test_btc_eth_anchor_profiles() -> None:
    rng = np.random.default_rng(31)
    btc = np.cumsum(rng.normal(0.0, 0.002, 10_000))
    eth = 1.1 * btc + rng.normal(0.0, 0.001, 10_000)
    coin = 0.6 * btc + 0.4 * eth + rng.normal(0.0, 0.0008, 10_000)
    _assert_equivalent(coin, btc, 2_016)
    _assert_equivalent(coin, eth, 2_016)


def test_infinite_values_are_treated_as_missing() -> None:
    rng = np.random.default_rng(37)
    x = np.cumsum(rng.normal(0.0, 0.001, 4_000))
    y = 0.8 * x + rng.normal(0.0, 0.0005, 4_000)
    x[1_500:1_800] = np.inf
    y[2_900] = -np.inf
    _assert_equivalent(x, y, 100)


def test_window_minimum_and_large_window() -> None:
    rng = np.random.default_rng(41)
    x = np.cumsum(rng.normal(0.0, 0.001, 30_000))
    y = 0.8 * x + rng.normal(0.0, 0.0005, 30_000)
    _assert_equivalent(x, y, 12)
    _assert_equivalent(x, y, 2_016)


def test_huge_magnitude_series_stay_finite() -> None:
    """float64 squares of large-but-finite values overflow; the extended-
    precision products must keep the vectorized path finite and correct."""
    rng = np.random.default_rng(43)
    scale = 1e160
    x = scale * (1.0 + 1e-6 * np.cumsum(rng.normal(0.0, 0.001, 2_000)))
    # Noise std (1e148) far below the signal std (0.8 * ~3e151): the true
    # beta cov(x,y)/var(y) -> 0.8/0.64 = 1.25 within ~1e-7.
    y = 0.8 * x + scale * 1e-12 * rng.normal(0.0, 1.0, 2_000)
    corr, beta = _pair_stats(x, y, 100)
    assert np.isfinite(corr[100:]).all()
    assert np.isfinite(beta[100:]).all()
    # The true per-window beta (longdouble np.cov ground truth) is close to
    # 0.8*var(x)/(0.64*var(x)+var(noise)) but fluctuates slightly per window;
    # assert against ground truth, not a fixed constant.
    x_ext = x.astype(np.longdouble)
    y_ext = y.astype(np.longdouble)
    for index in (150, 393, 700, 1_200, 1_800):
        xv, yv = x_ext[index - 99 : index + 1], y_ext[index - 99 : index + 1]
        truth = np.cov(xv, yv, ddof=1)[0, 1] / np.var(yv, ddof=1)
        np.testing.assert_allclose(beta[index], float(truth), rtol=1e-9)
    # And it must agree with the reference implementation.
    _assert_equivalent(x, y, 100)


def test_shape_mismatch_raises_defect() -> None:
    rng = np.random.default_rng(47)
    x = np.cumsum(rng.normal(0.0, 0.001, 1_000))
    y = np.cumsum(rng.normal(0.0, 0.001, 999))
    with pytest.raises(ValueError, match="aligned 1-D"):
        _pair_stats(x, y, 100)
    two_d = x.reshape(500, 2)
    with pytest.raises(ValueError, match="aligned 1-D"):
        _pair_stats(two_d, x, 100)  # type: ignore[arg-type]