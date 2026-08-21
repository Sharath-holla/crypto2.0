from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pyarrow as pa
import pytest

from crypto_ai.data.quality.checks import validate_partition
from crypto_ai.data.quality.models import (
    ValidationContext,
    ValidationSeverity,
    ValidationStatus,
)
from crypto_ai.data.quality.policy import QualityPolicy
from crypto_ai.data.schema import candles_to_table
from tests.factories import make_candle


def _validate(candles, interval: str = "5m", **context_overrides):
    context = ValidationContext(
        symbol=context_overrides.pop("symbol", "BTCUSDT"),
        interval=interval,
        source=context_overrides.pop("source", "binance_usdm_futures_rest"),
        **context_overrides,
    )
    return validate_partition(candles_to_table(candles), context)


def _codes(result, status: ValidationStatus | None = None) -> set[str]:
    return {check.check_name for check in result.checks if status is None or check.status is status}


def test_valid_5m_and_chronological_data_pass() -> None:
    result = _validate([make_candle(index) for index in range(12)])

    assert result.status is ValidationStatus.PASS
    assert result.metrics["number_of_missing_candles"] == 0


def test_valid_1m_data_passes() -> None:
    candles = [make_candle(index, interval_minutes=1) for index in range(10)]

    result = _validate(candles, "1m")

    assert result.status is ValidationStatus.PASS


@pytest.mark.parametrize("drift", ["missing", "type", "unexpected"])
def test_schema_drift_fails(drift: str) -> None:
    table = candles_to_table([make_candle()])
    if drift == "missing":
        table = table.drop(["source"])
    elif drift == "type":
        table = table.set_column(table.column_names.index("open"), "open", pa.array(["bad"]))
    else:
        table = table.append_column("unexpected", pa.array([1]))

    result = validate_partition(
        table,
        ValidationContext(symbol="BTCUSDT", interval="5m"),
    )

    assert result.status is ValidationStatus.FAIL
    assert "schema_mismatch" in _codes(result, ValidationStatus.FAIL)


def test_duplicate_timestamp_distinguishes_exact_and_conflicting_rows() -> None:
    candle = make_candle()
    conflict = replace(
        candle,
        high=candle.high + Decimal("1"),
        close=candle.close + Decimal("1"),
    )

    exact = _validate([candle, candle])
    conflicting = _validate([candle, conflict])

    assert "exact_duplicate" in _codes(exact)
    assert "conflicting_duplicate" in _codes(conflicting)
    conflict_check = next(
        check for check in conflicting.checks if check.check_name == "conflicting_duplicate"
    )
    exact_check = next(check for check in exact.checks if check.check_name == "exact_duplicate")
    assert conflict_check.severity is ValidationSeverity.CRITICAL
    assert conflict_check.severity != exact_check.severity


def test_policy_can_warn_for_reported_exact_duplicate() -> None:
    candle = make_candle()

    result = validate_partition(
        candles_to_table([candle, candle]),
        ValidationContext(symbol="BTCUSDT", interval="5m"),
        QualityPolicy(allowed_duplicate_count=1),
    )

    assert result.status is ValidationStatus.WARN
    assert "exact_duplicate" in _codes(result, ValidationStatus.WARN)


def test_out_of_order_timestamp_fails() -> None:
    result = _validate([make_candle(1), make_candle(0)])

    assert "non_monotonic_timestamp" in _codes(result, ValidationStatus.FAIL)


def test_misaligned_5m_timestamp_fails() -> None:
    candle = make_candle()
    shifted = replace(
        candle,
        open_time=candle.open_time + timedelta(minutes=1),
        close_time=candle.close_time + timedelta(minutes=1),
    )

    result = _validate([shifted])

    assert "misaligned_open_time" in _codes(result, ValidationStatus.FAIL)


def test_open_time_not_before_close_and_invalid_duration_fail() -> None:
    candle = make_candle()
    invalid = replace(candle, close_time=candle.open_time)

    result = _validate([invalid])

    assert {"open_not_before_close", "invalid_close_time"} <= _codes(result, ValidationStatus.FAIL)


def test_single_and_multiple_gaps_report_counts_and_largest_run() -> None:
    single = _validate([make_candle(0), make_candle(2)])
    multiple = _validate([make_candle(0), make_candle(4)])

    assert single.metrics["number_of_missing_candles"] == 1
    assert single.metrics["largest_gap"] == 1
    assert multiple.metrics["number_of_missing_candles"] == 3
    assert multiple.metrics["largest_gap"] == 3
    assert multiple.metrics["gap_classification"] == "UNKNOWN_GAP"


