from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import pyarrow as pa

from crypto_ai.context.models import ObservationClass, ProviderCapability, TrainingEligibility
from crypto_ai.context.storage import ContextStore, payload_sha256
from crypto_ai.data.schema import DECIMAL_TYPE

OPEN_INTEREST_FEATURE_VERSION = "open_interest_context_v1"
OI_HISTORY_SCHEMA_VERSION = "binance_open_interest_history_v1"
OI_SNAPSHOT_SCHEMA_VERSION = "binance_open_interest_snapshot_v1"
OI_SOURCE_VERSION = "binance_usdm_open_interest_api_verified_2026-08-22"
OI_CURRENT_ENDPOINT = "/fapi/v1/openInterest"
OI_HISTORY_ENDPOINT = "/futures/data/openInterestHist"
OI_COVERAGE_LIMITATION = "official provider retention: latest 1 month only"
OI_ELIGIBILITY_REASON = (
    "Open-interest observations are forward collected and excluded from the current Phase 7 "
    "historical market-data baseline"
)
_PERIOD_MINUTES = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1_440,
}


def _common_fields() -> list[pa.Field]:
    return [
        pa.field("availability_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("provider", pa.string(), nullable=False),
        pa.field("source_endpoint", pa.string(), nullable=False),
        pa.field("raw_identifier", pa.string(), nullable=False),
        pa.field("raw_payload_checksum", pa.string(), nullable=False),
        pa.field("normalized_schema_version", pa.string(), nullable=False),
        pa.field("source_version", pa.string(), nullable=False),
        pa.field("observation_class", pa.string(), nullable=False),
        pa.field("training_eligibility", pa.string(), nullable=False),
        pa.field("training_eligible", pa.bool_(), nullable=False),
        pa.field("eligibility_reason", pa.string(), nullable=False),
        pa.field("availability_policy", pa.string(), nullable=False),
    ]


def open_interest_history_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("period", pa.string(), nullable=False),
            pa.field("sum_open_interest", DECIMAL_TYPE, nullable=False),
            pa.field("sum_open_interest_value", DECIMAL_TYPE, nullable=False),
            pa.field("provider_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
            *_common_fields(),
        ],
        metadata={
            b"schema_version": OI_HISTORY_SCHEMA_VERSION.encode(),
            b"feature_version": OPEN_INTEREST_FEATURE_VERSION.encode(),
            b"coverage_limitation": b"latest_1_month",
        },
    )


def open_interest_snapshot_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("open_interest", DECIMAL_TYPE, nullable=False),
            pa.field("provider_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
            *_common_fields(),
        ],
        metadata={
            b"schema_version": OI_SNAPSHOT_SCHEMA_VERSION.encode(),
            b"feature_version": OPEN_INTEREST_FEATURE_VERSION.encode(),
        },
    )


def _utc_ms(value: object) -> datetime:
    return datetime.fromtimestamp(int(value) / 1_000, tz=UTC)


