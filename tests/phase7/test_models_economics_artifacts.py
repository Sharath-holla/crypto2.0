from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json
from crypto_ai.phase7.config import CostConfig, FeatureConfig, ModelConfig, TargetConfig
from crypto_ai.phase7.economics import (
    adaptive_policy_cost_stress,
    build_oos_trades,
    fixed_policy_cost_stress,
    select_cal_b_thresholds,
)
from crypto_ai.phase7.features import generate_multiasset_features
from crypto_ai.phase7.fixtures import synthetic_candles, synthetic_descriptors, synthetic_registry
from crypto_ai.phase7.folds import fit_train_only_clusters
from crypto_ai.phase7.gold import build_multiasset_gold_chunks
from crypto_ai.phase7.models import fit_architecture, symbol_balanced_weights
from crypto_ai.phase7.targets import generate_multiasset_targets


def _model_tables() -> tuple[pa.Table, pa.Table, dict[str, int]]:
    train: list[dict[str, object]] = []
    validation: list[dict[str, object]] = []
    mapping = {"BTCUSDT": 0, "ETHUSDT": 0, "SOLUSDT": 1}
    for symbol_index, symbol in enumerate(mapping):
        for index in range(160):
            row = {
                "symbol": symbol,
                "f1": index / 100.0,
                "f2": float(symbol_index),
                "target": index / 200.0 + symbol_index * 0.01,
            }
            (train if index < 120 else validation).append(row)
    return pa.Table.from_pylist(train), pa.Table.from_pylist(validation), mapping


def test_symbol_balanced_weights_give_equal_total_mass() -> None:
    symbols = np.asarray(["A"] * 10 + ["B"] * 2, dtype=object)
    weights = symbol_balanced_weights(symbols)
    assert np.sum(weights[symbols == "A"]) == np.sum(weights[symbols == "B"])
    assert np.mean(weights) == 1.0


def test_all_four_model_architectures_fit_and_predict() -> None:
    train, validation, mapping = _model_tables()
    config = ModelConfig(
        minimum_train_rows_per_coin=100,
        minimum_validation_rows_per_coin=20,
        minimum_calibration_rows_per_coin=20,
        n_estimators=20,
        early_stopping_rounds=5,
        min_child_samples=5,
    )
    for architecture in ("G0", "C0", "P0", "H0"):
        model = fit_architecture(
            architecture,
            train,
            validation,
            feature_columns=("f1", "f2"),
            target_column="target",
            config=config,
            model_threads=1,
            cluster_mapping=mapping,
            symbol_balanced=True,
            hybrid_calibration=validation if architecture == "H0" else None,
            eligibility_calibration=validation,
        )
        predicted, covered = model.predict(validation)
        assert np.all(covered)
        assert np.all(np.isfinite(predicted))


def test_train_only_clusters_ignore_future_descriptors() -> None:
    cutoff = datetime(2022, 1, 1, tzinfo=UTC)
    descriptors = synthetic_descriptors(as_of=cutoff)
    mapping, report = fit_train_only_clusters(
        descriptors,
        train_end=cutoff,
        eligible_symbols={item.symbol for item in descriptors},
        cluster_count=3,
        seed=42,
    )
    future = descriptors + [
        item.model_copy(
            update={
                "as_of": datetime(2025, 1, 1, tzinfo=UTC),
                "realized_volatility": item.realized_volatility * 100,
            }
        )
        for item in descriptors
    ]
    changed, changed_report = fit_train_only_clusters(
        future,
        train_end=cutoff,
        eligible_symbols={item.symbol for item in descriptors},
        cluster_count=3,
        seed=42,
    )
    assert mapping == changed
    assert report["identity"] == changed_report["identity"]


def test_cost_stress_preserves_trade_identity_and_is_monotonic() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    table = pa.table(
        {
            "symbol": ["BTCUSDT"] * 6,
            "feature_time": [start + index * timedelta(hours=2) for index in range(6)],
            "entry_time": [start + index * timedelta(hours=2, minutes=5) for index in range(6)],
            "label_end_time": [
                start + index * timedelta(hours=2) + timedelta(hours=1) for index in range(6)
            ],
            "raw_future_return": [0.01, -0.01, 0.02, -0.02, 0.015, -0.015],
        }
    )
    predictions = np.asarray([0.02, -0.02, 0.02, -0.02, 0.02, -0.02])
    config = CostConfig(minimum_calibration_trades=1)
    thresholds, _ = select_cal_b_thresholds(
        table,
        predictions,
        target_column="raw_future_return",
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
        cluster_mapping={"BTCUSDT": 0},
        granularity="global",
        config=config,
    )
    trades = build_oos_trades(
        table,
        predictions,
        thresholds,
        target_column="raw_future_return",
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
        cluster_mapping={"BTCUSDT": 0},
        horizon_minutes=60,
        config=config,
    )
    stress = fixed_policy_cost_stress(trades, config)
    adaptive = adaptive_policy_cost_stress(
        table,
        predictions,
        thresholds,
        target_column="raw_future_return",
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
        cluster_mapping={"BTCUSDT": 0},
        horizon_minutes=60,
        config=config,
    )
    identities = {item["trade_identity_hash"] for item in stress.values()}
    net = [stress[str(value)]["summed_net_return"] for value in config.fixed_policy_multipliers]
    assert len(identities) == 1
    assert net == sorted(net, reverse=True)
    assert all(item["policy_thresholds_retuned"] is False for item in adaptive.values())


def test_checkpoint_verifies_artifact_checksum(tmp_path: Path) -> None:
    artifact = atomic_json(tmp_path / "artifact.json", {"value": 1})
    store = CheckpointStore(tmp_path / "checkpoints", "run-1")
    store.complete("stage", [artifact], {"purpose": "test"})
    assert store.is_complete("stage")
    artifact.write_text('{"value": 2}\n', encoding="utf-8")
    assert not store.is_complete("stage")


def test_chunked_gold_records_partition_checksums_and_lineage(tmp_path: Path) -> None:
    candles = synthetic_candles(rows_per_symbol=100)
    features = generate_multiasset_features(
        candles,
        registry=synthetic_registry(),
        config=FeatureConfig(
            correlation_window_rows=24,
            liquidity_window_rows=24,
            volatility_window_rows=24,
            daily_volatility_rows=24,
            seven_day_volatility_rows=48,
            include_12h=False,
            include_1d=False,
            include_derivatives=False,
        ),
    )
    targets = generate_multiasset_targets(
        candles,
        features.table,
        config=TargetConfig(),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    registry = synthetic_registry()
    result = build_multiasset_gold_chunks(
        [("fixture", features, targets)],
        feature_columns=features.feature_columns,
        output_root=tmp_path,
        universe_version="universe_v1",
        universe_hash="fixture-universe",
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
        prospective_holdout_start=datetime(2026, 8, 1, tzinfo=UTC),
        lineage={"fixture": True},
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["storage_mode"] == "bounded_time_chunks"
    assert manifest["prospective_holdout_used"] is False
    assert manifest["row_count"] == result.row_count
    assert all(
        (result.manifest_path.parent / item["path"]).is_file()
        for item in manifest["partition_files"]
    )
