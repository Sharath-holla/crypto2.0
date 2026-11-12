"""Explicit protocol fixtures; no model quality or real Ollama success is claimed."""

import asyncio
import json

import httpx
import pytest
from company_os import models as m
from company_os import spending
from company_os.config import settings
from company_os.native import Decoder, NativeAdapter, request_spec
from company_os.providers import ProviderError


class StalledStream(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False
        self.entered = asyncio.Event()

    async def __aiter__(self):
        self.entered.set()
        await asyncio.Event().wait()
        yield b""

    async def aclose(self):
        self.closed = True


@pytest.mark.usefixtures("contract_inference")
@pytest.mark.parametrize("stream", [True, False])
async def test_idle_cancellation_closes_transport_without_a_first_token(stream):
    body = StalledStream()

    async def check():
        if body.entered.is_set():
            raise ProviderError("Owner cancelled during model loading", uncertain=True)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body))
    ) as client:
        with pytest.raises(ProviderError, match="Owner cancelled"):
            await asyncio.wait_for(
                NativeAdapter(client).request(
                    m.Provider(kind="ollama", base_url="http://localhost:11434"),
                    m.ModelConfig(identifier="explicit-protocol-fixture"),
                    "system",
                    "prompt",
                    {},
                    stream=stream,
                    check=check,
                ),
                timeout=3,
            )
    assert body.closed


@pytest.mark.usefixtures("contract_inference")
async def test_total_timeout_cancels_and_closes_stalled_response():
    body = StalledStream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body))
    ) as client:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                NativeAdapter(client).request(
                    m.Provider(kind="ollama", base_url="http://localhost:11434"),
                    m.ModelConfig(identifier="explicit-protocol-fixture"),
                    "s",
                    "p",
                    {},
                ),
                timeout=0.1,
            )
    assert body.closed


@pytest.mark.usefixtures("contract_inference")
@pytest.mark.parametrize("reason,valid", [("length", False), ("stop", True), ("unknown", False)])
async def test_ollama_stop_reason_preserves_usage_and_rejects_incomplete_json(reason, valid):
    data = {
        "message": {"content": '{"answer":"fixture"}'},
        "done": True,
        "done_reason": reason,
        "prompt_eval_count": 12,
        "eval_count": 8,
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps(data) + "\n"))
    ) as client:
        result = await NativeAdapter(client).request(
            m.Provider(kind="ollama", base_url="http://localhost:11434"),
            m.ModelConfig(identifier="explicit-protocol-fixture"),
            "s",
            "p",
            {},
        )
    assert (result.input_tokens, result.output_tokens) == (12, 8)
    assert result.data == ({"answer": "fixture"} if valid else {"_invalid_output": True})


async def test_unsupported_local_tool_never_sends_inference(monkeypatch):
    async def verified(*unused):
        return spending.Decision(
            True, "LOCAL_AVAILABLE", "Fixture local manifest", capabilities=("completion",)
        )

    monkeypatch.setattr(spending, "authorize", verified)

    def reject(_):
        raise AssertionError("Unsupported tool request was sent")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
        with pytest.raises(ProviderError, match="does not advertise tool") as error:
            await NativeAdapter(client).request(
                m.Provider(kind="ollama"),
                m.ModelConfig(identifier="fixture"),
                "s",
                "p",
                {},
                tools=[{"name": "sum_numbers"}],
            )
    assert not error.value.uncertain


def test_local_request_has_bounded_context_output_and_residency(monkeypatch):
    monkeypatch.setattr(settings(), "ollama_context_tokens", 2048)
    _, _, body = request_spec(
        m.Provider(kind="ollama"),
        m.ModelConfig(identifier="fixture", context_tokens=32768),
        "s",
        "p",
        {"type": "object"},
        [],
        [],
        768,
        "",
    )
    assert body["options"] == {"num_predict": 768, "num_ctx": 2048, "temperature": 0}
    assert body["keep_alive"] == 0 and body["format"] == {"type": "object"}


def test_local_stream_tool_indices_do_not_duplicate_or_rename_calls():
    decoder = Decoder("ollama")
    event = {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "index": 0,
                        "name": "sum_numbers",
                        "arguments": {"numbers": [7, 13]},
                    }
                }
            ]
        }
    }
    decoder.feed(event)
    decoder.feed(event)
    decoder.feed({"done": True, "prompt_eval_count": 3, "eval_count": 4})
    result = decoder.result(True)
    assert len(result.data["calls"]) == 1
    assert result.data["calls"][0]["name"] == "sum_numbers"
    event["message"]["tool_calls"][0]["function"]["name"] = "other_tool"
    with pytest.raises(ProviderError, match="identity changed"):
        decoder.feed(event)
