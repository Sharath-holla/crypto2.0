"""Encrypted provider secrets. The vault key is independent of authentication keys."""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .config import settings
from .models import Provider, ProviderCredential


class VaultUnavailable(ValueError):
    pass


def vault_key() -> bytes:
    try:
        key = base64.urlsafe_b64decode(settings().provider_secret_key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise VaultUnavailable("PROVIDER_SECRET_KEY must be a base64 encoded 32-byte key") from None
    if len(key) != 32:
        raise VaultUnavailable("Configure the independent PROVIDER_SECRET_KEY before saving credentials")
    return key


def stored_credential(provider: Provider, session: Session | None = None):
    session = session or object_session(provider)
    if not session:
        return None
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.org_id == provider.org_id, ProviderCredential.provider_id == provider.id
        )
    )


def aad(provider: Provider, version: int) -> bytes:
    return f"aiventra-provider:{provider.org_id}:{provider.id}:{version}".encode()


def save_secret(session: Session, provider: Provider, secret: str) -> ProviderCredential:
    key = vault_key()
    record = stored_credential(provider, session)
    version = record.version + 1 if record else 1
    nonce = os.urandom(12)
    ciphertext = base64.urlsafe_b64encode(
        nonce + AESGCM(key).encrypt(nonce, secret.encode(), aad(provider, version))
    ).decode()
    if record:
        record.ciphertext, record.version = ciphertext, version
    else:
        record = ProviderCredential(
            org_id=provider.org_id, provider_id=provider.id, ciphertext=ciphertext, version=version
        )
        session.add(record)
    return record


def secret_for(provider: Provider, session: Session | None = None) -> str:
    record = stored_credential(provider, session)
    if not record:
        return os.environ.get(provider.credential_env, "")
    try:
        payload = base64.urlsafe_b64decode(record.ciphertext)
        return AESGCM(vault_key()).decrypt(payload[:12], payload[12:], aad(provider, record.version)).decode()
    except (ValueError, InvalidTag, UnicodeError):
        raise VaultUnavailable(
            "Stored credential cannot be decrypted with the configured vault key"
        ) from None


def credential_facts(provider: Provider, session: Session) -> dict:
    stored = stored_credential(provider, session)
    try:
        ready = bool(secret_for(provider, session)) or provider.kind in {"ollama", "mock"}
        error = ""
    except VaultUnavailable:
        ready, error = False, "vault_unavailable"
    try:
        vault_key()
        available = True
    except VaultUnavailable:
        available = False
    return {
        "credential_configured": ready,
        "credential_source": "vault"
        if stored
        else "environment"
        if os.environ.get(provider.credential_env)
        else "none",
        "credential_error": error,
        "vault_available": available,
    }


def credential_revision(provider: Provider, session: Session) -> str:
    # Read columns rather than an identity-map object: detect rotations during an HTTP request.
    stored = session.execute(
        select(ProviderCredential.ciphertext, ProviderCredential.version).where(
            ProviderCredential.provider_id == provider.id, ProviderCredential.org_id == provider.org_id
        )
    ).first()
    value = (
        f"vault:{stored.version}:{stored.ciphertext}"
        if stored
        else f"env:{os.environ.get(provider.credential_env, '')}"
    )
    return hashlib.sha256(value.encode()).hexdigest()
