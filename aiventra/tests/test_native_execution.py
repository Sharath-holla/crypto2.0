import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from company_os import models as m
from company_os.benchmarks import CASES, Answer, current_profile, grade
from company_os.db import uid
from company_os.gateway import eligible_models, execute
from company_os.native import NativeAdapter, request_spec
from company_os.organization import agent_for
from company_os.providers import HTTPAdapter, ProviderError, Response
from company_os.tools import ToolCall, guard, invoke
from company_os.workflows import tick
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("contract_inference")

KINDS = ["openai", "anthropic", "gemini", "xai", "ollama", "compatible"]


@pytest.mark.parametrize("kind", KINDS)
async def test_native_nonstream_tool_results_are_not_fake_streams(monkeypatch, kind):
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    call = {"name": "sum_numbers", "arguments": '{"numbers":[7,13]}'}
    if kind == "openai":
        data = {
            "status": "completed",
            "output": [{"type": "function_call", "call_id": "native-call", **call}],
            "usage": {"input_tokens": 9, "output_tokens": 7},
        }
    elif kind == "anthropic":
        data = {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "native-call",
                    "name": call["name"],
                    "input": json.loads(call["arguments"]),
                }
            ],
            "usage": {"input_tokens": 9, "output_tokens": 7},
        }
    elif kind in {"gemini", "ollama"}:
        data = events(kind, tool=True)[0]
    else:
        data = {
            "choices": [
                {
                    "message": {"tool_calls": [{"id": "native-call", "function": call}]},
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 7},
        }
    provider = m.Provider(
        kind=kind,
        base_url="http://localhost:11434" if kind == "ollama" else "https://api.openai.com/v1",
        credential_env="NATIVE_CONTRACT_KEY",
    )
    captured, traces = [], []

    async def handler(request):
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=data)

    async def emit(*args):
        traces.append(args)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await NativeAdapter(client).request(
            provider,
            m.ModelConfig(identifier="contract"),
            "system",
            "prompt",
            {},
            tools=[{"name": "sum_numbers", "description": "Calculator", "parameters": {"type": "object"}}],
            stream=False,
            emit=emit,
        )
    assert result.data["calls"][0]["arguments"] == {"numbers": [7, 13]}
    assert (result.input_tokens, result.output_tokens) == (9, 7)
    assert traces[-1][-1] is False
    if kind == "gemini":
        assert ":generateContent" in captured[0][0] and "alt=sse" not in captured[0][0]
    else:
        assert captured[0][1]["stream"] is False


async def test_native_known_incomplete_usage_is_preserved(monkeypatch):
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    rows = [{"type": "response.incomplete", "response": {"usage": {"input_tokens": 9, "output_tokens": 7}}}]
    provider = m.Provider(
        kind="openai", base_url="https://api.openai.com/v1", credential_env="NATIVE_CONTRACT_KEY"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=stream_content("openai", rows)))
    ) as client:
        result = await NativeAdapter(client).request(
            provider, m.ModelConfig(identifier="contract"), "system", "prompt", {}
        )
    assert result.data == {"_invalid_output": True} and (result.input_tokens, result.output_tokens) == (9, 7)


