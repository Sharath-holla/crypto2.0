"""Explicit HTTP/host-memory fixtures; these tests never contact a real Ollama daemon."""

import json

import httpx
import pytest
from company_os import local_ai, spending
from company_os.config import settings
from company_os.local_ai import diagnostics
from company_os.models import ModelConfig, Provider
from company_os.native import Decoder, NativeAdapter
from company_os.providers import HTTPAdapter, ProviderError, ollama_metadata


def provider(endpoint="http://127.0.0.1:11434"):
    return Provider(kind="ollama", base_url=endpoint, credential_env="", enabled=True)


def answer(**changes):
    return {
        "model": "qwen3:0.6b",
        "response": '{"answer":"actual fixture content"}',
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 20,
        "eval_count": 10,
        "eval_duration": 1_000_000_000,
        "load_duration": 100_000_000,
        **changes,
    }


async def test_structured_ollama_identity_timing_and_no_thinking(contract_inference):
    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == "qwen3:0.6b" and body["think"] is False
        assert not request.headers.get("Authorization") and body["keep_alive"] == 0
        return httpx.Response(200, json=answer())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        response = await HTTPAdapter(client).request(
            provider(), ModelConfig(identifier="qwen3:0.6b"), "policy", "brief", {}
        )
    assert response.data == {"answer": "actual fixture content"}
    assert response.metadata["identity_verified"] and response.metadata["completed"]
    assert response.metadata["tokens_per_second"] == 10
    assert response.metadata["load_duration_ns"] == 100_000_000


@pytest.mark.parametrize("wire_model", ["different:latest", "qwen3:cloud"])
async def test_wrong_model_is_not_a_success(contract_inference, wire_model):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=answer(model=wire_model)))
    ) as client:
        with pytest.raises(ProviderError, match="different execution model"):
            await HTTPAdapter(client).request(
                provider(), ModelConfig(identifier="qwen3:0.6b"), "policy", "brief", {}
            )


@pytest.mark.parametrize(
    "changes", [{"response": ""}, {"response": "not JSON"}, {"done": False}, {"done_reason": "length"}]
)
async def test_incomplete_or_malformed_output_keeps_usage(contract_inference, changes):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=answer(**changes)))
    ) as client:
        response = await HTTPAdapter(client).request(
            provider(), ModelConfig(identifier="qwen3:0.6b"), "policy", "brief", {}
        )
    assert response.data == {"_invalid_output": True} and response.output_tokens == 10


async def test_native_ollama_reports_identity_and_ignores_reasoning(contract_inference):
    def handle(request):
        body = json.loads(request.content)
        assert body["think"] is False and body["stream"] is True
        rows = [
            {
                "model": "qwen3:0.6b",
                "message": {"thinking": "Private reasoning fixture", "content": '{"answer":"saved"}'},
                "done": False,
            },
            {**answer(), "message": {"content": ""}},
        ]
        return httpx.Response(200, content="".join(json.dumps(row) + "\n" for row in rows))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        response = await NativeAdapter(client).request(
            provider(), ModelConfig(identifier="qwen3:0.6b"), "policy", "brief", {}
        )
    assert response.data == {"answer": "saved"} and response.metadata["identity_verified"]
    assert response.metadata["streamed"] and "Private reasoning" not in str(response)


def test_stream_model_change_rejected():
    decoder = Decoder("ollama")
    decoder.feed({"model": "qwen3:0.6b", "message": {"content": ""}, "done": False})
    with pytest.raises(ProviderError, match="identity changed"):
        decoder.feed({"model": "another", "message": {"content": ""}, "done": False})


@pytest.mark.parametrize("available", [None, 512])
async def test_low_or_unknown_memory_blocks_before_network(monkeypatch, available):
    monkeypatch.setattr(settings(), "ollama_min_available_memory_mb", 1536)
    monkeypatch.setattr(local_ai, "available_memory_mb", lambda: available)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Resource-blocked inference attempted network")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    with pytest.raises(spending.InferenceBlocked) as error:
        await spending.authorize(provider(), ModelConfig(identifier="qwen3:0.6b"))
    assert error.value.decision.state == "LOCAL_RESOURCES_BLOCKED"


