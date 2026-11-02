"""Added by Claude (2026-11-02, finding M-02): TEST access is measured, not asserted."""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_ai.phase7.folds import TestAccessViolation
from tests.phase7.test_training_error_classification import _fold_data


def test_release_logs_rows_and_feature_time_range(tmp_path: Path) -> None:
    fold = _fold_data(tmp_path)
    assert fold.test_access_summary()["test_release_count"] == 0
    assert fold.test_touched_by("spec-a|raw") is False
    fold.release_test(frozen_identity="id-1", expected_identity="id-1", consumer="spec-a|raw")
    summary = fold.test_access_summary("spec-a|raw")
    assert summary["test_release_count"] == 1
    entry = summary["releases"][0]
    assert entry["rows"] == 3 and entry["frozen_identity"] == "id-1"
    assert entry["feature_time_min"] < entry["feature_time_max"]
    assert fold.test_touched_by("spec-a|raw") is True
    assert fold.test_touched_by("spec-b|raw") is False


def test_identity_mismatch_fails_loudly(tmp_path: Path) -> None:
    fold = _fold_data(tmp_path)
    with pytest.raises(TestAccessViolation):
        fold.release_test(frozen_identity="id-1", expected_identity="id-2", consumer="x")
    assert fold.test_access_summary()["test_release_count"] == 0


def test_same_consumer_with_a_new_identity_is_rejected(tmp_path: Path) -> None:
    fold = _fold_data(tmp_path)
    fold.release_test(frozen_identity="id-1", consumer="spec-a|raw")
    fold.release_test(frozen_identity="id-1", consumer="spec-a|raw")  # idempotent resume
    with pytest.raises(TestAccessViolation):
        fold.release_test(frozen_identity="id-2", consumer="spec-a|raw")


def test_missing_identity_still_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _fold_data(tmp_path).release_test(frozen_identity="")
