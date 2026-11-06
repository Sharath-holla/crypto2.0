"""CHANGED BY CLAUDE (2026-11-06, closure): research code can never reach an order-capable module.

The scan is static (AST) and transitive over ``src/crypto_ai``: no module reachable from the
Phase 7 entrypoints may import the live trader, the CoinSwitch client, the trader config or any
module whose source defines an order-placing function. A runtime guard additionally stops the
order client from existing in a research process.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FORBIDDEN_PREFIXES = (
    "main_trader",
    "main_signal",
    "pipeline.live_trader",
    "pipeline.coinswitch_client",
    "pipeline.config_trader",
    "dashboard",
    "aiventra",
    "coinswitch",
)
ORDER_MARKERS = ("place_hft_order", "cancel_hft_order", "place_order", "create_order", "new_order")


def _module_path(name: str) -> Path | None:
    base = SRC / Path(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _reachable(entry_points: list[str]) -> dict[str, Path]:
    seen: dict[str, Path] = {}
    stack = list(entry_points)
    while stack:
        name = stack.pop()
        path = _module_path(name)
        if path is None or name in seen:
            continue
        seen[name] = path
        stack.extend(item for item in _imports(path) if item.startswith("crypto_ai"))
    return seen


def _all_research_modules() -> list[str]:
    return sorted(
        ".".join(path.relative_to(SRC).with_suffix("").parts).removesuffix(".__init__")
        for path in (SRC / "crypto_ai").rglob("*.py")
    )


def test_no_crypto_ai_module_imports_an_order_capable_module() -> None:
    offenders = []
    for name in _all_research_modules():
        path = _module_path(name)
        assert path is not None
        for imported in _imports(path):
            if imported.split(".")[0] == "pipeline" or imported.startswith(FORBIDDEN_PREFIXES):
                offenders.append(f"{name} imports {imported}")
    assert offenders == []


def test_phase7_reachable_closure_contains_no_order_function() -> None:
    closure = _reachable(
        [
            "crypto_ai.phase7.training",
            "crypto_ai.phase7.pipeline",
            "crypto_ai.phase7.admission",
            "crypto_ai.phase7.benchmark_one_spec",
            "crypto_ai.phase7.preflight",
            "crypto_ai.phase7.feature_census",
        ]
    )
    assert len(closure) > 20, "the scan must actually traverse the research package"
    hits = {
        name: marker
        for name, path in closure.items()
        for marker in ORDER_MARKERS
        if marker in path.read_text()
    }
    assert hits == {}


def test_the_scan_would_catch_a_planted_live_import(tmp_path: Path) -> None:
    planted = tmp_path / "bad.py"
    planted.write_text("from pipeline.coinswitch_client import CoinSwitchClient\n")
    assert any(item.startswith("pipeline") for item in _imports(planted))


def test_order_client_refuses_to_exist_in_research_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("aiohttp")
    pytest.importorskip("cryptography")
    monkeypatch.setenv("CRYPTO_AI_RESEARCH_MODE", "1")
    try:
        module = importlib.import_module("pipeline.coinswitch_client")
    except Exception as error:  # pipeline config may need live settings; never touch them
        pytest.skip(f"order client not importable without live configuration: {error!r}")
    with pytest.raises(RuntimeError, match="RESEARCH_MODE_ORDER_CLIENT_BLOCKED"):
        module.CoinSwitchClient("not-a-real-key", "00")
