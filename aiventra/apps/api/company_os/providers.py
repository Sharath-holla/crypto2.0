import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from .config import settings
from .credentials import VaultUnavailable, secret_for
from .models import ModelConfig, Provider
from .security import validate_endpoint


@dataclass
class Response:
    data: dict
    input_tokens: int
    output_tokens: int
    metadata: dict = field(default_factory=dict)


def ollama_metadata(data):
    """Retain allowlisted transport facts, never reasoning or arbitrary response fields."""
    if "done" in data and type(data["done"]) is not bool:
        raise ProviderError("Invalid local completion marker; reconcile the request", uncertain=True)
    value = {
        "completed": data.get("done") is True,
        "reported_model": data.get("model")
        if isinstance(data.get("model"), str) and len(data["model"]) <= 200
        else None,
        "done_reason": data.get("done_reason")
        if isinstance(data.get("done_reason"), str) and len(data["done_reason"]) <= 40
        else None,
    }
    for name in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        if type(data.get(name)) is int and data[name] >= 0:
            value[name + "_ns"] = data[name]
    if (
        value.get("eval_duration_ns", 0) > 0
        and type(data.get("eval_count")) is int
        and data["eval_count"] >= 0
    ):
        value["tokens_per_second"] = round(data["eval_count"] * 1_000_000_000 / value["eval_duration_ns"], 3)
    return value


def verify_ollama_identity(metadata, expected):
    actual = metadata.get("reported_model")
    if actual is not None and actual != expected:
        raise ProviderError(
            "Ollama reported a different execution model; reconcile the request", uncertain=True
        )
    metadata["identity_verified"] = actual == expected
    return metadata


class ProviderError(Exception):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class ProviderUnavailable(ProviderError):
    def __init__(self, context: dict):
        super().__init__("Waiting for an eligible configured provider/model with server credentials")
        self.context = context


class LocalInferenceBusy(Exception):
    """Retry admission without creating a model run, spending or consuming an attempt."""


class FreeProviderUnavailable(ProviderUnavailable):
    def __init__(self, context: dict):
        super().__init__(context)
        self.args = (
            "WAITING_FOR_FREE_PROVIDER: no eligible zero-cost model; saved work requires owner resumption",
        )


def scrub_secret(value, secret: str):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [scrub_secret(item, secret) for item in value]
    if isinstance(value, dict):
        return {scrub_secret(key, secret): scrub_secret(item, secret) for key, item in value.items()}
    return value


def configured(provider: Provider) -> bool:
    try:
        return provider.kind in {"mock", "ollama"} or bool(secret_for(provider))
    except VaultUnavailable:
        return False


def provider_identity(provider: Provider) -> str:
    return (urlsplit(provider.base_url).hostname or provider.kind).lower()


def model_identity(model: ModelConfig, provider: Provider) -> tuple[str, str]:
    return provider_identity(provider), model.identifier


def strict_schema(schema: dict) -> dict:
    schema = json.loads(json.dumps(schema))

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)
    return schema


class HTTPAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    async def request(
        self,
        provider: Provider,
        model: ModelConfig,
        system: str,
        prompt: str,
        schema: dict,
        max_output: int = 2048,
    ) -> Response:
        from . import spending

        await spending.authorize(provider, model)
        base = validate_endpoint(
            provider.base_url, settings().provider_allowed_hosts, local_allowed=provider.kind == "ollama"
        )
        try:
            secret = "" if provider.kind == "ollama" else secret_for(provider)
        except VaultUnavailable:
            raise ProviderError("Provider credential vault unavailable") from None
        if provider.kind != "ollama" and not secret:
            raise ProviderError("Provider credentials are not configured")
        schema = strict_schema(schema)
        if provider.kind == "openai":
            path, headers = "/responses", {"Authorization": f"Bearer {secret}"}
            body = {
                "model": model.identifier,
                "instructions": system,
                "input": prompt,
                "max_output_tokens": max_output,
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "agent_result",
                        "strict": True,
                        "schema": schema,
                    }
                },
            }
        elif provider.kind == "anthropic":
            path = "/messages"
            headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
            body = {
                "model": model.identifier,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_output,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }
        elif provider.kind == "gemini":
            from urllib.parse import quote

            path, headers = (
                f"/models/{quote(model.identifier, safe='')}:generateContent",
                {"x-goog-api-key": secret},
            )
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "maxOutputTokens": max_output,
                },
            }
        elif provider.kind == "ollama":
            path, headers = "/api/generate", {}
            body = {
                "model": model.identifier,
                "system": system,
                "prompt": prompt,
                "format": schema,
                "stream": False,
                "think": settings().ollama_thinking,
                "options": {
                    "num_predict": max_output,
                    "num_ctx": min(model.context_tokens or 4096, settings().ollama_context_tokens),
                    "temperature": 0,
                },
                "keep_alive": settings().ollama_keep_alive_seconds,
            }
        elif provider.kind in {"compatible", "xai"}:
            path, headers = "/chat/completions", {"Authorization": f"Bearer {secret}"}
            body = {
                "model": model.identifier,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "max_tokens": max_output,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "agent_result", "strict": True, "schema": schema},
                },
            }
        else:
            raise ProviderError("Unsupported provider kind")
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                60, read=settings().ollama_read_timeout_seconds if provider.kind == "ollama" else 60
            ),
            follow_redirects=False,
            trust_env=False,
        )
        try:
            response = await client.post(base + path, headers=headers, json=body)
            if response.status_code >= 400:
                raise ProviderError(
                    f"Provider HTTP {response.status_code}", uncertain=response.status_code >= 500
                )
            data = response.json()
            if provider.kind == "openai":
                output = "".join(
                    part.get("text", "")
                    for item in data.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
                usage = data.get("usage", {})
                in_tokens, out_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            elif provider.kind == "anthropic":
                output = "".join(
                    part.get("text", "") for part in data.get("content", []) if part.get("type") == "text"
                )
                usage = data.get("usage", {})
                # Cached input is conservatively charged at ordinary input rate; label remains estimated.
                in_tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                )
                out_tokens = usage.get("output_tokens")
            elif provider.kind == "gemini":
                output = "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])
                usage = data.get("usageMetadata", {})
                in_tokens = usage.get("promptTokenCount")
                out_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
            elif provider.kind == "ollama":
                output, in_tokens, out_tokens = (
                    data["response"],
                    data.get("prompt_eval_count"),
                    data.get("eval_count"),
                )
            else:
                output = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                in_tokens, out_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if type(in_tokens) is not int or type(out_tokens) is not int or min(in_tokens, out_tokens) < 0:
                raise ProviderError(
                    "Provider omitted verifiable usage; reconciliation required", uncertain=True
                )
            try:
                if secret:
                    output = output.replace(secret, "[REDACTED]")
                result = (
                    {"_invalid_output": True}
                    if provider.kind == "ollama"
                    and (data.get("done_reason", "stop") != "stop" or data.get("done") is False)
                    else scrub_secret(json.loads(output), secret)
                )
            except (ValueError, TypeError):
                # Usage must survive malformed output so it can be charged before escalating.
                result = {"_invalid_output": True}
            metadata = (
                verify_ollama_identity(ollama_metadata(data), model.identifier)
                if provider.kind == "ollama"
                else {}
            )
            return Response(result, in_tokens, out_tokens, metadata)
        except httpx.HTTPError:
            raise ProviderError(
                "Provider network failure; billing outcome uncertain", uncertain=True
            ) from None
        except (KeyError, ValueError, TypeError):
            raise ProviderError(
                "Unexpected provider response; reconciliation required", uncertain=True
            ) from None
        finally:
            if own_client:
                await client.aclose()


