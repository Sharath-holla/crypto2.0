from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.config import FeatureConfig
from crypto_ai.phase7.context_sidecar import (
    context_source_projection,
    load_sidecar_source,
    read_sidecar,
    sidecar_cache_identity,
    write_sidecar,
)
from crypto_ai.phase7.features import (
    FOLD_CONTEXT_SOURCE_COLUMNS,
    build_fold_context_table,
    generate_multiasset_features,
)
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_registry


def _config():
    return FeatureConfig(liquidity_window_rows=24, seven_day_volatility_rows=48)


def _candles():
    table = synthetic_candles(rows_per_symbol=180)
    # Both individual-symbol and all-peer gap edges are preserved.
    return table.take(pa.array([i for i in range(table.num_rows) if i % 31 and i % 180 != 60]))


def _identity():
    return dict(
        gold_manifest_sha256="g" * 64,
        registry_hash="registry",
        universe_hash="universe",
        registry_sha256="r" * 64,
        universe_sha256="u" * 64,
        silver_manifests=[{"sha256": "s" * 64}],
        configuration_hash="config",
    )


def test_context_projection_matches_real_feature_producer_exactly_including_nan_and_gaps():
    candles = _candles()
    projected = context_source_projection(candles, _config())
    produced = (
        generate_multiasset_features(candles, registry=synthetic_registry(), config=_config())
        .table.select(FOLD_CONTEXT_SOURCE_COLUMNS)
        .sort_by([("symbol", "ascending"), ("feature_time", "ascending")])
    )
    assert projected.schema == produced.schema
    assert projected["symbol"].to_pylist() == produced["symbol"].to_pylist()
    assert projected["feature_time"].to_pylist() == produced["feature_time"].to_pylist()
    for name in FOLD_CONTEXT_SOURCE_COLUMNS[2:]:
        np.testing.assert_array_equal(projected[name].to_numpy(), produced[name].to_numpy())


def test_projection_and_context_ignore_future_labels_and_label_availability():
    candles = _candles()
    plain = context_source_projection(candles, _config())
    # This includes all-symbol target disappearance: there is no target input at all.
    malicious = candles.append_column("raw_future_return", pa.array(np.ones(candles.num_rows) * 99))
    malicious = malicious.append_column("label_available", pa.array([False] * candles.num_rows))
    labelled = context_source_projection(malicious, _config())
    assert plain.equals(labelled) or all(
        np.array_equal(plain[c].to_numpy(), labelled[c].to_numpy(), equal_nan=True)
        for c in FOLD_CONTEXT_SOURCE_COLUMNS[2:]
    )
    context = build_fold_context_table(plain)
    assert context.num_rows == candles.num_rows
    assert set(labelled.column_names) == set(FOLD_CONTEXT_SOURCE_COLUMNS)


def test_sidecar_projection_is_truncation_invariant():
    candles = _candles()
    cutoff = min(candles["open_time"].to_pylist()) + timedelta(minutes=5 * 100)
    truncated = candles.filter(pa.compute.less(candles["open_time"], cutoff))
    before = context_source_projection(truncated, _config())
    full = context_source_projection(candles, _config())
    historical = full.filter(pa.compute.less_equal(full["feature_time"], cutoff))
    assert before["symbol"].to_pylist() == historical["symbol"].to_pylist()
    assert before["feature_time"].to_pylist() == historical["feature_time"].to_pylist()
    for c in FOLD_CONTEXT_SOURCE_COLUMNS[2:]:
        np.testing.assert_array_equal(before[c].to_numpy(), historical[c].to_numpy())


def test_sidecar_publication_reload_identity_and_tampering(tmp_path):
    source = context_source_projection(_candles(), _config())
    path = write_sidecar(tmp_path / "sidecar", [source], _identity())
    report = read_sidecar(path)
    start, end = (
        min(source["feature_time"].to_pylist()),
        max(source["feature_time"].to_pylist()) + timedelta(microseconds=1),
    )
    loaded = load_sidecar_source(path, start, end)
    assert loaded["symbol"].to_pylist() == source["symbol"].to_pylist()
    for c in FOLD_CONTEXT_SOURCE_COLUMNS[2:]:
        np.testing.assert_array_equal(loaded[c].to_numpy(), source[c].to_numpy())
    expected = dict(
        gold_manifest_sha256="g" * 64, registry_hash="registry", universe_hash="universe"
    )
    first = sidecar_cache_identity(path, **expected)
    for field in expected:
        wrong = {**expected, field: "wrong"}
        with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
            sidecar_cache_identity(path, **wrong)
    assert first["source"] == "FEATURE_CONTEXT_SIDECAR"
    partition = path.parent / report["partitions"][0]["path"]
    partition.write_bytes(partition.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="PARTITION_HASH_MISMATCH"):
        load_sidecar_source(path, start, end)
    path.write_text(json.dumps({**report, "rows": 0}))
    with pytest.raises(ValueError, match="INCOMPLETE_OR_HASH_MISMATCH"):
        read_sidecar(path)