def _epoch_ms(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Open-interest range timestamps must be timezone-aware")
    return int(value.astimezone(UTC).timestamp() * 1_000)


class BinanceOpenInterestProvider:
    provider_id = "binance_open_interest"
    capabilities = frozenset(
        {
            ProviderCapability.RECENT_HISTORY,
            ProviderCapability.CURRENT_SNAPSHOT,
            ProviderCapability.RESEARCH_FEATURES,
        }
    )

    def __init__(self, request_json: Callable[[str, dict[str, object] | None], Any]) -> None:
        self._request_json = request_json

    def fetch_snapshot(self, symbol: str) -> Any:
        return self._request_json(OI_CURRENT_ENDPOINT, {"symbol": symbol.upper()})

    def fetch_recent_history(
        self,
        *,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        ingested_at: datetime | None = None,
        limit: int = 500,
        provider_history_days: int = 30,
    ) -> list[dict[str, object]]:
        if period not in _PERIOD_MINUTES:
            raise ValueError(f"Unsupported Binance open-interest period: {period}")
        if not 1 <= limit <= 500:
            raise ValueError("Binance open-interest history limit must be from 1 through 500")
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Open-interest range timestamps must be timezone-aware")
        start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
        if start_utc >= end_utc:
            raise ValueError("Open-interest history range must be half-open with start < end")
        if start_utc < captured - timedelta(days=provider_history_days):
            raise ValueError("Requested open-interest history exceeds official recent retention")
        if end_utc > captured:
            raise ValueError("Open-interest history end cannot be after the collection time")
        start_ms, end_ms = _epoch_ms(start_utc), _epoch_ms(end_utc)
        step_ms = _PERIOD_MINUTES[period] * 60_000
        cursor = start_ms
        rows: list[dict[str, object]] = []
        while cursor < end_ms:
            payload = self._request_json(
                OI_HISTORY_ENDPOINT,
                {
                    "symbol": symbol.upper(),
                    "period": period,
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": limit,
                },
            )
            if not isinstance(payload, list):
                raise ValueError("Binance open-interest history response must be a JSON array")
            page = [item for item in payload if isinstance(item, dict)]
            if len(page) != len(payload):
                raise ValueError("Binance open-interest history rows must be JSON objects")
            rows.extend(page)
            if not page:
                break
            try:
                timestamps = [int(item["timestamp"]) for item in page]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Binance open-interest history row has no valid timestamp"
                ) from exc
            next_cursor = max(timestamps) + step_ms
            if next_cursor <= cursor:
                raise ValueError("Binance open-interest pagination did not advance")
            cursor = next_cursor
            if len(page) < limit:
                break
        return rows

    def normalize_snapshot(
        self,
        payload: Any,
        *,
        symbol: str,
        ingested_at: datetime | None = None,
    ) -> pa.Table:
        if not isinstance(payload, dict):
            raise ValueError("Binance current open-interest response must be a JSON object")
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        expected_symbol = symbol.upper()
        try:
            actual_symbol = str(payload["symbol"]).upper()
            if actual_symbol != expected_symbol:
                raise ValueError(
                    f"Binance open-interest symbol mismatch: {actual_symbol} != {expected_symbol}"
                )
            timestamp_ms = int(payload["time"])
            value = Decimal(str(payload["openInterest"]))
            if value < 0:
                raise ValueError("Current open interest cannot be negative")
        except (KeyError, InvalidOperation, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Invalid Binance current open-interest response: {payload!r}"
            ) from exc
        checksum = payload_sha256(payload)
        row = {
            "symbol": expected_symbol,
            "open_interest": value,
            "provider_timestamp": _utc_ms(timestamp_ms),
            "availability_time": captured,
            "ingested_at": captured,
            "provider": self.provider_id,
            "source_endpoint": OI_CURRENT_ENDPOINT,
            "raw_identifier": f"{expected_symbol}:{timestamp_ms}",
            "raw_payload_checksum": checksum,
            "normalized_schema_version": OI_SNAPSHOT_SCHEMA_VERSION,
            "source_version": OI_SOURCE_VERSION,
            "observation_class": ObservationClass.FORWARD_OBSERVATION_DATA.value,
            "training_eligibility": TrainingEligibility.FORWARD_ONLY.value,
            "training_eligible": False,
            "eligibility_reason": OI_ELIGIBILITY_REASON,
            "availability_policy": "OBSERVED_AT_INGESTION",
        }
        return pa.Table.from_pylist([row], schema=open_interest_snapshot_schema())

    def normalize_history(
        self,
        payload: Any,
        *,
        symbol: str,
        period: str,
        requested_start: datetime,
        requested_end: datetime,
        ingested_at: datetime | None = None,
    ) -> tuple[pa.Table, int]:
        if period not in _PERIOD_MINUTES:
            raise ValueError(f"Unsupported Binance open-interest period: {period}")
        if not isinstance(payload, list):
            raise ValueError("Binance open-interest history response must be a JSON array")
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        start_ms, end_ms = _epoch_ms(requested_start), _epoch_ms(requested_end)
        expected_symbol = symbol.upper()
        checksum = payload_sha256(payload)
        by_timestamp: dict[int, dict[str, object]] = {}
        duplicate_count = 0
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError("Binance open-interest history rows must be JSON objects")
            try:
                actual_symbol = str(raw["symbol"]).upper()
                if actual_symbol != expected_symbol:
                    raise ValueError(
                        "Binance open-interest symbol mismatch: "
                        f"{actual_symbol} != {expected_symbol}"
                    )
                timestamp_ms = int(raw["timestamp"])
                if timestamp_ms < start_ms or timestamp_ms >= end_ms:
                    continue
                sum_open_interest = Decimal(str(raw["sumOpenInterest"]))
                sum_open_interest_value = Decimal(str(raw["sumOpenInterestValue"]))
                if sum_open_interest < 0 or sum_open_interest_value < 0:
                    raise ValueError("Historical open-interest values cannot be negative")
            except (KeyError, InvalidOperation, TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Invalid Binance open-interest history row: {raw!r}") from exc
            row: dict[str, object] = {
                "symbol": expected_symbol,
                "period": period,
                "sum_open_interest": sum_open_interest,
                "sum_open_interest_value": sum_open_interest_value,
                "provider_timestamp": _utc_ms(timestamp_ms),
                "availability_time": captured,
                "ingested_at": captured,
                "provider": self.provider_id,
                "source_endpoint": OI_HISTORY_ENDPOINT,
                "raw_identifier": f"{expected_symbol}:{period}:{timestamp_ms}",
                "raw_payload_checksum": checksum,
                "normalized_schema_version": OI_HISTORY_SCHEMA_VERSION,
                "source_version": OI_SOURCE_VERSION,
                "observation_class": ObservationClass.FORWARD_OBSERVATION_DATA.value,
                "training_eligibility": TrainingEligibility.FORWARD_ONLY.value,
                "training_eligible": False,
                "eligibility_reason": OI_ELIGIBILITY_REASON,
                "availability_policy": "OBSERVED_AT_INGESTION",
            }
            previous = by_timestamp.get(timestamp_ms)
            if previous is not None:
                if (
                    previous["sum_open_interest"] != sum_open_interest
                    or previous["sum_open_interest_value"] != sum_open_interest_value
                ):
                    raise ValueError(f"Conflicting Binance open-interest row at {timestamp_ms}")
                duplicate_count += 1
                continue
            by_timestamp[timestamp_ms] = row
        rows = [by_timestamp[key] for key in sorted(by_timestamp)]
        return pa.Table.from_pylist(rows, schema=open_interest_history_schema()), duplicate_count

    def collect_snapshot(
        self,
        *,
        symbol: str,
        store: ContextStore,
        config_hash: str,
        ingested_at: datetime | None = None,
    ):
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        payload = self.fetch_snapshot(symbol)
        table = self.normalize_snapshot(payload, symbol=symbol, ingested_at=captured)
        return store.persist(
            raw_payload=payload,
            table=table,
            ingested_at=captured,
            source_endpoint=OI_CURRENT_ENDPOINT,
            source_version=OI_SOURCE_VERSION,
            schema_version=OI_SNAPSHOT_SCHEMA_VERSION,
            observation_class=ObservationClass.FORWARD_OBSERVATION_DATA,
            eligibility=TrainingEligibility.FORWARD_ONLY,
            eligibility_reason=OI_ELIGIBILITY_REASON,
            config_hash=config_hash,
            symbol=symbol.upper(),
            coverage_limitation="point-in-time snapshot collected only when invoked",
            availability_policy="OBSERVED_AT_INGESTION",
        )

    def collect_recent_history(
        self,
        *,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        store: ContextStore,
        config_hash: str,
        ingested_at: datetime | None = None,
        limit: int = 500,
        provider_history_days: int = 30,
    ):
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        payload = self.fetch_recent_history(
            symbol=symbol,
            period=period,
            start=start,
            end=end,
            ingested_at=captured,
            limit=limit,
            provider_history_days=provider_history_days,
        )
        table, duplicate_count = self.normalize_history(
            payload,
            symbol=symbol,
            period=period,
            requested_start=start,
            requested_end=end,
            ingested_at=captured,
        )
        return store.persist(
            raw_payload=payload,
            table=table,
            ingested_at=captured,
            source_endpoint=OI_HISTORY_ENDPOINT,
            source_version=OI_SOURCE_VERSION,
            schema_version=OI_HISTORY_SCHEMA_VERSION,
            observation_class=ObservationClass.FORWARD_OBSERVATION_DATA,
            eligibility=TrainingEligibility.FORWARD_ONLY,
            eligibility_reason=OI_ELIGIBILITY_REASON,
            config_hash=config_hash,
            requested_start=start,
            requested_end=end,
            symbol=symbol.upper(),
            period=period,
            input_duplicate_count=duplicate_count,
            coverage_limitation=OI_COVERAGE_LIMITATION,
            availability_policy="OBSERVED_AT_INGESTION",
        )


def _latest_before(rows: list[dict[str, object]], cutoff: datetime) -> dict[str, object] | None:
    return next((row for row in reversed(rows) if row["provider_timestamp"] <= cutoff), None)


def build_open_interest_features(
    feature_times: Sequence[datetime],
    observations: pa.Table,
    *,
    allow_forward_only: bool = False,
    max_staleness_minutes: float = 10.0,
) -> pa.Table:
    """Build optional OI features without activating them in the Phase 7 baseline."""

    rows = observations.to_pylist()
    eligible_rows = [
        row
        for row in rows
        if isinstance(row.get("availability_time"), datetime)
        and (
            bool(row.get("training_eligible"))
            or (
                allow_forward_only
                and row.get("training_eligibility") == TrainingEligibility.FORWARD_ONLY.value
            )
        )
    ]
    eligible_rows.sort(key=lambda row: (row["availability_time"], row["provider_timestamp"]))
    result: list[dict[str, object]] = []
    for raw_time in feature_times:
        if raw_time.tzinfo is None or raw_time.utcoffset() is None:
            raise ValueError("Open-interest feature times must be timezone-aware")
        feature_time = raw_time.astimezone(UTC)
        available = [row for row in eligible_rows if row["availability_time"] <= feature_time]
        latest = max(
            available,
            key=lambda row: (row["provider_timestamp"], row["availability_time"]),
            default=None,
        )
        output: dict[str, object] = {
            "feature_time": feature_time,
            "has_open_interest": 0,
            "open_interest_age_minutes": None,
            "oi_change_5m": None,
            "oi_change_15m": None,
            "oi_change_1h": None,
            "oi_pct_change_5m": None,
            "oi_pct_change_1h": None,
            "oi_value_change": None,
            "oi_change_zscore": None,
        }
        if latest is None:
            result.append(output)
            continue
        age = (feature_time - latest["availability_time"]).total_seconds() / 60
        output["open_interest_age_minutes"] = age
        if age < 0 or age > max_staleness_minutes:
            result.append(output)
            continue
        oi_column = "sum_open_interest" if "sum_open_interest" in latest else "open_interest"
        current = float(latest[oi_column])
        provider_time = latest["provider_timestamp"]
        causal = [
            row
            for row in available
            if row["provider_timestamp"] <= provider_time
            and row["availability_time"] <= feature_time
        ]
        causal.sort(key=lambda row: row["provider_timestamp"])
        output["has_open_interest"] = 1
        for minutes, suffix in ((5, "5m"), (15, "15m"), (60, "1h")):
            lag = _latest_before(causal, provider_time - timedelta(minutes=minutes))
            if lag is None:
                continue
            previous = float(lag[oi_column])
            change = current - previous
            output[f"oi_change_{suffix}"] = change
            if suffix in {"5m", "1h"} and previous != 0:
                output[f"oi_pct_change_{suffix}"] = change / previous
        if "sum_open_interest_value" in latest:
            value_lag = _latest_before(causal, provider_time - timedelta(minutes=5))
            if value_lag is not None:
                output["oi_value_change"] = float(latest["sum_open_interest_value"]) - float(
                    value_lag["sum_open_interest_value"]
                )
        changes: list[float] = []
        for prior, current_row in zip(causal, causal[1:], strict=False):
            changes.append(float(current_row[oi_column]) - float(prior[oi_column]))
        if len(changes) >= 2 and output["oi_change_5m"] is not None:
            recent = changes[-288:]
            std = statistics.pstdev(recent)
            if std > 0:
                output["oi_change_zscore"] = (
                    float(output["oi_change_5m"]) - statistics.fmean(recent)
                ) / std
        result.append(output)
    schema = pa.schema(
        [pa.field("feature_time", pa.timestamp("us", tz="UTC"), nullable=False)]
        + [pa.field("has_open_interest", pa.int8(), nullable=False)]
        + [
            pa.field(name, pa.float64(), nullable=True)
            for name in (
                "open_interest_age_minutes",
                "oi_change_5m",
                "oi_change_15m",
                "oi_change_1h",
                "oi_pct_change_5m",
                "oi_pct_change_1h",
                "oi_value_change",
                "oi_change_zscore",
            )
        ],
        metadata={b"feature_version": OPEN_INTEREST_FEATURE_VERSION.encode()},
    )
    return pa.Table.from_pylist(result, schema=schema)
