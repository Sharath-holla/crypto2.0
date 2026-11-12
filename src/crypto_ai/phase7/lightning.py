#!/usr/bin/env python3
"""Lightning entrypoint for Phase 7A; delegates to the provider-neutral runner."""

from __future__ import annotations

import os
import sys

from crypto_ai.phase7.phase7a import pipeline_dispatcher

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
    # The canonical dispatcher now owns the single train-stage preflight for
    # BOTH the direct CLI and this wrapper. Do not smoke-fit a backend twice.
    return pipeline_dispatcher().main()


if __name__ == "__main__":
    raise SystemExit(main())
