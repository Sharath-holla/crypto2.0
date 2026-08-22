from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_ai.context.binance_open_interest import (
    OI_COVERAGE_LIMITATION,
    BinanceOpenInterestProvider,
    build_open_interest_features,
    open_interest_history_schema,
)
from crypto_ai.context.storage import ContextStore


def _history_row(timestamp: int, oi: str = "100", value: str = "200") -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "sumOpenInterest": oi,
        "sumOpenInterestValue": value,
        "timestamp": timestamp,
    }


def test_current_snapshot_normalization_is_exact_and_forward_only() -> None:
    provider = BinanceOpenInterestProvider(lambda *_: None)
    captured = datetime(2026, 8, 22, tzinfo=UTC)
    table = provider.normalize_snapshot(
        {"symbol": "BTCUSDT", "openInterest": "10659.509", "time": 1_589_437_530_011},
        symbol="BTCUSDT",
        ingested_at=captured,
    )
    row = table.to_pylist()[0]
    assert row["open_interest"] == Decimal("10659.509")
    assert row["availability_time"] == captured
    assert row["observation_class"] == "FORWARD_OBSERVATION_DATA"
    assert row["training_eligibility"] == "FORWARD_ONLY"
    assert row["training_eligible"] is False


@pytest.mark.parametrize(
    "payload,symbol",
    [
        ([], "BTCUSDT"),
        ({"symbol": "ETHUSDT", "openInterest": "1", "time": 1}, "BTCUSDT"),
        ({"symbol": "BTCUSDT", "openInterest": "-1", "time": 1}, "BTCUSDT"),
        ({"symbol": "BTCUSDT", "time": 1}, "BTCUSDT"),
    ],
)
def test_invalid_current_snapshot_is_rejected(payload: object, symbol: str) -> None:
    with pytest.raises(ValueError):
        BinanceOpenInterestProvider(lambda *_: None).normalize_snapshot(payload, symbol=symbol)


def test_history_normalization_sorts_deduplicates_and_preserves_5m_period() -> None:
    provider = BinanceOpenInterestProvider(lambda *_: None)
    start = datetime(2026, 7, 20, tzinfo=UTC)
    end = start + timedelta(minutes=15)
    first_ms = int(start.timestamp() * 1_000)
    table, duplicates = provider.normalize_history(
        [
            _history_row(first_ms + 300_000, "101", "201"),
            _history_row(first_ms),
            _history_row(first_ms),
        ],
        symbol="BTCUSDT",
        period="5m",
        requested_start=start,
        requested_end=end,
        ingested_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
    )
    rows = table.to_pylist()
    assert duplicates == 1
    assert table.num_rows == 2
    assert all(row["period"] == "5m" for row in rows)
    assert [row["sum_open_interest"] for row in rows] == [Decimal("100"), Decimal("101")]


def test_conflicting_history_duplicate_is_rejected() -> None:
    provider = BinanceOpenInterestProvider(lambda *_: None)
    start = datetime(2026, 7, 20, tzinfo=UTC)
    timestamp = int(start.timestamp() * 1_000)
    with pytest.raises(ValueError, match="Conflicting Binance"):
        provider.normalize_history(
            [_history_row(timestamp, "100"), _history_row(timestamp, "101")],
            symbol="BTCUSDT",
            period="5m",
            requested_start=start,
            requested_end=start + timedelta(minutes=5),
        )


def test_recent_history_paginates_forward() -> None:
    captured = datetime(2026, 8, 20, tzinfo=UTC)
    start = captured - timedelta(minutes=15)
    start_ms = int(start.timestamp() * 1_000)
    calls: list[dict[str, object]] = []

    def request(_path: str, params: dict[str, object] | None):
        assert params is not None
        calls.append(params)
        if len(calls) == 1:
            return [_history_row(start_ms), _history_row(start_ms + 300_000)]
        return [_history_row(start_ms + 600_000)]

    rows = BinanceOpenInterestProvider(request).fetch_recent_history(
        symbol="BTCUSDT",
        period="5m",
        start=start,
        end=captured,
        ingested_at=captured,
        limit=2,
    )
    assert len(rows) == 3
    assert calls[0]["startTime"] == start_ms
    assert calls[1]["startTime"] == start_ms + 600_000


def test_recent_history_empty_response_is_legitimate_empty_coverage() -> None:
    captured = datetime(2026, 8, 20, tzinfo=UTC)
    rows = BinanceOpenInterestProvider(lambda *_: []).fetch_recent_history(
        symbol="BTCUSDT",
        period="5m",
        start=captured - timedelta(hours=1),
        end=captured,
        ingested_at=captured,
    )
    assert rows == []


