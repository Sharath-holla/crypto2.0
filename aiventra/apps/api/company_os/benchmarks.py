"""Versioned deterministic microbenchmarks, never certification of production code quality."""

import ast

from pydantic import Field
from sqlalchemy import select

from . import models as m
from .credentials import credential_revision
from .db import now
from .providers import ProviderError, ProviderUnavailable
from .schemas import Strict
from .security import digest

SUITE = "micro-v1"
CASES = [
    ("simple", "Return the decimal sum of 17 and 25, with no other text."),
    (
        "business",
        "List these five requirements for a refund workflow: actor, permission, audit, idempotency, acceptance. Use each word.",
    ),
    (
        "architecture",
        "Name controls for an at-least-once queue: idempotency, retry, dead letter, transactional outbox. Use each phrase.",
    ),
    ("coding", "Return only Python source for add(a, b), returning a + b. No Markdown fences."),
    (
        "repair",
        "Repair `def first(xs): return xs[0]` to return None for an empty list, otherwise xs[0]. Return only Python source without fences.",
    ),
    ("testing", "List edge cases for an integer addition function: zero, negative, large. Use each word."),
    (
        "review",
        "Review SQL built by concatenating untrusted input. Include injection, parameterized, validation. Use each word.",
    ),
    ("tools", "Use sum_numbers exactly once with numbers [7, 13], then answer only the decimal result."),
]


class Answer(Strict):
    answer: str = Field(min_length=1, max_length=12000)


def fingerprint(session, model, provider):
    return digest(
        {
            "model": model.identifier,
            "provider": provider.base_url,
            "kind": provider.kind,
            "capabilities": model.capabilities,
            "sensitivity": model.sensitivity,
            "prices": [model.input_price_micro_per_million, model.output_price_micro_per_million],
            "credential_revision": credential_revision(provider, session),
        }
    )


def current_profile(session, model, provider):
    profile = session.scalar(
        select(m.BenchmarkProfile).where(
            m.BenchmarkProfile.model_id == model.id, m.BenchmarkProfile.org_id == model.org_id
        )
    )
    return (
        profile
        if profile
        and profile.suite_version == SUITE
        and now() - profile.checked_at <= 2592000
        and profile.fingerprint == fingerprint(session, model, provider)
        else None
    )


def grade(case, answer):
    text = answer.strip().lower()
    if case == "simple":
        return 100 if text == "42" else 0
    keywords = {
        "business": ["actor", "permission", "audit", "idempotency", "acceptance"],
        "architecture": ["idempotency", "retry", "dead letter", "transactional outbox"],
        "testing": ["zero", "negative", "large"],
        "review": ["injection", "parameterized", "validation"],
    }
    if case in keywords:
        return round(100 * sum(word in text for word in keywords[case]) / len(keywords[case]))
    try:
        tree = ast.parse(answer)
        expected = {
            "coding": ["def add(a, b):\n    return a + b"],
            "repair": [
                "def first(xs):\n    return xs[0] if xs else None",
                "def first(xs):\n    if not xs:\n        return None\n    return xs[0]",
                "def first(xs):\n    if xs:\n        return xs[0]\n    return None",
            ],
        }
        if case in expected:
            return (
                100
                if any(ast.dump(tree) == ast.dump(ast.parse(reference)) for reference in expected[case])
                else 0
            )
    except (SyntaxError, AttributeError, IndexError, ValueError, RecursionError):
        pass
    return 0


