"""Research/training code must never import order-capable legacy trading code (defect 20)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_MODULE_PARTS = ("live_trader", "coinswitch", "main_trader", "dashboard")
# CHANGED BY CLAUDE (2026-11-02, finding M-08): research coverage widened beyond phase7.
RESEARCH_PATHS = (
    "src/crypto_ai/phase5",
    "src/crypto_ai/phase6",
    "src/crypto_ai/research",
    "src/crypto_ai/phase7",
    "src/crypto_ai/research_scope.py",
    "scripts/run_phase7a_pipeline.py",
    "scripts/validate_phase7_gold.py",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _research_files() -> list[Path]:
    files: list[Path] = []
    for relative in RESEARCH_PATHS:
        target = ROOT / relative
        files.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target])
    return files


def test_research_files_are_found() -> None:
    assert len(_research_files()) > 20


def test_no_research_module_imports_order_capable_code() -> None:
    offenders = {
        str(path.relative_to(ROOT)): sorted(
            module
            for module in _imported_modules(path)
            if any(part in module.lower() for part in FORBIDDEN_MODULE_PARTS)
        )
        for path in _research_files()
    }
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_order_capable_legacy_files_carry_the_legacy_header() -> None:
    """Added by Claude (2026-11-02, finding M-08)."""
    for relative in ("pipeline/live_trader.py", "pipeline/coinswitch_client.py", "main_trader.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "LEGACY – NOT USED BY RESEARCH" in text.splitlines()[0], relative