async def test_diagnostics_are_get_only_and_not_inference(monkeypatch):
    monkeypatch.setattr(local_ai, "available_memory_mb", lambda: 4096)
    calls = []

    def handle(request):
        assert request.method == "GET" and request.url.host == "127.0.0.1"
        calls.append(request.url.path)
        data = (
            {"version": "fixture-version"}
            if request.url.path.endswith("version")
            else {"models": [{"name": "qwen3:0.6b", "digest": "a" * 64, "size": 523_000_000, "size_vram": 0}]}
        )
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        value = await diagnostics(provider(), client)
    assert value["reachable"] and value["version"] == "fixture-version"
    assert calls == ["/api/version", "/api/tags", "/api/ps"]
    assert not value["check_invokes_inference"] and value["loaded_models"][0]["size_vram"] == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.test",
        "http://example.test:11434",
        "http://127.0.0.1:11434/private",
        "http://user:secret@localhost:11434",
    ],
)
async def test_diagnostics_reject_nonlocal_or_credential_endpoints(endpoint):
    with pytest.raises(PermissionError):
        await diagnostics(provider(endpoint))


async def test_diagnostics_unavailable_and_empty_registry():
    def unavailable(request):
        raise httpx.ConnectError("controlled service unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        value = await diagnostics(provider(), client)
    assert not value["reachable"] and value["installed_models"] == []

    def empty(request):
        data = {"version": "fixture"} if request.url.path.endswith("version") else {"models": []}
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(empty)) as client:
        value = await diagnostics(provider(), client)
    assert value["reachable"] and not value["installed_models"]


def test_metadata_ignores_arbitrary_server_fields():
    metadata = ollama_metadata(
        {"model": {"secret": "must not persist"}, "thinking": "private", "eval_duration": True}
    )

    assert (
        metadata["reported_model"] is None
        and "thinking" not in metadata
        and "eval_duration_ns" not in metadata
    )


@pytest.mark.parametrize("marker", [1, "true", None, [], {}])
def test_completion_marker_must_be_boolean(marker):
    with pytest.raises(ProviderError, match="completion marker"):
        ollama_metadata({"done": marker})


@pytest.mark.parametrize(
    "kind,reference,expected",
    [
        ("ollama", "", 201),
        ("ollama", "OLLAMA_API_KEY", 422),
        ("openai", "", 422),
        ("openai", "JWT_SECRET", 422),
        ("openai", "OPENAI_API_KEY", 201),
    ],
)
def test_registration_preserves_credential_free_local_boundary(http, kind, reference, expected):
    response = http.post(
        "/providers",
        json={
            "name": "Registration boundary fixture",
            "kind": kind,
            "base_url": "http://127.0.0.1:11434" if kind == "ollama" else "https://api.openai.com/v1",
            "credential_env": reference,
        },
    )
    assert response.status_code == expected, response.text
    if expected == 201 and kind == "ollama":
        assert response.json()["credential_env"] == ""
        assert response.json()["credential_configured"] is False


def test_local_diagnostics_owner_scope_and_no_inference(http, company, monkeypatch):
    from company_os import models as m
    from company_os.db import uid
    from company_os.security import token_for
    from sqlalchemy import func, select

    response = http.post(
        "/providers",
        json={
            "name": "Local diagnostics fixture",
            "kind": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "credential_env": "",
        },
    )
    identity = response.json()["id"]
    calls = []

    async def controlled(p):
        calls.append(p.id)
        return {"reachable": True, "installed_models": [], "check_invokes_inference": False}

    monkeypatch.setattr("company_os.local_ai.diagnostics", controlled)
    result = http.get(f"/providers/{identity}/local-status")
    assert result.status_code == 200 and result.json()["check_invokes_inference"] is False
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(m.ModelRun)) == 0
        other = m.Provider(
            id=uid(),
            org_id="another-tenant",
            name="Other tenant",
            kind="ollama",
            base_url="http://127.0.0.1:11434",
            credential_env="",
        )
        # Use an existing organization row to preserve foreign keys in this fixture.
        org = m.Organization(id=other.org_id, name="Other tenant fixture")
        session.add(org)
        session.flush()
        session.add(other)
        session.commit()
        assert http.get(f"/providers/{other.id}/local-status").status_code == 404
        client_user = m.User(
            id=uid(),
            org_id=company["org"].id,
            email="local-client@test",
            client_id=company["client"].id,
            role="client",
        )
        session.add(client_user)
        session.flush()
        client_token = token_for(client_user, session)
        session.commit()
    assert (
        http.get(
            f"/providers/{identity}/local-status",
            headers={
                "Authorization": "Bearer " + client_token,
            },
        ).status_code
        == 403
    )
    assert calls == [identity]


