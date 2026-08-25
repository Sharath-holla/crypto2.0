from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_ai.contracts.events import EventEnvelope
from crypto_ai.contracts.versioning import (
    ContractConflict,
    ContractDescriptor,
    ContractRegistry,
    SemanticVersion,
    VersionCompatibility,
    assess_version_change,
    canonical_sha256,
)


def _descriptor(version: str, schema: object) -> ContractDescriptor:
    return ContractDescriptor(
        name="prediction.envelope",
        version=SemanticVersion.parse(version),
        schema_sha256=canonical_sha256(schema),
        owner="model-platform",
    )


def test_semantic_version_requires_three_nonnegative_integer_components() -> None:
    assert str(SemanticVersion.parse("2.3.4")) == "2.3.4"
    for invalid in ("1", "1.2", "1.2.3.4", "1.-2.0", "v1.0.0"):
        with pytest.raises(ValueError):
            SemanticVersion.parse(invalid)


def test_contract_registry_is_idempotent_and_rejects_conflicting_schema() -> None:
    registry = ContractRegistry()
    descriptor = _descriptor("1.0.0", {"fields": ["symbol"]})
    assert registry.register(descriptor) == descriptor
    assert registry.register(descriptor) == descriptor
    with pytest.raises(ContractConflict):
        registry.register(_descriptor("1.0.0", {"fields": ["symbol", "price"]}))


def test_registry_resolves_latest_compatible_major_and_classifies_changes() -> None:
    registry = ContractRegistry()
    v1 = registry.register(_descriptor("1.0.0", {"required": ["symbol"]}))
    v1_1 = registry.register(_descriptor("1.1.0", {"required": ["symbol"], "optional": ["id"]}))
    v2 = registry.register(_descriptor("2.0.0", {"required": ["instrument"]}))
    assert registry.resolve("prediction.envelope") == v2
    assert registry.resolve("prediction.envelope", major=1) == v1_1
    assert assess_version_change(v1, v1) == VersionCompatibility.EXACT
    assert assess_version_change(v1, v1_1) == VersionCompatibility.BACKWARD_COMPATIBLE
    assert assess_version_change(v1_1, v2) == VersionCompatibility.BREAKING


def test_canonical_hash_is_order_independent_and_preserves_decimal_text() -> None:
    first = {"quantity": Decimal("1.2300"), "symbol": "BTCUSDT"}
    second = {"symbol": "BTCUSDT", "quantity": Decimal("1.2300")}
    assert canonical_sha256(first) == canonical_sha256(second)
    assert canonical_sha256(first) != canonical_sha256({**second, "quantity": Decimal("1.23")})


def _event(**changes: object) -> EventEnvelope:
    base = {
        "event_id": "event-1",
        "event_type": "prediction.emitted",
        "schema_version": SemanticVersion(1, 0, 0),
        "aggregate_type": "prediction",
        "aggregate_id": "prediction-1",
        "sequence": 0,
        "occurred_at": datetime(2026, 6, 1, tzinfo=UTC),
        "observed_at": datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
        "producer": "research-model",
        "correlation_id": "decision-1",
        "payload": {"symbol": "BTCUSDT", "value": Decimal("0.001")},
    }
    base.update(changes)
    return EventEnvelope(**base)  # type: ignore[arg-type]


def test_event_envelope_has_deterministic_content_identity_and_immutable_payload() -> None:
    first = _event()
    second = _event(payload={"value": Decimal("0.001"), "symbol": "BTCUSDT"})
    assert first.content_sha256 == second.content_sha256
    with pytest.raises(TypeError):
        first.payload["symbol"] = "ETHUSDT"  # type: ignore[index]


def test_event_envelope_separates_event_time_from_knowledge_time() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        _event(observed_at=datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _event(occurred_at=datetime(2026, 6, 1))
    later = _event(observed_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(seconds=5))
    assert later.observed_at > later.occurred_at


def test_event_sequence_cannot_be_negative() -> None:
    with pytest.raises(ValueError, match="sequence"):
        _event(sequence=-1)
