"""Fail-closed readiness report; never fit, execute trades, or invent portfolio accounting.

This gate consumes independently qualified artifact attestations. It does not
perform the financial/statistical qualification itself or choose sample thresholds.
Every claim must cite immutable evidence for the same experiment. Synthetic test
results and regression-smoke reports cannot serve as out-of-sample evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from crypto_ai.phase7.selection_chronology import (
    INDEPENDENT_EVALUATION,
    authorize_use,
    load_protocol,
)

REQUIREMENTS = (
    "funding_model_complete",
    "execution_costs_qualified",
    "non_overlapping_trade_policy",
    "capital_allocation_defined",
    "concurrent_positions_defined",
    "leverage_defined",
    "equity_curve_available",
    "portfolio_risk_metrics_available",
    "fitted_model_artifacts",
    "out_of_sample_results",
    "sufficient_trades",
    "multiple_evaluation_folds",
    "baseline_superiority",
    "cost_stress_robustness",
    "no_selection_contamination",
)


def tradability_readiness(
    evidence: Mapping[str, Any] | None = None,
    *,
    model_pipeline_validated: bool = False,
) -> dict[str, Any]:
    """Require hash-verified qualification evidence plus precommitted chronological OOS.

    Each evidence entry is {path, sha256}; its JSON must name the requirement,
    a common experiment_identity, qualified=true, and synthetic=false. The OOS
    attestation must also provide the registered protocol, folds, spec and a
    sample-size contract that was committed before evaluation. These are
    attestations from a separate qualification process, not smoke metrics.
    """
    evidence = evidence or {}
    checks: dict[str, bool] = {}
    failures: dict[str, str] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for requirement in REQUIREMENTS:
        entry = evidence.get(requirement)
        checks[requirement] = False
        if not isinstance(entry, Mapping):
            failures[requirement] = "QUALIFIED_EVIDENCE_MISSING"
            continue
        try:
            path = Path(entry["path"])
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("EVIDENCE_HASH_MISMATCH")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("INVALID_QUALIFICATION_ARTIFACT")
            if (
                payload.get("requirement") != requirement
                or payload.get("qualified") is not True
                or payload.get("synthetic") is not False
                or not isinstance(payload.get("experiment_identity"), str)
                or not payload["experiment_identity"]
            ):
                raise ValueError("NOT_QUALIFIED_REAL_EXPERIMENT_EVIDENCE")
            if (
                requirement == "funding_model_complete"
                and payload.get("funding_model_status") != "COMPLETE"
            ):
                raise ValueError("FUNDING_NOT_MODELLED_OR_NOT_COMPLETE")
            if requirement == "execution_costs_qualified" and (
                payload.get("execution_cost_assumptions_qualified") is not True
                or payload.get("entry_price_assumptions_qualified") is not True
                or payload.get("cost_model_label") == "STATIC_COST_STRESS"
            ):
                raise ValueError("STATIC_COST_STRESS_IS_NOT_QUALIFIED_EXECUTION")
            if (
                requirement == "portfolio_risk_metrics_available"
                and payload.get("metric_scope") != "PORTFOLIO_EQUITY_CURVE"
            ):
                raise ValueError("TRADE_RETURN_PROXIES_ARE_NOT_PORTFOLIO_METRICS")
            payloads[requirement] = payload
            checks[requirement] = True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures[requirement] = str(exc)
    identities = {p["experiment_identity"] for p in payloads.values()}
    if len(identities) > 1:
        failures["experiment_identity"] = "MIXED_EXPERIMENT_EVIDENCE"
    oos = payloads.get("out_of_sample_results")
    if oos:
        try:
            if oos.get("evidence_class") != "REAL_PRECOMMITTED_OUT_OF_SAMPLE":
                raise ValueError("REGRESSION_SMOKE_IS_NOT_TRADABILITY_EVIDENCE")
            protocol = load_protocol(Path(oos["selection_protocol_path"]))
            folds = oos["evaluation_folds"]
            if not isinstance(folds, list) or len(set(folds)) < 2 or len(set(folds)) != len(folds):
                raise ValueError("MULTIPLE_DISTINCT_EVALUATION_FOLDS_REQUIRED")
            authorize_use(protocol, INDEPENDENT_EVALUATION, folds, spec=oos["spec"])
            trades, minimum = oos["trade_count"], oos["precommitted_minimum_trades"]
            if (
                type(trades) is not int
                or type(minimum) is not int
                or minimum <= 0
                or trades < minimum
                or oos.get("sample_contract_precommitted") is not True
            ):
                raise ValueError("PRECOMMITTED_SAMPLE_SIZE_CONTRACT_NOT_MET")
            if (
                any(
                    oos.get(k) is not False
                    for k in (
                        "test_used_for_selection",
                        "july_2026_used",
                        "prospective_holdout_used",
                        "prospective_holdout_evaluation_authorized",
                    )
                )
                or oos.get("prospective_holdout_status") != "LOCKED_UNUSED"
            ):
                raise ValueError("SELECTION_OR_HOLDOUT_CONTAMINATION")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures["out_of_sample_results"] = str(exc)
            checks["out_of_sample_results"] = False
    if model_pipeline_validated is not True:
        failures["model_pipeline"] = "PIPELINE_VERIFICATION_INCOMPLETE"
    validated = all(checks.values()) and not failures
    return {
        "schema": "phase7_tradability_readiness_v1",
        "MODEL_PIPELINE_VALIDATED": model_pipeline_validated is True,
        "TRADABILITY_VALIDATED": validated,
        "tradability": "ESTABLISHED" if validated else "NOT_ESTABLISHED",
        "requirements": checks,
        "blockers": failures,
        "qualification_scope": "Qualified-evidence gate; no portfolio or execution engine",
        "holdout": {"status": "LOCKED_UNUSED", "used": False, "evaluation_authorized": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite readiness evidence")
    supplied = json.loads(args.evidence.read_text()) if args.evidence else {}
    report = tradability_readiness(supplied)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["tradability"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
