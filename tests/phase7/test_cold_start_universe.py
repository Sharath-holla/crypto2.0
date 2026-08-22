from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import FeatureConfig, ModelConfig, UniverseConfig
from crypto_ai.phase7.features import MARKET_CONTEXT_COLUMNS, generate_multiasset_features
from crypto_ai.phase7.fixtures import synthetic_candles
from crypto_ai.phase7.folds import fit_train_only_clusters
from crypto_ai.phase7.models import fit_architecture
from crypto_ai.phase7.registry import SymbolRegistry, build_symbol_registry
from crypto_ai.phase7.training import matched_architecture_comparisons
from crypto_ai.phase7.universe import (
    FoldActiveUniverse,
    SymbolDescriptor,
    build_expansion_policy,
    select_fold_active_universe,
    select_pilot_universe,
)

CORE_CUTOFF = datetime(2022, 1, 1, tzinfo=UTC)
RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
FIRST_CORE_EVIDENCE = datetime(2019, 1, 1, tzinfo=UTC)
NEW_EVIDENCE = datetime(2023, 1, 1, tzinfo=UTC)


def _registry(
    additions: dict[str, tuple[datetime, datetime | None]] | None = None,
) -> SymbolRegistry:
    additions = additions or {"NEWUSDT": (NEW_EVIDENCE, None)}
    current_symbols = ["BTCUSDT", "ETHUSDT"] + [
        symbol for symbol, (_, available_until) in additions.items() if available_until is None
    ]
    exchange_info = {
        "symbols": [
            {
                "symbol": symbol,
                "baseAsset": symbol.removesuffix("USDT"),
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }
            for symbol in current_symbols
        ]
    }
    evidence: list[dict[str, object]] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        evidence.append(
            {
                "symbol": symbol,
                "base_asset": symbol.removesuffix("USDT"),
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": FIRST_CORE_EVIDENCE,
                "last_market_data_time": RESEARCH_CUTOFF - timedelta(minutes=5),
                "available_intervals": ["5m", "12h", "1d"],
            }
        )
    for symbol, (available_from, available_until) in additions.items():
        effective_until = available_until or RESEARCH_CUTOFF
        payload: dict[str, object] = {
            "symbol": symbol,
            "base_asset": symbol.removesuffix("USDT"),
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
            "first_market_data_time": available_from,
            "last_market_data_time": effective_until - timedelta(minutes=5),
            "available_intervals": ["5m", "12h", "1d"],
        }
        if available_until is not None:
            payload["available_until"] = available_until
        evidence.append(payload)
    return build_symbol_registry(
        exchange_info,
        evidence,
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=RESEARCH_CUTOFF,
    )


def _descriptor(
    symbol: str,
    as_of: datetime,
    available_from: datetime,
    *,
    liquidity: float = 1_000_000.0,
    volatility: float = 0.02,
) -> SymbolDescriptor:
    return SymbolDescriptor(
        symbol=symbol,
        as_of=as_of,
        source_max_time=as_of - timedelta(days=1),
        trailing_quote_volume=liquidity,
        realized_volatility=volatility,
        trade_intensity=1_000.0,
        funding_variability=0.0001,
        btc_beta=1.0 if symbol == "BTCUSDT" else 0.5,
        btc_correlation=1.0 if symbol == "BTCUSDT" else 0.6,
        history_days=(as_of - available_from).total_seconds() / 86_400,
        coverage_ratio=1.0,
    )


def _config(*, expansion_max: int = 2, total_max: int = 4) -> UniverseConfig:
    return UniverseConfig(
        core_target_size=2,
        fixture_mode=True,
        core_selection_cutoff=CORE_CUTOFF,
        expansion_max_symbols_per_fold=expansion_max,
        total_max_symbols_per_fold=total_max,
        minimum_history_days=365,
        age_bucket_edges_days=(365, 730, 1460),
        selection_lookback_days=90,
    )


def _core_context(
    registry: SymbolRegistry,
    config: UniverseConfig,
) -> tuple[object, object, list[SymbolDescriptor]]:
    descriptors = [
        _descriptor("BTCUSDT", CORE_CUTOFF, FIRST_CORE_EVIDENCE, liquidity=10_000_000),
        _descriptor("ETHUSDT", CORE_CUTOFF, FIRST_CORE_EVIDENCE, liquidity=8_000_000),
    ]
    core = select_pilot_universe(
        registry,
        descriptors,
        selection_cutoff=CORE_CUTOFF,
        config=config,
    )
    return core, build_expansion_policy(core, config), descriptors