async def test_gateway_persists_transport_receipt_after_sqlite_reconnect(
    http, company, contract_inference, monkeypatch
):
    from company_os import models as m
    from company_os.db import uid
    from company_os.workflows import tick
    from sqlalchemy import select
    from test_agent_operations import live_model

    with company["factory"]() as session:
        p, model = live_model(session, company, kind="ollama")
        p.base_url, p.credential_env = "http://127.0.0.1:11434", ""
        model.identifier = "qwen3:0.6b"
        session.commit()
        provider_id, model_id = p.id, model.id
    original = NativeAdapter.request
    calls = []

    async def controlled(self, *args, **kwargs):
        def handle(request):
            calls.append(json.loads(request.content)["model"])
            return httpx.Response(200, json=answer(message={"content": '{"value":"aiventra_probe_ok"}'}))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await original(NativeAdapter(client), *args, **kwargs)

    monkeypatch.setattr(NativeAdapter, "request", controlled)
    response = http.post(
        f"/providers/{provider_id}/inference-probe",
        json={
            "request_id": uid(),
            "model_id": model_id,
        },
    )
    assert response.status_code == 201, response.text
    assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    with company["factory"]() as session:
        receipt = session.scalar(
            select(m.BusinessRecord).where(m.BusinessRecord.kind == "invocation_receipt")
        )
        data = receipt.data
        assert data["verification"] == "FIXTURE_TESTED"  # Never certify this controlled transport as live.
        assert data["accepted"] and data["status"] == "succeeded"
        assert (
            data["requested_model_id"]
            == data["selected_model_id"]
            == data["attempted_model_id"]
            == data["successful_model_id"]
            == model_id
        )
        assert data["transport"]["reported_model"] == "qwen3:0.6b"
        assert data["transport"]["identity_verified"] and data["transport"]["completed"]
        assert data["transport"]["tokens_per_second"] == 10
        assert data["output_tokens"] == 10 and data["result_sha256"]
    assert calls == ["qwen3:0.6b"]
    assert http.get("/ai-readiness").json()["live_verified_models"] == 0


def test_local_discovery_metadata_is_idempotent_and_never_proves_capability(http, company, monkeypatch):
    from company_os.provider_catalog import discover

    response = http.post(
        "/providers",
        json={
            "name": "Installed Qwen catalog fixture",
            "kind": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "credential_env": "",
        },
    )
    identity = response.json()["id"]
    row = {
        "name": "qwen3:0.6b",
        "digest": "a" * 64,
        "size": 523_000_000,
        "details": {"parameter_size": "0.6B", "quantization_level": "Q4_K_M"},
    }

    async def controlled(p):
        def handle(request):
            assert request.method == "GET" and request.url.path == "/api/tags"
            assert not request.headers.get("authorization")
            return httpx.Response(200, json={"models": [row]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await discover(p, client)

    monkeypatch.setattr("company_os.routes.provider_operations.discover", controlled)
    model_id = None
    for _ in range(2):
        assert http.post(f"/providers/{identity}/discover").status_code == 200
        values = [
            value for value in http.get("/model-catalog").json()["models"] if value["provider_id"] == identity
        ]
        assert len(values) == 1
        value = values[0]
        assert model_id in {None, value["id"]}
        model_id = value["id"]
        assert value["local_metadata"] == {
            "digest": "a" * 64,
            "size_bytes": 523_000_000,
            "parameter_size": "0.6B",
            "quantization_level": "Q4_K_M",
        }
        assert value["capabilities"] == [] and value["configured_quality"] == 0
        assert value["live_inference_at"] is None
    company["factory"].kw["bind"].dispose()
    row.clear()
    row["name"] = "qwen3:0.6b"
    assert http.post(f"/providers/{identity}/discover").status_code == 200
    value = next(value for value in http.get("/model-catalog").json()["models"] if value["id"] == model_id)
    assert value["local_metadata"] == {}  # Unknown current metadata must not reuse a stale digest.
