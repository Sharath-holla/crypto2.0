from __future__ import annotations

from collections.abc import Iterable

import pyarrow as pa

from crypto_ai.domain import Candle

CANDLE_SCHEMA_VERSION = "1.0.0"
DECIMAL_TYPE = pa.decimal128(38, 18)


def candle_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("open_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("close_time", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("open", DECIMAL_TYPE, nullable=False),
            pa.field("high", DECIMAL_TYPE, nullable=False),
            pa.field("low", DECIMAL_TYPE, nullable=False),
            pa.field("close", DECIMAL_TYPE, nullable=False),
            pa.field("base_volume", DECIMAL_TYPE, nullable=False),
            pa.field("quote_volume", DECIMAL_TYPE, nullable=False),
            pa.field("trade_count", pa.int64(), nullable=False),
            pa.field("taker_buy_base_volume", DECIMAL_TYPE, nullable=False),
            pa.field("taker_buy_quote_volume", DECIMAL_TYPE, nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        ],
        metadata={b"schema_version": CANDLE_SCHEMA_VERSION.encode("ascii")},
    )


def candles_to_table(candles: Iterable[Candle]) -> pa.Table:
    rows = list(candles)
    schema = candle_schema()
    columns = {
        "symbol": [row.symbol for row in rows],
        "open_time": [row.open_time for row in rows],
        "close_time": [row.close_time for row in rows],
        "open": [row.open for row in rows],
        "high": [row.high for row in rows],
        "low": [row.low for row in rows],
        "close": [row.close for row in rows],
        "base_volume": [row.base_volume for row in rows],
        "quote_volume": [row.quote_volume for row in rows],
        "trade_count": [row.trade_count for row in rows],
        "taker_buy_base_volume": [row.taker_buy_base_volume for row in rows],
        "taker_buy_quote_volume": [row.taker_buy_quote_volume for row in rows],
        "source": [row.source for row in rows],
        "ingested_at": [row.ingested_at for row in rows],
    }
    return pa.Table.from_pydict(columns, schema=schema)


def schema_errors(schema: pa.Schema) -> list[str]:
    expected = candle_schema()
    errors: list[str] = []
    if schema.names != expected.names:
        errors.append(f"column order/names differ: expected {expected.names}, got {schema.names}")
        return errors
    for actual_field, expected_field in zip(schema, expected, strict=True):
        if actual_field.type != expected_field.type:
            errors.append(
                f"{actual_field.name} type differs: expected {expected_field.type}, "
                f"got {actual_field.type}"
            )
        if actual_field.nullable != expected_field.nullable:
            errors.append(
                f"{actual_field.name} nullability differs: expected "
                f"{expected_field.nullable}, got {actual_field.nullable}"
            )
    return errors
