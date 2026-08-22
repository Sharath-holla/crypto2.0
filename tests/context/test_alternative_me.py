from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pytest

from crypto_ai.context.alternative_me import (
    FEAR_GREED_AVAILABILITY_POLICY,
    AlternativeMeFearGreedProvider,
    build_fear_greed_features,
    fear_greed_schema,
)
from crypto_ai.context.storage import ContextStore
from crypto_ai.data.storage import file_sha256


def _payload(*rows: dict[str, str]) -> dict[str, object]:
    return {"name": "Fear and Greed Index", "data": list(rows), "metadata": {"error": None}}


def _row(value: str, classification: str, timestamp: int) -> dict[str, str]:
    return {
        "value": value,
        "value_classification": classification,
        "timestamp": str(timestamp),
    }


def _eligible_table(*, future_value: int | None = None) -> pa.Table:
    provider = AlternativeMeFearGreedProvider(lambda *_: None)
    payload_rows = [
        _row("20", "Extreme Fear", 1_767_225_600),
        _row("30", "Fear", 1_767_312_000),
    ]
    if future_value is not None:
        payload_rows.append(_row(str(future_value), "Greed", 1_767_398_400))
    table, _ = provider.normalize_history(
        _payload(*payload_rows), ingested_at=datetime(2026, 1, 4, tzinfo=UTC)
    )
    rows = table.to_pylist()
    for index, row in enumerate(rows):
        row["availability_time"] = datetime(2026, 1, 2 + index, tzinfo=UTC)
        row["training_eligibility"] = "HISTORICAL_RESEARCH_CANDIDATE"
        row["training_eligible"] = True
        row["eligibility_reason"] = "fixture knowledge time"
        row["availability_policy"] = "FIXTURE_VERIFIED_PUBLICATION_TIME"
    return pa.Table.from_pylist(rows, schema=fear_greed_schema())


def test_fetch_history_uses_documented_limit_zero() -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []

    def request(path: str, params: dict[str, object] | None):
        calls.append((path, params))
        return _payload()

    result = AlternativeMeFearGreedProvider(request).fetch_history()
    assert result == _payload()
    assert calls == [("/fng/", {"limit": 0, "format": "json"})]


def test_normalization_parses_values_classification_and_sorts() -> None:
    provider = AlternativeMeFearGreedProvider(lambda *_: None)
    table, duplicates = provider.normalize_history(
        _payload(
            _row("47", "Neutral", 1_551_070_800),
            _row("40", "Fear", 1_551_157_200),
        ),
        ingested_at=datetime(2026, 8, 22, tzinfo=UTC),
    )
    rows = table.to_pylist()
    assert duplicates == 0
    assert [row["value"] for row in rows] == [47, 40]
    assert [row["value_classification"] for row in rows] == ["Neutral", "Fear"]
    assert all(row["scope"] == "GLOBAL" for row in rows)
    assert all(row["observation_class"] == "HISTORICAL_RESEARCH_DATA" for row in rows)
    assert all(row["availability_time"] is None for row in rows)
    assert all(row["training_eligible"] is False for row in rows)
    assert all(row["availability_policy"] == FEAR_GREED_AVAILABILITY_POLICY for row in rows)


def test_identical_duplicate_is_counted_and_removed() -> None:
    provider = AlternativeMeFearGreedProvider(lambda *_: None)
    duplicate = _row("50", "Neutral", 1_700_000_000)
    table, count = provider.normalize_history(_payload(duplicate, dict(duplicate)))
    assert table.num_rows == 1
    assert count == 1


def test_conflicting_duplicate_is_rejected() -> None:
    provider = AlternativeMeFearGreedProvider(lambda *_: None)
    with pytest.raises(ValueError, match="Conflicting Fear & Greed"):
        provider.normalize_history(
            _payload(
                _row("20", "Fear", 1_700_000_000),
                _row("80", "Greed", 1_700_000_000),
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"metadata": {"error": "failed"}, "data": []},
        {"metadata": {"error": None}},
        _payload({"value": "bad", "value_classification": "Fear", "timestamp": "1"}),
        _payload(_row("101", "Greed", 1_700_000_000)),
    ],
)
def test_malformed_responses_are_rejected(payload: object) -> None:
    with pytest.raises(ValueError):
        AlternativeMeFearGreedProvider(lambda *_: None).normalize_history(payload)


def test_manifest_checksum_and_idempotent_reuse(tmp_path: Path) -> None:
    payload = _payload(_row("40", "Fear", 1_551_157_200))
    provider = AlternativeMeFearGreedProvider(lambda *_: payload)
    store = ContextStore(
        tmp_path,
        provider_id="alternative_me",
        dataset_name="history",
        key_columns=("scope", "provider_timestamp"),
    )
    first = provider.collect_history(
        store=store,
        config_hash="config-a",
        ingested_at=datetime(2026, 8, 22, tzinfo=UTC),
    )
    second = provider.collect_history(
        store=store,
        config_hash="config-a",
        ingested_at=datetime(2026, 8, 22, 1, tzinfo=UTC),
    )
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert first.reused is False
    assert second.reused is True
    assert second.dataset_version == first.dataset_version
    assert manifest["raw_payload_sha256"] == file_sha256(first.raw_path)
    assert manifest["dataset_sha256"] == file_sha256(first.dataset_path)
    assert manifest["training_eligible"] is False
    assert manifest["observation_class"] == "HISTORICAL_RESEARCH_DATA"


def test_asof_join_excludes_future_observation() -> None:
    observations = _eligible_table()
    before = datetime(2026, 1, 2, 23, 59, tzinfo=UTC)
    after = datetime(2026, 1, 3, tzinfo=UTC)
    rows = build_fear_greed_features([before, after], observations).to_pylist()
    assert rows[0]["fear_greed_value"] == 20.0
    assert rows[1]["fear_greed_value"] == 30.0


def test_future_perturbation_does_not_change_earlier_features() -> None:
    feature_time = datetime(2026, 1, 3, tzinfo=UTC)
    baseline = build_fear_greed_features([feature_time], _eligible_table()).to_pylist()
    perturbed = build_fear_greed_features(
        [feature_time], _eligible_table(future_value=99)
    ).to_pylist()
    assert baseline == perturbed


def test_missing_is_not_neutral_and_staleness_is_explicit() -> None:
    observations = _eligible_table()
    missing = build_fear_greed_features(
        [datetime(2026, 1, 1, tzinfo=UTC)], observations
    ).to_pylist()[0]
    stale = build_fear_greed_features(
        [datetime(2026, 1, 10, tzinfo=UTC)],
        observations,
        max_staleness_hours=48,
    ).to_pylist()[0]
    assert missing["has_fear_greed"] == 0
    assert missing["fear_greed_value"] is None
    assert missing["neutral_flag"] == 0
    assert stale["has_fear_greed"] == 0
    assert stale["fear_greed_age_hours"] > 48


def test_causal_changes_and_windows_use_only_known_values() -> None:
    observations = _eligible_table()
    row = build_fear_greed_features(
        [datetime(2026, 1, 3, 1, tzinfo=UTC)], observations
    ).to_pylist()[0]
    assert row["fear_greed_change_1d"] == 10.0
    assert row["fear_greed_mean_7d"] == 25.0
    assert row["fear_flag"] == 1
    assert row["neutral_flag"] == 0
