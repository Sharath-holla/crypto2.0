import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .consulting import enqueue_consulting
from .db import SessionLocal, uid
from .models import Client, Requirement
from .organization import generate_role_reference, seed
from .workflows import tick


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "seed", "demo", "worker-once", "roles"])
    args = parser.parse_args()
    settings().validate_startup()
    if args.command == "init":
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    if args.command in {"init", "seed", "demo"}:
        with SessionLocal() as session:
            org = seed(session)
            if args.command == "demo" and not session.scalar(
                select(Requirement).where(Requirement.title == "Cloud migration assessment · fixture")
            ):
                if not settings().mock_enabled:
                    raise ValueError("Demo requires MOCK_ENABLED=true")
                requirement = Requirement(
                    id=uid(),
                    org_id=org.id,
                    client_id=session.scalar(select(Client.id).where(Client.org_id == org.id)),
                    title="Cloud migration assessment · fixture",
                    mode="mock",
                    text="I want to move workloads and data from Google Cloud to Lightning AI. Compare compatible architectures and total cost before migration. No inventory or current rates supplied.",
                )
                session.add(requirement)
                session.flush()
                enqueue_consulting(session, requirement)
                session.commit()
        if args.command == "demo":

            async def demo():
                for _ in range(10):
                    if not await tick():
                        break

            asyncio.run(demo())
        print("Database initialized; existing records preserved.")
    if args.command == "worker-once":
        print("Work available:", asyncio.run(tick()))
    if args.command in {"init", "roles"}:
        generate_role_reference(Path("docs/agent-role-reference.md"))


if __name__ == "__main__":
    main()
