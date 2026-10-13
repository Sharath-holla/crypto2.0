"""Bounded native SSE/NDJSON inference. Only public text and function calls are retained."""

import asyncio
import json
from urllib.parse import quote

import httpx

from .config import settings
from .credentials import secret_for
from .providers import (
    ProviderError,
    Response,
    ollama_metadata,
    scrub_secret,
    strict_schema,
    verify_ollama_identity,
)
from .security import clean, validate_endpoint


def wire_history(kind, history):
    messages = []
    for turn in history:
        calls = turn.get("calls", [])
        if kind == "openai":
            for call in calls:
                messages.extend(
                    [
                        {
                            "type": "function_call",
                            "call_id": call["id"],
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"]),
                        },
                        {
                            "type": "function_call_output",
                            "call_id": call["id"],
                            "output": json.dumps(turn["results"][call["id"]]),
                        },
                    ]
                )
        elif kind == "anthropic":
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                        for c in calls
                    ],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": c["id"],
                            "content": json.dumps(turn["results"][c["id"]]),
                        }
                        for c in calls
                    ],
                }
            )
        elif kind == "gemini":
            messages.append(
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {"name": c["name"], "args": c["arguments"]},
                            **({"thoughtSignature": c["signature"]} if c.get("signature") else {}),
                        }
                        for c in calls
                    ],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": c["name"], "response": turn["results"][c["id"]]}}
                        for c in calls
                    ],
                }
            )
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.get("answer", ""),
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": c["arguments"]
                                if kind == "ollama"
                                else json.dumps(c["arguments"]),
                            },
                        }
                        for c in calls
                    ],
                }
            )
            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "tool_name": c["name"],
                    "content": json.dumps(turn["results"][c["id"]]),
                }
                for c in calls
            )
    return messages


def request_spec(provider, model, system, prompt, schema, tools, history, max_output, secret):
    kind = provider.kind
    functions = [{"type": "function", "function": t} for t in tools]
    previous = wire_history(kind, history)
    if kind == "openai":
        body = {
            "model": model.identifier,
            "instructions": system,
            "input": [{"role": "user", "content": prompt}, *previous],
            "store": False,
            "stream": True,
            "max_output_tokens": max_output,
        }
        if tools:
            body["tools"] = [{"type": "function", **t, "strict": True} for t in tools]
            body["parallel_tool_calls"] = False
        else:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agent_result",
                    "strict": True,
                    "schema": strict_schema(schema),
                }
            }
        return "/responses", {"Authorization": f"Bearer {secret}"}, body
    if kind == "anthropic":
        body = {
            "model": model.identifier,
            "system": system,
            "messages": [{"role": "user", "content": prompt}, *previous],
            "stream": True,
            "max_tokens": max_output,
        }
        if tools:
            body["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ]
        else:
            body["output_config"] = {"format": {"type": "json_schema", "schema": strict_schema(schema)}}
        return "/messages", {"x-api-key": secret, "anthropic-version": "2023-06-01"}, body
    if kind == "gemini":
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}, *previous],
            "generationConfig": {"maxOutputTokens": max_output},
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parametersJsonSchema": t["parameters"],
                        }
                        for t in tools
                    ]
                }
            ]
        else:
            body["generationConfig"].update(responseMimeType="application/json", responseJsonSchema=schema)
        return (
            f"/models/{quote(model.identifier, safe='')}:streamGenerateContent?alt=sse",
            {"x-goog-api-key": secret},
            body,
        )
    body = {
        "model": model.identifier,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}, *previous],
        "stream": True,
    }
    if tools:
        body["tools"] = functions
    elif kind == "ollama":
        body["format"] = schema
    else:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "agent_result", "strict": True, "schema": strict_schema(schema)},
        }
    if kind == "ollama":
        body["think"] = settings().ollama_thinking
        body["options"] = {
            "num_predict": max_output,
            "num_ctx": min(model.context_tokens or 4096, settings().ollama_context_tokens),
            "temperature": 0,
        }
        body["keep_alive"] = settings().ollama_keep_alive_seconds
        return "/api/chat", {}, body
    if kind not in {"compatible", "xai"}:
        raise ProviderError("Unsupported native provider")
    body.update(max_tokens=max_output, stream_options={"include_usage": True})
    return "/chat/completions", {"Authorization": f"Bearer {secret}"}, body


