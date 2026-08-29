from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from crypto_ai.context.base import ContextProviderError, RetryingPublicJsonClient
from crypto_ai.context.commands import context_status, fear_greed_plan, open_interest_plan
from crypto_ai.context.config import CONTEXT_NETWORK_GUARD, ContextConfig, load_context_config
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.runner import _fixture_features, phase7_plan


def test_context_config_is_training_disabled_and_holdout_locked() -> None:
    config = load_context_config(Path("configs/context/default.toml"))
    assert config.alternative_me.training_enabled is False
    assert config.open_interest.training_enabled is False
    assert config.july_2026_used is False
    assert config.prospective_holdout_used is False
    assert config.research_cutoff.isoformat() == "2026-07-01T00:00:00+00:00"
    assert config.prospective_holdout_start.isoformat() == "2026-08-01T00:00:00+00:00"


def test_context_network_guard_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ContextConfig()
    monkeypatch.delenv(CONTEXT_NETWORK_GUARD, raising=False)
    with pytest.raises(RuntimeError, match="Context network access is locked"):
        config.assert_network_allowed()
    monkeypatch.setenv(CONTEXT_NETWORK_GUARD, "1")
    config.assert_network_allowed()


def test_status_and_plans_never_use_network(tmp_path: Path) -> None:
    config = ContextConfig(data_root=tmp_path)
    status = context_status(config)
    fear_plan = fear_greed_plan(config)
    oi_plan = open_interest_plan(config, symbol="BTCUSDT")
    assert status["network_used"] is False
    assert fear_plan["network_used"] is False
    assert oi_plan["network_used"] is False
    assert status["phase7_baseline_context"] == "MARKET_DATA_ONLY"
    assert status["providers"]["cryptopanic"]["status"] == "NOT_IMPLEMENTED"
    assert status["providers"]["arkham"]["status"] == "NOT_IMPLEMENTED"
    assert status["providers"]["reddit"]["status"] == "NOT_IMPLEMENTED"


def test_public_client_retries_retryable_http_status() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"ok": True})

    with RetryingPublicJsonClient(
        "https://provider.test",
        max_retries=1,
        retry_base_seconds=0.25,
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    ) as client:
        assert client.get_json("/data") == {"ok": True}
    assert attempts == 2
    assert sleeps == [0.25]


def test_public_client_surfaces_http_failure() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "missing"}))
    with (
        RetryingPublicJsonClient(
            "https://provider.test", max_retries=0, transport=transport
        ) as client,
        pytest.raises(ContextProviderError, match="Public context request failed"),
    ):
        client.get_json("/missing")


def test_public_client_surfaces_malformed_json() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-json"))
    with (
        RetryingPublicJsonClient(
            "https://provider.test", max_retries=0, transport=transport
        ) as client,
        pytest.raises(ContextProviderError, match="Public context request failed"),
    ):
        client.get_json("/bad")


def test_phase7_baseline_feature_matrix_has_no_context_columns() -> None:
    _, features, _ = _fixture_features()
    assert len(features.feature_columns) == 54
    assert not any(name.startswith("fear_greed_") for name in features.feature_columns)
    assert not any(name.startswith("oi_") for name in features.feature_columns)


def test_context_foundation_does_not_change_versioned_phase7_plan() -> None:
    config = load_phase7_config(Path("configs/phase7/research_v1.toml"))
    plan = phase7_plan(config)
    assert config.configuration_hash == "cc550337f1f4ee4654124bf6"
    assert config.targets.decision_latency_bars == 1
    assert plan["calendar_fold_count"] == 16
    assert plan["architectures"] == ["G0", "C0", "P0", "H0"]
    assert plan["core_universe_version"] == "core_universe_v1"
    assert plan["expansion_universe_version"] == "expansion_universe_v1"
    assert plan["research_cutoff_exclusive"] == "2026-07-01T00:00:00+00:00"
    assert plan["prospective_holdout_used"] is False


def test_context_config_rejects_phase7_boundary_changes() -> None:
    payload = ContextConfig().model_dump(mode="json")
    payload["research_cutoff"] = "2026-07-02T00:00:00Z"
    with pytest.raises(ValueError, match="preserve the Phase 7 cutoff"):
        ContextConfig.model_validate(payload)


def test_context_status_is_json_serializable(tmp_path: Path) -> None:
    encoded = json.dumps(context_status(ContextConfig(data_root=tmp_path)), sort_keys=True)
    assert "MARKET_DATA_ONLY" in encoded