def _membership(
    registry: SymbolRegistry,
    descriptors: list[SymbolDescriptor],
    *,
    train_end: datetime,
    config: UniverseConfig | None = None,
) -> FoldActiveUniverse:
    config = config or _config()
    core, policy, core_descriptors = _core_context(registry, config)
    return select_fold_active_universe(
        registry,
        core_descriptors + descriptors,
        fold_id=f"fold-{train_end.date().isoformat()}",
        train_end=train_end,
        core_universe=core,
        expansion_policy=policy,
        config=config,
        research_view="EXPANDING",
    )


def test_post_2022_symbol_is_absent_before_listing() -> None:
    membership = _membership(_registry(), [], train_end=datetime(2022, 10, 1, tzinfo=UTC))
    assert "NEWUSDT" not in membership.active_symbols
    assert "NEWUSDT" not in {item.symbol for item in membership.members}


def test_minimum_history_gate_keeps_new_symbol_ineligible() -> None:
    train_end = datetime(2023, 12, 31, tzinfo=UTC)
    membership = _membership(
        _registry(),
        [_descriptor("NEWUSDT", train_end, NEW_EVIDENCE)],
        train_end=train_end,
    )
    new = next(item for item in membership.members if item.symbol == "NEWUSDT")
    assert new.eligible is False
    assert new.quality_status == "INELIGIBLE_HISTORY"
    assert new.reason == "insufficient_point_in_time_history"


def test_new_symbol_is_admitted_causally_after_sufficient_history() -> None:
    train_end = datetime(2024, 7, 1, tzinfo=UTC)
    membership = _membership(
        _registry(),
        [_descriptor("NEWUSDT", train_end, NEW_EVIDENCE)],
        train_end=train_end,
    )
    assert membership.expansion_eligible_symbols == ("NEWUSDT",)
    assert "NEWUSDT" in membership.active_symbols
    new = next(item for item in membership.members if item.symbol == "NEWUSDT")
    assert new.source == "EXPANSION"
    assert new.age_bucket == "DAYS_365_729"


def test_future_admission_does_not_modify_earlier_membership() -> None:
    registry = _registry()
    early = datetime(2022, 10, 1, tzinfo=UTC)
    baseline = _membership(registry, [], train_end=early)
    future_descriptor = _descriptor("NEWUSDT", datetime(2024, 7, 1, tzinfo=UTC), NEW_EVIDENCE)
    perturbed = _membership(registry, [future_descriptor], train_end=early)
    assert baseline.membership_hash == perturbed.membership_hash
    assert baseline.active_symbols == perturbed.active_symbols


def test_future_survival_does_not_change_2024_eligibility() -> None:
    train_end = datetime(2024, 7, 1, tzinfo=UTC)
    descriptor = _descriptor("NEWUSDT", train_end, NEW_EVIDENCE)
    shorter = _membership(
        _registry({"NEWUSDT": (NEW_EVIDENCE, datetime(2025, 1, 1, tzinfo=UTC))}),
        [descriptor],
        train_end=train_end,
    )
    longer = _membership(
        _registry({"NEWUSDT": (NEW_EVIDENCE, datetime(2026, 1, 1, tzinfo=UTC))}),
        [descriptor],
        train_end=train_end,
    )
    assert shorter.active_symbols == longer.active_symbols
    assert "NEWUSDT" in shorter.expansion_eligible_symbols


def test_future_liquidity_does_not_change_fold_admission() -> None:
    registry = _registry()
    train_end = datetime(2024, 7, 1, tzinfo=UTC)
    known = _descriptor("NEWUSDT", train_end, NEW_EVIDENCE, liquidity=2_000_000)
    baseline = _membership(registry, [known], train_end=train_end)
    future = known.model_copy(
        update={
            "as_of": datetime(2025, 1, 1, tzinfo=UTC),
            "source_max_time": datetime(2024, 12, 31, tzinfo=UTC),
            "trailing_quote_volume": 999_000_000.0,
        }
    )
    perturbed = _membership(registry, [known, future], train_end=train_end)
    assert baseline.membership_hash == perturbed.membership_hash


