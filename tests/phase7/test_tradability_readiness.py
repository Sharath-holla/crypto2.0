from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from crypto_ai.phase7.tradability import REQUIREMENTS, tradability_readiness


def _evidence(tmp_path):
    protocol = Path(__file__).parents[2] / "configs/research/phase7_selection_chronology_v1.json"
    calendar = json.loads(protocol.read_text())
    entries = {}
    for requirement in REQUIREMENTS:
        payload = dict(
            requirement=requirement,
            qualified=True,
            synthetic=False,
            experiment_identity="fixture-experiment",
        )
        if requirement == "funding_model_complete":
            payload["funding_model_status"] = "COMPLETE"
        if requirement == "execution_costs_qualified":
            payload.update(
                execution_cost_assumptions_qualified=True, entry_price_assumptions_qualified=True
            )
        if requirement == "portfolio_risk_metrics_available":
            payload["metric_scope"] = "PORTFOLIO_EQUITY_CURVE"
        if requirement == "out_of_sample_results":
            payload.update(
                evidence_class="REAL_PRECOMMITTED_OUT_OF_SAMPLE",
                selection_protocol_path=str(protocol),
                evaluation_folds=calendar["evaluation_folds"],
                spec=calendar["precommitted_specs"][0],
                trade_count=2000,
                precommitted_minimum_trades=1000,
                sample_contract_precommitted=True,
                test_used_for_selection=False,
                july_2026_used=False,
                prospective_holdout_used=False,
                prospective_holdout_evaluation_authorized=False,
                prospective_holdout_status="LOCKED_UNUSED",
            )
        path = tmp_path / f"{requirement}.json"
        path.write_text(json.dumps(payload))
        entries[requirement] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return entries


def test_no_evidence_or_truthy_flags_cannot_establish_tradability():
    assert tradability_readiness()["TRADABILITY_VALIDATED"] is False
    assert (
        tradability_readiness(dict.fromkeys(REQUIREMENTS, True), model_pipeline_validated=True)[
            "TRADABILITY_VALIDATED"
        ]
        is False
    )


@pytest.mark.parametrize("missing", REQUIREMENTS)
def test_every_requirement_is_mandatory_even_with_pipeline_validated(tmp_path, missing):
    entries = _evidence(tmp_path)
    # The complete fixture checks gate mechanics; it is never written as project evidence.
    assert (
        tradability_readiness(entries, model_pipeline_validated=True)["TRADABILITY_VALIDATED"]
        is True
    )
    del entries[missing]
    result = tradability_readiness(entries, model_pipeline_validated=True)
    assert result["TRADABILITY_VALIDATED"] is False
    assert missing in result["blockers"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("synthetic", True),
        ("evidence_class", "REGRESSION_SMOKE"),
        ("test_used_for_selection", True),
        ("prospective_holdout_used", True),
        ("trade_count", 0),
        ("evaluation_folds", []),
    ],
)
def test_synthetic_smoke_insufficient_or_contaminated_oos_is_rejected(tmp_path, field, value):
    entries = _evidence(tmp_path)
    entry = entries["out_of_sample_results"]
    path = Path(entry["path"])
    payload = {**json.loads(path.read_text()), field: value}
    path.write_text(json.dumps(payload))
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        tradability_readiness(entries, model_pipeline_validated=True)["TRADABILITY_VALIDATED"]
        is False
    )


@pytest.mark.parametrize(
    "requirement,field,value",
    [
        ("funding_model_complete", "funding_model_status", "NOT_MODELLED"),
        ("execution_costs_qualified", "cost_model_label", "STATIC_COST_STRESS"),
        ("portfolio_risk_metrics_available", "metric_scope", "TRADE_LEVEL_PROXY_NOT_PORTFOLIO"),
    ],
)
def test_missing_economic_engines_cannot_be_hidden_by_a_qualified_label(
    tmp_path,
    requirement,
    field,
    value,
):
    entries = _evidence(tmp_path)
    entry = entries[requirement]
    path = Path(entry["path"])
    path.write_text(json.dumps({**json.loads(path.read_text()), field: value}))
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        tradability_readiness(entries, model_pipeline_validated=True)["TRADABILITY_VALIDATED"]
        is False
    )


def test_forged_hash_and_mixed_experiments_are_rejected(tmp_path):
    entries = _evidence(tmp_path)
    entry = entries["funding_model_complete"]
    path = Path(entry["path"])
    payload = {**json.loads(path.read_text()), "experiment_identity": "other"}
    path.write_text(json.dumps(payload))
    assert (
        tradability_readiness(entries, model_pipeline_validated=True)["TRADABILITY_VALIDATED"]
        is False
    )
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        tradability_readiness(entries, model_pipeline_validated=True)["TRADABILITY_VALIDATED"]
        is False
    )