def events(kind, text=None, tool=False):
    text = text or json.dumps({"answer": "hello"})
    args = '{"numbers":[7,13]}'
    if kind == "openai":
        rows = (
            [
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "function_call",
                        "call_id": "call-test",
                        "name": "sum_numbers",
                        "arguments": "",
                    },
                },
                {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": args},
            ]
            if tool
            else [{"type": "response.output_text.delta", "delta": text}]
        )
        return [
            *rows,
            {"type": "response.completed", "response": {"usage": {"input_tokens": 9, "output_tokens": 7}}},
        ]
    if kind == "anthropic":
        rows = [{"type": "message_start", "message": {"usage": {"input_tokens": 9}}}]
        rows += (
            [
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call-test",
                        "name": "sum_numbers",
                        "input": {},
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": args},
                },
            ]
            if tool
            else [{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}]
        )
        return [*rows, {"type": "message_delta", "usage": {"output_tokens": 7}}, {"type": "message_stop"}]
    if kind == "gemini":
        part = (
            {
                "functionCall": {"name": "sum_numbers", "args": json.loads(args)},
                "thoughtSignature": "opaque-contract-signature",
            }
            if tool
            else {"text": text}
        )
        return [
            {
                "candidates": [{"content": {"parts": [part]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 7},
            }
        ]
    if kind == "ollama":
        message = (
            {"tool_calls": [{"function": {"name": "sum_numbers", "arguments": json.loads(args)}}]}
            if tool
            else {"content": text}
        )
        return [{"message": message, "done": True, "prompt_eval_count": 9, "eval_count": 7}]
    delta = (
        {
            "tool_calls": [
                {"index": 0, "id": "call-test", "function": {"name": "sum_numbers", "arguments": args}}
            ]
        }
        if tool
        else {"content": text}
    )
    return [
        {"choices": [{"delta": delta, "finish_reason": "tool_calls" if tool else "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 7}},
    ]


def stream_content(kind, rows):
    return "".join(
        (json.dumps(row) + "\n") if kind == "ollama" else ("data: " + json.dumps(row) + "\n\n")
        for row in rows
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("tool", [False, True])
async def test_six_native_protocols_usage_tools_and_result_roundtrip(monkeypatch, kind, tool):
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    bases = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
        "xai": "https://api.x.ai/v1",
        "ollama": "http://localhost:11434",
        "compatible": "https://api.openai.com/v1",
    }
    provider = m.Provider(kind=kind, base_url=bases[kind], credential_env="NATIVE_CONTRACT_KEY")
    model = m.ModelConfig(identifier="contract-model")
    captured, previews = [], []

    async def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=stream_content(kind, events(kind, tool=tool)))

    async def emit(text, count, complete, tools, *unused):
        previews.append((text, count, complete, tools))

    defs = (
        [
            {
                "name": "sum_numbers",
                "description": "Calculator",
                "parameters": {
                    "type": "object",
                    "properties": {"numbers": {"type": "array", "items": {"type": "integer"}}},
                    "required": ["numbers"],
                    "additionalProperties": False,
                },
            }
        ]
        if tool
        else None
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await NativeAdapter(client).request(
            provider, model, "system", "prompt", {"type": "object"}, tools=defs, emit=emit
        )
    assert (result.input_tokens, result.output_tokens) == (9, 7)
    assert captured[0].get("stream", kind == "gemini") is True and previews[-1][2]
    if tool:
        call = result.data["calls"][0]
        assert call["name"] == "sum_numbers" and call["arguments"] == {"numbers": [7, 13]}
        _, _, body = request_spec(
            provider,
            model,
            "system",
            "prompt",
            {},
            defs,
            [{**result.data, "results": {call["id"]: {"sum": 20}}}],
            20,
            "contract",
        )
        assert "20" in json.dumps(body) and "sum_numbers" in json.dumps(body)
        if kind == "gemini":
            assert "opaque-contract-signature" in json.dumps(body)
    else:
        assert result.data == {"answer": "hello"}


@pytest.mark.parametrize("fault", ["truncated", "missing_usage", "bad_json", "oversized", "http500"])
async def test_native_faults_hold_uncertain_billing(monkeypatch, fault):
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    provider = m.Provider(
        kind="openai", base_url="https://api.openai.com/v1", credential_env="NATIVE_CONTRACT_KEY"
    )
    rows = events("openai")
    if fault == "truncated":
        rows.pop()
    if fault == "missing_usage":
        rows[-1]["response"]["usage"] = {}
    content = stream_content("openai", rows)
    if fault == "bad_json":
        content = "data: INVALID\n\n"
    if fault == "oversized":
        content = "data: " + "x" * 262145
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500 if fault == "http500" else 200, content=content)
        )
    ) as client:
        with pytest.raises(ProviderError) as error:
            await NativeAdapter(client).request(
                provider, m.ModelConfig(identifier="contract"), "system", "prompt", {}
            )
        assert error.value.uncertain


async def test_native_split_secret_and_malformed_output_preserve_usage(monkeypatch):
    secret = "native-secret-contract-value"
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", secret)
    text = json.dumps({"answer": ("ordinary word " * 100) + secret})
    rows = [
        {"type": "response.output_text.delta", "delta": text[: len(text) - 12]},
        {"type": "response.output_text.delta", "delta": text[len(text) - 12 :]},
        events("openai")[-1],
    ]
    previews = []

    async def emit(text, *unused):
        previews.append(text)

    provider = m.Provider(
        kind="openai", base_url="https://api.openai.com/v1", credential_env="NATIVE_CONTRACT_KEY"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=stream_content("openai", rows)))
    ) as client:
        result = await NativeAdapter(client).request(
            provider, m.ModelConfig(identifier="contract"), "system", "prompt", {}, emit=emit
        )
    assert secret not in json.dumps([previews, result.data])
    assert "native-secret-" not in previews[0] and "[REDACTED]" in result.data["answer"]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=stream_content("openai", events("openai", "INVALID")))
        )
    ) as client:
        result = await NativeAdapter(client).request(
            provider, m.ModelConfig(identifier="contract"), "system", "prompt", {}
        )
    assert result.data == {"_invalid_output": True} and result.output_tokens == 7


