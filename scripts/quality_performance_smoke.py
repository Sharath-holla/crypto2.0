from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_ai.data.quality.checks import validate_partition
from crypto_ai.data.quality.models import ValidationContext, ValidationStatus
from crypto_ai.data.schema import candles_to_table
from crypto_ai.domain import Candle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic Phase 2 validator performance smoke")
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument(
        "--tracemalloc",
        action="store_true",
        help="Measure Python allocations (substantially increases runtime)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.rows < 1:
        raise ValueError("--rows must be positive")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    captured_at = datetime(2026, 8, 19, tzinfo=UTC)
    candles = []
    for index in range(args.rows):
        open_time = start + index * timedelta(minutes=5)
        price = Decimal("60000") + Decimal(index) / Decimal("100")
        candles.append(
            Candle(
                symbol="BTCUSDT",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5) - timedelta(milliseconds=1),
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price + Decimal("1"),
                base_volume=Decimal("10"),
                quote_volume=Decimal("600000"),
                trade_count=100,
                taker_buy_base_volume=Decimal("5"),
                taker_buy_quote_volume=Decimal("300000"),
                source="binance_usdm_futures_rest",
                ingested_at=captured_at,
            )
        )
    table = candles_to_table(candles)
    del candles
    if args.tracemalloc:
        tracemalloc.start()
    started = time.perf_counter()
    result = validate_partition(
        table,
        ValidationContext(symbol="BTCUSDT", interval="5m", source="binance_usdm_futures_rest"),
    )
    duration = time.perf_counter() - started
    if args.tracemalloc:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mib: float | None = round(peak / 1024 / 1024, 3)
    else:
        peak_mib = None
    print(
        json.dumps(
            {
                "rows": table.num_rows,
                "runtime_seconds": round(duration, 6),
                "tracemalloc_peak_mib": peak_mib,
                "status": result.status.value,
                "candidate_outliers": result.metrics.get("candidate_outliers", 0),
                "missing_candles": result.metrics.get("number_of_missing_candles", 0),
            },
            sort_keys=True,
        )
    )
    return 0 if result.status is not ValidationStatus.FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
