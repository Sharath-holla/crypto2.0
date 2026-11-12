"""Portable content identities; reads manifests and source, never trains or builds a cache."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7.context_sidecar import SIDECAR_ENV, read_sidecar
from crypto_ai.phase7.experiment_identity import experiment_control_identity
from crypto_ai.phase7.hardening import current_config
from crypto_ai.phase7.preparation_identity import preparation_source_identity
from crypto_ai.phase7.result_publication import selection_protocol_identity
from crypto_ai.phase7.training import scientific_source_identity


def identity_summary(gold_manifest: Path, sidecar: Path) -> dict[str, str]:
    """Require explicit, matching frozen inputs; paths are absent from the digest output."""
    manifest = read_sidecar(sidecar)
    gold_sha = file_sha256(gold_manifest)
    if manifest["identity"]["gold_manifest_sha256"] != gold_sha:
        raise ValueError("SIDECAR_GOLD_IDENTITY_MISMATCH")
    previous = os.environ.get(SIDECAR_ENV)
    try:
        os.environ[SIDECAR_ENV] = str(sidecar)
        science = scientific_source_identity()["manifest_sha256"]
    finally:
        if previous is None:
            os.environ.pop(SIDECAR_ENV, None)
        else:
            os.environ[SIDECAR_ENV] = previous
    return {
        "PREPARATION_DIGEST": preparation_source_identity()["manifest_sha256"],
        "SCIENTIFIC_SOURCE_DIGEST": science,
        "EXPERIMENT_CONTROL_DIGEST": experiment_control_identity(asdict(current_config()))[
            "manifest_sha256"
        ],
        "SELECTION_PROTOCOL_DIGEST": selection_protocol_identity()["selection_protocol_sha256"],
        "SIDECAR_SHA": file_sha256(sidecar),
        "GOLD_MANIFEST_SHA": gold_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-manifest", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--expect", type=Path, help="Require exact match with a saved JSON summary")
    args = parser.parse_args()
    result = identity_summary(args.gold_manifest, args.sidecar)
    if args.expect and json.loads(args.expect.read_text()) != result:
        raise ValueError("SOURCE_TRANSFER_IDENTITY_MISMATCH")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
