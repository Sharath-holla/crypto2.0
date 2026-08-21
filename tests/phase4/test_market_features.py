from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from crypto_ai.data.schema import candles_to_table
from crypto_ai.phase4.asof import causal_asof_join
from crypto_ai.phase4.features import FEATURE_GROUPS, generate_features_v2
from crypto_ai.phase4.market_data import (
    DerivativesMarketDataClient,
    MarketDataKind,
    ingest_public_market_data,
    validate_market_table,
)
from tests.research_helpers import make_research_candles


def test_asof_join_never_uses_future_or_stale_observation() -> None:
    result = causal_asof_join(
        np.asarray([100, 200, 350, 700]),
        np.asarray([150, 300]),
        {"value": np.asarray([1.0, 2.0])},
        maximum_age_us=250,
    )

    np.testing.assert_allclose(result.values["value"], [np.nan, 1.0, 2.0, np.nan], equal_nan=True)
    np.testing.assert_array_equal(result.available, [False, True, True, False])
    assert result.source_indices.tolist() == [-1, 0, 1, 1]


def test_public_funding_adapter_preserves_decimal_and_half_open_end() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)

    def request(path: str, params: dict[str, object] | None) -> object:
        assert path == "/fapi/v1/fundingRate"
        assert params is not None
        return [
            {
                "symbol": "BTCUSDT",
                "fundingTime": start_ms,
                "fundingRate": "0.000012345678901234",
                "markPrice": "65000.123456789012345678",
                "rateType": "Regular",
            },
            {
                "symbol": "BTCUSDT",
                "fundingTime": start_ms + 8 * 3_600_000,
                "fundingRate": "0.1",
                "markPrice": "65001",
            },
        ]

    table = DerivativesMarketDataClient(request).fetch(
        MarketDataKind.FUNDING,
        symbol="BTCUSDT",
        start=start,
        end=start + timedelta(hours=8),
        ingested_at=start + timedelta(days=1),
    )

    assert table.num_rows == 1
    assert table.column("funding_rate")[0].as_py() == Decimal("0.000012345678901234")
    assert validate_market_table(table, MarketDataKind.FUNDING)["status"] == "PASS"


def test_price_kline_availability_is_close_boundary() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)

    def request(_: str, __: dict[str, object] | None) -> object:
        return [[start_ms, "10", "12", "9", "11", "0", start_ms + 299_999]]

    table = DerivativesMarketDataClient(request).fetch(
        MarketDataKind.MARK_KLINE,
        symbol="BTCUSDT",
        start=start,
        end=start + timedelta(minutes=5),
        ingested_at=start + timedelta(days=1),
    )

    assert table.column("availability_time")[0].as_py() == start + timedelta(minutes=5)


def test_index_kline_uses_official_pair_parameter() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)

    def request(path: str, params: dict[str, object] | None) -> object:
        assert path == "/fapi/v1/indexPriceKlines"
        assert params is not None
        assert params["pair"] == "BTCUSDT"
        assert "symbol" not in params
        return [[start_ms, "10", "12", "9", "11", "0", start_ms + 299_999]]

    DerivativesMarketDataClient(request).fetch(
        MarketDataKind.INDEX_KLINE,
        symbol="BTCUSDT",
        start=start,
        end=start + timedelta(minutes=5),
        ingested_at=start + timedelta(days=1),
    )


def test_feature_v2_is_causal_and_gap_safe() -> None:
    candles = make_research_candles(800)
    first = generate_features_v2(candles_to_table(candles), interval="5m")
    mutated = list(candles)
    mutated[600] = replace(
        mutated[600],
        open=mutated[600].open * 2,
        high=mutated[600].high * 2,
        low=mutated[600].low * 2,
        close=mutated[600].close * 2,
    )
    second = generate_features_v2(candles_to_table(mutated), interval="5m")

    assert first.columns == tuple(
        name
        for group in (
            "price",
            "trend",
            "momentum",
            "volatility",
            "volume",
            "pressure",
            "regime",
            "time",
        )
        for name in FEATURE_GROUPS[group]
    )
    assert len(first.columns) == 47
    for name in first.columns:
        np.testing.assert_allclose(
            first.values[name][:600], second.values[name][:600], equal_nan=True
        )

    gapped = generate_features_v2(
        candles_to_table(make_research_candles(900, gap_index=500)), interval="5m"
    )
    assert not np.any(gapped.valid_mask[500 : 500 + 335])
    assert gapped.valid_mask[500 + 335]


def test_feature_v2_rejects_impossible_taker_volume() -> None:
    candles = make_research_candles(400)
    candles[10] = replace(
        candles[10],
        taker_buy_base_volume=candles[10].base_volume + Decimal("1"),
    )
    with pytest.raises(ValueError, match="cannot exceed"):
        generate_features_v2(candles_to_table(candles), interval="5m")


def test_market_ingestion_is_restartable_across_retrieval_times(tmp_path) -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    start_ms = int(start.timestamp() * 1_000)

    def request(_: str, __: dict[str, object] | None) -> object:
        return [
            {
                "fundingTime": start_ms,
                "fundingRate": "0.0001",
                "markPrice": "65000",
            }
        ]

    client = DerivativesMarketDataClient(request)
    first = client.fetch(
        MarketDataKind.FUNDING,
        symbol="BTCUSDT",
        start=start,
        end=start + timedelta(hours=1),
        ingested_at=start + timedelta(days=1),
    )
    second = client.fetch(
        MarketDataKind.FUNDING,
        symbol="BTCUSDT",
        start=start,
        end=start + timedelta(hours=1),
        ingested_at=start + timedelta(days=2),
    )
    first_manifest = ingest_public_market_data(
        first,
        kind=MarketDataKind.FUNDING,
        symbol="BTCUSDT",
        interval=None,
        output_root=tmp_path,
        request_start=start,
        request_end=start + timedelta(hours=1),
    )
    second_manifest = ingest_public_market_data(
        second,
        kind=MarketDataKind.FUNDING,
        symbol="BTCUSDT",
        interval=None,
        output_root=tmp_path,
        request_start=start,
        request_end=start + timedelta(hours=1),
    )

    assert first_manifest == second_manifest
