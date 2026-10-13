"""Read-only restart snapshot; run before/after service restarts and compare output."""

import json

from company_os import models as m
from company_os.config import settings
from company_os.db import SessionLocal
from company_os.security import digest
from sqlalchemy import select

assert settings().ai_spending_mode == "ZERO_COST_ONLY"
with SessionLocal() as session:
    saved = [
        {
            "id": workflow.id,
            "status": workflow.status,
            "step": workflow.step,
            "attempts": workflow.attempts,
            "revision": workflow.revision,
            "wait_context": workflow.wait_context,
            "last_error": workflow.last_error,
        }
        for workflow in session.scalars(select(m.Workflow).order_by(m.Workflow.id))
        if workflow.wait_context.get("spending_mode") == "ZERO_COST_ONLY"
        and workflow.status in {"waiting_for_free_provider", "paused"}
    ]
    assert saved, "Create a blocked live browser-test workflow before checking recovery"
    proofs = [
        {
            "model_id": row.model_id,
            "fingerprint": row.fingerprint,
            "checked_at": row.checked_at,
            "state": row.state,
            "evidence_digest": row.evidence_digest,
        }
        for row in session.scalars(select(m.LocalModelVerification).order_by(m.LocalModelVerification.id))
    ]
    print(
        json.dumps(
            {
                "spending_mode": "ZERO_COST_ONLY",
                "saved_workflows": len(saved),
                "saved_digest": digest(saved),
                "local_verifications": len(proofs),
                "verification_digest": digest(proofs),
            },
            sort_keys=True,
        )
    )
