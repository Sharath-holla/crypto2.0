"""Pure conservative wallet/deadline decisions; no account mutations or training metrics."""

from __future__ import annotations

import math
from datetime import UTC, datetime

ABSOLUTE_WALLET_FLOOR_USD = 1.0


def policy(contract):
    p = {
        "absolute_floor_usd": 1.0,
        "checkpoint_trigger_usd": 1.75,
        "checkpoint_grace_seconds": 90,
        "shutdown_seconds": 120,
        "billing_lag_seconds": 300,
        "export_seconds": 30,
        "api_latency_seconds": 30,
        "safety_margin_usd": 0.25,
        **contract.get("wallet_policy", {}),
    }
    if p["absolute_floor_usd"] != ABSOLUTE_WALLET_FLOOR_USD:
        raise ValueError("ABSOLUTE_WALLET_FLOOR_MUST_REMAIN_ONE_DOLLAR")
    for name, value in p.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("INVALID_WALLET_POLICY: " + name)
    if p["checkpoint_trigger_usd"] <= 1 or not 0 < p["checkpoint_grace_seconds"] <= 120:
        raise ValueError("UNSAFE_CHECKPOINT_TRIGGER_OR_GRACE")
    if p["shutdown_seconds"] < 60 or p["billing_lag_seconds"] < 60:
        raise ValueError("INSUFFICIENT_STOP_RESERVE")
    return p


def decision(c, *, wallet_usd, billed_usd=0, now=None, api_healthy=True, reason=None):
    p = policy(c)
    now = now or datetime.now(UTC)
    start = datetime.fromisoformat(c["session_start_utc"].replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(c["hard_stop_utc"].replace("Z", "+00:00"))
    rate = float(c["all_in_usd_per_hour_upper_bound"])
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("APPROVED_ALL_IN_RATE_REQUIRED")
    projected = max(0, (now - start).total_seconds()) * rate / 3600
    if not math.isfinite(float(billed_usd)) or float(billed_usd) < 0:
        api_healthy, billed_usd = False, 0
    wallet_valid = wallet_usd is not None and math.isfinite(float(wallet_usd))
    api_healthy = api_healthy and wallet_valid
    decline = max(0, c["wallet_usd_at_start"] - float(wallet_usd)) if wallet_valid else 0
    spend = max(projected, float(billed_usd), decline)
    effective_wallet = (
        min(float(wallet_usd), c["wallet_usd_at_start"] - spend)
        if wallet_valid
        else (c["wallet_usd_at_start"] - spend)
    )
    reserve_seconds = sum(
        p[k]
        for k in (
            "checkpoint_grace_seconds",
            "shutdown_seconds",
            "billing_lag_seconds",
            "export_seconds",
            "api_latency_seconds",
        )
    )
    trigger = max(
        p["checkpoint_trigger_usd"], 1 + rate * reserve_seconds / 3600 + p["safety_margin_usd"]
    )
    deadline_seconds = (deadline - now).total_seconds()
    budget_seconds = (c["max_session_usd"] - spend) * 3600 / rate
    wallet_seconds = (effective_wallet - 1 - p["safety_margin_usd"]) * 3600 / rate
    graceful_seconds = max(
        0,
        min(
            p["checkpoint_grace_seconds"],
            deadline_seconds - p["shutdown_seconds"],
            budget_seconds - p["shutdown_seconds"],
            wallet_seconds - p["shutdown_seconds"],
        ),
    )
    if reason is None:
        if not api_healthy or not wallet_valid:
            reason = "API_HEALTH_FAILURE"
        elif effective_wallet <= trigger:
            reason = "LOW_WALLET_PREEMPTION"
        elif (
            min(deadline_seconds, budget_seconds)
            <= p["shutdown_seconds"] + p["checkpoint_grace_seconds"]
        ):
            reason = "HARD_DEADLINE" if deadline_seconds <= budget_seconds else "SESSION_BUDGET"
    action = (
        "CONTINUE"
        if reason is None
        else ("CHECKPOINT_AND_STOP" if graceful_seconds >= 5 and api_healthy else "EMERGENCY_STOP")
    )
    return {
        "action": action,
        "reason": reason,
        "wallet_usd": wallet_usd if wallet_valid else None,
        "effective_wallet_usd": effective_wallet,
        "absolute_floor_usd": 1.0,
        "configured_trigger_usd": p["checkpoint_trigger_usd"],
        "effective_trigger_usd": trigger,
        "session_spend_upper_usd": spend,
        "all_in_rate_usd_per_hour": rate,
        "remaining_safe_minutes": max(
            0,
            min(
                deadline_seconds - p["shutdown_seconds"],
                budget_seconds - p["shutdown_seconds"],
                (effective_wallet - trigger) * 3600 / rate,
            )
            / 60,
        ),
        "grace_seconds": graceful_seconds if action == "CHECKPOINT_AND_STOP" else 0,
        "provider_billing_is_lagging": True,
    }