def test_sidecar_rejects_july_and_partial_build(tmp_path):
    source = context_source_projection(_candles(), _config())
    july = source.set_column(
        1,
        "feature_time",
        pa.array(
            [datetime(2026, 7, 1, tzinfo=UTC)] * source.num_rows, type=pa.timestamp("us", tz="UTC")
        ),
    )
    with pytest.raises(ValueError, match="forbidden"):
        write_sidecar(tmp_path / "forbidden", [july], _identity())
    assert not (tmp_path / "forbidden/SIDECAR_COMPLETE").exists()
    with pytest.raises(ValueError, match="only the declared"):
        write_sidecar(
            tmp_path / "labels",
            [source.append_column("target", pa.array([0.0] * source.num_rows))],
            _identity(),
        )


def test_sidecar_input_changes_invalidate_cache_and_model_resume(tmp_path, monkeypatch):
    from test_preparation_identity import _key

    from crypto_ai.phase7 import training

    source = context_source_projection(_candles(), _config())
    # The cache fixture has these specific canonical Gold/registry/universe identities.
    identity = {**_identity(), "gold_manifest_sha256": "m" * 64, "configuration_hash": "cfg"}
    first = write_sidecar(tmp_path / "first", [source], identity)
    second = write_sidecar(tmp_path / "second", [source], {**identity, "source_revision": "other"})
    monkeypatch.setenv("PHASE7_FEATURE_CONTEXT_SIDECAR", str(first))
    key_a, resume_a = _key(), training.training_stage_resume_identity()
    monkeypatch.setenv("PHASE7_FEATURE_CONTEXT_SIDECAR", str(second))
    assert _key() != key_a
    assert training.training_stage_resume_identity() != resume_a


def test_canonical_fold_loader_uses_sidecar_even_without_any_gold_targets(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from crypto_ai.phase7 import training

    source = context_source_projection(_candles(), _config())
    path = write_sidecar(tmp_path / "sidecar", [source], _identity())
    monkeypatch.setenv("PHASE7_FEATURE_CONTEXT_SIDECAR", str(path))

    def forbidden(*args, **kwargs):
        raise AssertionError("Gold label availability must not decide sidecar context")

    monkeypatch.setattr(training, "_load_fold_rows", forbidden)
    plan = SimpleNamespace(
        train_start=min(source["feature_time"].to_pylist()),
        test_end=max(source["feature_time"].to_pylist()) + timedelta(microseconds=1),
    )
    manifest = {"registry_hash": "registry", "lineage": {"core_universe_hash": "universe"}}
    loaded = training._load_fold_context_source(
        manifest,
        plan,
        (15, 30, 60, 120),
        gold_manifest_sha256="g" * 64,
        configuration_hash="config",
    )
    assert loaded.num_rows == source.num_rows
    assert loaded["symbol"].to_pylist() == source["symbol"].to_pylist()
    with pytest.raises(ValueError, match="configuration_hash"):
        training._load_fold_context_source(
            manifest, plan, (15,), gold_manifest_sha256="g" * 64, configuration_hash="wrong"
        )


def test_real_gold_cannot_prepare_or_load_context_without_its_required_sidecar(monkeypatch):
    from test_preparation_identity import _key

    from crypto_ai.phase7 import training

    monkeypatch.delenv("PHASE7_FEATURE_CONTEXT_SIDECAR", raising=False)
    manifest = {"dataset_id": "gold-phase7-0cbf2910e8d96c9d19826598"}
    with pytest.raises(ValueError, match="M01_FEATURE_CONTEXT_SIDECAR_REQUIRED"):
        training._load_fold_context_source(manifest, None, (60,))
    with pytest.raises(ValueError, match="M01_FEATURE_CONTEXT_SIDECAR_REQUIRED"):
        _key(manifest=manifest)
