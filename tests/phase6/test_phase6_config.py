from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from crypto_ai.phase6.config import Phase6Config


def _config(**overrides: object) -> Phase6Config:
    values = {
        "silver_5m_manifests": (Path("5m.json"),),
        "silver_12h_manifests": (Path("12h.json"),),
        "silver_1d_manifests": (Path("1d.json"),),
        "phase6_research_cutoff": datetime(2026, 7, 1, tzinfo=UTC),
        "prospective_holdout_start": datetime(2026, 8, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return Phase6Config.model_validate(values)


def test_phase6_cutoff_and_holdout_are_locked() -> None:
    config = _config()

    assert config.phase6_research_cutoff == datetime(2026, 7, 1, tzinfo=UTC)
    assert config.prospective_holdout_start == datetime(2026, 8, 1, tzinfo=UTC)


def test_phase6_rejects_research_after_safe_july_boundary() -> None:
    with pytest.raises(ValidationError, match="preserved July buffer"):
        _config(phase6_research_cutoff=datetime(2026, 7, 10, tzinfo=UTC))


def test_phase6_rejects_changed_prospective_holdout() -> None:
    with pytest.raises(ValidationError, match="permanently locked"):
        _config(prospective_holdout_start=datetime(2026, 9, 1, tzinfo=UTC))
