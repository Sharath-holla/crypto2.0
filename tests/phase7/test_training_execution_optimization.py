from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.training import _finite, phase7_experiment_specs


def test_arrow_finite_filter_preserves_complete_case_semantics() -> None:
    table = pa.table(
        {
            "row": [0, 1, 2, 3, 4, 5],
            "f1": pa.chunked_array([[1.0, None, np.nan], [2.0, np.inf, 3.0]]),
            "f2": [1.0, 2.0, 3.0, -np.inf, 5.0, 6.0],
            "target": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        }
    )
    filtered = _finite(table, ("f1", "f2"), "target")
    assert filtered.column("row").to_pylist() == [0, 5]


def test_canonical_bundle_and_estimator_count_is_unchanged() -> None:
    config = load_phase7_config(Path("configs/phase7/research_v1.toml"))
    specs = phase7_experiment_specs(config)
    by_architecture = Counter(spec.architecture for spec in specs)
    assert by_architecture == {"G0": 34, "C0": 8, "P0": 8, "H0": 8}
    assert 16 * 2 * len(specs) == 1_856
    estimators_per_fold_view_at_30 = (
        by_architecture["G0"]
        + by_architecture["C0"] * config.models.cluster_count
        + by_architecture["P0"] * 30
        + by_architecture["H0"]
    )
    assert estimators_per_fold_view_at_30 == 314
    assert 16 * 2 * estimators_per_fold_view_at_30 == 10_048
