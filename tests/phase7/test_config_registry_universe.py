from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from crypto_ai.phase7.config import Phase7Config, UniverseConfig, load_phase7_config
from crypto_ai.phase7.fixtures import synthetic_descriptors, synthetic_registry
from crypto_ai.phase7.pipeline import run_phase7_cloud
from crypto_ai.phase7.registry import build_symbol_registry
from crypto_ai.phase7.runner import phase7_plan
from crypto_ai.phase7.runner import test_phase7_universe as run_universe_test
from crypto_ai.phase7.sources import BinancePublicDiscoveryClient
from crypto_ai.phase7.universe import (
    EligibilityStatus,
    fold_local_eligibility,
    select_pilot_universe,
)


def test_repository_phase7_config_is_locked_and_plannable() -> None:
    config = load_phase7_config(Path("configs/phase7/research_v1.toml"))
    plan = phase7_plan(config)
    assert config.research_cutoff == datetime(2026, 7, 1, tzinfo=UTC)
    assert config.prospective_holdout_start == datetime(2026, 8, 1, tzinfo=UTC)
    assert plan["estimated_walk_forward_folds"] == 16
    assert plan["research_views"] == ["CORE", "EXPANDING"]
    assert plan["core_universe_target_size"] == 20
    assert plan["expansion_max_symbols_per_fold"] == 10
    assert plan["total_max_symbols_per_fold"] == 30
    assert plan["network_used"] is False
    assert plan["stages"] == ["registry", "universe", "data", "gold", "train", "report"]


def test_invalid_research_boundary_is_rejected() -> None:
    with pytest.raises(ValueError, match="research cutoff is locked"):
        Phase7Config(research_cutoff=datetime(2026, 7, 2, tzinfo=UTC))


def test_heavy_cloud_pipeline_is_environment_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PHASE7_ALLOW_CLOUD_RESEARCH", raising=False)
    with pytest.raises(RuntimeError, match="training VM"):
        run_phase7_cloud(Phase7Config(), stage="registry", resume=False)


def test_historical_registry_retains_delisted_contract() -> None:
    first = datetime(2020, 1, 1, tzinfo=UTC)
    delisted = datetime(2021, 7, 1, tzinfo=UTC)
    registry = build_symbol_registry(
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                }
            ]
        },
        [
            {
                "symbol": "BTCUSDT",
                "first_market_data_time": first,
                "last_market_data_time": datetime(2026, 7, 1, tzinfo=UTC),
                "available_intervals": ["5m", "12h", "1d"],
            },
            {
                "symbol": "OLDUSDT",
                "base_asset": "OLD",
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "first_market_data_time": first,
                "last_market_data_time": delisted,
                "available_intervals": ["5m"],
            },
        ],
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    record = registry.by_symbol()["OLDUSDT"]
    assert record.exists_at(datetime(2021, 6, 1, tzinfo=UTC))
    assert not record.exists_at(delisted + timedelta(minutes=6))


def test_universe_ignores_future_descriptor_perturbation() -> None:
    config = UniverseConfig(
        core_target_size=4,
        fixture_mode=True,
        expansion_max_symbols_per_fold=2,
        total_max_symbols_per_fold=6,
        minimum_history_days=90,
        age_bucket_edges_days=(90, 180, 365),
        selection_lookback_days=30,
    )
    descriptors = synthetic_descriptors(as_of=config.selection_cutoff)
    registry = synthetic_registry()
    baseline = select_pilot_universe(
        registry,
        descriptors,
        selection_cutoff=config.selection_cutoff,
        config=config,
    )
    future = descriptors + [
        item.model_copy(
            update={
                "as_of": datetime(2025, 1, 1, tzinfo=UTC),
                "trailing_quote_volume": item.trailing_quote_volume * 1_000,
            }
        )
        for item in descriptors
    ]
    perturbed = select_pilot_universe(
        registry,
        future,
        selection_cutoff=config.selection_cutoff,
        config=config,
    )
    assert baseline.universe_hash == perturbed.universe_hash


def test_fold_liquidity_eligibility_uses_only_train_known_descriptor() -> None:
    config = UniverseConfig(
        core_target_size=4,
        fixture_mode=True,
        expansion_max_symbols_per_fold=2,
        total_max_symbols_per_fold=6,
        minimum_history_days=90,
        age_bucket_edges_days=(90, 180, 365),
        minimum_trailing_quote_volume=500_000,
        selection_lookback_days=30,
    )
    registry = synthetic_registry()
    descriptors = synthetic_descriptors(as_of=datetime(2022, 1, 1, tzinfo=UTC))
    descriptors[2] = descriptors[2].model_copy(update={"trailing_quote_volume": 1.0})
    descriptors.append(
        descriptors[2].model_copy(
            update={
                "as_of": datetime(2024, 1, 1, tzinfo=UTC),
                "trailing_quote_volume": 99_000_000.0,
            }
        )
    )
    decisions = fold_local_eligibility(
        registry,
        descriptors,
        train_end=datetime(2023, 1, 1, tzinfo=UTC),
        config=config,
    )
    by_symbol = {item.symbol: item for item in decisions}
    assert by_symbol["SOLUSDT"].status is EligibilityStatus.INELIGIBLE_LIQUIDITY


def test_local_universe_command_contract() -> None:
    result = run_universe_test(Phase7Config())
    assert result["status"] == "PASS"
    assert result["future_descriptor_perturbation_invariant"] is True
    assert result["core_universe_version"] == "core_universe_v1"
    assert result["expansion_universe_version"] == "expansion_universe_v1"
    assert result["expansion_as_of"] == "fold_train_end"
    assert result["prospective_holdout_used"] is False


def test_official_archive_discovery_uses_s3_xml_catalog_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fapi.binance.com":
            return httpx.Response(200, json={"symbols": []})
        assert request.url.path == "/data.binance.vision/"
        prefix = request.url.params["prefix"]
        if prefix.endswith("klines/"):
            body = """<?xml version="1.0"?>
            <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
              <IsTruncated>false</IsTruncated>
              <CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
            </ListBucketResult>"""
        else:
            body = """<?xml version="1.0"?>
            <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
              <IsTruncated>false</IsTruncated>
              <Contents><Key>data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2021-01.zip</Key></Contents>
            </ListBucketResult>"""
        return httpx.Response(200, text=body)

    with BinancePublicDiscoveryClient(transport=httpx.MockTransport(handler)) as client:
        evidence = client.historical_evidence(intervals=("5m",))
    assert evidence[0]["symbol"] == "BTCUSDT"
    assert evidence[0]["first_market_data_time"] == "2021-01-01T00:00:00+00:00"
