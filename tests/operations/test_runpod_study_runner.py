"""ADDED BY CLAUDE (2026-11-14): RunPod study runner planning, scope refusal, dry run."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "study_runner", ROOT / "scripts/runpod/study_runner.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

ARCHS = ("G0-unbalanced", "C0", "G0", "H0", "P0", "G0-symbol-id")


def _ledger(folds=("fold-000-a", "fold-001-b"), done=()) -> dict:
    runs = {}
    for fold in folds:
        for horizon in (15, 60):
            for arch in ARCHS:
                name = f"architecture-{arch}-A6-{horizon}m-raw"
                runs[f"{fold}|{name}"] = {
                    "fold_id": fold,
                    "spec": name,
                    "cache_group": f"{fold}|{horizon}m|raw",
                    "status": "COMPLETE_VERIFIED" if (fold, name) in done else "PENDING",
                }
    return {"runs": runs}


def test_groups_are_chronological_and_specs_in_fixed_order() -> None:
    groups = runner.cache_groups(_ledger())
    assert [g["cache_group"] for g in groups] == [
        "fold-000-a|15m|raw",
        "fold-000-a|60m|raw",
        "fold-001-b|15m|raw",
        "fold-001-b|60m|raw",
    ]
    assert [runner._arch(r["spec"]) for r in groups[0]["runs"]] == list(runner.SPEC_ORDER)


def test_verified_runs_are_skipped_on_resume() -> None:
    done = {
        ("fold-000-a", "architecture-G0-A6-60m-raw"),
        ("fold-000-a", "architecture-C0-A6-60m-raw"),
    }
    group = [
        g for g in runner.cache_groups(_ledger(done=done)) if g["cache_group"].endswith("60m|raw")
    ][0]
    assert "architecture-G0-A6-60m-raw" not in group["pending"]
    assert len(group["pending"]) == 4


def test_fold_filter() -> None:
    groups = runner.cache_groups(_ledger(), folds=["fold-001-b"])
    assert {g["fold_id"] for g in groups} == {"fold-001-b"}


def test_installed_admission_refuses_other_folds_and_dry_run_starts_nothing(
    tmp_path, monkeypatch, capsys
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(_ledger()))
    monkeypatch.setattr(runner, "supported_folds", lambda first: {first})
    common = ["--ledger", str(ledger), "--first-fold", "fold-000-a"]
    run = ["run", *common, "--owner", "x", "--deadline", "2099-01-01T00:00:00Z"]
    run += ["--cost-ceiling", "1", "--currency", "USD", "--hourly-cost", "1"]
    assert runner.main(run) == 2  # fold-001-b refused even with --execute absent
    assert "fold-001-b" in capsys.readouterr().out
    assert runner.main([*run, "--fold", "fold-000-a"]) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_real_installed_entrypoint_has_no_fold_argument_yet() -> None:
    # freeze v3: only Fold 0 is admissible; v4 must add --fold-id deliberately.
    assert runner.supported_folds("fold-000-a0e9a4f72689") == {"fold-000-a0e9a4f72689"}
