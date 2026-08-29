from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_ai.data.binance import ArchiveCandleBounds
from crypto_ai.phase7.acquisition import plan_candle_download_request
from crypto_ai.phase7.config import UniverseConfig
from crypto_ai.phase7.registry import SymbolRecord, build_symbol_registry
from crypto_ai.phase7.universe import EligibilityStatus, evaluate_eligibility

RESEARCH_CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)
COARSE_ARCHIVE_START = datetime(2025, 6, 1, tzinfo=UTC)
ONBOARD_DATE = datetime(2025, 6, 5, 8, 30, tzinfo=UTC)


def _record(*, onboard_date: datetime | None, available_from: datetime) -> SymbolRecord:
    metadata: dict[str, object] = {
        "symbol": "NEWCOINUSDT",
        "baseAsset": "NEWCOIN",
        "quoteAsset": "USDT",
        "contractType": "PERPETUAL",
        "status": "TRADING",
    }
    if onboard_date is not None:
        metadata["onboardDate"] = int(onboard_date.timestamp() * 1_000)
    registry = build_symbol_registry(
        {"symbols": [metadata]},
        [
            {
                "symbol": "NEWCOINUSDT",
                "first_market_data_time": available_from,
                "last_market_data_time": RESEARCH_CUTOFF - timedelta(minutes=5),
                "available_intervals": ["5m", "12h", "1d"],
                "availability_evidence": "OFFICIAL_ARCHIVE_PERIOD_EVIDENCE",
            }
        ],
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=RESEARCH_CUTOFF,
    )
    return registry.records[0]


def _exact_bounds(first: datetime, last: datetime, interval: timedelta) -> ArchiveCandleBounds:
    return ArchiveCandleBounds(
        first_open_time=first,
        last_open_time=last,
        end_exclusive=last + interval,
        inspected_objects=("first.zip", "last.zip"),
    )


@pytest.mark.parametrize(
    ("interval", "expected_start"),
    [
        ("1d", datetime(2025, 6, 5, tzinfo=UTC)),
        ("12h", datetime(2025, 6, 5, tzinfo=UTC)),
        ("5m", ONBOARD_DATE),
    ],
)
def test_download_request_starts_at_listing_candle_bucket(
    interval: str,
    expected_start: datetime,
) -> None:
    record = _record(onboard_date=ONBOARD_DATE, available_from=COARSE_ARCHIVE_START)

    request = plan_candle_download_request(
        record,
        interval=interval,
        start=COARSE_ARCHIVE_START,
        end=datetime(2025, 7, 1, tzinfo=UTC),
    )

    assert request is not None
    assert request.start_utc == expected_start


def test_earlier_onboard_date_cannot_move_request_before_market_data_evidence() -> None:
    verified_start = datetime(2025, 6, 5, tzinfo=UTC)
    record = _record(
        onboard_date=datetime(2025, 6, 1, 8, 30, tzinfo=UTC),
        available_from=verified_start,
    )

    request = plan_candle_download_request(
        record,
        interval="1d",
        start=COARSE_ARCHIVE_START,
        end=datetime(2025, 7, 1, tzinfo=UTC),
    )

    assert record.available_from == verified_start
    assert record.causal_available_from == verified_start
    assert request is not None
    assert request.start_utc == verified_start


def test_missing_onboard_date_preserves_available_from_request_behavior() -> None:
    record = _record(onboard_date=None, available_from=COARSE_ARCHIVE_START)

    request = plan_candle_download_request(
        record,
        interval="1d",
        start=datetime(2025, 5, 1, tzinfo=UTC),
        end=datetime(2025, 7, 1, tzinfo=UTC),
    )

    assert request is not None
    assert request.start_utc == COARSE_ARCHIVE_START