async def benchmark_step(session, workflow, token, work):
    from .gateway import execute
    from .tools import ToolTurn, definitions, guard, invoke
    from .workflows import checkpoint

    model = session.get(m.ModelConfig, work.subject_id)
    provider = session.get(m.Provider, model.provider_id)
    agent = session.get(m.Agent, work.participants[0])
    if workflow.step == 0 and not session.scalar(
        select(m.ModelRun.id).where(m.ModelRun.workflow_id == workflow.id)
    ):
        work.input = {**work.input, "fingerprint": fingerprint(session, model, provider)}
        session.commit()
    if fingerprint(session, model, provider) != work.input["fingerprint"]:
        raise PermissionError("Model configuration changed during benchmark; start a new suite")
    case, prompt = CASES[workflow.step]
    status, score = "rubric_failed", 0
    error = ""
    try:
        if case == "tools":
            defs = definitions(agent, benchmark=True)
            turn = await execute(
                session,
                workflow,
                agent,
                "benchmark_tools_0",
                ToolTurn,
                {"task": prompt},
                quality=0,
                capabilities={"structured"},
                native_tools=defs,
            )
            guard(session, workflow, agent)
            run_id = session.scalar(
                select(m.ModelRun.id).where(
                    m.ModelRun.workflow_id == workflow.id,
                    m.ModelRun.step_name == "benchmark_tools_0",
                    m.ModelRun.status == "succeeded",
                )
            )
            if len(turn.calls) == 1:
                call = turn.calls[0]
                result = invoke(
                    session, workflow, agent, None, "benchmark_tools_0", run_id, call, {"sum_numbers"}
                )
                session.commit()
                final = await execute(
                    session,
                    workflow,
                    agent,
                    "benchmark_tools_1",
                    ToolTurn,
                    {"task": prompt},
                    quality=0,
                    capabilities={"structured"},
                    native_tools=defs,
                    native_history=[{**turn.model_dump(), "results": {call.id: result}}],
                )
                score = (
                    100
                    if call.name == "sum_numbers"
                    and call.arguments == {"numbers": [7, 13]}
                    and result == {"sum": 20}
                    and not final.calls
                    and final.answer.strip() == "20"
                    else 0
                )
        else:
            answer = await execute(
                session,
                workflow,
                agent,
                f"benchmark_{case}",
                Answer,
                {"task": prompt, "evaluation": "Return an answer conforming to the requested JSON schema"},
                quality=0,
                capabilities={"structured"},
            )
            score = grade(case, answer.answer)
        if score == 100:
            status = "passed"
    except ProviderError as exc:
        if exc.uncertain or isinstance(exc, ProviderUnavailable):
            raise
        error = str(exc)
        status = "provider_rejected"
    guard(session, workflow, agent)
    runs = list(
        session.scalars(
            select(m.ModelRun).where(
                m.ModelRun.workflow_id == workflow.id, m.ModelRun.step_name.like(f"benchmark_{case}%")
            )
        )
    )
    metrics = {
        "run_ids": [r.id for r in runs],
        "cost_micro": sum(r.cost_micro for r in runs),
        "duration_ms": sum(r.duration_ms for r in runs),
        "call_count": len(runs),
        "successful_calls": sum(r.status == "succeeded" for r in runs),
        "error": error,
        "rubric": "micro-v1 deterministic checks; code is parsed, never executed on host",
    }
    row = m.BenchmarkResult(
        org_id=work.org_id,
        work_id=work.id,
        model_id=model.id,
        case_name=case,
        score=score,
        status=status,
        metrics=metrics,
    )
    session.add(row)
    session.flush()
    complete = workflow.step == len(CASES) - 1
    if complete:
        results = list(session.scalars(select(m.BenchmarkResult).where(m.BenchmarkResult.work_id == work.id)))
        profile = session.scalar(select(m.BenchmarkProfile).where(m.BenchmarkProfile.model_id == model.id))
        if not profile:
            profile = m.BenchmarkProfile(
                org_id=work.org_id,
                model_id=model.id,
                work_id=work.id,
                suite_version=SUITE,
                fingerprint=work.input["fingerprint"],
            )
            session.add(profile)
        totals = {
            "quality": round(sum(r.score for r in results) / len(CASES)),
            "reliability": round(
                100
                * sum(r.metrics["successful_calls"] for r in results)
                / max(sum(r.metrics["call_count"] for r in results), 1)
            ),
            "rubric_pass_rate": round(100 * sum(r.status == "passed" for r in results) / len(CASES)),
            "cost_micro": sum(r.metrics["cost_micro"] for r in results),
            "latency_ms": round(
                sum(r.metrics["duration_ms"] for r in results)
                / max(sum(r.metrics["call_count"] for r in results), 1)
            ),
            "cases": {r.case_name: r.score for r in results},
            "observed": (
                ["structured"]
                if any(r.metrics["successful_calls"] for r in results if r.case_name != "tools")
                else []
            )
            + (["tools"] if score == 100 else []),
            "scope": "deterministic microbenchmarks; not production certification",
        }
        run_ids = [run_id for result in results for run_id in result.metrics["run_ids"]]
        if session.scalar(
            select(m.RunTrace.id).where(
                m.RunTrace.run_id.in_(run_ids),
                m.RunTrace.usage_known.is_(True),
                m.RunTrace.state == "completed",
            )
        ):
            totals["observed"].append("streaming")
        totals["cost_micro_per_quality_point"] = round(
            totals["cost_micro"] / max(sum(r.score for r in results), 1), 4
        )
        profile.work_id, profile.suite_version = work.id, SUITE
        profile.fingerprint, profile.checked_at, profile.metrics = work.input["fingerprint"], now(), totals
        work.result = totals
    checkpoint(session, workflow, token, f"benchmark_{case}", metrics, complete=complete)
