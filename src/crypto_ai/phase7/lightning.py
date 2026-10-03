#!/usr/bin/env python3
"""Lightning entrypoint for Phase 7A; delegates to the provider-neutral runner."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from crypto_ai.phase7.phase7a import CONFIG_PATH, pipeline_dispatcher
from crypto_ai.phase7.preflight import build_preflight_report

REQUIRED_RUNTIME_VARIABLES = (
    "PHASE7_DATA_ROOT",
    "PHASE7_GOLD_ROOT",
    "PHASE7_ARTIFACT_ROOT",
    "PHASE7_CACHE_ROOT",
    "PHASE7_CHECKPOINT_ROOT",
    "PHASE7_MODEL_ROOT",
    "PHASE7_REPORT_ROOT",
    "PHASE7_LOG_ROOT",
    "PHASE7_LGBM_DEVICE",
    "PHASE7_CACHE_MODE",
)


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        return pipeline_dispatcher().main()
    missing = [name for name in REQUIRED_RUNTIME_VARIABLES if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "Lightning Phase 7A runtime variables are required: " + ", ".join(missing)
        )
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--stage")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args, _ = parser.parse_known_args()
    if args.stage == "train":
        validation_path = os.environ.get("PHASE7_GOLD_VALIDATION_REPORT", "").strip()
        report = build_preflight_report(
            args.config,
            gold_validation_report=Path(validation_path) if validation_path else None,
        )
        if report["status"] != "PASS":
            raise RuntimeError(
                "Lightning preflight failed: " + "; ".join(report["blocking_errors"])
            )
    return pipeline_dispatcher().main()


if __name__ == "__main__":
    raise SystemExit(main())
