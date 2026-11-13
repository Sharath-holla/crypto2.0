"""Content identity of the code that can change PREPARED MATRICES (cache validity).

CHANGED BY CLAUDE (2026-11-06, smoke-readiness closure) - new file, standard library only.

Before: the prepared-cache key hashed all of ``TRAINING_CRITICAL_SOURCE_FILES`` (34 whole files,
including the monolithic ``training.py``, ``economics.py``, ``hardening``-adjacent code). Editing a
reporting line or the Cal-B threshold rule therefore invalidated every multi-GB matrix cache even
though no matrix value could change.

Now the cache key depends on:

* WHOLE FILES that decide rows, feature values, targets, membership, fold slicing, context, dtypes
  and ordering (data/feature/label/fold/universe/gold/cache-format modules), and
* SPECIFIC FUNCTIONS (plus the same-module helpers they call) from the two files that mix matrix
  preparation with fitting/evaluation: ``training.py`` and ``models.py``,
* the manually bumped :data:`PREPARATION_SEMANTICS_VERSION`.

Source text is normalised with the tokenizer (comments and blank lines ignored), so formatting or
comment-only edits do not invalidate a cache but any token change in a listed function does.
Economics, hardening, selection, ledger, reporting and documentation are deliberately absent: they
change the resume/evaluation identity (``scientific_source_identity`` still hashes them), not the
matrices.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import tokenize
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PREPARATION_SEMANTICS_VERSION = "phase7_preparation_semantics_v2_feature_context_sidecar"
ALGORITHM = "phase7_preparation_source_manifest_v1"

PREPARATION_SOURCE_FILES: tuple[str, ...] = (
    "configs/data/binance.toml",
    "configs/data_quality/default.toml",
    "configs/phase7/research_core20_primary_v1.toml",
    "configs/phase7/research_v1.toml",
    "src/crypto_ai/data/ingestion/manifest.py",
    "src/crypto_ai/data/schema.py",
    "src/crypto_ai/data/storage/__init__.py",
    "src/crypto_ai/data/storage/parquet.py",
    "src/crypto_ai/domain/__init__.py",
    "src/crypto_ai/domain/candle.py",
    "src/crypto_ai/features/baseline.py",
    "src/crypto_ai/phase4/asof.py",
    "src/crypto_ai/phase4/features.py",
    "src/crypto_ai/phase4_1/features.py",
    "src/crypto_ai/phase5/config.py",
    "src/crypto_ai/phase5/folds.py",
    "src/crypto_ai/phase6/config.py",
    "src/crypto_ai/phase6/features.py",
    "src/crypto_ai/phase6/labels.py",
    "src/crypto_ai/phase7/acquisition.py",
    "src/crypto_ai/phase7/config.py",
    "src/crypto_ai/phase7/cross_section.py",
    "src/crypto_ai/phase7/context_sidecar.py",
    "src/crypto_ai/phase7/features.py",
    "src/crypto_ai/phase7/folds.py",
    "src/crypto_ai/phase7/gold.py",
    "src/crypto_ai/phase7/gold_validation.py",
    # ADDED BY CLAUDE (2026-11-13): the opt-in low-memory profile can build the prepared tables
    # and matrices, so its source binds the cache identity like every other preparation module.
    "src/crypto_ai/phase7/low_memory.py",
    "src/crypto_ai/phase7/prepared_cache.py",
    "src/crypto_ai/phase7/quality.py",
    "src/crypto_ai/phase7/registry.py",
    "src/crypto_ai/phase7/segments.py",
    # ADDED BY CLAUDE (2026-11-13): opt-in chronological batch staging of fold slicing.
    "src/crypto_ai/phase7/staged_fold.py",
    "src/crypto_ai/phase7/targets.py",
    "src/crypto_ai/phase7/universe.py",
)
# (file, root function/class names). The same-module closure of each root is hashed too.
PREPARATION_FUNCTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "src/crypto_ai/phase7/training.py",
        (
            "_load_fold_rows",
            "_load_fold_context_source",
            "_finite",
            "_prepare_training_segments",
            "_prediction_target",
            "causal_descriptor_identity",
            "_prepared_cache_identity",
        ),
    ),
    ("src/crypto_ai/phase7/models.py", ("prepare_architecture_inputs",)),
)


def _normalised(source: str) -> str:
    """Token stream without comments / blank lines: stable under formatting-only edits."""

    parts: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}:
            continue
        parts.append(f"{tokenize.tok_name[token.type]}:{token.string}")
    return "\n".join(parts)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _top_level(tree: ast.Module) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            nodes[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nodes[node.target.id] = node
    return nodes


def _closure(nodes: Mapping[str, ast.AST], roots: Sequence[str]) -> list[str]:
    missing = [name for name in roots if name not in nodes]
    if missing:
        raise RuntimeError(f"preparation-critical symbol(s) not found: {missing}")
    seen: list[str] = []
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.append(name)
        for child in ast.walk(nodes[name]):
            if isinstance(child, ast.Name) and child.id in nodes and child.id not in seen:
                stack.append(child.id)
    return sorted(seen)


def _segment(lines: list[str], node: ast.AST) -> str:
    start = node.lineno
    for decorator in getattr(node, "decorator_list", []):
        start = min(start, decorator.lineno)
    return "\n".join(lines[start - 1 : node.end_lineno])


def preparation_source_identity(
    repository_root: Path | None = None,
    *,
    files: Sequence[str] | None = None,
    functions: Sequence[tuple[str, Sequence[str]]] | None = None,
) -> dict[str, Any]:
    """Identity of everything that can change a prepared matrix. Missing inputs fail closed."""

    root = (repository_root or Path(__file__).parents[3]).resolve()
    file_records = []
    for relative in sorted(set(PREPARATION_SOURCE_FILES if files is None else files)):
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"preparation-critical source file is missing: {relative}")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        file_records.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest()})
    function_records = []
    for relative, roots in PREPARATION_FUNCTIONS if functions is None else functions:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"preparation-critical source file is missing: {relative}")
        source = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
        nodes = _top_level(ast.parse(source))
        lines = source.split("\n")
        for name in _closure(nodes, list(roots)):
            function_records.append(
                {
                    "path": relative,
                    "symbol": name,
                    "sha256": _digest(_normalised(_segment(lines, nodes[name]))),
                }
            )
    identity = {
        "algorithm": ALGORITHM,
        "semantics_version": PREPARATION_SEMANTICS_VERSION,
        "files": file_records,
        "functions": function_records,
    }
    manifest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {**identity, "manifest_sha256": manifest}
