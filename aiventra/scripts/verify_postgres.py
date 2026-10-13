"""Verify a disposable migrated PostgreSQL stack; creates labeled test records."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from threading import Event, local

from company_os.authentication import count_attempt
from company_os.config import settings
from company_os.db import Base, SessionLocal, engine, uid
from company_os.finance import BudgetExceeded, reserve
from company_os.models import (
    AuditEvent,
    Budget,
    Client,
    Conversation,
    Organization,
    Provider,
    ProviderProbe,
    User,
    Workflow,
)
from company_os.provider_state import probe_for
from company_os.routes.conversations import (
    ConversationInput,
    TurnInput,
    cancel_turn,
    create_conversation,
    send_turn,
)
from company_os.security import audit, verify_audit
from company_os.staffing import admit, lock_org
from sqlalchemy import BigInteger, event, inspect, select, text, update
from sqlalchemy.exc import DBAPIError


def verify_chat_contention(factory, owner_id, client_id):
    """Exercise real worker admission against cancellation, without inference."""
    with factory() as session:
        owner = session.get(User, owner_id)
        conversation = create_conversation(ConversationInput(id=uid(), client_id=client_id), owner, session)
        turn = send_turn(
            conversation["id"],
            TurnInput(request_id=uid(), version=1, text="Concurrency verification fixture"),
            owner,
            session,
        )
        workflow_id, org_id = turn["workflow"]["id"], owner.org_id
        bind = session.get_bind()

    locked, writing = Event(), Event()
    context = local()
    first_writes = []

    def observe(connection, cursor, statement, parameters, execution_context, executemany):
        if getattr(context, "cancelling", False) and statement.lstrip().upper().startswith("UPDATE "):
            if not first_writes:
                first_writes.append(statement)
                writing.set()

    def dispatch():
        with factory() as session:
            lock_org(session, org_id)
            locked.set()
            assert writing.wait(20), "Cancellation did not reach its first write"
            session.get(Organization, org_id).paused = False
            workflow = session.get(Workflow, workflow_id)
            agents = admit(session, workflow)
            assert agents is not None
            session.execute(
                update(Workflow)
                .where(Workflow.id == workflow_id, Workflow.status == "queued")
                .values(status="running", lease_until=2**31 - 1, lease_token=uid(), capacity_agents=agents)
            )
            session.commit()

    def cancel():
        assert locked.wait(20), "Worker did not acquire admission lock"
        context.cancelling = True
        with factory() as session:
            return cancel_turn(conversation["id"], turn["id"], session.get(User, owner_id), session)

    event.listen(bind, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            worker = pool.submit(dispatch)
            cancellation = pool.submit(cancel)
            worker.result(timeout=30)
            result = cancellation.result(timeout=30)
    finally:
        event.remove(bind, "before_cursor_execute", observe)
    assert first_writes[0].lstrip().upper().startswith("UPDATE ORGANIZATIONS ")
    assert result["workflow"]["status"] == "cancelled"
    with factory() as session:
        workflow = session.get(Workflow, workflow_id)
        assert workflow.lease_until == 0 and workflow.lease_token != turn["workflow"]["lease_token"]
        assert admit(session, workflow) is None
        assert session.get(Conversation, conversation["id"]).version == 3
        assert verify_audit(session, org_id)["valid"]


def verify():
    if engine.dialect.name != "postgresql" or settings().app_env == "production":
        raise RuntimeError("Use a disposable non-production PostgreSQL stack")
    inspector = inspect(engine)
    checked = 0
    for table in Base.metadata.sorted_tables:
        stored = {column["name"]: column["type"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name.endswith("_micro") or column.name.endswith("_micro_per_million"):
                assert isinstance(stored[column.name], BigInteger), f"Narrow money column: {table.name}"
                checked += 1
    assert checked == 13

    marker = uid()
    with SessionLocal() as session:
        org = Organization(name="CI PostgreSQL verification " + marker, paused=True)
        session.add(org)
        session.flush()
        budget = Budget(org_id=org.id, scope="ci-verification:" + marker, limit_micro=5_000_000_000)
        session.add(budget)
        session.commit()
        org_id, budget_id = org.id, budget.id

    with SessionLocal() as session:
        owner = User(org_id=org_id, email=f"ci-chat-{marker}@example.test", role="owner")
        client = Client(org_id=org_id, name="CI chat contention fixture")
        session.add_all([owner, client])
        session.commit()
        owner_id, client_id = owner.id, client.id
    verify_chat_contention(SessionLocal, owner_id, client_id)
    verify_catalog_sync(SessionLocal, org_id)

    def attempt(_):
        with SessionLocal() as session:
            try:
                reserve(session, [session.get(Budget, budget_id)], 3_000_000_000)
                session.commit()
                return True
            except BudgetExceeded:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(attempt, range(4))) == [False, False, False, True]
    with SessionLocal() as session:
        budget = session.get(Budget, budget_id)
        assert (budget.limit_micro, budget.reserved_micro, budget.spent_micro) == (
            5_000_000_000,
            3_000_000_000,
            0,
        )

    def increment(_):
        with SessionLocal() as session:
            count = count_attempt(session, "ci-postgres-counter:" + marker)
            session.commit()
            return count

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(increment, range(8))) == list(range(1, 9))

    with SessionLocal() as session:
        provider = Provider(
            org_id=org_id,
            name="CI concurrent probe contract",
            kind="openai",
            base_url="https://api.openai.com/v1",
            credential_env="CI_CONTRACT_API_KEY",
        )
        session.add(provider)
        session.commit()
        provider_id = provider.id

    def create_probe(_):
        with SessionLocal() as session:
            record = probe_for(session, session.get(Provider, provider_id))
            session.commit()
            return record.id

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(create_probe, range(4)))) == 1
    with SessionLocal() as session:
        assert (
            len(session.scalars(select(ProviderProbe).where(ProviderProbe.provider_id == provider_id)).all())
            == 1
        )

    with SessionLocal() as session:
        audit(session, org_id, "ci-verifier", "verification.postgres", budget_id)
        session.commit()
        assert verify_audit(session, org_id)["valid"]
        event_id = session.scalar(select(AuditEvent.id).where(AuditEvent.org_id == org_id))
        for command in (
            "UPDATE audit_events SET action='tampered' WHERE id=:id",
            "DELETE FROM audit_events WHERE id=:id",
        ):
            try:
                with session.begin_nested():
                    session.execute(text(command), {"id": event_id})
            except DBAPIError as error:
                assert "audit append only" in str(error.orig)
            else:
                raise AssertionError("Database allowed audit mutation")
        assert verify_audit(session, org_id)["valid"]
    print(
        "PostgreSQL verified: 13 BIGINT money columns, large atomic caps, concurrent login counters/probe creation, chat admission/cancellation, catalog synchronization, append-only audit"
    )


def verify_catalog_sync(factory, org_id):
    """Real storage compatibility; explicit metadata fixture, never a provider call."""
    from company_os import model_catalog, spending
    from company_os.models import ModelConfig

    with factory() as session:
        lock_org(session, org_id)
        provider = Provider(
            org_id=org_id,
            name="CI catalog storage fixture",
            kind="openai",
            base_url="https://api.openai.com/v1",
        )
        session.add(provider)
        session.flush()
        from company_os.registry_provenance import classify

        classify(session, provider, "test_fixture", {"contract": "postgresql_catalog_storage"})
        state = model_catalog.record(session, provider, create=True)
        catalog = [{"identifier": "ci-storage-contract-model"}]
        model_catalog.synchronize(session, provider, state, catalog)
        model_catalog.synchronize(session, provider, state, catalog)
        model = session.scalar(select(ModelConfig).where(ModelConfig.provider_id == provider.id))
        assert model.capabilities == [] and model.quality == 0 and model.context_tokens == 0
        identity = model.id
        model.capabilities, model.quality, model.enabled = ["structured", "reasoning"], 90, False
        session.commit()
        model_catalog.synchronize(session, provider, state, [])
        session.commit()
        assert not model_catalog.available(model) and not spending.assess(provider, model).allowed
        model_catalog.synchronize(session, provider, state, catalog)
        session.commit()
        rows = session.scalars(select(ModelConfig).where(ModelConfig.provider_id == provider.id)).all()
        assert len(rows) == 1 and rows[0].id == identity
        assert model.capabilities == ["structured", "reasoning"] and model.quality == 90 and not model.enabled
        assert model_catalog.available(model)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-test-records", action="store_true", required=True)
    parser.parse_args()
    verify()
