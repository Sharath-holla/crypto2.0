from concurrent.futures import ThreadPoolExecutor

import pytest
from company_os.db import now
from company_os.finance import BudgetExceeded, estimate_rates, reserve, token_cost
from company_os.models import Budget, ModelConfig, ModelRun, Notification, Project, Requirement, Workflow
from company_os.security import verify_audit
from company_os.workflows import tick
from sqlalchemy import select


def test_deterministic_decimal_estimates():
    rates = [
        {
            "alternative": "Hybrid",
            "quantity": "0.3",
            "unit_price_micro": 100000,
            "one_time": False,
            "retrieved_at": now(),
        }
    ]
    assert estimate_rates(rates, ["Hybrid"])[0]["recurring_micro"] == 30000
    assert estimate_rates([], ["Unknown"])[0]["recurring_micro"] is None
    model = ModelConfig(input_price_micro_per_million=2500000, output_price_micro_per_million=10000000)
    assert token_cost(model, 100, 20) == 450


def test_h_atomic_budget_caps_and_concurrent_reservation(company):
    with company["factory"]() as session:
        budget = session.scalar(select(Budget))
        budget.limit_micro = 100
        session.commit()
        budget_id = budget.id

    def attempt():
        with company["factory"]() as session:
            row = session.get(Budget, budget_id)
            try:
                reserve(session, [row], 60)
                session.commit()
                return True
            except BudgetExceeded:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == [False, True]
    with company["factory"]() as session:
        assert session.get(Budget, budget_id).reserved_micro == 60


def test_reservation_rolls_back_all_caps(company):
    with company["factory"]() as session:
        first = session.scalar(select(Budget))
        second = Budget(org_id=company["org"].id, scope="tiny", limit_micro=1)
        session.add(second)
        session.commit()
        with pytest.raises(BudgetExceeded):
            reserve(session, [first, second], 10)
        session.expire_all()
        assert session.get(Budget, first.id).reserved_micro == 0


def test_large_budgets_remain_exact_across_reservation_and_session_reopen(company):
    with company["factory"]() as session:
        budget = session.scalar(select(Budget))
        budget.limit_micro = 1_000_000_000_000
        reserve(session, [budget], 3_000_000_000)
        session.commit()
        budget_id = budget.id
    with company["factory"]() as session:
        budget = session.get(Budget, budget_id)
        assert budget.limit_micro == 1_000_000_000_000
        assert budget.reserved_micro == 3_000_000_000


@pytest.mark.parametrize("scope", ["requirement", "project"])
async def test_h_workflow_pauses_before_spend_and_alerts_owner(company, http, requirement, scope):
    subject_id = requirement["id"]
    if scope == "project":
        for _ in range(7):
            await tick(company["factory"])
        proposal = http.get("/state").json()["proposals"][0]
        response = http.post(
            f"/proposals/{proposal['id']}/approve",
            json={
                "version": proposal["version"],
                "content_hash": proposal["content_hash"],
                "selection": proposal["content"]["recommendation"],
            },
        )
        assert response.status_code == 200
        subject_id = response.json()["id"]
    with company["factory"]() as session:
        # Synthetic fixture rates exercise the paid-operation guard; no network call or real cost.
        for model in session.scalars(select(ModelConfig)):
            model.input_price_micro_per_million = 1000000
            model.output_price_micro_per_million = 1000000
        budget = session.scalar(select(Budget).where(Budget.scope == f"{scope}:{subject_id}"))
        budget.limit_micro = 0
        before_runs = len(session.scalars(select(ModelRun)).all())
        session.commit()
    assert await tick(company["factory"])
    with company["factory"]() as session:
        subject = session.get(Project if scope == "project" else Requirement, subject_id)
        assert subject.status == "budget_paused"
        assert any(row.status == "needs_attention" for row in session.scalars(select(Workflow)))
        assert len(session.scalars(select(ModelRun)).all()) == before_runs
        assert session.scalar(select(Notification)) is not None
        assert all(row.spent_micro == row.reserved_micro == 0 for row in session.scalars(select(Budget)))
        assert verify_audit(session, company["org"].id)["valid"]
