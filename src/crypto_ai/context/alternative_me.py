from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import pyarrow as pa

from crypto_ai.context.models import ObservationClass, ProviderCapability, TrainingEligibility
from crypto_ai.context.storage import ContextStore, payload_sha256

FEAR_GREED_FEATURE_VERSION = "fear_greed_context_v1"
FEAR_GREED_SCHEMA_VERSION = "alternative_me_fear_greed_v1"
FEAR_GREED_SOURCE_VERSION = "alternative_me_fng_api_verified_2026-08-22"
FEAR_GREED_ENDPOINT = "/fng/"
FEAR_GREED_AVAILABILITY_POLICY = "HISTORICAL_PUBLICATION_TIME_UNVERIFIED"
FEAR_GREED_ELIGIBILITY_REASON = (
    "Alternative.me documents a historical value timestamp but not a reliable historical "
    "publication/knowledge timestamp"
)


def fear_greed_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("scope", pa.string(), nullable=False),
            pa.field("value", pa.int16(), nullable=False),
            pa.field("value_classification", pa.string(), nullable=False),
            pa.field("provider_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("availability_time", pa.timestamp("us", tz="UTC"), nullable=True),
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
        ],
        metadata={
            b"schema_version": FEAR_GREED_SCHEMA_VERSION.encode(),
            b"feature_version": FEAR_GREED_FEATURE_VERSION.encode(),
            b"scope": b"GLOBAL_MARKET_CONTEXT",
        },
    )


