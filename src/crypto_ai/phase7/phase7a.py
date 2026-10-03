"""Canonical Phase 7A selection and repository-aware dispatch, without fits on import."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crypto_ai.phase7.config import Phase7Config
from crypto_ai.phase7.training import ExperimentSpec, phase7_experiment_specs

CONFIG_PATH = Path("configs/phase7/research_core20_primary_v1.toml")


def primary_specs(config: Phase7Config) -> tuple[ExperimentSpec, ...]:
    specs = tuple(item for item in phase7_experiment_specs(config) if item.feature_group == "A6")
    expected = set()
    for horizon in (15, 30, 60, 120):
        for target in ("raw", "volatility_normalized"):
            for architecture, balance, symbol_id in (
                ("G0", True, False),
                ("C0", True, False),
                ("P0", False, False),
                ("H0", True, False),
                ("G0", True, True),
                ("G0", False, False),
            ):
                expected.add((architecture, horizon, target, balance, symbol_id))
    actual = {
        (s.architecture, s.horizon_minutes, s.target_type, s.symbol_balanced, s.explicit_symbol_id)
        for s in specs
    }
    if len(specs) != 48 or len({s.name for s in specs}) != 48 or actual != expected:
        raise ValueError(
            "Phase 7A canonical primary set must contain exactly the approved 48 variants"
        )
    if any(s.name.startswith(("feature-ablation-", "htf-control-")) for s in specs):
        raise ValueError("Deferred controls leaked into the primary set")
    return specs


def select_one_spec(config: Phase7Config, spec_id: str) -> ExperimentSpec:
    matches = [item for item in primary_specs(config) if item.name == spec_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or deferred canonical primary spec: {spec_id}")
    return matches[0]


def enumerate_specs(config: Phase7Config) -> dict[str, Any]:
    primary = {item.name for item in primary_specs(config)}
    records = []
    for item in phase7_experiment_specs(config):
        classification = (
            "PRIMARY_A6"
            if item.name in primary
            else "DEFERRED_HTF"
            if item.name.startswith("htf-control-")
            else "DEFERRED_ABLATIONS"
        )
        records.append(
            {
                "spec_id": item.name,
                **asdict(item),
                "research_view": "CORE",
                "classification": classification,
            }
        )
    return {
        "specs": records,
        "counts": {
            kind: sum(row["classification"] == kind for row in records)
            for kind in ("PRIMARY_A6", "DEFERRED_ABLATIONS", "DEFERRED_HTF")
        },
        "total": len(records),
    }


def pipeline_dispatcher() -> Any:
    """Resolve the preserved repository runner by file, not sys.path/scripts imports.

    The scientific workspace requires configs/history/source-stage artifacts. An
    installed wheel alone is deliberately insufficient; set PHASE7_REPOSITORY_ROOT
    when the editable install's repository is not the desired reviewed checkout.
    """
    root = Path(os.environ.get("PHASE7_REPOSITORY_ROOT", Path(__file__).parents[3])).resolve()
    path = root / "scripts" / "run_phase7a_pipeline.py"
    if not path.is_file():
        raise RuntimeError("Phase 7A requires a reviewed repository; set PHASE7_REPOSITORY_ROOT")
    spec = importlib.util.spec_from_file_location("crypto_ai_phase7a_repository_dispatch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the Phase 7A repository dispatcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
