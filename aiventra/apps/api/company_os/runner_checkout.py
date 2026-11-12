"""Read-only GitHub acquisition in the dedicated broker. Never imported by coding agents."""

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import time
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .publication import GitHub
from .runner_protocol import RunInput


class ScopedCheckoutReader:
    """Read-only capability; credentials remain in the trusted broker process."""

    def __init__(self, repository):
        self.github = GitHub(repository)

    async def request(self, method, path):
        if method != "GET" or not path.startswith(
            ("git/ref/heads/", "git/commits/", "git/trees/", "git/blobs/")
        ):
            raise ValueError("Checkout reader permits Git object reads only")
        return await self.github.request(method, path)


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    org_id: UUID
    project_id: UUID
    repository: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    branch: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,99}$")
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")


class CheckoutScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_id: UUID
    project_id: UUID


class CheckoutExecution(CheckoutScope):
    job_id: UUID
    suite: str = Field(pattern=r"^(python-unittest|node-test)$")
    timeout: int = Field(default=120, ge=1, le=120)


def limits():
    def bounded(name, default, low, high):
        return max(low, min(high, int(os.environ.get(name, str(default)))))

    return {
        "files": bounded("RUNNER_CHECKOUT_MAX_FILES", 500, 1, 500),
        "bytes": bounded("RUNNER_CHECKOUT_MAX_BYTES", 5000000, 1024, 5000000),
        "timeout": bounded("RUNNER_CHECKOUT_TIMEOUT", 90, 1, 180),
        "ttl": bounded("RUNNER_CHECKOUT_TTL", 3600, 60, 86400),
        "retained": bounded("RUNNER_CHECKOUT_MAX_RETAINED", 8, 1, 64),
    }


def safe_name(name):
    RunInput(job_id=UUID(int=1), suite="python-unittest", files={name: ""})
    for segment in name.split("/"):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.@()+ -]{1,120}", segment)
            or segment.rstrip(" .") != segment
            or segment.split(".")[0].upper()
            in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}
        ):
            raise ValueError("Unsafe repository filename")


async def acquire(data):
    policy = limits()
    if ".." in data.branch or data.branch.endswith(("/", ".")) or "//" in data.branch:
        raise ValueError("Invalid branch/ref")
    github = ScopedCheckoutReader(data.repository)
    from urllib.parse import quote

    ref = await github.request("GET", "git/ref/heads/" + quote(data.branch, safe=""))
    if ref.get("object", {}).get("sha") != data.commit:
        raise ValueError("Branch moved; import and approve a fresh immutable commit")
    commit = await github.request("GET", "git/commits/" + data.commit)
    tree = commit.get("tree", {}).get("sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", tree):
        raise ValueError("Invalid commit tree")
    listing = await github.request("GET", "git/trees/" + tree + "?recursive=1")
    if listing.get("truncated"):
        raise ValueError("Repository tree exceeds safe discovery limits")
    blobs, seen, size = [], set(), 0
    for item in listing["tree"]:
        name = item["path"]
        safe_name(name)
        folded = name.lower()
        if folded in seen:
            raise ValueError("Duplicate or case-colliding repository paths")
        seen.add(folded)
        if item["type"] == "tree":
            continue
        if item["type"] != "blob" or item["mode"] not in {"100644", "100755"}:
            raise ValueError("Links, submodules and special repository files are forbidden")
        if not re.fullmatch(r"[a-f0-9]{40}", item["sha"]) or not 0 <= item.get("size", -1) <= 1000000:
            raise ValueError("Invalid or oversized repository blob")
        size += item["size"]
        blobs.append(item)
        if len(blobs) > policy["files"] or size > policy["bytes"]:
            raise ValueError("Repository exceeds configured file/size limits")
    parallel = asyncio.Semaphore(8)

    async def read(item):
        async with parallel:
            blob = await github.request("GET", "git/blobs/" + item["sha"])
            if blob.get("encoding") != "base64":
                raise ValueError("Invalid GitHub blob encoding")
            raw = base64.b64decode("".join(blob["content"].split()), validate=True)
            if (
                len(raw) != item["size"]
                or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != item["sha"]
            ):
                raise ValueError("GitHub blob identity mismatch")
            text = raw.decode("utf-8")
            from .security import redact

            if "\0" in text or redact(text) != text:
                raise ValueError("Binary or potentially sensitive source requires a separate template")
            return item["path"], text

    files = dict(await asyncio.gather(*(read(item) for item in blobs)))
    RunInput(job_id=data.job_id, suite="python-unittest", files=files)
    return files


