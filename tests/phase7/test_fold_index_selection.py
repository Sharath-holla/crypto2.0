"""--fold-index selects one existing canonical fold; the default is the previous Fold-0 path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7 import benchmark_one_spec
from crypto_ai.phase7.benchmark_one_spec import benchmark_plan
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.phase7a import CONFIG_PATH
from crypto_ai.phase7.run_contract import approval_binding

SPEC = "architecture-G0-A6-60m-raw"
# Identities observed in the completed real Fold-0 smoke (attempt 14) and the frozen fold plan.
FOLD0_RUN = "benchmark-only-f46d8127ce60a5dc6935201e"
PILOT = {
    0: "fold-000-a0e9a4f72689",
    5: "fold-005-2cf830b9f251",
    10: "fold-010-01be2e390a0b",
    15: "fold-015-ed49f0aadaf7",
}


@pytest.fixture(scope="module")
def config():
    return load_phase7_config(CONFIG_PATH)


def canonical_folds(config):
    return plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )


def test_default_and_index_zero_are_the_previous_fold0_plan(config, tmp_path):
    default = benchmark_plan(config, SPEC, tmp_path)
    explicit = benchmark_plan(config, SPEC, tmp_path, fold_index=0)
    assert default == explicit
    assert default["fold_id"] == canonical_folds(config)[0].fold_id == PILOT[0]
    assert Path(default["run_root"]).name == FOLD0_RUN


@pytest.mark.parametrize("index", [5, 10, 15])
def test_index_selects_exactly_that_canonical_fold_and_changes_nothing_else(
    config, tmp_path, index
):
    folds = canonical_folds(config)
    assert len(folds) == 16
    base = benchmark_plan(config, SPEC, tmp_path)
    plan = benchmark_plan(config, SPEC, tmp_path, fold_index=index)
    assert plan["fold_id"] == folds[index].fold_id == PILOT[index]
    assert Path(plan["run_root"]).name != FOLD0_RUN
    changed = {key for key in base if base[key] != plan[key]}
    assert changed == {"fold_id", "run_root"}
    assert config.configuration_hash == "93f987736b1a79d26b773957"


@pytest.mark.parametrize("bad", [-1, 16, 99, True, 1.0, "5", None])
def test_invalid_fold_index_fails_closed(config, tmp_path, bad):
    with pytest.raises(ValueError, match="UNKNOWN_CANONICAL_FOLD_INDEX"):
        benchmark_plan(config, SPEC, tmp_path, fold_index=bad)


@pytest.mark.parametrize("value", ["abc", "1.5", "16", "-1"])
def test_cli_rejects_invalid_fold_index(monkeypatch, tmp_path, value):
    argv = ["benchmark_one_spec", "--spec-id", SPEC, "--output-root", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", [*argv, "--fold-index", value])
    with pytest.raises(SystemExit) as exc:
        benchmark_one_spec.main()
    assert exc.value.code == 2


def test_cli_enumerate_refuses_a_fold(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["benchmark_one_spec", "--enumerate", "--fold-index", "5"])
    with pytest.raises(SystemExit) as exc:
        benchmark_one_spec.main()
    assert exc.value.code == 2


def test_owner_scope_accepts_only_canonical_folds(config, monkeypatch):
    monkeypatch.delenv("PHASE7_FEATURE_CONTEXT_SIDECAR", raising=False)
    for fold_id in PILOT.values():
        # Past the scope check, the next requirement (the sidecar) is what stops this fixture.
        with pytest.raises(ValueError, match="M01_FEATURE_CONTEXT_SIDECAR_REQUIRED"):
            approval_binding(config, SPEC, fold_id)
    for fold_id in ("fold-005-000000000000", "fold-016-ed49f0aadaf7", ""):
        with pytest.raises(ValueError, match="OWNER_SCOPE_REFUSED"):
            approval_binding(config, SPEC, fold_id)
    with pytest.raises(ValueError, match="OWNER_SCOPE_REFUSED"):
        approval_binding(config, "architecture-G0-A6-30m-raw", PILOT[5])