@pytest.mark.parametrize(
    ("code", "changes"),
    [
        ("high_below_open", {"high": Decimal("64999")}),
        ("high_below_close", {"high": Decimal("65000.5")}),
        ("low_above_open", {"low": Decimal("65000.5")}),
        ("low_above_close", {"low": Decimal("65002")}),
        ("high_below_low", {"high": Decimal("65000"), "low": Decimal("65000.5")}),
        ("non_positive_price", {"open": Decimal("0")}),
    ],
)
def test_impossible_ohlc_relationships_fail(code: str, changes: dict) -> None:
    result = _validate([replace(make_candle(), **changes)])

    assert code in _codes(result, ValidationStatus.FAIL)
    assert result.metrics["invalid_ohlc"] == 1


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("base_volume", "negative_base_volume"),
        ("quote_volume", "negative_quote_volume"),
        ("taker_buy_base_volume", "negative_taker_buy_base_volume"),
        ("taker_buy_quote_volume", "negative_taker_buy_quote_volume"),
        ("trade_count", "negative_trade_count"),
    ],
)
def test_negative_volume_and_trade_values_fail(field: str, code: str) -> None:
    value = -1 if field == "trade_count" else Decimal("-1")

    result = _validate([replace(make_candle(), **{field: value})])

    assert code in _codes(result, ValidationStatus.FAIL)


def test_taker_volume_and_trade_count_relationships_fail() -> None:
    candle = make_candle()
    taker = replace(candle, taker_buy_base_volume=candle.base_volume + Decimal("1"))
    no_trades = replace(candle, trade_count=0)

    assert "taker_buy_base_exceeds_volume" in _codes(_validate([taker]), ValidationStatus.FAIL)
    assert "positive_volume_without_trades" in _codes(_validate([no_trades]), ValidationStatus.FAIL)


def test_zero_volume_reports_percentage_runs_and_configurable_warning() -> None:
    candle = make_candle()
    candles = [
        replace(candle, base_volume=Decimal("0"), taker_buy_base_volume=Decimal("0")),
        replace(
            make_candle(1),
            base_volume=Decimal("0"),
            taker_buy_base_volume=Decimal("0"),
        ),
        make_candle(2),
    ]
    policy = QualityPolicy(zero_volume_failure_percentage=100.0)

    result = validate_partition(
        candles_to_table(candles),
        ValidationContext(symbol="BTCUSDT", interval="5m"),
        policy,
    )

    assert result.status is ValidationStatus.WARN
    assert result.metrics["zero_volume_count"] == 2
    assert result.metrics["consecutive_zero_volume_runs"] == [2]


def test_statistical_spike_is_warning_and_row_is_not_deleted() -> None:
    candles = []
    for index in range(30):
        price = Decimal("100000") if index == 20 else Decimal("65000")
        candle = make_candle(index)
        candles.append(
            replace(
                candle,
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price,
            )
        )
    table = candles_to_table(candles)

    result = validate_partition(
        table,
        ValidationContext(symbol="BTCUSDT", interval="5m"),
    )

    assert result.status is ValidationStatus.WARN
    assert result.metrics["candidate_outliers"] >= 1
    assert table.num_rows == 30
    assert table["close"].to_pylist()[20] == Decimal("100000.000000000000000000")


def test_short_normal_volatile_sample_is_not_marked_corrupt() -> None:
    candles = []
    for index, price in enumerate(["65000", "66000", "64500", "67000", "65500", "68000"]):
        candle = make_candle(index)
        value = Decimal(price)
        candles.append(
            replace(
                candle,
                open=value,
                high=value + Decimal("100"),
                low=value - Decimal("100"),
                close=value,
            )
        )

    result = _validate(candles)

    assert "candidate_price_outlier" not in _codes(result)
    assert result.status is ValidationStatus.PASS


def test_stale_repeated_flat_candles_warn() -> None:
    price = Decimal("65000")
    candles = [
        replace(make_candle(index), open=price, high=price, low=price, close=price)
        for index in range(3)
    ]

    result = _validate(candles)

    assert "stale_flat_run" in _codes(result, ValidationStatus.WARN)


def test_source_symbol_ingestion_and_partition_consistency_failures() -> None:
    base = make_candle()
    mixed = [base, make_candle(1, symbol="ETHUSDT")]
    future = replace(base, ingested_at=datetime.now(UTC) + timedelta(days=1))
    start = base.open_time + timedelta(minutes=5)

    assert "symbol_consistency" in _codes(_validate(mixed), ValidationStatus.FAIL)
    assert "future_ingestion_timestamp" in _codes(_validate([future]), ValidationStatus.FAIL)
    assert "partition_boundary" in _codes(
        _validate(
            [base],
            range_start=start,
            range_end=start + timedelta(minutes=5),
        ),
        ValidationStatus.FAIL,
    )
