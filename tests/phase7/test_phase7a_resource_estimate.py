"""CHANGED BY CLAUDE (2026-11-06, final hardening): the resource estimate is pure and fails safe."""

from __future__ import annotations

import pytest

from crypto_ai.phase7.resource_estimate import GIB, check_capacity, estimate_spec_resources


def test_estimate_matches_hand_calculation() -> None:
    out = estimate_spec_resources(total_gold_rows=40_000_000, feature_count=109)
    rows = 10_000_000
    assert out["rows_per_horizon_upper_bound"] == rows
    assert out["feature_matrix_bytes"] == rows * 109 * 8
    assert out["ram_required_bytes"] == int(rows * 109 * 8 * 3.0 * 1.2)


def test_insufficient_capacity_is_reported_not_ignored() -> None:
    out = estimate_spec_resources(total_gold_rows=50_352_548, feature_count=109)
    errors = check_capacity(out, ram_available=8 * GIB, disk_free=10 * GIB)
    assert len(errors) == 2 and errors[0].startswith("RAM") and errors[1].startswith("DISK")
    assert check_capacity(out, ram_available=10_000 * GIB, disk_free=10_000 * GIB) == []


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        estimate_spec_resources(total_gold_rows=0, feature_count=109)
