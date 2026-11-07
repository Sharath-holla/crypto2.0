from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from tests.historical_source import BUNDLE, COMMIT, historical_blob, historical_phase7_paths

ROOT = Path(__file__).parents[2]
CONTRACT = "configs/contracts/phase7_scientific_baseline_v1_9.json"


def test_anchored_history_is_identical_without_git(tmp_path):
    target = tmp_path / BUNDLE
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / BUNDLE, target)
    data = historical_blob(tmp_path, COMMIT, CONTRACT)
    assert (
        hashlib.sha256(data).hexdigest()
        == "03f74723105f3f4a389fabd0a0140bdccefa5f8e1ea9449ee71b26f5408897bb"
    )
    assert data == historical_blob(ROOT, COMMIT, CONTRACT)
    assert historical_phase7_paths(tmp_path, COMMIT) == historical_phase7_paths(ROOT, COMMIT)


def test_corrupt_or_wrong_history_bundle_fails_closed(tmp_path):
    target = tmp_path / BUNDLE
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / BUNDLE, target)
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        historical_blob(tmp_path, "0" * 40, CONTRACT)
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        historical_blob(tmp_path, COMMIT, CONTRACT)
