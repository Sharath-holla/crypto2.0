"""Rotate local owner password and signing key without printing either value."""

import secrets
from pathlib import Path

from company_os.config import settings
from company_os.db import SessionLocal
from company_os.models import User
from company_os.security import audit, password_hasher
from sqlalchemy import select

path = Path(__file__).resolve().parents[1] / ".env"
password = secrets.token_urlsafe(24)
signing_key = secrets.token_urlsafe(48)
lines = path.read_text(encoding="utf-8").splitlines()
for index, line in enumerate(lines):
    if line.startswith("OWNER_PASSWORD="):
        lines[index] = "OWNER_PASSWORD=" + password
    if line.startswith("JWT_SECRET="):
        lines[index] = "JWT_SECRET=" + signing_key
with SessionLocal() as session:
    user = session.scalar(select(User).where(User.email == settings().owner_email, User.role == "owner"))
    if not user:
        raise ValueError("Existing owner not found")
    user.password_hash = password_hasher.hash(password)
    audit(session, user.org_id, "local-administrator", "auth.local_secrets_rotated", user.id)
    session.commit()
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Local credentials rotated. Restart API and worker. Read new credentials only in private .env.")
