"""Finite-row filtering must be accounted for per segment (defect 19)."""

from __future__ import annotations

import pytest

from crypto_ai.phase7.training import finite_row_accounting


def test_counts_pre_post_and_drops_per_segment() -> None:
    result = finite_row_accounting(
        {"train": (100, 98), "validation": (50, 50), "test": (0, 0)}
    )
    assert result["segments"]["train"] == {
        "pre_filter_rows": 100,
        "post_filter_rows": 98,
        "dropped_rows": 2,
        "dropped_fraction": 0.02,
    }
    assert result["segments"]["validation"]["dropped_rows"] == 0
    assert result["segments"]["test"]["dropped_fraction"] == 0.0
    assert result["total_dropped_rows"] == 2
    assert "nonfinite" in result["policy"]


@pytest.mark.parametrize("pair", [(5, 6), (-1, 0), (3, -1)])
def test_impossible_counts_are_rejected(pair: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="invalid finite-row accounting"):
        finite_row_accounting({"train": pair})
