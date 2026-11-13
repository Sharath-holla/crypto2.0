#!/usr/bin/env python3
"""Reload a saved Phase 7 model (hash-registry verified) and re-run permitted predictions.

ADDED BY CLAUDE (2026-11-13). Inference only: no fit, refit or update. Loads the model through
``models.load_model`` (refuses a file whose SHA-256 is not registered), loads the prepared cache
read-only, predicts Validation and Cal-A twice and requires bit-identical outputs. TEST is not
touched here (it is released only inside the canonical run after its selection is frozen); the
August holdout is never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase7/research_core20_primary_v1.toml")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.models import load_model
    from crypto_ai.phase7.prepared_cache import PreparedDataCache

    config = load_phase7_config(args.config)
    plan = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    model = load_model(args.model)
    entries = [p for p in args.cache_root.iterdir() if len(p.name) == 64 and p.is_dir()]
    if len(entries) != 1:
        raise SystemExit(f"expected exactly one prepared cache, found {len(entries)}")
    identity = json.loads((entries[0] / "manifest.json").read_text())["identity"]
    bundle = PreparedDataCache(args.cache_root, "read_only").load(identity, plan)
    result = {
        "model": str(args.model),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "model_identity": model.metadata.get("model_identity"),
        "architecture": model.architecture,
        "feature_count": len(model.feature_columns),
        "cache_id": bundle.cache_id,
        "predictions": {},
    }
    for name in ("validation", "calibration_a"):
        table = getattr(bundle.prepared, name)
        first, covered_first = model.predict(table)
        second, covered_second = model.predict(table)
        same = np.array_equal(first, second, equal_nan=True) and np.array_equal(
            covered_first, covered_second
        )
        result["predictions"][name] = {
            "rows": table.num_rows,
            "covered": int(np.count_nonzero(covered_first)),
            "deterministic": bool(same),
            "sha256": hashlib.sha256(np.asarray(first, dtype=np.float64).tobytes()).hexdigest(),
        }
    result["status"] = (
        "RELOAD_VERIFIED"
        if all(item["deterministic"] for item in result["predictions"].values())
        else "FAILED"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0 if result["status"] == "RELOAD_VERIFIED" else 3


if __name__ == "__main__":
    sys.exit(main())