def model(session, company):
    provider = m.Provider(
        id=uid(),
        org_id=company["org"].id,
        kind="openai",
        name="Native controlled contract",
        base_url="https://api.openai.com/v1",
        credential_env="NATIVE_CONTRACT_KEY",
    )
    session.add(provider)
    session.flush()
    entry = m.ModelConfig(
        id=uid(),
        org_id=provider.org_id,
        provider_id=provider.id,
        identifier="contract-only",
        capabilities=["structured", "tools", "streaming", "reasoning"],
        quality=95,
        sensitivity="confidential",
        input_price_micro_per_million=1000000,
        output_price_micro_per_million=1000000,
        price_source="https://example.test/contract",
    )
    session.add(entry)
    session.commit()
    return provider, entry


async def project(http, company, requirement):
    for _ in range(7):
        await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    result = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": proposal["version"],
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert result.status_code == 200
    for _ in range(40):
        if not await tick(company["factory"]):
            break
    return result.json()


async def test_tool_job_waits_without_credentials_and_deduplicates(http, company, requirement):
    approved = await project(http, company, requirement)
    with company["factory"]() as session:
        agent = agent_for(session, company["org"].id, "CTO")
    data = {
        "request_id": str(uuid4()),
        "project_id": approved["id"],
        "agent_id": agent.id,
        "objective": "Save a scoped architecture decision",
        "budget_micro": 100000,
    }
    response = http.post("/agent-tool-jobs", json=data)
    assert response.status_code == 201
    assert http.post("/agent-tool-jobs", json=data).json()["work"]["id"] == data["request_id"]
    await tick(company["factory"])
    state = http.get("/state").json()
    workflow = next(w for w in state["workflows"] if w["id"] == response.json()["workflow"]["id"])
    assert workflow["status"] == "waiting_for_free_provider"
    assert not [r for r in state["runs"] if r["workflow_id"] == workflow["id"]]
    assert not state["tool_invocations"]


