from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import now
from .models import Budget, ModelConfig, ModelRun, Transaction


class BudgetExceeded(Exception):
    pass


def token_cost(model: ModelConfig, input_tokens: int, output_tokens: int) -> int:
    numerator = (
        input_tokens * model.input_price_micro_per_million
        + output_tokens * model.output_price_micro_per_million
    )
    return (numerator + 999999) // 1000000


def reserve(session: Session, budgets: list[Budget], amount: int) -> None:
    # All caps participate in one transaction. A nested savepoint reverses earlier updates on failure.
    with session.begin_nested():
        for budget in sorted(budgets, key=lambda row: row.id):
            result = session.execute(
                update(Budget)
                .where(
                    Budget.id == budget.id,
                    Budget.spent_micro + Budget.reserved_micro + amount <= Budget.limit_micro,
                )
                .values(reserved_micro=Budget.reserved_micro + amount, version=Budget.version + 1)
            )
            if result.rowcount != 1:
                raise BudgetExceeded(f"Hard budget reached: {budget.scope}")


def settle(session: Session, run: ModelRun, amount: int, basis: str) -> None:
    if session.scalar(select(Transaction).where(Transaction.run_id == run.id)):
        return
    for budget_id in run.budget_ids:
        session.execute(
            update(Budget)
            .where(Budget.id == budget_id)
            .values(
                reserved_micro=Budget.reserved_micro - run.reserved_micro,
                spent_micro=Budget.spent_micro + amount,
                version=Budget.version + 1,
            )
        )
    run.cost_micro = amount
    run.cost_basis = basis
    session.add(Transaction(org_id=run.org_id, run_id=run.id, amount_micro=amount, basis=basis))


def estimate_rates(rates: list[dict], alternatives: list[str]) -> list[dict]:
    result = []
    for name in alternatives:
        lines = [rate for rate in rates if rate["alternative"] == name]
        recurring = 0
        one_time = 0
        for rate in lines:
            value = int(
                (Decimal(rate["quantity"]) * rate["unit_price_micro"]).to_integral_value(
                    rounding=ROUND_CEILING
                )
            )
            if rate["one_time"]:
                one_time += value
            else:
                recurring += value
        result.append(
            {
                "alternative": name,
                "recurring_micro": recurring if lines else None,
                "one_time_micro": one_time if lines else None,
                "twelve_month_micro": recurring * 12 + one_time if lines else None,
                "basis": "owner_supplied_partial_estimate" if lines else "unknown: pricing evidence required",
                "lines": lines,
                "complete": False,
                "warnings": [
                    "Confirm compute, storage, egress, licenses, operational labor and migration downtime.",
                    *(
                        ["Source older than 30 days"]
                        if any(now() - x["retrieved_at"] > 2592000 for x in lines)
                        else []
                    ),
                ],
            }
        )
    return result
