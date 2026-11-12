from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

BRANCH = "integration/aiventra-crypto-os"
SOURCE_BRANCH = "phase7a-pre-lightning-hardening-20261003"
SOURCE_HEAD = "24dd8148af8cc1db4827dd40d2754d5ec1846ee6"
GOLD_ID = "gold-phase7-0cbf2910e8d96c9d19826598"
CONFIG_HASH = "93f987736b1a79d26b773957"
RUN_ID = "phase7a-core20-primary-" + CONFIG_HASH


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def require_branch(root: Path) -> None:
    if git(root, "branch", "--show-current") != BRANCH:
        raise PermissionError("Integration execution is allowed only on " + BRANCH)
    if git(root, "rev-parse", SOURCE_BRANCH) != SOURCE_HEAD:
        raise PermissionError("The scientific source branch changed; owner review required")
    if git(
        root,
        "diff",
        "--name-only",
        SOURCE_HEAD,
        "--",
        "src/crypto_ai",
        "configs",
        "scripts/run_phase7a_pipeline.py",
    ):
        raise PermissionError("Scientific source/configuration changed; execution refused")


@dataclass(frozen=True)
class CryptoPaths:
    repo: Path
    persistent: Path
    gold: Path
    data: Path
    historical: Path
    checkpoints: Path
    cache: Path
    models: Path
    reports: Path
    logs: Path
    verification: Path
    runtime: Path

    @classmethod
    def from_environment(cls) -> CryptoPaths:
        repo = Path(
            os.environ.get("CRYPTO_REPO_ROOT", Path(__file__).resolve().parents[2])
        ).resolve()
        persistent = Path(
            os.environ.get("CRYPTO_PERSISTENT_ROOT", repo / "local_artifacts")
        ).resolve()

        def path(variable, default):
            return Path(os.environ.get(variable, default)).expanduser().resolve()

        historical = path("CRYPTO_HISTORICAL_ROOT", persistent / "phase7")
        result = cls(
            repo,
            persistent,
            path("CRYPTO_GOLD_ROOT", repo / "data/gold/phase7a_core20_primary_v1"),
            path("CRYPTO_PHASE7_DATA_ROOT", repo / "data/phase7"),
            historical,
            path("CRYPTO_CHECKPOINT_ROOT", historical / "checkpoints"),
            path("CRYPTO_CACHE_ROOT", historical / "prepared_cache"),
            path("CRYPTO_MODEL_ROOT", historical / "models"),
            path("CRYPTO_REPORT_ROOT", historical / "reports"),
            path("CRYPTO_LOG_ROOT", historical / "logs"),
            path("CRYPTO_VERIFICATION_ROOT", historical / "verification"),
            path("CRYPTO_CONTROL_ROOT", persistent / "aiventra-control"),
        )
        if any(
            result.runtime.is_relative_to(protected) or protected.is_relative_to(result.runtime)
            for protected in (
                result.gold,
                result.data,
                result.checkpoints,
                result.cache,
                result.models,
                result.reports,
                result.logs,
                result.verification,
            )
        ):
            raise ValueError("Control runtime must not overlap protected scientific roots")
        return result

    def engine_environment(self) -> dict[str, str]:
        return {
            "PHASE7_REPOSITORY_ROOT": str(self.repo),
            "PHASE7_DATA_ROOT": str(self.data.parent),
            "PHASE7_GOLD_ROOT": str(self.gold),
            "PHASE7_ARTIFACT_ROOT": str(self.historical),
            "PHASE7_CHECKPOINT_ROOT": str(self.checkpoints),
            "PHASE7_CACHE_ROOT": str(self.cache),
            "PHASE7_MODEL_ROOT": str(self.models),
            "PHASE7_REPORT_ROOT": str(self.reports),
            "PHASE7_LOG_ROOT": str(self.logs),
        }
