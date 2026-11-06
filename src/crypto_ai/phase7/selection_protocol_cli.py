"""Generate the frozen selection-chronology protocol from the REAL canonical fold calendar.

CHANGED BY CLAUDE (2026-11-06, smoke-readiness closure) - new file. Read-only on data: it reads the
Phase 7 config, plans the 16 folds (no market data), and writes one immutable JSON file. A second
run with identical content is a no-op; different content is refused (``PROTOCOL_IMMUTABLE``).

    python -m crypto_ai.phase7.selection_protocol_cli
        [--config configs/phase7/research_core20_primary_v1.toml]
        [--output configs/research/phase7_selection_chronology_v1.json]

Roles (decided here, BEFORE any model result exists):
  * folds 0-9  DEVELOPMENT  (fit, early stopping, comparison, predeclared selection)
  * folds 10-15 EVALUATION  (precommitted spec only; TEST windows start at/after the last
                             development TEST end and overlap no development segment)
  * every fold may be reported DESCRIPTIVELY; none of that is independent evidence by itself.
  * smoke: fold 0 only, engineering plumbing, no scientific claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.selection_chronology import (
    DESCRIPTIVE_REPORT,
    build_selection_protocol,
    fold_calendar,
    write_protocol,
)

DEFAULT_CONFIG = Path("configs/phase7/research_core20_primary_v1.toml")
DEFAULT_OUTPUT = Path("configs/research/phase7_selection_chronology_v1.json")
PRIMARY_SPEC = "architecture-G0-A6-60m-raw"
DEVELOPMENT_COUNT = 10
SELECTION_POLICY_VERSION = "phase7_selection_policy_v1"


def build(config_path: Path) -> dict:
    config = load_phase7_config(config_path)
    plans = plan_folds(
        config.data_start,
        config.research_cutoff,
        config.prospective_holdout_start,
        config.schedule,
    )
    if len(plans) != 16:
        raise SystemExit(f"expected 16 canonical folds, planned {len(plans)}")
    ids = [plan.fold_id for plan in plans]
    modes = {
        "smoke": {
            "purpose": "REGRESSION_PLUMBING_AND_PIPELINE_SMOKE",
            "folds": [ids[0]],
            "spec": PRIMARY_SPEC,
            "backend": "cpu",
            "metric_class": "DEVELOPMENT_METRIC",
            "scientific_claims_allowed": [],
        },
        "pilot": {
            "purpose": "PRECOMMITTED_SINGLE_SPEC_WALK_FORWARD",
            "spec": PRIMARY_SPEC,
            "development_supporting_folds": ids[:DEVELOPMENT_COUNT],
            "evaluation_supporting_folds": ids[DEVELOPMENT_COUNT:],
            "descriptive_only_folds": [],
            "claims_allowed": [
                "development folds: DEVELOPMENT_METRIC (descriptive)",
                "evaluation folds: INDEPENDENT_EVALUATION_METRIC for the precommitted spec only",
            ],
            "default_use_of_all_16_folds": DESCRIPTIVE_REPORT,
        },
    }
    return build_selection_protocol(
        fold_calendar(plans),
        development_fold_ids=ids[:DEVELOPMENT_COUNT],
        evaluation_fold_ids=ids[DEVELOPMENT_COUNT:],
        selection_policy_version=SELECTION_POLICY_VERSION,
        precommitted_specs=[PRIMARY_SPEC],
        modes=modes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    protocol = build(args.config)
    write_protocol(args.output, protocol)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "protocol_sha256": protocol["protocol_sha256"],
                "development_folds": len(protocol["development_folds"]),
                "evaluation_folds": len(protocol["evaluation_folds"]),
                "overlap_rows": len(protocol["overlap_matrix"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