class Decoder:
    def __init__(self, kind):
        self.kind, self.text, self.calls = kind, "", {}
        self.input_tokens = self.output_tokens = None
        self.terminal = False
        self.invalid_output = False
        self.events = 0
        self.metadata = {}

    def call(self, index, name="", arguments="", call_id="", signature=None):
        record = self.calls.setdefault(
            str(index), {"id": call_id or f"call-{index}", "name": "", "arguments": "", "signature": None}
        )
        if call_id:
            record["id"] = call_id
        record["name"] += name
        if isinstance(arguments, dict):
            record["arguments"] = json.dumps(arguments)
        else:
            record["arguments"] += arguments
        if signature:
            record["signature"] = signature

    def feed(self, event):
        if not isinstance(event, dict) or event.get("error") or event.get("type") == "error":
            raise ProviderError("Native provider stream error; reconciliation required", uncertain=True)
        self.events += 1
        kind = self.kind
        if kind == "openai":
            event_type = event.get("type", "")
            if event_type == "response.output_text.delta":
                self.text += event.get("delta", "")
            elif event_type == "response.output_item.added" and event["item"]["type"] == "function_call":
                item = event["item"]
                self.call(event["output_index"], item["name"], item.get("arguments", ""), item["call_id"])
            elif event_type == "response.function_call_arguments.delta":
                self.call(event["output_index"], arguments=event["delta"])
            elif event_type == "response.completed":
                usage = event["response"]["usage"]
                self.input_tokens, self.output_tokens = usage["input_tokens"], usage["output_tokens"]
                self.terminal = True
            elif event_type == "response.incomplete" and event.get("response", {}).get("usage"):
                usage = event["response"]["usage"]
                self.input_tokens, self.output_tokens = usage["input_tokens"], usage["output_tokens"]
                self.terminal = self.invalid_output = True
            elif event_type in {"response.failed", "response.incomplete"}:
                raise ProviderError("Native response incomplete; reconciliation required", uncertain=True)
        elif kind == "anthropic":
            event_type = event.get("type", "")
            if event_type == "message_start":
                usage = event["message"]["usage"]
                self.input_tokens = (
                    usage["input_tokens"]
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
            elif event_type == "content_block_start" and event["content_block"]["type"] == "tool_use":
                block = event["content_block"]
                self.call(event["index"], block["name"], call_id=block["id"])
            elif event_type == "content_block_delta":
                delta = event["delta"]
                if delta["type"] == "text_delta":
                    self.text += delta["text"]
                elif delta["type"] == "input_json_delta":
                    self.call(event["index"], arguments=delta["partial_json"])
            elif event_type == "message_delta":
                self.output_tokens = event["usage"]["output_tokens"]
                if event.get("delta", {}).get("stop_reason") in {"max_tokens", "refusal", "pause_turn"}:
                    self.invalid_output = True
            elif event_type == "message_stop":
                self.terminal = True
        elif kind == "gemini":
            for candidate in event.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part and not part.get("thought"):
                        self.text += part["text"]
                    if "functionCall" in part:
                        call = part["functionCall"]
                        self.call(
                            len(self.calls),
                            call["name"],
                            call.get("args", {}),
                            signature=part.get("thoughtSignature"),
                        )
                if candidate.get("finishReason"):
                    self.terminal = True
                    self.invalid_output = candidate["finishReason"] != "STOP"
            usage = event.get("usageMetadata")
            if usage:
                self.input_tokens = usage.get("promptTokenCount")
                candidates = usage.get("candidatesTokenCount")
                thoughts = usage.get("thoughtsTokenCount", 0)
                self.output_tokens = (
                    candidates + thoughts if type(candidates) is int and type(thoughts) is int else None
                )
        elif kind == "ollama":
            previous_model = self.metadata.get("reported_model")
            if previous_model and event.get("model") and previous_model != event["model"]:
                raise ProviderError("Ollama model identity changed within stream", uncertain=True)
            self.metadata.update(
                {key: value for key, value in ollama_metadata(event).items() if value is not None}
            )
            message = event.get("message", {})
            self.text += message.get("content", "")
            for call in message.get("tool_calls", []):
                function = call["function"]
                index = function.get("index", len(self.calls))
                if type(index) is not int or index not in range(4):
                    raise ProviderError("Invalid local tool index", uncertain=True)
                previous = self.calls.get(str(index))
                if previous and previous["name"] != function["name"]:
                    raise ProviderError("Local tool identity changed within stream", uncertain=True)
                self.call(index, "" if previous else function["name"], function["arguments"])
            if event.get("done"):
                self.terminal = True
                self.invalid_output = event.get("done_reason", "stop") not in {"stop", "tool_calls"}
                self.input_tokens, self.output_tokens = (
                    event.get("prompt_eval_count"),
                    event.get("eval_count"),
                )
        else:
            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                self.text += delta.get("content") or ""
                for call in delta.get("tool_calls", []):
                    function = call.get("function", {})
                    self.call(
                        call["index"],
                        function.get("name", ""),
                        function.get("arguments", ""),
                        call.get("id", ""),
                    )
                if choice.get("finish_reason") in {"stop", "tool_calls"}:
                    self.terminal = True
                elif choice.get("finish_reason") in {"length", "content_filter"}:
                    self.terminal = self.invalid_output = True
            usage = event.get("usage")
            if usage:
                self.input_tokens, self.output_tokens = (
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                )
        if (
            len(self.text) > 131072
            or len(self.calls) > 4
            or any(len(c["arguments"]) > 16000 for c in self.calls.values())
        ):
            raise ProviderError(
                "Native output exceeded server bounds; reconciliation required", uncertain=True
            )

    def result(self, tool_mode):
        if (
            len(self.text) > 131072
            or len(self.calls) > 4
            or any(len(c["arguments"]) > 16000 for c in self.calls.values())
        ):
            raise ProviderError("Native output exceeded server bounds", uncertain=True)
        if not self.terminal or any(
            type(n) is not int or n < 0 for n in (self.input_tokens, self.output_tokens)
        ):
            raise ProviderError("Incomplete native stream or usage; reconciliation required", uncertain=True)
        if self.invalid_output:
            return Response({"_invalid_output": True}, self.input_tokens, self.output_tokens, self.metadata)
        if tool_mode:
            calls = []
            for call in self.calls.values():
                try:
                    arguments = json.loads(call["arguments"] or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError()
                except ValueError:
                    arguments = {"_invalid_arguments": True}
                calls.append({**call, "arguments": arguments})
            data = {"answer": self.text, "calls": calls}
        else:
            try:
                data = json.loads(self.text)
            except ValueError:
                data = {"_invalid_output": True}
        return Response(data, self.input_tokens, self.output_tokens, self.metadata)

    def full_response(self, data):
        if self.kind == "openai":
            for index, item in enumerate(data.get("output", [])):
                if item["type"] == "function_call":
                    self.call(index, item["name"], item["arguments"], item["call_id"])
                elif item["type"] == "message":
                    self.text += "".join(
                        p["text"] for p in item.get("content", []) if p["type"] == "output_text"
                    )
            usage = data["usage"]
            self.input_tokens, self.output_tokens = usage["input_tokens"], usage["output_tokens"]
            self.terminal = data.get("status") in {"completed", "incomplete"}
            self.invalid_output = data.get("status") == "incomplete"
        elif self.kind == "anthropic":
            for index, block in enumerate(data["content"]):
                if block["type"] == "text":
                    self.text += block["text"]
                elif block["type"] == "tool_use":
                    self.call(index, block["name"], block["input"], block["id"])
            usage = data["usage"]
            self.input_tokens = (
                usage["input_tokens"]
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            self.output_tokens = usage["output_tokens"]
            self.terminal = data["stop_reason"] in {"end_turn", "tool_use", "max_tokens", "stop_sequence"}
            self.invalid_output = data["stop_reason"] == "max_tokens"
        elif self.kind in {"gemini", "ollama"}:
            self.feed(data)
        else:
            choices = []
            for choice in data["choices"]:
                delta = choice["message"]
                for index, call in enumerate(delta.get("tool_calls", [])):
                    call["index"] = index
                choices.append({"delta": delta, "finish_reason": choice["finish_reason"]})
            self.feed({"choices": choices, "usage": data.get("usage")})
        self.events = 1


class NativeAdapter:
    def __init__(self, client=None):
        self.client = client

    async def request(
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
        from . import spending

        decision = await spending.authorize(provider, model)
        if (
            provider.kind == "ollama"
            and tools
            and decision.state == "LOCAL_AVAILABLE"
            and "tools" not in decision.capabilities
        ):
            raise ProviderError("Installed Ollama model does not advertise tool calling; no inference sent")
        base = validate_endpoint(
            provider.base_url, settings().provider_allowed_hosts, local_allowed=provider.kind == "ollama"
        )
        secret = "" if provider.kind == "ollama" else secret_for(provider)
        if provider.kind != "ollama" and not secret:
            raise ProviderError("Provider credentials are not configured")
        path, headers, body = request_spec(
            provider, model, system, prompt, schema, tools or [], history or [], max_output, secret
        )
        if not stream:
            if provider.kind == "gemini":
                path = path.replace(":streamGenerateContent?alt=sse", ":generateContent")
            else:
                body["stream"] = False
                body.pop("stream_options", None)
        client = self.client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                60,
                read=settings().ollama_read_timeout_seconds if provider.kind == "ollama" else 15,
            ),
            follow_redirects=False,
            trust_env=False,
        )
        decoder = Decoder(provider.kind)
        total, data_lines = 0, []

        async def consume():
            nonlocal total, data_lines
            async with client.stream("POST", base + path, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"Provider HTTP {response.status_code}", uncertain=response.status_code >= 500
                    )
                if not stream:
                    chunks = []
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > 1000000:
                            raise ProviderError("Native response exceeded transport bounds", uncertain=True)
                        chunks.append(chunk)
                    decoder.full_response(json.loads(b"".join(chunks)))
                if stream:
                    async for line in response.aiter_lines():
                        total += len(line.encode())
                        if total > 4000000 or len(line) > 262144:
                            raise ProviderError("Native stream exceeded transport bounds", uncertain=True)
                        if provider.kind == "ollama":
                            payload = line if line else None
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                            continue
                        elif line == "" and data_lines:
                            payload, data_lines = "\n".join(data_lines), []
                        else:
                            continue
                        if not payload or payload == "[DONE]":
                            continue
                        decoder.feed(json.loads(payload))
                        if emit:
                            # Hold the tail and unfinished word so split credentials never publish a prefix.
                            cutoff = decoder.text.rfind(
                                " ", 0, max(0, len(decoder.text) - max(512, len(secret) * 2))
                            )
                            preview = decoder.text[: max(0, cutoff)]
                            await emit(
                                clean(scrub_secret(preview, secret)),
                                decoder.events,
                                False,
                                len(decoder.calls),
                            )
                    if data_lines:
                        decoder.feed(json.loads("\n".join(data_lines)))

        pending = None
        try:
            if check:
                await check()
            pending = asyncio.create_task(consume())
            # Check authority even while connecting, loading a model or awaiting its first token.
            while not pending.done():
                await asyncio.wait({pending}, timeout=1)
                if check:
                    await check()
            await pending
            result = decoder.result(bool(tools))
            if provider.kind == "ollama":
                result.metadata = verify_ollama_identity(result.metadata, model.identifier)
                result.metadata["streamed"] = stream
            result.data = clean(scrub_secret(result.data, secret))
            if emit:
                await emit(
                    clean(scrub_secret(decoder.text, secret)),
                    decoder.events,
                    True,
                    len(decoder.calls),
                    stream,
                )
            return result
        except httpx.HTTPError:
            raise ProviderError("Native network failure; reconciliation required", uncertain=True) from None
        except (KeyError, TypeError, ValueError):
            raise ProviderError("Invalid native protocol; reconciliation required", uncertain=True) from None
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            if self.client is None:
                await client.aclose()