def test_future_listed_symbol_does_not_change_historical_breadth() -> None:
    registry = _registry()
    base_all = synthetic_candles(rows_per_symbol=180, start=datetime(2022, 1, 1, tzinfo=UTC))
    base_symbols = np.asarray(base_all.column("symbol").to_pylist(), dtype=object)
    base = base_all.filter(pa.array(np.isin(base_symbols, ["BTCUSDT", "ETHUSDT"])))
    future_all = synthetic_candles(rows_per_symbol=180, start=datetime(2024, 1, 1, tzinfo=UTC))
    future_symbols = np.asarray(future_all.column("symbol").to_pylist(), dtype=object)
    future = future_all.filter(pa.array(future_symbols == "SOLUSDT"))
    future = future.set_column(
        future.schema.get_field_index("symbol"),
        "symbol",
        pa.array(["NEWUSDT"] * future.num_rows),
    )
    config = FeatureConfig(
        correlation_window_rows=24,
        liquidity_window_rows=24,
        volatility_window_rows=24,
        daily_volatility_rows=24,
        seven_day_volatility_rows=48,
        include_12h=False,
        include_1d=False,
        include_derivatives=False,
    )
    baseline = generate_multiasset_features(base, registry=registry, config=config).table
    changed = generate_multiasset_features(
        pa.concat_tables([base, future]), registry=registry, config=config
    ).table
    historical = changed.filter(
        pa.compute.less(changed["feature_time"], pa.scalar(datetime(2023, 1, 1, tzinfo=UTC)))
    )
    assert (
        baseline["market_membership_hash"].to_pylist()
        == historical["market_membership_hash"].to_pylist()
    )
    for column in MARKET_CONTEXT_COLUMNS:
        before = np.asarray(baseline[column].to_pylist(), dtype=np.float64)
        after = np.asarray(historical[column].to_pylist(), dtype=np.float64)
        assert np.allclose(before, after, equal_nan=True)


def test_future_behavior_does_not_change_train_only_cluster_assignment() -> None:
    train_end = datetime(2024, 7, 1, tzinfo=UTC)
    descriptors = [
        _descriptor("BTCUSDT", train_end, FIRST_CORE_EVIDENCE, liquidity=10_000_000),
        _descriptor("ETHUSDT", train_end, FIRST_CORE_EVIDENCE, liquidity=8_000_000),
        _descriptor("NEWUSDT", train_end, NEW_EVIDENCE, liquidity=2_000_000),
    ]
    baseline, baseline_report = fit_train_only_clusters(
        descriptors,
        train_end=train_end,
        eligible_symbols={"BTCUSDT", "ETHUSDT", "NEWUSDT"},
        cluster_count=2,
        seed=42,
    )
    future = descriptors[-1].model_copy(
        update={
            "as_of": datetime(2025, 1, 1, tzinfo=UTC),
            "source_max_time": datetime(2024, 12, 31, tzinfo=UTC),
            "realized_volatility": 100.0,
            "trailing_quote_volume": 999_000_000.0,
        }
    )
    changed, changed_report = fit_train_only_clusters(
        descriptors + [future],
        train_end=train_end,
        eligible_symbols={"BTCUSDT", "ETHUSDT", "NEWUSDT"},
        cluster_count=2,
        seed=42,
    )
    assert baseline == changed
    assert baseline_report["identity"] == changed_report["identity"]


def _model_table(symbol_rows: dict[str, int]) -> pa.Table:
    rows: list[dict[str, object]] = []
    for symbol_index, (symbol, count) in enumerate(symbol_rows.items()):
        for index in range(count):
            rows.append(
                {
                    "symbol": symbol,
                    "f1": index / 100.0,
                    "target": index / 200.0 + symbol_index * 0.01,
                }
            )
    return pa.Table.from_pylist(rows)


def _model_config() -> ModelConfig:
    return ModelConfig(
        minimum_train_rows_per_coin=100,
        minimum_validation_rows_per_coin=20,
        minimum_calibration_rows_per_coin=20,
        n_estimators=20,
        early_stopping_rounds=5,
        min_child_samples=5,
    )


def test_young_symbol_remains_per_coin_ineligible_until_mature() -> None:
    train = _model_table({"BTCUSDT": 120, "NEWUSDT": 50})
    validation = _model_table({"BTCUSDT": 25, "NEWUSDT": 25})
    calibration = _model_table({"BTCUSDT": 25, "NEWUSDT": 25})
    model = fit_architecture(
        "P0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=_model_config(),
        model_threads=1,
        cluster_mapping={"BTCUSDT": 0, "NEWUSDT": 0},
        eligibility_calibration=calibration,
    )
    assert model.metadata["per_symbol_eligibility"]["NEWUSDT"]["status"] == ("PER_COIN_INELIGIBLE")
    assert model.metadata["per_symbol_eligibility"]["NEWUSDT"]["reasons"] == [
        "insufficient_train_rows"
    ]


