"""Added by Claude (2026-11-02, finding L-07): no production invariant may rely on ``assert``."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src" / "crypto_ai"


def test_source_has_no_assert_statements() -> None:
    offenders = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.relative_to(SOURCE)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Assert)
        ]
    assert not offenders, offenders
