"""Closed, credential-free protocol shared by the worker and trusted Docker broker."""

from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUITES = {
    "python-unittest": (
        "python:3.12-slim",
        ["python", "-I", "-m", "unittest", "discover", "-v"],
        ["python", "-I", "-m", "compileall", "-q", "/workspace"],
    ),
    "node-test": (
        "node:22-slim",
        ["node", "--test"],
        [
            "node",
            "-e",
            "const fs=require('node:fs'),p=require('node:path'),c=require('node:child_process');function walk(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){const f=p.join(d,e.name);if(e.isDirectory())walk(f);else if(/\\.(js|mjs|cjs)$/.test(f)){const r=c.spawnSync(process.execPath,['--check',f],{stdio:'inherit'});if(r.status!==0)process.exit(1);}}}walk('/workspace');",
        ],
    ),
}
for _round in (1, 2, 3):
    SUITES[f"python-qa-{_round}"] = (
        "aiventra-quality-python:1",
        ["python", "-I", "/opt/aiventra/quality_runner.py", "test", str(_round)],
        ["python", "-I", "/opt/aiventra/quality_runner.py", "build", str(_round)],
    )


def request_digest(data):
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


FORBIDDEN = {
    ".git",
    "node_modules",
    ".venv",
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
}


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    suite: Literal["python-unittest", "node-test", "python-qa-1", "python-qa-2", "python-qa-3"]
    files: dict[str, str] = Field(min_length=1, max_length=500)
    timeout: int = Field(ge=1, le=120, default=120)

    @model_validator(mode="after")
    def safe_files(self):
        size = 0
        for name, content in self.files.items():
            path = PurePosixPath(name)
            if (
                not name
                or len(name) > 400
                or path.is_absolute()
                or "\\" in name
                or ":" in name
                or any(part in {"..", "."} or part in FORBIDDEN for part in path.parts)
                or any(part.startswith(".env") for part in path.parts)
                or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
                or str(path) != name
            ):
                raise ValueError("Unsafe or secret file path")
            count = len(content.encode())
            if count > 1_000_000:
                raise ValueError("File exceeds 1 MB")
            size += count
        if size > 5_000_000:
            raise ValueError("Snapshot exceeds 5 MB")
        return self
