from decimal import Decimal

import pyarrow as pa

from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION, candles_to_table, schema_errors
from tests.factories import make_candle


def test_canonical_schema_preserves_exact_decimals_and_utc() -> None:
    candle = make_candle()

    table = candles_to_table([candle])

    assert not schema_errors(table.schema)
    assert table.schema.metadata[b"schema_version"] == CANDLE_SCHEMA_VERSION.encode()
    assert table["open"].to_pylist() == [Decimal("65000.123456789012345678")]
    assert table["open"].type == pa.decimal128(38, 18)
    assert table["open_time"].type == pa.timestamp("us", tz="UTC")
    assert table["open_time"].to_pylist()[0].utcoffset().total_seconds() == 0


def test_schema_rejects_reordered_columns() -> None:
    table = candles_to_table([make_candle()])
    reordered = table.select(list(reversed(table.column_names)))

    errors = schema_errors(reordered.schema)

    assert errors
    assert "column order/names differ" in errors[0]
