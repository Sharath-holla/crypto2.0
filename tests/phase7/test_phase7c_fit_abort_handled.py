"""CHANGED BY CLAUDE (2026-11-05, Phase 7C finding N-02).

FitAbortedError is raised inside the LightGBM callback when ``abort_after_worse_checks`` fires. The
training loop must catch it around ``_run_one`` and stop cleanly (structural check: the full loop
needs real fold data, which unit tests must not read).
"""

from __future__ import annotations

import ast
from pathlib import Path

TRAINING = Path(__file__).resolve().parents[2] / "src/crypto_ai/phase7/training.py"


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    node = handler.type
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple):
        return {item.id for item in node.elts if isinstance(item, ast.Name)}
    return set()


def test_run_one_call_is_guarded_against_fit_abort() -> None:
    tree = ast.parse(TRAINING.read_text())
    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        calls_run_one = any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "_run_one"
            for statement in node.body
            for inner in ast.walk(statement)
        )
        if calls_run_one and any("FitAbortedError" in _handler_names(h) for h in node.handlers):
            guarded = True
    assert guarded, "FitAbortedError must be handled around _run_one"


def test_partial_summary_names_the_aborted_spec() -> None:
    assert '"aborted_fit"' in TRAINING.read_text()


def test_report_records_the_hardening_settings_it_ran_under() -> None:
    """N-03: pilot/gate/abort settings sit outside the frozen config hash; reports record them."""
    assert '"hardening_config": asdict(current_config())' in TRAINING.read_text()