def test_later_onboard_date_prevents_causal_pre_listing_eligibility() -> None:
    record = _record(onboard_date=ONBOARD_DATE, available_from=COARSE_ARCHIVE_START)
    before_onboard = ONBOARD_DATE - timedelta(microseconds=1)

    decision = evaluate_eligibility(
        record,
        None,
        as_of=before_onboard,
        config=UniverseConfig(fixture_mode=True),
    )

    assert record.available_from == COARSE_ARCHIVE_START
    assert record.causal_available_from == ONBOARD_DATE
    assert not record.exists_at(before_onboard)
    assert record.exists_at(ONBOARD_DATE)
    assert decision.status is EligibilityStatus.INELIGIBLE_NOT_AVAILABLE
    assert record.history_days_at(before_onboard) == 0.0
    expected_history = (record.last_market_data_time - ONBOARD_DATE).total_seconds() / 86_400
    assert record.history_days == pytest.approx(expected_history)


@pytest.mark.parametrize(
    ("interval", "first", "last", "duration"),
    [
        (
            "1d",
            datetime(2022, 1, 26, tzinfo=UTC),
            datetime(2022, 4, 11, tzinfo=UTC),
            timedelta(days=1),
        ),
        (
            "12h",
            datetime(2022, 1, 26, 12, tzinfo=UTC),
            datetime(2022, 4, 11, 12, tzinfo=UTC),
            timedelta(hours=12),
        ),
        (
            "5m",
            datetime(2022, 1, 26, 0, 5, tzinfo=UTC),
            datetime(2022, 4, 11, 23, 55, tzinfo=UTC),
            timedelta(minutes=5),
        ),
    ],
)
def test_exact_interval_bounds_trim_only_partial_outer_months(
    interval: str,
    first: datetime,
    last: datetime,
    duration: timedelta,
) -> None:
    record = _record(onboard_date=None, available_from=datetime(2022, 1, 1, tzinfo=UTC))
    bounds = _exact_bounds(first, last, duration)

    request = plan_candle_download_request(
        record,
        interval=interval,
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2022, 5, 1, tzinfo=UTC),
        exact_bounds=bounds,
    )

    assert request is not None
    assert request.start_utc == first
    assert request.end_utc == last + duration


def test_exact_data_start_wins_when_onboard_precedes_verified_interval_rows() -> None:
    record = _record(
        onboard_date=datetime(2022, 1, 10, tzinfo=UTC),
        available_from=datetime(2022, 1, 1, tzinfo=UTC),
    )
    exact_start = datetime(2022, 1, 26, tzinfo=UTC)

    request = plan_candle_download_request(
        record,
        interval="1d",
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2022, 5, 1, tzinfo=UTC),
        exact_bounds=_exact_bounds(
            exact_start,
            datetime(2022, 4, 11, tzinfo=UTC),
            timedelta(days=1),
        ),
    )

    assert request is not None
    assert request.start_utc == exact_start


def test_later_onboard_bucket_still_wins_over_exact_archive_start() -> None:
    record = _record(onboard_date=ONBOARD_DATE, available_from=COARSE_ARCHIVE_START)

    request = plan_candle_download_request(
        record,
        interval="1d",
        start=COARSE_ARCHIVE_START,
        end=datetime(2025, 7, 1, tzinfo=UTC),
        exact_bounds=_exact_bounds(
            datetime(2025, 6, 1, tzinfo=UTC),
            datetime(2025, 6, 30, tzinfo=UTC),
            timedelta(days=1),
        ),
    )

    assert request is not None
    assert request.start_utc == datetime(2025, 6, 5, tzinfo=UTC)


@pytest.mark.parametrize("status", ["INACTIVE", "TRADING"])
def test_exact_bounds_do_not_filter_symbols_by_current_status(status: str) -> None:
    record = _record(onboard_date=None, available_from=datetime(2022, 1, 1, tzinfo=UTC))
    record = record.model_copy(update={"current_status": status})

    request = plan_candle_download_request(
        record,
        interval="1d",
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2022, 5, 1, tzinfo=UTC),
        exact_bounds=_exact_bounds(
            datetime(2022, 1, 26, tzinfo=UTC),
            datetime(2022, 4, 11, tzinfo=UTC),
            timedelta(days=1),
        ),
    )

    assert request is not None
    assert request.start_utc == datetime(2022, 1, 26, tzinfo=UTC)
    assert request.end_utc == datetime(2022, 4, 12, tzinfo=UTC)