def receipt_path(root, identity):
    return root / "checkout-results" / (str(UUID(str(identity))) + ".json")


def source_path(root, identity):
    path = root / "checkouts" / str(UUID(str(identity)))
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Unsafe checkout storage")
    return path


def store(root, identity, value):
    path = receipt_path(root, identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def cleanup(root, identity):
    path = source_path(root, identity)
    if path.exists():
        for entry in [path, *path.rglob("*")]:
            if entry.is_symlink():
                raise ValueError("Checkout integrity changed")
            entry.chmod(0o700 if entry.is_dir() else 0o600)
        shutil.rmtree(path)


def get(root, identity, org_id, project_id):
    path = receipt_path(root, identity)
    if not path.is_file():
        raise HTTPException(404, "Checkout not found")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["org_id"] != str(org_id) or value["project_id"] != str(project_id):
        raise HTTPException(404, "Checkout not found")
    if value["status"] == "ready" and value["expires_at"] <= time.time():
        cleanup(root, identity)
        value["status"] = "expired"
        store(root, identity, value)
    return value


def files(root, value):
    if value["status"] != "ready":
        raise ValueError("Checkout is unavailable; request a fresh checkout")
    source = source_path(root, value["job_id"])
    if {entry.relative_to(source).as_posix() for entry in source.rglob("*") if entry.is_file()} != set(
        value["file_hashes"]
    ):
        raise ValueError("Checkout integrity changed")
    result = {}
    for name, expected in value["file_hashes"].items():
        path = source.joinpath(*name.split("/"))
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or not path.is_file():
            raise ValueError("Checkout integrity changed")
        safe_name(name)
        if path.stat().st_size > 1000000:
            raise ValueError("Checkout integrity changed")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Checkout integrity changed")
        result[name] = raw.decode("utf-8")
    return result


def recover(root):
    for path in (root / "checkout-results").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["status"] == "fetching" or value.get("expires_at", 0) <= time.time():
            cleanup(root, path.stem)
            value["status"] = "interrupted" if value["status"] == "fetching" else "expired"
            store(root, path.stem, value)


def expire_sources(root):
    retained = 0
    for path in (root / "checkout-results").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["status"] == "ready" and value["expires_at"] <= time.time():
            cleanup(root, path.stem)
            value["status"] = "expired"
            store(root, path.stem, value)
        retained += value["status"] in {"ready", "fetching"}
        if value["status"] not in {"ready", "fetching"} and time.time() - value["created_at"] > 604800:
            path.unlink()
    return retained


async def checkout(root, data):
    identity = str(data.job_id)
    existing = receipt_path(root, identity)
    if existing.exists():
        saved = get(root, identity, data.org_id, data.project_id)
        if any(saved[key] != val for key, val in data.model_dump(mode="json").items()):
            raise HTTPException(409, "Checkout request scope conflict")
        return saved
    if expire_sources(root) >= limits()["retained"]:
        raise HTTPException(429, "Temporary checkout capacity reached; clean up an existing checkout")
    value = {
        **data.model_dump(mode="json"),
        "status": "fetching",
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + limits()["ttl"],
    }
    store(root, identity, value)
    try:
        snapshot = await asyncio.wait_for(acquire(data), timeout=limits()["timeout"])
        source = source_path(root, identity)
        source.mkdir(parents=True, exist_ok=False)
        for name, content in snapshot.items():
            path = source.joinpath(*name.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.encode())
            path.chmod(0o400)
        for path in [source, *[entry for entry in source.rglob("*") if entry.is_dir()]]:
            path.chmod(0o500)
        hashes = {name: hashlib.sha256(content.encode()).hexdigest() for name, content in snapshot.items()}
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        value.update(
            status="ready",
            file_count=len(snapshot),
            bytes=sum(len(text.encode()) for text in snapshot.values()),
            file_hashes=hashes,
            source_digest=digest,
            checked_out_at=int(time.time()),
            execution="Not executed; separate exact owner approval required",
            method="commit-pinned GitHub tree/blob snapshot; no Git hooks or repository commands",
        )
    except (Exception, asyncio.CancelledError) as exc:
        cleanup(root, identity)
        value.update(
            status="failed",
            error="Scoped GitHub credential required"
            if "credential is not configured" in str(exc)
            else "Checkout failed: missing repository/ref, moved commit, unsafe source, size or time limit",
        )
    store(root, identity, value)
    return value
