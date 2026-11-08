"""Experiment-control identity: code and settings that change what a RUN means (IA-04).

CHANGED BY CLAUDE (2026-11-06, final architecture repair) - new file, standard library only.

Three identities, deliberately separate:
  DATA_PREPARATION_IDENTITY  prepared-cache key; unchanged by this module. ``hardening.py`` is NOT
  in
                             it, so editing a reporting/qualification helper does not invalidate the
                             large prepared cache. (``training.py`` still is, because feature-matrix
                             preparation has not yet been extracted from it - see the report.)
  MODEL_FIT_IDENTITY         scientific source + backend + environment (existing resume identity).
  EXPERIMENT_CONTROL_IDENTITY  THIS module: hardening/qualification/selection/ledger source files
  and
                             the ACTIVE hardening settings (abort rule, pilot, gate, baselines,
                             thresholds, success criteria). Bound into checkpoint/resume identity so
                             a
                             run cannot silently mix policies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXPERIMENT_CONTROL_ALGORITHM = "phase7_experiment_control_manifest_v1"
# CHANGED BY CLAUDE (2026-11-08): settings that only change what is DISPLAYED or LOGGED are not part
# of what a run means, so changing them must not change the control identity (and so must not block
# a resume). ``hardening.SETTING_CLASSES`` classifies every setting; a test keeps both lists equal.
MONITORING_ONLY_SETTINGS = frozenset(
    {
        "console_table",
        "console_precision_recall",
        "fixed_threshold_bps",
        "metric_max_rows",
        "monitor_max_rows",
        "monitor_diagnostics_every_checks",
        "monitor_xs_ic_every_checks",
        "monitor_xs_ic_min_symbols",
        "health_gap_ratio_warn",
        "health_gap_ratio_severe",
        "health_variance_collapse_ratio",
        "health_plateau_rounds",
        "health_improvement_rel_tol",
        "health_min_iterations",
        "health_min_available_ram_gib",
        "health_min_free_disk_gib",
    }
)
EXPERIMENT_CONTROL_SOURCE_FILES = (
    "src/crypto_ai/phase7/hardening.py",
    # CHANGED BY CLAUDE (2026-11-08): the definition of the descriptive LONG / SHORT diagnostics.
    "src/crypto_ai/phase7/action_metrics.py",
    # Fit acceptance rules must invalidate resume when their implementation changes.
    "src/crypto_ai/phase7/fit_boundary.py",
    "src/crypto_ai/phase7/admission.py",
    "src/crypto_ai/phase7/run_contract.py",
    "src/crypto_ai/phase7/result_integrity.py",
    "src/crypto_ai/phase7/selection_chronology.py",
    "src/crypto_ai/phase7/result_ledger.py",
    "src/crypto_ai/phase7/result_publication.py",
    "src/crypto_ai/phase7/experiment_identity.py",
)


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def experiment_control_identity(
    hardening_settings: Mapping[str, Any],
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Hash the control-plane source files plus the active settings. Missing files fail closed."""

    root = repository_root.resolve() if repository_root is not None else Path(__file__).parents[3]
    records = []
    for relative in sorted(set(EXPERIMENT_CONTROL_SOURCE_FILES)):
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"experiment-control source file is missing: {relative}")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        records.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest()})
    # OLD CODE (kept for reference): "hardening_settings": dict(hardening_settings),
    identity = {
        "algorithm": EXPERIMENT_CONTROL_ALGORITHM,
        "files": records,
        "hardening_settings": {
            key: value
            for key, value in dict(hardening_settings).items()
            if key not in MONITORING_ONLY_SETTINGS
        },
        "monitoring_only_settings_excluded": sorted(MONITORING_ONLY_SETTINGS),
    }
    return {**identity, "manifest_sha256": _digest(identity)}