def test_young_hybrid_symbol_uses_cluster_then_global_fallback() -> None:
    train = _model_table({"BTCUSDT": 120, "NEWUSDT": 50})
    validation = _model_table({"BTCUSDT": 25, "NEWUSDT": 25})
    model = fit_architecture(
        "H0",
        train,
        validation,
        feature_columns=("f1",),
        target_column="target",
        config=_model_config(),
        model_threads=1,
        cluster_mapping={"BTCUSDT": 0, "NEWUSDT": 0},
        hybrid_calibration=validation,
        eligibility_calibration=validation,
    )
    assert "NEWUSDT" not in model.symbol_corrections
    assert 0 in model.cluster_corrections
    status = model.metadata["hybrid_symbol_correction_eligibility"]["NEWUSDT"]
    assert status["status"] == "SYMBOL_CORRECTION_INELIGIBLE"
    assert status["fallback"] == "cluster_then_global"
    sample = _model_table({"NEWUSDT": 5})
    predicted, covered = model.predict(sample)
    global_prediction = model.estimators["global"].predict(
        np.asarray(sample.column("f1").to_pylist(), dtype=np.float64).reshape(-1, 1)
    )
    assert np.all(covered)
    assert np.allclose(predicted, global_prediction + model.cluster_corrections[0])


def test_global_models_handle_unknown_eligible_symbol_safely() -> None:
    train = _model_table({"BTCUSDT": 120})
    validation = _model_table({"BTCUSDT": 25})
    unseen = _model_table({"NEWUSDT": 5})
    for explicit_symbol_id in (False, True):
        model = fit_architecture(
            "G0",
            train,
            validation,
            feature_columns=("f1",),
            target_column="target",
            config=_model_config(),
            model_threads=1,
            explicit_symbol_id=explicit_symbol_id,
            eligibility_calibration=validation,
        )
        predicted, covered = model.predict(unseen)
        assert np.all(covered)
        assert np.all(np.isfinite(predicted))
        expected_policy = "ALL_ZERO_KNOWN_SYMBOL_LEVELS" if explicit_symbol_id else "NOT_APPLICABLE"
        assert model.metadata["unknown_symbol_id_policy"] == expected_policy


def test_expansion_never_exceeds_fold_caps() -> None:
    additions = {
        f"NEW{index}USDT": (NEW_EVIDENCE + timedelta(days=index), None) for index in range(8)
    }
    registry = _registry(additions)
    config = _config(expansion_max=3, total_max=4)
    train_end = datetime(2025, 1, 1, tzinfo=UTC)
    descriptors = [
        _descriptor(symbol, train_end, available_from, liquidity=1_000_000 + index)
        for index, (symbol, (available_from, _)) in enumerate(additions.items())
    ]
    membership = _membership(
        registry,
        descriptors,
        train_end=train_end,
        config=config,
    )
    assert len(membership.expansion_eligible_symbols) == 2
    assert len(membership.active_symbols) == 4
    assert len(membership.expansion_eligible_symbols) <= config.expansion_max_symbols_per_fold
    assert len(membership.active_symbols) <= config.total_max_symbols_per_fold
    assert any(item.reason == "expansion_fold_cap" for item in membership.members)


def test_matched_architecture_comparison_uses_identical_observations() -> None:
    def report(architecture: str, symbols: tuple[str, ...]) -> dict[str, object]:
        metric = {
            "count": 5,
            "mae": 0.1,
            "rmse": 0.2,
            "r2": 0.0,
            "directional_accuracy": 0.5,
            "pearson_ic": 0.1,
            "spearman_ic": 0.1,
        }
        return {
            "status": "COMPLETE",
            "research_view": "EXPANDING",
            "fold_id": "fold-1",
            "spec": {
                "name": f"architecture-{architecture}-A6-60m-raw",
                "architecture": architecture,
                "feature_group": "A6",
                "horizon_minutes": 60,
                "target_type": "raw",
            },
            "test_coverage_keys_by_symbol": {
                symbol: {"row_count": 5, "identity": f"same-{symbol}"} for symbol in symbols
            },
            "test_metrics": {
                "per_symbol": {symbol: metric for symbol in symbols},
                "coverage": {"covered_symbol_names": list(symbols)},
            },
        }

    reports = [
        report("G0", ("BTCUSDT", "NEWUSDT")),
        report("C0", ("BTCUSDT", "NEWUSDT")),
        report("P0", ("BTCUSDT",)),
        report("H0", ("BTCUSDT", "NEWUSDT")),
    ]
    comparison = matched_architecture_comparisons(reports)[0]  # type: ignore[arg-type]
    assert comparison["matched_symbols"] == ["BTCUSDT"]
    assert comparison["matched_row_count"] == 5
    assert set(comparison["architectures"]) == {"G0", "C0", "P0", "H0"}