class AlternativeMeFearGreedProvider:
    provider_id = "alternative_me"
    capabilities = frozenset(
        {ProviderCapability.HISTORICAL_FETCH, ProviderCapability.RESEARCH_FEATURES}
    )

    def __init__(self, request_json: Callable[[str, dict[str, object] | None], Any]) -> None:
        self._request_json = request_json

    def fetch_history(self) -> Any:
        return self._request_json(FEAR_GREED_ENDPOINT, {"limit": 0, "format": "json"})

    def normalize_history(
        self,
        payload: Any,
        *,
        ingested_at: datetime | None = None,
    ) -> tuple[pa.Table, int]:
        if not isinstance(payload, dict):
            raise ValueError("Alternative.me Fear & Greed response must be a JSON object")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("error") not in {None, ""}:
            raise ValueError("Alternative.me Fear & Greed response reports an error")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("Alternative.me Fear & Greed response is missing a data array")
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        checksum = payload_sha256(payload)
        by_timestamp: dict[datetime, dict[str, object]] = {}
        duplicate_count = 0
        for raw in data:
            if not isinstance(raw, dict):
                raise ValueError("Alternative.me Fear & Greed rows must be JSON objects")
            try:
                value_decimal = Decimal(str(raw["value"]))
                value = int(value_decimal)
                if value_decimal != value or not 0 <= value <= 100:
                    raise ValueError("Fear & Greed value must be an integer from 0 through 100")
                classification = str(raw["value_classification"]).strip()
                if not classification:
                    raise ValueError("Fear & Greed classification cannot be empty")
                timestamp_value = int(raw["timestamp"])
                timestamp = datetime.fromtimestamp(timestamp_value, tz=UTC)
            except (KeyError, InvalidOperation, TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Invalid Alternative.me Fear & Greed row: {raw!r}") from exc
            row: dict[str, object] = {
                "scope": "GLOBAL",
                "value": value,
                "value_classification": classification,
                "provider_timestamp": timestamp,
                "availability_time": None,
                "ingested_at": captured,
                "provider": self.provider_id,
                "source_endpoint": FEAR_GREED_ENDPOINT,
                "raw_identifier": str(timestamp_value),
                "raw_payload_checksum": checksum,
                "normalized_schema_version": FEAR_GREED_SCHEMA_VERSION,
                "source_version": FEAR_GREED_SOURCE_VERSION,
                "observation_class": ObservationClass.HISTORICAL_RESEARCH_DATA.value,
                "training_eligibility": TrainingEligibility.NOT_TRAINING_ELIGIBLE.value,
                "training_eligible": False,
                "eligibility_reason": FEAR_GREED_ELIGIBILITY_REASON,
                "availability_policy": FEAR_GREED_AVAILABILITY_POLICY,
            }
            previous = by_timestamp.get(timestamp)
            if previous is not None:
                if previous["value"] != value or previous["value_classification"] != classification:
                    raise ValueError(
                        f"Conflicting Fear & Greed observation at {timestamp.isoformat()}"
                    )
                duplicate_count += 1
                continue
            by_timestamp[timestamp] = row
        rows = [by_timestamp[key] for key in sorted(by_timestamp)]
        return pa.Table.from_pylist(rows, schema=fear_greed_schema()), duplicate_count

    def collect_history(
        self,
        *,
        store: ContextStore,
        config_hash: str,
        ingested_at: datetime | None = None,
    ):
        captured = (ingested_at or datetime.now(UTC)).astimezone(UTC)
        payload = self.fetch_history()
        table, duplicate_count = self.normalize_history(payload, ingested_at=captured)
        return store.persist(
            raw_payload=payload,
            table=table,
            ingested_at=captured,
            source_endpoint=FEAR_GREED_ENDPOINT,
            source_version=FEAR_GREED_SOURCE_VERSION,
            schema_version=FEAR_GREED_SCHEMA_VERSION,
            observation_class=ObservationClass.HISTORICAL_RESEARCH_DATA,
            eligibility=TrainingEligibility.NOT_TRAINING_ELIGIBLE,
            eligibility_reason=FEAR_GREED_ELIGIBILITY_REASON,
            config_hash=config_hash,
            input_duplicate_count=duplicate_count,
            availability_policy=FEAR_GREED_AVAILABILITY_POLICY,
            coverage_limitation=(
                "provider returns all available values for limit=0; knowledge time unverified"
            ),
        )


def _last_at_or_before(rows: list[dict[str, object]], cutoff: datetime) -> dict[str, object] | None:
    return next(
        (row for row in reversed(rows) if row["provider_timestamp"] <= cutoff),
        None,
    )


def build_fear_greed_features(
    feature_times: Sequence[datetime],
    observations: pa.Table,
    *,
    max_staleness_hours: float = 48.0,
) -> pa.Table:
    """Build disabled-by-default global features using strict availability-time as-of joins."""

    rows = observations.to_pylist()
    known_rows = [
        row
        for row in rows
        if isinstance(row.get("availability_time"), datetime) and bool(row.get("training_eligible"))
    ]
    known_rows.sort(key=lambda row: (row["availability_time"], row["provider_timestamp"]))
    output: list[dict[str, object]] = []
    for raw_time in feature_times:
        if raw_time.tzinfo is None or raw_time.utcoffset() is None:
            raise ValueError("Fear & Greed feature times must be timezone-aware")
        feature_time = raw_time.astimezone(UTC)
        available = [row for row in known_rows if row["availability_time"] <= feature_time]
        latest = max(
            available,
            key=lambda row: (row["provider_timestamp"], row["availability_time"]),
            default=None,
        )
        base: dict[str, object] = {
            "feature_time": feature_time,
            "has_fear_greed": 0,
            "fear_greed_value": None,
            "fear_greed_change_1d": None,
            "fear_greed_change_3d": None,
            "fear_greed_change_7d": None,
            "fear_greed_mean_7d": None,
            "fear_greed_mean_30d": None,
            "fear_greed_std_30d": None,
            "fear_greed_zscore_30d": None,
            "fear_greed_age_hours": None,
            "extreme_fear_flag": 0,
            "fear_flag": 0,
            "neutral_flag": 0,
            "greed_flag": 0,
            "extreme_greed_flag": 0,
        }
        if latest is None:
            output.append(base)
            continue
        age_hours = (feature_time - latest["availability_time"]).total_seconds() / 3_600
        base["fear_greed_age_hours"] = age_hours
        if age_hours < 0 or age_hours > max_staleness_hours:
            output.append(base)
            continue
        provider_time = latest["provider_timestamp"]
        causally_known = [
            row
            for row in available
            if row["provider_timestamp"] <= provider_time
            and row["availability_time"] <= feature_time
        ]
        causally_known.sort(key=lambda row: row["provider_timestamp"])
        value = float(latest["value"])
        base["has_fear_greed"] = 1
        base["fear_greed_value"] = value
        for days in (1, 3, 7):
            lag = _last_at_or_before(causally_known, provider_time - timedelta(days=days))
            if lag is not None:
                base[f"fear_greed_change_{days}d"] = value - float(lag["value"])
        for days in (7, 30):
            start = provider_time - timedelta(days=days)
            window = [
                float(row["value"])
                for row in causally_known
                if start < row["provider_timestamp"] <= provider_time
            ]
            if window:
                base[f"fear_greed_mean_{days}d"] = statistics.fmean(window)
            if days == 30 and len(window) >= 2:
                std = statistics.pstdev(window)
                base["fear_greed_std_30d"] = std
                if std > 0:
                    base["fear_greed_zscore_30d"] = (
                        value - float(base["fear_greed_mean_30d"])
                    ) / std
        classification = " ".join(str(latest["value_classification"]).lower().split())
        flag_column = {
            "extreme fear": "extreme_fear_flag",
            "fear": "fear_flag",
            "neutral": "neutral_flag",
            "greed": "greed_flag",
            "extreme greed": "extreme_greed_flag",
        }.get(classification)
        if flag_column is not None:
            base[flag_column] = 1
        output.append(base)
    schema = pa.schema(
        [pa.field("feature_time", pa.timestamp("us", tz="UTC"), nullable=False)]
        + [pa.field("has_fear_greed", pa.int8(), nullable=False)]
        + [
            pa.field(name, pa.float64(), nullable=True)
            for name in (
                "fear_greed_value",
                "fear_greed_change_1d",
                "fear_greed_change_3d",
                "fear_greed_change_7d",
                "fear_greed_mean_7d",
                "fear_greed_mean_30d",
                "fear_greed_std_30d",
                "fear_greed_zscore_30d",
                "fear_greed_age_hours",
            )
        ]
        + [
            pa.field(name, pa.int8(), nullable=False)
            for name in (
                "extreme_fear_flag",
                "fear_flag",
                "neutral_flag",
                "greed_flag",
                "extreme_greed_flag",
            )
        ],
        metadata={b"feature_version": FEAR_GREED_FEATURE_VERSION.encode()},
    )
    table = pa.Table.from_pylist(output, schema=schema)
    for column in table.column_names:
        if column.startswith("fear_greed_") and pa.types.is_floating(
            table.schema.field(column).type
        ):
            values = table[column].to_pylist()
            if any(value is not None and not math.isfinite(value) for value in values):
                raise ValueError(f"Non-finite Fear & Greed feature: {column}")
    return table