@pytest.mark.parametrize("cancel_child", [False, True])
async def test_native_tool_handoff_creates_real_peer_artifact_and_rejects_scope(
    http, company, requirement, monkeypatch, cancel_child
):
    approved = await project(http, company, requirement)
    project_id = approved["id"]
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    with company["factory"]() as session:
        provider, entry = model(session, company)
        author = agent_for(session, company["org"].id, "CTO")
        peer = agent_for(session, company["org"].id, "Business Analyst")
        author_id, peer_id, model_id = author.id, peer.id, entry.id

    async def handler(request):
        body = json.loads(request.content)
        if body.get("tools") and not any(i.get("type") == "function_call_output" for i in body["input"]):
            rows = [
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "function_call",
                        "name": "handoff_document",
                        "call_id": "handoff-contract",
                        "arguments": "",
                    },
                },
                {
                    "type": "response.function_call_arguments.delta",
                    "output_index": 0,
                    "delta": json.dumps(
                        {
                            "agent_id": peer_id,
                            "objective": "Document acceptance evidence for the approved project",
                        }
                    ),
                },
                events("openai")[-1],
            ]
        elif body.get("tools"):
            rows = events("openai", "Handoff is queued; peer completion must be checked.")
        else:
            rows = events(
                "openai",
                json.dumps(
                    {
                        "title": "Controlled peer artifact",
                        "content": "Actual stored document produced by the controlled native adapter.",
                        "acceptance_checks": ["Scoped document persisted"],
                    }
                ),
            )
        return httpx.Response(200, content=stream_content("openai", rows))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(
            "company_os.native.NativeAdapter.__init__",
            lambda self, unused=None: setattr(self, "client", client),
        )
        response = http.post(
            "/agent-tool-jobs",
            json={
                "request_id": str(uuid4()),
                "project_id": project_id,
                "agent_id": author_id,
                "peer_ids": [peer_id],
                "objective": "Hand off an acceptance document to the selected peer",
                "model_override": model_id,
            },
        )
        assert response.status_code == 201
        if cancel_child:
            await tick(company["factory"])
            cancelled = http.post(f"/agent-work/{response.json()['work']['id']}/cancel")
            assert cancelled.status_code == 200
            for _ in range(3):
                await tick(company["factory"])
            snapshot = http.get("/state").json()
            child = next(
                t for t in snapshot["tasks"] if t["payload"].get("job_id") == response.json()["work"]["id"]
            )
            assert child["status"] == "cancelled" and not child["evidence"]
            assert (
                len([r for r in snapshot["runs"] if r["workflow_id"] == response.json()["workflow"]["id"]])
                == 1
            )
            return
        for _ in range(12):
            if not await tick(company["factory"]):
                break
    state = http.get("/state").json()
    work_id = response.json()["work"]["id"]
    handoff = next(t for t in state["tasks"] if t["payload"].get("job_id") == work_id)
    assert handoff["status"] == "completed" and handoff["assigned_agent_id"] == peer_id
    artifact = next(a for a in state["artifacts"] if a["id"] == handoff["evidence"]["artifact_id"])
    assert artifact["sha256"] == handoff["evidence"]["sha256"]
    assert all(t["usage_known"] for t in state["run_traces"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        workflow.status, workflow.lease_until = "running", 9999999999
        session.commit()
        run = session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
        call = ToolCall(id="foreign-contract", name="read_artifact", arguments={"artifact_id": str(uuid4())})
        result = invoke(
            session,
            workflow,
            session.get(m.Agent, author_id),
            session.get(m.Project, project_id),
            "deny",
            run.id,
            call,
            {"read_artifact"},
        )
        assert "error" in result
        bad = ToolCall(id="bad-args", name="sum_numbers", arguments={"numbers": ["7", 13]})
        assert "error" in invoke(
            session, workflow, session.get(m.Agent, author_id), None, "deny", run.id, bad, {"sum_numbers"}
        )
        workflow.status = "cancelled"
        session.commit()
        with pytest.raises(PermissionError):
            guard(session, workflow, session.get(m.Agent, author_id))


@pytest.mark.parametrize("supports_tools", [False, True])
async def test_benchmark_persists_profiles_and_invalidates_config(http, company, monkeypatch, supports_tools):
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    with company["factory"]() as session:
        provider, entry = model(session, company)
        entry.capabilities = ["structured"] + (["tools"] if supports_tools else [])
        session.commit()
        model_id = entry.id
    answers = {
        "simple": "42",
        "business": "actor permission audit idempotency acceptance",
        "architecture": "idempotency retry dead letter transactional outbox",
        "coding": "def add(a, b):\n    return a + b",
        "repair": "def first(xs):\n    return xs[0] if xs else None",
        "testing": "zero negative large",
        "review": "injection parameterized validation",
    }

    async def request(self, provider, model, system, prompt, schema, max_output=2048):
        task = json.loads(prompt)["task"]
        case = next(name for name, text in CASES if text == task)
        return Response({"answer": answers[case]}, 10, 20)

    monkeypatch.setattr(HTTPAdapter, "request", request)

    async def native_request(
        self,
        provider,
        model,
        system,
        prompt,
        schema,
        max_output=2048,
        tools=None,
        history=None,
        emit=None,
        stream=True,
        check=None,
    ):
        if not supports_tools:
            raise ProviderError("Provider HTTP 400")
        if history:
            return Response({"answer": "20", "calls": []}, 10, 20)
        return Response(
            {
                "answer": "",
                "calls": [
                    {
                        "id": "benchmark-call",
                        "name": "sum_numbers",
                        "arguments": {"numbers": [7, 13]},
                        "signature": None,
                    }
                ],
            },
            10,
            20,
        )

    monkeypatch.setattr(NativeAdapter, "request", native_request)
    response = http.post("/model-benchmarks", json={"request_id": str(uuid4()), "model_id": model_id})
    assert response.status_code == 201
    for _ in range(8):
        await tick(company["factory"])
    state = http.get("/state").json()
    assert len(state["benchmark_results"]) == 8
    assert {row["status"] for row in state["benchmark_results"]} == (
        {"passed"} if supports_tools else {"passed", "provider_rejected"}
    )
    profile = state["benchmark_profiles"][0]
    assert profile["metrics"]["quality"] == (100 if supports_tools else 88)
    assert profile["metrics"]["cost_micro"] == (270 if supports_tools else 210)
    assert profile["metrics"]["reliability"] == (100 if supports_tools else 88)
    assert len(state["tool_invocations"]) == (1 if supports_tools else 0)
    recommendations = http.get("/model-recommendations").json()
    assert all(
        recommendations[policy]["model_id"] == model_id for policy in ["economy", "balanced", "quality"]
    )
    assert recommendations["manual"]["model_id"] is None
    with company["factory"]() as session:
        entry = session.get(m.ModelConfig, model_id)
        provider = session.get(m.Provider, entry.provider_id)
        assert current_profile(session, entry, provider)
        selected = eligible_models(
            session, entry.org_id, "live", {"structured"}, 90, "internal", 100, "quality"
        )
        assert any(candidate.id == model_id for candidate, _ in selected) is supports_tools
        entry.identifier = "changed-model"
        session.commit()
        assert current_profile(session, entry, provider) is None
        assert any(
            candidate.id == model_id
            for candidate, _ in eligible_models(
                session, entry.org_id, "live", {"structured"}, 90, "internal", 100, "quality"
            )
        )
        agent = agent_for(session, entry.org_id, "CEO")
        agent.routing_policy = "manual"
        workflow = m.Workflow(
            id=uid(),
            org_id=entry.org_id,
            kind="diagnostic",
            mode="live",
            status="running",
            lease_token=uid(),
            lease_until=9999999999,
        )
        session.add(workflow)
        session.commit()
        with pytest.raises(PermissionError):
            await execute(session, workflow, agent, "manual", Answer, {"task": CASES[0][1]}, quality=0)
        assert not session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
        session.add(
            m.ModelPolicy(org_id=entry.org_id, scope=f"agent:{agent.id}", preferred_model_id=entry.id)
        )
        session.commit()
        answer = await execute(session, workflow, agent, "manual", Answer, {"task": CASES[0][1]}, quality=0)
        assert answer.answer == "42"
        run = session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
        assert (
            run.model_id == model_id
            and "current_prices=" in run.routing_reason
            and "benchmark=" in run.routing_reason
        )
    assert grade("coding", "import os\nos.system('danger')") == 0


async def test_native_cancellation_closes_stream_holds_usage_and_executes_no_tools(
    http, company, requirement, monkeypatch
):
    approved = await project(http, company, requirement)
    monkeypatch.setenv("NATIVE_CONTRACT_KEY", "native-contract-secret")
    with company["factory"]() as session:
        provider, entry = model(session, company)
        author = agent_for(session, company["org"].id, "CTO")
        author_id, model_id = author.id, entry.id
    response = http.post(
        "/agent-tool-jobs",
        json={
            "request_id": str(uuid4()),
            "project_id": approved["id"],
            "agent_id": author_id,
            "objective": "Save a scoped architecture decision",
            "model_override": model_id,
        },
    )
    workflow_id = response.json()["workflow"]["id"]
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield stream_content(
                "openai", [{"type": "response.output_text.delta", "delta": "working " * 100}]
            ).encode()
            with company["factory"]() as session:
                workflow = session.get(m.Workflow, workflow_id)
                workflow.status, workflow.lease_token = "cancelled", uid()
                session.commit()
            await asyncio.sleep(0.25)
            yield stream_content(
                "openai", [{"type": "response.output_text.delta", "delta": "remaining"}]
            ).encode()

        async def aclose(self):
            closed.append(True)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Stream()))
    ) as client:
        monkeypatch.setattr(
            NativeAdapter, "__init__", lambda self, unused=None: setattr(self, "client", client)
        )
        await tick(company["factory"])
    state = http.get("/state").json()
    run = next(r for r in state["runs"] if r["workflow_id"] == workflow_id)
    assert run["status"] == "uncertain" and run["reserved_micro"] > 0 and run["cost_micro"] == 0
    assert not state["tool_invocations"] and closed
    trace = next(t for t in state["run_traces"] if t["run_id"] == run["id"])
    assert trace["state"] == "interrupted" and not trace["preview"] and not trace["usage_known"]
