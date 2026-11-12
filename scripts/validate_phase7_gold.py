#!/usr/bin/env python3
"""Read-only, fail-closed validation of a migrated Phase 7A Gold dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai.phase7.artifacts import atomic_json
from crypto_ai.phase7.gold_validation import validate_phase7_gold


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-root", type=Path, required=True)
    parser.add_argument(
        "--skip-file-hashes",
        action="store_true",
        help="Skip partition SHA-256 checks (not acceptable for the final migration gate).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional immutable JSON report used by the Phase 7A preflight gate.",
    )
    args = parser.parse_args()
    if args.output is not None and args.output.resolve().is_relative_to(args.gold_root.resolve()):
        parser.error("validation output must be outside immutable Gold")
    report = validate_phase7_gold(
        args.gold_root,
        verify_hashes=not args.skip_file_hashes,
    )
    if args.output is not None:
        atomic_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
