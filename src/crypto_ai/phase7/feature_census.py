"""Read-only feature-key census: independent feature availability vs Gold keys (IA-05 / M-01).

CHANGED BY CLAUDE (2026-11-06, final architecture repair) - new file.

Gold is an inner join of feature rows and future labels, so a (symbol, feature_time) key whose every
horizon label is unavailable (gaps, terminal rows, the data cutoff) is absent from Gold. The
fold-time cross-sectional context is built from the Gold keys that remain, so peers that vanished
this way silently change the percentile ranks and market aggregates seen by the survivors, and a
timestamp where ALL peers vanish cannot be observed from Gold at all. This tool measures that loss
against an INDEPENDENT feature-key source. It never writes into Gold, never mutates anything, and
refuses to overwrite its own output.

The numeric core takes plain integer arrays so it is unit-testable without pyarrow. The command-line
wrapper reads only the ``symbol`` / ``feature_time`` key columns.

    python -m crypto_ai.phase7.feature_census --features-path F --gold-path G --output OUT.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

CENSUS_SCHEMA = "phase7_feature_key_census_v1"
_TIME_SPAN = 1 << 42  # > any epoch-millisecond value this project can hold
DEFAULT_BAR_MS = 5 * 60 * 1000
# Thresholds are PRE-DECLARED here, not tuned after looking at data.
MATERIAL_TIMESTAMP_FRACTION = 0.01  # >1% of timestamps with any peer lost
MATERIAL_PEER_LOSS_FRACTION = 0.10  # any timestamp losing >=10% of its peers
MATERIAL_MIN_PEERS = 5  # ... among timestamps that had at least this many peers


def _encode(keys: Mapping[str, np.ndarray]) -> tuple[np.ndarray, dict[str, int]]:
    codes = {symbol: index for index, symbol in enumerate(sorted(keys))}
    parts = [
        codes[symbol] * _TIME_SPAN + np.asarray(times, dtype=np.int64)
        for symbol, times in sorted(keys.items())
    ]
    flat = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)
    return np.unique(flat), codes


def _members(encoded: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    times = encoded % _TIME_SPAN
    unique, counts = np.unique(times, return_counts=True)
    return unique, counts


def census_keys(
    feature_keys: Mapping[str, np.ndarray],
    gold_keys: Mapping[str, np.ndarray],
    *,
    windows: Mapping[str, tuple[int, int]] | None = None,
    bar_ms: int = DEFAULT_BAR_MS,
    terminal_bars: int = 24,
) -> dict[str, Any]:
    """Compare the independent feature keys with the Gold keys. All times are epoch ms."""

    symbols = sorted(set(feature_keys) | set(gold_keys))
    feature_all = {s: np.asarray(feature_keys.get(s, []), dtype=np.int64) for s in symbols}
    gold_all = {s: np.asarray(gold_keys.get(s, []), dtype=np.int64) for s in symbols}
    feature_enc, codes = _encode(feature_all)
    if not len(feature_enc):
        raise ValueError("DATA_INSUFFICIENT: independent feature-key domain is empty")
    gold_enc, _ = _encode(gold_all)
    lost = feature_enc[~np.isin(feature_enc, gold_enc)]
    extra = gold_enc[~np.isin(gold_enc, feature_enc)]
    f_times, f_counts = _members(feature_enc)
    g_times, g_counts = _members(gold_enc)
    gold_at = np.zeros(len(f_times), dtype=np.int64)
    if len(g_times):
        position = np.searchsorted(g_times, f_times)
        hit = (position < len(g_times)) & (
            g_times[np.minimum(position, len(g_times) - 1)] == f_times
        )
        gold_at[hit] = g_counts[position[hit]]
    lost_peers = f_counts - gold_at
    whole = (gold_at == 0) & (f_counts > 0)
    partial = (lost_peers > 0) & ~whole
    loss_fraction = lost_peers / np.maximum(f_counts, 1)
    big = (f_counts >= MATERIAL_MIN_PEERS) & (loss_fraction >= MATERIAL_PEER_LOSS_FRACTION)
    # classify each lost key: terminal (last bars of that symbol's feature history) vs interior
    last_feature = {s: (int(t.max()) if len(t) else -1) for s, t in feature_all.items()}
    inverse = {index: symbol for symbol, index in codes.items()}
    lost_codes = lost // _TIME_SPAN
    lost_times = lost % _TIME_SPAN
    terminal = np.array(
        [
            last_feature[inverse[int(c)]] - int(t) < terminal_bars * bar_ms
            for c, t in zip(lost_codes, lost_times, strict=True)
        ],
        dtype=bool,
    )
    per_symbol = {
        s: {
            "feature_keys": int(len(np.unique(feature_all[s]))),
            "gold_keys": int(len(np.unique(gold_all[s]))),
            "lost_keys": int(np.sum(lost_codes == codes[s])),
        }
        for s in symbols
    }
    by_window: dict[str, Any] = {}
    for name, (start, end) in (windows or {}).items():
        inside = (f_times >= start) & (f_times < end)
        by_window[name] = {
            "timestamps": int(inside.sum()),
            "timestamps_with_peer_loss": int((lost_peers[inside] > 0).sum()),
            "timestamps_with_all_peers_lost": int(whole[inside].sum()),
            "lost_keys": int(((lost_times >= start) & (lost_times < end)).sum()),
        }
    timestamp_fraction = float((lost_peers > 0).mean()) if len(f_times) else 0.0
    material = bool(whole.any() or big.any() or timestamp_fraction > MATERIAL_TIMESTAMP_FRACTION)
    if len(lost) == 0:
        verdict = "NO_LOSS"
    elif material:
        verdict = "MATERIAL_LOSS_SIDECAR_REQUIRED"
    else:
        verdict = "IMMATERIAL_LOSS_RECORDED"
    return {
        "schema": CENSUS_SCHEMA,
        "read_only": True,
        "verdict": verdict,
        "feature_keys": int(len(feature_enc)),
        "gold_keys": int(len(gold_enc)),
        "lost_keys": int(len(lost)),
        "lost_terminal_keys": int(terminal.sum()),
        "lost_interior_keys": int((~terminal).sum()),
        "extra_gold_keys_not_in_features": int(len(extra)),
        "timestamps": int(len(f_times)),
        "timestamps_with_peer_loss": int((lost_peers > 0).sum()),
        "timestamps_with_partial_peer_loss": int(partial.sum()),
        "timestamps_with_one_peer_lost": int((lost_peers == 1).sum()),
        "timestamps_with_multiple_peers_lost": int((lost_peers >= 2).sum()),
        "timestamps_with_all_peers_lost": int(whole.sum()),
        "timestamps_with_material_peer_loss": int(big.sum()),
        "timestamp_loss_fraction": timestamp_fraction,
        "max_peer_loss_fraction": float(loss_fraction.max()) if len(f_times) else 0.0,
        "thresholds": {
            "timestamp_fraction": MATERIAL_TIMESTAMP_FRACTION,
            "peer_loss_fraction": MATERIAL_PEER_LOSS_FRACTION,
            "min_peers": MATERIAL_MIN_PEERS,
        },
        "per_symbol": per_symbol,
        "by_window": by_window,
    }


def canonical_parquet_paths(path: Path) -> tuple[Path, ...]:
    """Select explicit manifest references only; never discover data by walking a tree.

    Accept a manifest JSON, a dataset root with manifest.json, the Gold dataset/
    child of such a root, or one explicitly supplied Parquet file. Unreferenced
    files (including forensic recovery extras) are never candidates.
    """
    path = path.expanduser().resolve()
    if path.is_file() and path.suffix == ".parquet":
        records = [{"path": str(path)}]
        root = path.parent
    else:
        if path.is_dir():
            manifest = path / "manifest.json"
            if not manifest.is_file() and path.name == "dataset":
                manifest = path.parent / "manifest.json"
        else:
            manifest = path
        if not manifest.is_file() or manifest.suffix != ".json":
            raise ValueError(f"DATA_INSUFFICIENT: canonical manifest required at {path}")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        records = payload.get("partition_files", payload.get("partitions"))
        if not isinstance(records, list) or not records:
            raise ValueError(f"DATA_INSUFFICIENT: no canonical partitions in {manifest}")
        root = manifest.parent.resolve()
    selected = []
    for record in records:
        reference = Path(record["path"])
        resolved = reference.resolve() if reference.is_absolute() else (root / reference).resolve()
        if not reference.is_absolute() and not resolved.is_relative_to(root):
            raise ValueError("canonical partition escapes manifest root")
        if resolved.suffix != ".parquet" or resolved.name.startswith("."):
            raise ValueError(f"partial/forensic path cannot be a scientific partition: {reference}")
        if not resolved.is_file():
            raise ValueError(f"DATA_INSUFFICIENT: missing canonical partition {resolved}")
        selected.append(resolved)
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate canonical partition references")
    return tuple(selected)


def _keys_from_parquet(path: Path) -> dict[str, np.ndarray]:
    import pyarrow as pa
    import pyarrow.dataset as ds

    parts: dict[str, list[np.ndarray]] = {}
    files = canonical_parquet_paths(path)
    scanner = ds.dataset([str(p) for p in files], format="parquet").scanner(
        columns=["symbol", "feature_time"], batch_size=65_536, use_threads=False
    )
    for batch in scanner.to_batches():
        times = batch.column("feature_time").cast(pa.timestamp("ms", tz="UTC")).cast(pa.int64())
        symbols = np.asarray(batch.column("symbol").to_pylist(), dtype=object)
        values = np.asarray(times.to_numpy(zero_copy_only=False), dtype=np.int64)
        for symbol in np.unique(symbols):
            parts.setdefault(str(symbol), []).append(np.unique(values[symbols == symbol]))
    return {symbol: np.unique(np.concatenate(chunks)) for symbol, chunks in parts.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--features-path", type=Path, required=True, help="Canonical key manifest or dataset root"
    )
    parser.add_argument(
        "--gold-path",
        type=Path,
        required=True,
        help="Canonical Gold/context manifest or dataset root",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing census: {args.output}")
    result = census_keys(_keys_from_parquet(args.features_path), _keys_from_parquet(args.gold_path))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{result['verdict']}: lost {result['lost_keys']} of {result['feature_keys']} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
