"""CHANGED BY CLAUDE (2026-11-06, IA-05/M-01): feature-key census and context-sensitivity tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7 import feature_census as fc
from crypto_ai.phase7.features import FOLD_CONTEXT_SOURCE_COLUMNS, build_fold_context_table

BAR = fc.DEFAULT_BAR_MS


def _keys(symbols, n):
    return {s: np.arange(n, dtype=np.int64) * BAR for s in symbols}


def test_no_loss_when_gold_matches_features():
    keys = _keys("ABCDEF", 50)
    result = fc.census_keys(keys, keys)
    assert result["verdict"] == "NO_LOSS" and result["lost_keys"] == 0


def test_completely_empty_gold_cannot_hide_all_peer_loss():
    features = _keys("ABCDEF", 100)
    result = fc.census_keys(features, {})
    assert result["lost_keys"] == 600
    assert result["timestamps_with_all_peers_lost"] == 100
    assert result["verdict"] == "MATERIAL_LOSS_SIDECAR_REQUIRED"


def test_empty_independent_source_cannot_clear_m01():
    with pytest.raises(ValueError, match="DATA_INSUFFICIENT"):
        fc.census_keys({}, {})


def test_streamed_key_reader_deduplicates_horizons_and_files(tmp_path):
    import pyarrow.parquet as pq

    table = _source("ABCDEF", 15)
    for index in range(2):
        pq.write_table(pa.concat_tables([table, table]), tmp_path / f"part-{index}.parquet")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"partitions": [{"path": f"part-{index}.parquet"} for index in range(2)]})
    )
    # Neither a preserved partial nor a tempting unreferenced .parquet may be opened.
    (tmp_path / ".dataset.parquet.forensic.partial").write_bytes(b"must not be scanned")
    (tmp_path / "unreferenced.parquet").write_bytes(b"must not be scanned")
    keys = fc._keys_from_parquet(tmp_path)
    assert set(keys) == set("ABCDEF")
    assert all(len(times) == 15 for times in keys.values())


def test_unmanifested_directory_is_not_scientific_discovery(tmp_path):
    with pytest.raises(ValueError, match="canonical manifest required"):
        fc.canonical_parquet_paths(tmp_path)


def test_manifest_cannot_promote_a_forensic_partial(tmp_path):
    path = tmp_path / ".dataset.parquet.forensic.partial"
    path.write_bytes(b"preserved")
    (tmp_path / "manifest.json").write_text(json.dumps({"partitions": [{"path": path.name}]}))
    with pytest.raises(ValueError, match="partial/forensic"):
        fc.canonical_parquet_paths(tmp_path)


def test_silver_candle_key_projection_matches_actual_feature_producer():
    from crypto_ai.phase7.config import FeatureConfig
    from crypto_ai.phase7.features import generate_multiasset_features
    from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry

    candles = synthetic_candles(rows_per_symbol=60)
    # Missing candles stay missing; feature generation preserves every remaining input key.
    candles = candles.take(pa.array([i for i in range(candles.num_rows) if i % 13]))
    result = generate_multiasset_features(
        candles, registry=synthetic_registry(), config=FeatureConfig()
    )
    projected = {
        (s, t + timedelta(minutes=5))
        for s, t in zip(
            candles["symbol"].to_pylist(), candles["open_time"].to_pylist(), strict=True
        )
    }
    actual = set(
        zip(
            result.table["symbol"].to_pylist(),
            result.table["feature_time"].to_pylist(),
            strict=True,
        )
    )
    assert actual == projected
    assert len(actual) == candles.num_rows == result.table.num_rows


def test_terminal_edge_loss_is_classified_terminal_and_immaterial():
    features = _keys("ABCDEFGHIJ", 1000)
    gold = {s: t[:-3] for s, t in features.items()}  # last 3 bars lack every label
    result = fc.census_keys(features, gold)
    assert result["lost_keys"] == 30
    assert result["lost_interior_keys"] == 0 and result["lost_terminal_keys"] == 30
    # 3 of 1000 timestamps lose ALL peers: that is exactly what Gold cannot show on its own
    assert result["timestamps_with_all_peers_lost"] == 3
    assert result["verdict"] == "MATERIAL_LOSS_SIDECAR_REQUIRED"


def test_whole_timestamp_loss_is_detected_even_though_gold_never_sees_it():
    features = _keys("ABCDEF", 100)
    gold = {s: np.delete(t, 40) for s, t in features.items()}  # interior gap hits every peer
    result = fc.census_keys(features, gold)
    assert result["timestamps_with_all_peers_lost"] == 1
    assert result["lost_interior_keys"] == 6
    assert result["verdict"] == "MATERIAL_LOSS_SIDECAR_REQUIRED"


def test_single_symbol_gap_is_partial_loss_and_immaterial_when_rare():
    features = _keys("ABCDEFGHIJKLMNOPQRST", 5000)
    gold = dict(features)
    gold["A"] = np.delete(features["A"], 2500)
    result = fc.census_keys(features, gold)
    assert result["timestamps_with_partial_peer_loss"] == 1
    assert result["timestamps_with_all_peers_lost"] == 0
    assert result["verdict"] == "IMMATERIAL_LOSS_RECORDED"


def test_gold_keys_absent_from_features_are_reported():
    features = _keys("ABC", 10)
    gold = {**features, "D": np.array([0], dtype=np.int64)}
    assert fc.census_keys(features, gold)["extra_gold_keys_not_in_features"] == 1


def test_window_breakdown_counts_losses_inside_window_only():
    features = _keys("ABCDEF", 100)
    gold = {s: np.delete(t, 40) for s, t in features.items()}
    windows = {"early": (0, 10 * BAR), "mid": (30 * BAR, 50 * BAR)}
    result = fc.census_keys(features, gold, windows=windows)
    assert result["by_window"]["early"]["lost_keys"] == 0
    assert result["by_window"]["mid"]["timestamps_with_all_peers_lost"] == 1


def _source(symbols, n, *, drop=()):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    rng = np.random.default_rng(7)
    for i in range(n):
        for s in symbols:
            if (s, i) in drop:
                continue
            rows.append((s, start + timedelta(minutes=5 * i), *rng.normal(size=6)))
    columns = {name: [] for name in FOLD_CONTEXT_SOURCE_COLUMNS}
    for row in rows:
        for name, value in zip(FOLD_CONTEXT_SOURCE_COLUMNS, row, strict=True):
            columns[name].append(value)
    columns["feature_time"] = pa.array(columns["feature_time"], type=pa.timestamp("us", tz="UTC"))
    return pa.table(columns)


def _context_by_key(table):
    ctx = build_fold_context_table(table)
    sym = ctx.column("symbol").to_pylist()
    ts = ctx.column("feature_time").to_pylist()
    hashes = ctx.column("market_membership_hash").to_pylist()
    return {(a, b): h for a, b, h in zip(sym, ts, hashes, strict=True)}


def test_context_ignores_label_availability_of_other_horizons():
    """Duplicating each feature row per horizon (long-format Gold) must not change context."""

    base = _source("ABCDE", 20)
    doubled = pa.concat_tables([base, base])
    assert _context_by_key(base) == _context_by_key(doubled)


def test_context_changes_when_a_peer_vanishes_so_the_census_matters():
    full = _source("ABCDE", 20)
    missing = _source("ABCDE", 20, drop={("E", 10)})
    a = _context_by_key(full)
    b = _context_by_key(missing)
    key = ("A", sorted({t for _, t in a})[10])
    assert a[key] != b[key]
