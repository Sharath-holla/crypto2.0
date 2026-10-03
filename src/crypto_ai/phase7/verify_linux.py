"""Linux software gate only: no Gold scan, backend smoke or production fit."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from crypto_ai.phase7.config import PathConfig
from crypto_ai.phase7.preflight import build_preflight_report
from crypto_ai.phase7.runtime import RuntimePaths


def verify_linux(repository: Path, output_root: Path) -> dict[str, Any]:
    if sys.platform != "linux":
        return {"status": "FAIL", "linux_validation": "NOT RUN", "reason": "Linux required"}
    runtime = RuntimePaths.resolve(PathConfig())
    output = output_root.resolve()
    for protected in (
        runtime.data_root,
        runtime.gold_root,
        runtime.model_root,
        runtime.report_root,
        runtime.checkpoint_root,
    ):
        protected = protected.resolve()
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError("software verification output overlaps protected input/artifact roots")
    root = output_root.resolve() / f"software-gate-{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    junit = root / "pytest.xml"
    commands = [
        [
            "uv",
            "run",
            "pytest",
            "-q",
            "--junitxml",
            str(junit),
            "--basetemp",
            str(root / "tmp"),
            "-o",
            f"cache_dir={root / 'cache'}",
        ],
        ["uv", "run", "ruff", "check", "src/crypto_ai", "scripts", "tests"],
        ["uv", "run", "ruff", "format", "--check", "src/crypto_ai", "scripts", "tests"],
        ["uv", "lock", "--check"],
        ["uv", "run", "python", "-m", "compileall", "-q", "src/crypto_ai", "scripts", "tests"],
        ["git", "diff", "--check"],
    ]
    environment = dict(os.environ)
    environment.pop("PHASE7_ALLOW_CLOUD_RESEARCH", None)
    environment["PHASE7_LGBM_DEVICE"] = "cpu"
    results = []
    for command in commands:
        outcome = subprocess.run(
            command, cwd=repository, env=environment, capture_output=True, text=True, check=False
        )
        results.append(
            {
                "command": command,
                "returncode": outcome.returncode,
                "stdout": outcome.stdout,
                "stderr": outcome.stderr,
            }
        )
    try:
        cases = ET.parse(junit).getroot().findall(".//testcase")
        bash = [case for case in cases if "test_log_rotation" in case.get("classname", "")]
        bash_passed = len(bash) == 5 and all(
            not any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
            for case in bash
        )
    except (OSError, ET.ParseError):
        bash_passed = False
    try:
        preflight = build_preflight_report(
            repository / "configs/phase7/research_core20_primary_v1.toml",
            create_outputs=False,
            run_backend_smoke=False,
            verification_only=True,
        )
    except (OSError, ValueError) as exc:
        preflight = {"status": "FAIL", "error": str(exc)}
    passed = all(item["returncode"] == 0 for item in results) and bash_passed
    passed = passed and preflight["status"] == "PASS"
    return {
        "status": "PASS" if passed else "FAIL",
        "linux_validation": "PASS" if passed else "FAIL",
        "training_ready": False,
        "bash_rotation_tests": "PASS" if bash_passed else "FAIL",
        "checks": results,
        "preflight": preflight,
        "junit": str(junit),
        "actual_gold_byte_validation": "NOT RUN",
        "gpu_smoke_test": "NOT RUN",
        "cpu_gpu_equivalence": "NOT RUN",
        "production_training": "NOT RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path(".pytest-linux-verification"))
    args = parser.parse_args()
    result = verify_linux(args.repository.resolve(), args.output_root)
    concise = dict(result)
    concise["checks"] = [
        {key: value for key, value in check.items() if key not in {"stdout", "stderr"}}
        for check in result.get("checks", [])
    ]
    if result["status"] != "PASS":
        concise["failures"] = [
            {
                "command": check["command"],
                "stderr_tail": check["stderr"][-2000:],
                "stdout_tail": check["stdout"][-2000:],
            }
            for check in result.get("checks", [])
            if check["returncode"]
        ]
    print(json.dumps(concise, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
