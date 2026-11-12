"""Out-of-folder SHA-256 registry for pickled model artifacts (added by Claude, finding L-08).

Model files are joblib/pickle files. The existing report-versus-model hash check lives next to
the artifact, so someone who can replace the model can replace the report too. This registry
keeps the expected hash in a DIFFERENT location (default ``~/.crypto_ai/model_hash_registry``,
override with ``PHASE7_MODEL_HASH_REGISTRY``) and ``load_model`` refuses a file whose hash does
not match its registered one. Set ``PHASE7_REQUIRE_MODEL_REGISTRY=1`` to also refuse models that
were never registered. Local trust model only: this is not a signature scheme.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from crypto_ai.data.storage import file_sha256

REGISTRY_ENV = "PHASE7_MODEL_HASH_REGISTRY"
REQUIRE_ENV = "PHASE7_REQUIRE_MODEL_REGISTRY"


class ModelRegistryError(ValueError):
    """A model artifact failed its out-of-folder hash check."""


def registry_root() -> Path:
    configured = os.environ.get(REGISTRY_ENV)
    return Path(configured) if configured else Path.home() / ".crypto_ai" / "model_hash_registry"


def _record_path(model_path: Path, root: Path) -> Path:
    key = hashlib.sha256(str(model_path.resolve()).encode("utf-8")).hexdigest()
    return root / f"{key}.json"


def _refuse_registry_inside_artifact_folder(model_path: Path, root: Path) -> None:
    if root.resolve() in model_path.resolve().parents:
        raise ModelRegistryError("the model hash registry must live outside the model folder")


def register_model_hash(model_path: Path, *, root: Path | None = None) -> Path:
    """Record the file's SHA-256 outside its folder, keeping earlier hashes for that path.

    Called only when a model is freshly published (``save_model`` refuses to overwrite, so a
    new file at a known path means the old one was removed by an explicit recovery step).
    """

    registry = root or registry_root()
    _refuse_registry_inside_artifact_folder(model_path, registry)
    registry.mkdir(parents=True, exist_ok=True)
    digest = file_sha256(model_path)
    record = _record_path(model_path, registry)
    previous: list[str] = []
    if record.exists():
        existing = json.loads(record.read_text(encoding="utf-8"))
        if existing.get("sha256") == digest:
            return record
        previous = [*existing.get("previous_sha256", []), str(existing.get("sha256"))]
    payload = {
        "path": str(model_path.resolve()),
        "sha256": digest,
        "previous_sha256": previous,
        "registered_at": datetime.now(UTC).isoformat(),
    }
    temporary = record.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, record)
    return record


def verify_registered_model(model_path: Path, *, root: Path | None = None) -> str:
    """Return ``VERIFIED`` or ``UNREGISTERED``; raise ModelRegistryError on any mismatch."""

    registry = root or registry_root()
    _refuse_registry_inside_artifact_folder(model_path, registry)
    record = _record_path(model_path, registry)
    if not record.is_file():
        if os.environ.get(REQUIRE_ENV) == "1":
            raise ModelRegistryError(f"model is not in the hash registry: {model_path}")
        return "UNREGISTERED"
    expected = json.loads(record.read_text(encoding="utf-8")).get("sha256")
    if not isinstance(expected, str) or file_sha256(model_path) != expected:
        raise ModelRegistryError(f"model hash does not match the registry; refusing: {model_path}")
    return "VERIFIED"
