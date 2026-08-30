from dataclasses import replace
from decimal import Decimal

import pyarrow as pa

from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.validation import validate_candles
from tests.factories import make_candle


def _error_codes(report) -> set[str]:
    return {issue.code for issue in report.errors}


def test_valid_candles_pass() -> None:
    table = candles_to_table([make_candle(index) for index in range(4)])

    report = validate_candles(table, "5m")

    assert report.is_valid
    assert report.gap_count == 0
    assert report.duplicate_count == 0


def test_duplicate_and_non_monotonic_timestamps_fail() -> None:
    table = candles_to_table([make_candle(0), make_candle(0)])

    report = validate_candles(table, "5m")

    assert not report.is_valid
    assert report.duplicate_count == 1
    assert {"duplicate_timestamp", "non_monotonic_timestamp"} <= _error_codes(report)


def test_gap_is_reported_and_never_filled() -> None:
    table = candles_to_table([make_candle(0), make_candle(2)])

    report = validate_candles(table, "5m")

    assert not report.is_valid
    assert report.gap_count == 1
    assert "missing_interval" in _error_codes(report)
    assert table.num_rows == 2


def test_invalid_ohlc_and_negative_volume_fail() -> None:
    candle = replace(
        make_candle(),
        high=Decimal("1"),
        base_volume=Decimal("-0.1"),
    )

    report = validate_candles(candles_to_table([candle]), "5m")

    assert {"invalid_ohlc", "negative_volume"} <= _error_codes(report)


def test_zero_volume_is_a_warning() -> None:
    candle = replace(
        make_candle(),
        base_volume=Decimal("0"),
        quote_volume=Decimal("0"),
        trade_count=0,
        taker_buy_base_volume=Decimal("0"),
        taker_buy_quote_volume=Decimal("0"),
    )

    report = validate_candles(candles_to_table([candle]), "5m")

    assert report.is_valid
    assert {warning.code for warning in report.warnings} == {"zero_volume"}


def test_missing_required_value_fails() -> None:
    table = candles_to_table([make_candle()])
    null_open = pa.array([None], type=table["open"].type)
    table = table.set_column(
        table.column_names.index("open"), table.schema.field("open"), null_open
    )

    report = validate_candles(table, "5m")

    assert not report.is_valid
    assert "missing_required_value" in _error_codes(report)