def fixture(schema_name: str, context: dict) -> Response:
    """Explicit deterministic test fixtures. Never used in live mode."""
    analysis = context.get("analysis", {})
    if schema_name == "CEOAnswer":
        data = {
            "answer": "**Local fixture · no live AI call**\n\nThis response verifies conversation persistence and workflow execution. Configure a real model for an advisory answer.\n\n| Evidence | Status |\n| --- | --- |\n| Conversation | Persisted |\n| External actions | None |\n\n```text\nExplicit fixture; no generated code executed.\n```",
            "questions": [],
        }
    elif schema_name in {"Analysis", "LeadAnalysis", "RequirementCritique"}:
        text = context.get("text", "")
        migration = any(word in text.lower() for word in ("migrat", "cloud", "lightning"))
        data = {
            "project_type": "cloud migration" if migration else "software delivery",
            "objectives": [text[:300]],
            "requirements": [text],
            "questions": [
                "Which workloads, services and regions are currently in use?",
                "What are compute, GPU, storage and traffic requirements?",
                "What budget, downtime and compliance constraints apply?",
            ]
            if migration
            else [
                "Which users and workflows must the first release support?",
                "What budget, deadline and hosting restrictions apply?",
            ],
            "assumptions": [
                "No external changes are authorized",
                "Current provider prices have not been verified",
            ],
            "acceptance_criteria": [
                "Alternatives reviewed with evidence",
                "Owner approves exact scope before implementation",
            ],
        }
    elif schema_name in {"Recommendation", "TechnicalDesign"}:
        role = context.get("role", "Specialist")
        data = {
            "summary": f"Fixture contribution from {role}: assess requirements and validate missing constraints.",
            "evidence": ["User-submitted requirement; no live research performed by fixture"],
            "risks": ["Unknown workload inventory and pricing; cannot establish cheapest provider"],
            "alternatives": [
                "Optimize current platform",
                "Hybrid migration",
                "Full migration after feasibility validation",
            ],
            "actions": ["Obtain workload inventory", "Validate pricing and compatibility before changes"],
        }
    elif schema_name == "ProposalContent":
        names = ["Optimize current platform", "Hybrid migration", "Full migration"]
        data = {
            "executive_summary": "Fixture consulting proposal. Validate workload compatibility and costs before selecting an architecture.",
            "business_problem": context.get("text", ""),
            "confirmed_requirements": analysis.get("requirements", []),
            "assumptions": analysis.get("assumptions", []),
            "open_questions": analysis.get("questions", []),
            "current_architecture": "Inventory not supplied; architecture assessment remains incomplete.",
            "alternatives": [
                {
                    "name": name,
                    "architecture": description,
                    "advantages": [benefit],
                    "disadvantages": [risk],
                    "reliability": "Requires validation against service objectives",
                }
                for name, description, benefit, risk in [
                    (
                        names[0],
                        "Retain current services; right-size eligible workloads.",
                        "Least migration disruption",
                        "Savings depend on utilization",
                    ),
                    (
                        names[1],
                        "Move compatible compute while retaining stateful managed services.",
                        "Incremental migration and rollback",
                        "Cross-provider networking and egress",
                    ),
                    (
                        names[2],
                        "Migrate eligible services only after compatibility testing.",
                        "Potential consolidated operations",
                        "Managed-service replacements and downtime",
                    ),
                ]
            ],
            "recommendation": names[1],
            "risks_and_mitigations": [
                "Unverified pricing: obtain source-backed rates",
                "Downtime: validate rollback and data integrity",
            ],
            "milestones": [
                "Architecture and inventory",
                "Implementation and review",
                "Independent verification",
                "Release preparation",
            ],
            "proposed_team": [
                "CTO",
                "Cloud Architect",
                "Backend Developer",
                "QA Director",
                "FinOps Engineer",
            ],
            "deliverables": [
                "Architecture assessment",
                "Implementation plan",
                "Test plan",
                "Release checklist",
            ],
            "acceptance_criteria": analysis.get("acceptance_criteria", ["Owner review"]),
            "required_approvals": [
                "Proposal approval",
                "Repository modification approval",
                "Cloud and deployment approval",
            ],
        }
    elif schema_name == "ProjectPlanResult":
        data = {
            "title": "Explicit fixture project plan",
            "summary": "Deterministic workflow test only; no live planning was performed.",
            "tasks": [
                {
                    "key": "requirements",
                    "role": "Business Analyst",
                    "kind": "document",
                    "objective": "Document approved requirements and acceptance criteria",
                    "acceptance": ["Explicit fixture evidence"],
                    "depends_on": [],
                }
            ],
            "risks": ["Real model quality remains unverified"],
        }
    elif schema_name == "DocumentResult":
        data = {
            "title": context.get("objective", "Task result")[:150],
            "content": "Fixture artifact for local workflow testing.\n\nObjective: "
            + context.get("objective", "")
            + "\n\nSource context: "
            + json.dumps(context.get("project", {}))
            + "\n\nLive specialist analysis remains pending.",
            "acceptance_checks": ["Artifact saved with content hash", "Scope preserved; no external changes"],
        }
    elif schema_name == "DeliveryReviewResult":
        data = {
            "approved": True,
            "summary": "Explicit deterministic final-review fixture; no live verification, release or client acceptance.",
            "checked_criteria": list(range(len(context["acceptance"]))),
            "findings": [],
        }
    elif schema_name == "MeetingDecision":
        data = {
            "summary": "Explicit fixture meeting; live deliberation remains pending.",
            "decisions": ["Collect verified evidence before implementation"],
            "unresolved": ["No live specialist inference performed"],
            "followups": [],
        }
    elif schema_name == "PatchResult":
        data = {
            "summary": "Fixture feature: a pure decimal-safe quote calculation with independent unit tests.",
            "files": [
                {
                    "path": "quote.py",
                    "content": "from decimal import Decimal\n\ndef quote(price, quantity):\n    return Decimal(str(price)) * Decimal(str(quantity))\n",
                },
                {
                    "path": "test_quote.py",
                    "content": "import unittest\nfrom decimal import Decimal\nfrom quote import quote\n\nclass QuoteTests(unittest.TestCase):\n    def test_decimal_precision(self):\n        self.assertEqual(quote('0.1', 3), Decimal('0.3'))\n\nif __name__ == '__main__':\n    unittest.main()\n",
                },
            ],
            "tests": "python-unittest",
        }
    elif schema_name == "ReviewResult":
        data = {
            "approved": False,
            "findings": ["Fixture review cannot certify a real implementation. Owner review required."],
            "acceptance_assessment": ["Actual diff available for human review"],
        }
    else:
        raise ProviderError("No fixture exists for this schema")
    if schema_name in {"LeadAnalysis", "RequirementCritique"}:
        data["specialist_roles"] = (
            ["Cloud Architect", "Security Architect", "FinOps Engineer"] if migration else []
        )
    if schema_name == "RequirementCritique":
        data["requirements"] = [text[:2000]]
        data["improvements"] = [
            {
                "id": "validation",
                "current_requirement": text[:2000],
                "gap": "Invalid-input behavior is not specified in this controlled fixture.",
                "recommendation": "Reject empty task titles without changing saved tasks.",
                "reason": "An explicit validation rule permits a reproducible acceptance test.",
                "complexity": "low",
                "business_impact": "Protect saved task data.",
                "security_performance_impact": "Validate bounded input before writes.",
                "essential": True,
            }
        ]
        data["proposed_specification"] = {
            "text": text,
            "goals": [text[:2000]],
            "functional_requirements": [text[:2000]],
            "nonfunctional_requirements": [],
            "user_roles": [],
            "user_journeys": [],
            "constraints": [],
            "dependencies": [],
            "acceptance_criteria": data["acceptance_criteria"],
            "risks": ["Deterministic fixture; no genuine model analysis or independent review."],
            "out_of_scope": ["Unauthorized publication or deployment"],
            "open_questions": data["questions"],
        }
    if schema_name == "TechnicalDesign":
        from .architecture_design import DesignOption

        options = []
        for name in ["Modular application", "Separated API and web client"]:
            option = {
                field: "Proposed fixture design; implementation and verification are pending."
                for field in DesignOption.model_fields
            }
            option.update(
                name=name,
                advantages=["Explicit component ownership"],
                disadvantages=["Requires implementation and measured validation"],
                architecture_decisions=["Keep SQLite active; preserve PostgreSQL compatibility"],
                unresolved_assumptions=["Hosting and resource requirements need owner confirmation"],
            )
            options.append(option)
        data.update(
            options=options,
            recommended_option=options[0]["name"],
            single_option_reason="",
            benchmarks_verified=False,
            cloud_prices_verified=False,
        )
    if schema_name == "ProposalContent" and context.get("approved_architecture_design"):
        design = context["approved_architecture_design"]["design"]
        data["alternatives"] = [
            {
                key: option[key]
                for key in ("name", "architecture", "advantages", "disadvantages", "reliability")
            }
            for option in design["options"]
        ]
        data["recommendation"] = design["recommended_option"]
    return Response(data, 0, 0)