def test_recent_history_cannot_exceed_official_retention() -> None:
    captured = datetime(2026, 8, 20, tzinfo=UTC)
    with pytest.raises(ValueError, match="official recent retention"):
        BinanceOpenInterestProvider(lambda *_: []).fetch_recent_history(
            symbol="BTCUSDT",
            period="5m",
            start=captured - timedelta(days=31),
            end=captured,
            ingested_at=captured,
            provider_history_days=30,
        )


def test_no_fake_historical_extension() -> None:
    provider = BinanceOpenInterestProvider(lambda *_: None)
    start = datetime(2026, 7, 20, tzinfo=UTC)
    valid_ms = int(start.timestamp() * 1_000)
    fake_old_ms = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1_000)
    table, _ = provider.normalize_history(
        [_history_row(fake_old_ms), _history_row(valid_ms)],
        symbol="BTCUSDT",
        period="5m",
        requested_start=start,
        requested_end=start + timedelta(minutes=5),
    )
    assert table.num_rows == 1
    assert table.to_pylist()[0]["provider_timestamp"].year == 2026


def test_history_manifest_records_coverage_and_restart_deduplication(tmp_path: Path) -> None:
    captured = datetime(2026, 8, 20, tzinfo=UTC)
    start = captured - timedelta(minutes=10)
    payload = [
        _history_row(int(start.timestamp() * 1_000)),
        _history_row(int((start + timedelta(minutes=5)).timestamp() * 1_000), "101", "201"),
    ]
    provider = BinanceOpenInterestProvider(lambda *_: payload)
    store = ContextStore(
        tmp_path,
        provider_id="binance_open_interest",
        dataset_name="recent_history/btcusdt/5m",
        key_columns=("symbol", "period", "provider_timestamp"),
        expected_step=timedelta(minutes=5),
    )
    first = provider.collect_recent_history(
        symbol="BTCUSDT",
        period="5m",
        start=start,
        end=captured,
        store=store,
        config_hash="config-a",
        ingested_at=captured,
    )
    second = provider.collect_recent_history(
        symbol="BTCUSDT",
        period="5m",
        start=start,
        end=captured,
        store=store,
        config_hash="config-a",
        ingested_at=captured + timedelta(minutes=1),
    )
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert second.reused is True
    assert manifest["coverage_limitation"] == OI_COVERAGE_LIMITATION
    assert manifest["training_eligibility"] == "FORWARD_ONLY"
    assert manifest["observation_class"] == "FORWARD_OBSERVATION_DATA"
    assert manifest["period"] == "5m"
    assert manifest["actual_start"].startswith("2026-")


def test_snapshot_restart_deduplicates_same_provider_key(tmp_path: Path) -> None:
    payload = {"symbol": "BTCUSDT", "openInterest": "10", "time": 1_776_643_200_000}
    provider = BinanceOpenInterestProvider(lambda *_: payload)
    store = ContextStore(
        tmp_path,
        provider_id="binance_open_interest",
        dataset_name="forward_snapshots/btcusdt",
        key_columns=("symbol", "provider_timestamp"),
    )
    first = provider.collect_snapshot(
        symbol="BTCUSDT",
        store=store,
        config_hash="config-a",
        ingested_at=datetime(2026, 4, 20, tzinfo=UTC),
    )
    second = provider.collect_snapshot(
        symbol="BTCUSDT",
        store=store,
        config_hash="config-a",
        ingested_at=datetime(2026, 4, 20, 0, 5, tzinfo=UTC),
    )
    assert first.reused is False
    assert second.reused is True
    assert second.row_count == 1


def test_forward_only_features_are_disabled_by_default_and_have_no_backfill() -> None:
    captured = datetime(2026, 7, 20, 0, 10, tzinfo=UTC)
    start = captured - timedelta(minutes=10)
    start_ms = int(start.timestamp() * 1_000)
    provider = BinanceOpenInterestProvider(lambda *_: None)
    table, _ = provider.normalize_history(
        [_history_row(start_ms), _history_row(start_ms + 300_000, "110", "220")],
        symbol="BTCUSDT",
        period="5m",
        requested_start=start,
        requested_end=captured,
        ingested_at=captured,
    )
    feature_times = [captured - timedelta(seconds=1), captured, captured + timedelta(minutes=1)]
    disabled = build_open_interest_features(feature_times, table).to_pylist()
    enabled = build_open_interest_features(
        feature_times, table, allow_forward_only=True
    ).to_pylist()
    assert all(row["has_open_interest"] == 0 for row in disabled)
    assert enabled[0]["has_open_interest"] == 0
    assert enabled[1]["has_open_interest"] == 1
    assert enabled[1]["oi_change_5m"] == 10.0


def test_history_schema_is_distinct_from_snapshot_schema() -> None:
    fields = set(open_interest_history_schema().names)
    assert "sum_open_interest" in fields
    assert "sum_open_interest_value" in fields
    assert "open_interest" not in fields
