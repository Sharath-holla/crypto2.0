#!/usr/bin/env python3
"""Report or explicitly remove unreferenced Phase 7A prepared-cache entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_ai.phase7.prepared_cache import (
    cache_size_report,
    cleanup_cache_entries,
    referenced_cache_ids,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, action="append", default=[])
    parser.add_argument("--artifact-root", type=Path, action="append", default=[])
    parser.add_argument("--offline", action="store_true", help="Confirm training is stopped.")
    parser.add_argument(
        "--remove",
        dest="cache_ids",
        action="append",
        default=[],
        metavar="CACHE_ID",
        help="Exact cache ID to remove; may be repeated. Referenced IDs are refused.",
    )
    args = parser.parse_args()
    if args.cache_ids and (not args.offline or not args.checkpoint_root or not args.artifact_root):
        parser.error("cleanup requires --offline and all active checkpoint/artifact roots")
    roots = tuple(args.checkpoint_root + args.artifact_root)
    protected = referenced_cache_ids(*roots)
    removed = (
        cleanup_cache_entries(
            args.cache_root,
            tuple(args.cache_ids),
            reference_roots=roots,
            offline=args.offline,
        )
        if args.cache_ids
        else []
    )
    print(
        json.dumps(
            {
                "cache": cache_size_report(args.cache_root),
                "protected_cache_ids": sorted(protected),
                "removed_cache_ids": removed,
                "automatic_eviction": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
