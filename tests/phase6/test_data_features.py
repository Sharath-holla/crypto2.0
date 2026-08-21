from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import numpy as np
import pytest

from crypto_ai.data.binance.archive import (
    ArchiveDataset,
    ArchiveFrequency,
    ArchiveObject,
    BinanceArchiveClient,
)
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.validation import validate_candles
from crypto_ai.phase6.config import FEATURE_RESEARCH_VERSION
from crypto_ai.phase6.data import aggregate_candles, reconcile_direct_vs_derived
from crypto_ai.phase6.features import (
    FEATURE_GROUPS_V3_RESEARCH,
    _align_higher,
    _higher_timeframe_values,
)
from tests.factories import make_candle


class _MetadataClient:
    def fetch_exchange_info(self, symbol: str) -> dict[str, object]:
        return {"instrument": {"symbol": symbol}}


def _higher_timeframe_archive(interval: str, step_minutes: int) -> bytes:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    rows = [
        "open_time,open,high,low,close,volume,close_time,quote_volume,"
        "count,taker_buy_volume,taker_buy_quote_volume,ignore"
    ]
    for index in range(2):
        opened = start + timedelta(minutes=step_minutes * index)
        open_ms = int(opened.timestamp() * 1_000)
        close_ms = open_ms + step_minutes * 60_000 - 1
        rows.append(f"{open_ms},100.000000000000000001,102,99,101,10,{close_ms},1010,20,6,606,0")
    payload = ("\n".join(rows) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"BTCUSDT-{interval}-2026-06.csv", payload)
    return buffer.getvalue()


@pytest.mark.parametrize("interval", ["12h", "1d"])
def test_official_archive_path_supports_higher_timeframes(interval: str) -> None:
    item = ArchiveObject(
        ArchiveDataset.KLINES,
        ArchiveFrequency.MONTHLY,
        "BTCUSDT",
        interval,
        datetime(2026, 6, 1, tzinfo=UTC).date(),
    )

    assert item.relative_url == (
        f"/monthly/klines/BTCUSDT/{interval}/BTCUSDT-{interval}-2026-06.zip"
    )


@pytest.mark.parametrize("interval,minutes", [("12h", 720), ("1d", 1440)])
def test_higher_timeframe_archive_ingestion_preserves_exact_decimals(
    tmp_path: Path, interval: str, minutes: int
) -> None:
    content = _higher_timeframe_archive(interval, minutes)
    digest = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".CHECKSUM"):
            return httpx.Response(
                200, content=f"{digest}  BTCUSDT-{interval}-2026-06.zip\n".encode()
            )
        return httpx.Response(200, content=content)

    client = BinanceArchiveClient(
        raw_root=tmp_path,
        metadata_client=_MetadataClient(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    start = datetime(2026, 6, 1, tzinfo=UTC)
    candles = client.fetch_klines(
        symbol="BTCUSDT",
        interval=interval,
        start=start,
        end=start + timedelta(minutes=2 * minutes),
        ingested_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    client.close()

    assert len(candles) == 2
    assert candles[0].open == Decimal("100.000000000000000001")
    assert candles[1].open_time - candles[0].open_time == timedelta(minutes=minutes)
    assert candles[0].source == "binance_usdm_futures_archive"


@pytest.mark.parametrize("interval,minutes", [("12h", 720), ("1d", 1440)])
def test_higher_timeframe_schema_and_timestamps_pass(interval: str, minutes: int) -> None:
    table = candles_to_table(
        [
            make_candle(
                i,
                start=datetime(2026, 6, 1, tzinfo=UTC),
                interval_minutes=minutes,
            )
            for i in range(5)
        ]
    )

    assert validate_candles(table, interval).is_valid


@pytest.mark.parametrize("target,rows", [("12h", 144), ("1d", 288)])
def test_direct_vs_derived_reconciliation_is_exact(target: str, rows: int) -> None:
    lower = candles_to_table(
        [
            make_candle(
                i,
                start=datetime(2026, 6, 1, tzinfo=UTC),
                interval_minutes=5,
            )
            for i in range(rows)
        ]
    )
    derived = aggregate_candles(lower, target)

    report = reconcile_direct_vs_derived(derived, derived, target)

    assert derived.num_rows == 1
    assert report["exact_match_rows"] == 1
    assert report["discrepant_rows"] == 0


def test_incomplete_derived_candle_is_rejected() -> None:
    lower = candles_to_table([make_candle(i) for i in range(143)])

    assert aggregate_candles(lower, "12h").num_rows == 0


def test_completed_candle_asof_mapping_uses_latest_available_bar() -> None:
    source = candles_to_table(
        [
            make_candle(
                i,
                start=datetime(2026, 6, 1, tzinfo=UTC),
                interval_minutes=720,
            )
            for i in range(3)
        ]
    )
    feature_times = np.asarray(
        [
            int(datetime(2026, 6, 1, 11, 55, tzinfo=UTC).timestamp() * 1_000_000),
            int(datetime(2026, 6, 1, 12, 0, tzinfo=UTC).timestamp() * 1_000_000),
            int(datetime(2026, 6, 2, 0, 0, tzinfo=UTC).timestamp() * 1_000_000),
        ]
    )
    aligned, available, source_time, availability = _align_higher(
        source, feature_times, {"x": np.asarray([1.0, 2.0, 3.0])}, "12h"
    )

    assert available.tolist() == [False, True, True]
    assert np.isnan(aligned["x"][0])
    assert aligned["x"][1:].tolist() == [1.0, 2.0]
    assert source_time[1] < availability[1] <= feature_times[1]


def test_higher_timeframe_future_perturbation_is_safe() -> None:
    candles = [make_candle(i, interval_minutes=720) for i in range(250)]
    first = _higher_timeframe_values(candles_to_table(candles), "12h")
    mutated = list(candles)
    for index in range(220, len(mutated)):
        mutated[index] = replace(mutated[index], close=mutated[index].close * 2)
    second = _higher_timeframe_values(candles_to_table(mutated), "12h")

    for name in FEATURE_GROUPS_V3_RESEARCH["higher_timeframe_12h"]:
        np.testing.assert_allclose(first[name][:220], second[name][:220], equal_nan=True)


def test_feature_research_version_is_isolated_and_contains_no_targets() -> None:
    new_columns = tuple(
        name
        for group in (
            "higher_timeframe_12h",
            "higher_timeframe_1d",
            "cross_timeframe",
            "market_stress_research",
        )
        for name in FEATURE_GROUPS_V3_RESEARCH[group]
    )

    assert FEATURE_RESEARCH_VERSION.startswith("market_v3_research")
    assert all(token not in name for name in new_columns for token in ("future", "mfe", "mae"))
