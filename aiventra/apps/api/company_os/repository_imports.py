"""Read-only, bounded GitHub metadata discovery through the existing scoped connector."""

import asyncio
import base64
import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from .publication import GitHub, PublicationError
from .repositories import SECRET_NAMES, SKIP
from .security import redact


def repository_name(value):
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.netloc != "github.com" or url.query or url.fragment:
            raise ValueError("Use an authorized github.com repository URL")
        value = url.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
        raise ValueError("Use an authorized owner/repository or HTTPS GitHub URL")
    return value


def safe_path(name):
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and ":" not in name
        and "\\" not in name
        and not any(part in SKIP for part in path.parts)
        and path.name not in SECRET_NAMES
        and not path.name.startswith(".env")
        and path.suffix.lower() not in {".pem", ".key", ".p12", ".pfx"}
    )


async def discover(repository, branch=None, client=None):
    repository = repository_name(repository)
    github = GitHub(repository, client)

    async def inspect():
        metadata = await github.request("GET", "")
        default = metadata["default_branch"]
        chosen = branch or default
        if (
            not isinstance(chosen, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,99}", chosen)
            or ".." in chosen
        ):
            raise ValueError("Invalid branch")
        branches = await github.request("GET", "branches?per_page=100")
        ref = await github.request("GET", "git/ref/heads/" + quote(chosen, safe=""))
        commit = ref["object"]["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("Invalid GitHub commit identity")
        snapshot = await github.request("GET", "git/commits/" + commit)
        tree_id = snapshot["tree"]["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", tree_id):
            raise ValueError("Invalid GitHub tree identity")
        tree = await github.request("GET", "git/trees/" + tree_id + "?recursive=1")
        entries = [
            item
            for item in tree["tree"][:3000]
            if item.get("type") == "blob" and item.get("mode") == "100644" and safe_path(item["path"])
        ]
        files = [item["path"] for item in entries]
        names = {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "cargo.toml",
            "go.mod",
            "compose.yaml",
            "readme.md",
        }
        documents, warnings = (
            {},
            ["Repository content is untrusted data; no execution or modification authorized"],
        )
        selected = [
            item
            for item in entries
            if PurePosixPath(item["path"]).name.lower() in names and item.get("size", 32769) <= 32768
        ][:8]
        total = 0
        for item in selected:
            sha = item["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("Invalid GitHub blob identity")
            blob = await github.request("GET", "git/blobs/" + sha)
            if blob.get("encoding") != "base64" or len(blob.get("content", "")) > 50000:
                raise ValueError("Invalid or oversized GitHub blob")
            raw = base64.b64decode("".join(blob["content"].split()), validate=True)
            total += len(raw)
            if (
                len(raw) > 32768
                or total > 131072
                or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest() != sha
            ):
                raise ValueError("GitHub blob integrity/size check failed")
            documents[item["path"]] = redact(raw.decode("utf-8"))[:12000]
        if tree.get("truncated") or len(tree["tree"]) > 3000:
            warnings.append("Source tree truncated; discovery is incomplete")
        if len(branches) == 100:
            warnings.append(
                "Branch list limited to the first 100 entries; an authorized branch can be entered explicitly"
            )
        stacks = sorted(
            {
                label
                for filename, label in {
                    "package.json": "JavaScript/TypeScript",
                    "pyproject.toml": "Python",
                    "requirements.txt": "Python",
                    "Cargo.toml": "Rust",
                    "go.mod": "Go",
                    "compose.yaml": "Docker Compose",
                }.items()
                if any(PurePosixPath(path).name == filename for path in files)
            }
        )
        return {
            "repository": repository,
            "url": "https://github.com/" + repository,
            "default_branch": default,
            "branch": chosen,
            "branches": [row["name"] for row in branches],
            "baseline_commit": commit,
            "tree_sha": tree_id,
            "files": files,
            "manifests": documents,
            "technology_stack": stacks,
            "test_files": [path for path in files if "test" in PurePosixPath(path).name.lower()][:300],
            "architecture_summary": "Deterministic source discovery; "
            + ", ".join(stacks or ["stack unknown"])
            + "; directories: "
            + ", ".join(
                sorted(
                    {PurePosixPath(path).parts[0] for path in files if len(PurePosixPath(path).parts) > 1}
                )[:20]
            ),
            "read_only": True,
            "remote_metadata_only": True,
            "baseline_tests": "Not executed; separate managed checkout and restricted runner approval required",
            "warnings": warnings,
        }

    try:
        return await asyncio.wait_for(inspect(), timeout=30)
    except (
        KeyError,
        TypeError,
        AttributeError,
        UnicodeDecodeError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        raise PublicationError(
            "GitHub repository discovery returned invalid data or exceeded limits"
        ) from exc
