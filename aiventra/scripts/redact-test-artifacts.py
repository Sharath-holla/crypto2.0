"""Redact local browser diagnostics in place, preserving artifacts."""

import io
import re
import zipfile
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
configuration = dotenv_values(root / ".env")
secrets = [
    value.encode()
    for name, value in configuration.items()
    if value and any(marker in name for marker in ("PASSWORD", "SECRET", "API_KEY"))
]


def redact(data: bytes) -> bytes:
    for secret in secrets:
        data = data.replace(secret, b"[REDACTED]")
    return re.sub(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", b"[REDACTED SESSION]", data)


directory = root / "apps" / "web" / "test-results"
if directory.exists():
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".txt", ".log"}:
            path.write_bytes(redact(path.read_bytes()))
        elif path.is_file() and path.suffix == ".zip":
            output = io.BytesIO()
            with (
                zipfile.ZipFile(path) as archive,
                zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as rewritten,
            ):
                for name in archive.namelist():
                    rewritten.writestr(name, redact(archive.read(name)))
            path.write_bytes(output.getvalue())
print("Browser diagnostic text and trace payloads redacted in place.")
