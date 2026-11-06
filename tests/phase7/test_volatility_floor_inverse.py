"""CHANGED BY CLAUDE (2026-11-06, closure): normalize -> inverse round trip around the floor."""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.targets import effective_normalization_scale
from crypto_ai.phase7.training import _to_raw_predictions

FLOOR = 1e-8


def _forward(raw: float, scale: float) -> float:
    """The exact formula used by targets.py for the normalized target."""

    return raw / max(abs(float(scale)), FLOOR)


@pytest.mark.parametrize(
    "scale",
    [
        pytest.param(1e-3, id="vol_above_floor"),
        pytest.param(FLOOR, id="vol_equals_floor"),
        pytest.param(1e-10, id="vol_below_floor"),
        pytest.param(0.0, id="vol_zero"),
        pytest.param(-2e-3, id="vol_negative"),
    ],
)
def test_inverse_recovers_the_raw_target(scale: float) -> None:
    raw = 0.0123
    normalized = _forward(raw, scale)
    table = pa.table({"ex_ante_volatility_scale": pa.array([scale], type=pa.float64())})
    recovered = _to_raw_predictions(
        table,
        np.array([normalized]),
        target_type="volatility_normalized",
        normalization_floor=FLOOR,
    )
    assert math.isclose(float(recovered[0]), raw, rel_tol=1e-12, abs_tol=1e-15)


def test_effective_scale_matches_the_forward_divisor() -> None:
    for scale in (1e-3, FLOOR, 1e-10, 0.0, -2e-3):
        assert effective_normalization_scale(scale, FLOOR) == max(abs(scale), FLOOR)
    assert math.isnan(effective_normalization_scale(float("nan"), FLOOR))


def test_missing_scale_stays_missing_and_raw_target_is_untouched() -> None:
    table = pa.table({"ex_ante_volatility_scale": pa.array([None, 1e-3], type=pa.float64())})
    out = _to_raw_predictions(
        table,
        np.array([0.5, 0.5]),
        target_type="volatility_normalized",
        normalization_floor=FLOOR,
    )
    assert math.isnan(out[0]) and math.isclose(out[1], 5e-4)
    passthrough = _to_raw_predictions(
        table, np.array([0.5, 0.5]), target_type="raw", normalization_floor=FLOOR
    )
    assert passthrough.tolist() == [0.5, 0.5]
