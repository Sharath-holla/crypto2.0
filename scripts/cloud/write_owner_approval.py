#!/usr/bin/env python3
"""Show, then (only with --confirm) write the owner approval for ONE Phase 7A step.

ADDED BY CLAUDE (2026-11-13). The binding is computed by the production
``run_contract.approval_binding`` from the REAL staged data and current source (Gold manifest,
sidecar, digests, spec, fold, memory profile and, for training, the VALIDATED record), so an
approval can never name anything other than what will actually run. Without ``--confirm`` it
only prints the binding for the owner to read. The owner's name, deadline and cost ceiling must
come from the owner's own message; this script never invents them.

  uv run python scripts/cloud/write_owner_approval.py --mode prepare \\
      --owner "<owner name>" --deadline 2026-11-14T18:00:00Z --cost-ceiling 5 --currency USD \\
      --output "$CRYPTO2_LOCAL/evidence/approval-prepare.json" [--confirm]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def build(args: argparse.Namespace) -> dict:
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.run_contract import approval_binding

    config = load_phase7_config(args.config)
    first = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )[0]
    deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    if deadline.utcoffset() is None or deadline.utcoffset().total_seconds() != 0:
        raise SystemExit("deadline must be UTC (suffix Z)")
    if deadline <= datetime.now(UTC):
        raise SystemExit("deadline is in the past")
    if not args.cost_ceiling > 0:
        raise SystemExit("cost ceiling must be positive")
    return {
        "schema": "phase7_owner_smoke_approval_v1",
        "status": "APPROVED",
        "owner": args.owner,
        "mode": args.mode,
        "binding": approval_binding(config, args.spec_id, first.fold_id, mode=args.mode),
        "stop_deadline_utc": deadline.isoformat(),
        "cost_ceiling": args.cost_ceiling,
        "cost_currency": args.currency,
        "scope": f"ONE {args.mode} run of {args.spec_id} on {first.fold_id}; nothing else",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["prepare", "train"], required=True)
    parser.add_argument("--spec-id", default="architecture-G0-A6-60m-raw")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--deadline", required=True, help="UTC, e.g. 2026-11-14T18:00:00Z")
    parser.add_argument("--cost-ceiling", type=float, required=True)
    parser.add_argument("--currency", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase7/research_core20_primary_v1.toml")
    )
    parser.add_argument("--confirm", action="store_true", help="write the file (owner-approved)")
    args = parser.parse_args(argv)
    approval = build(args)
    print(json.dumps(approval, indent=1, sort_keys=True))
    if not args.confirm:
        print("NOT WRITTEN: re-run with --confirm only after the owner approves this binding.")
        return 0
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing approval: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(approval, indent=1, sort_keys=True), encoding="utf-8")
    print(f"WRITTEN: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
