"""Owner-approved GitHub Git-data publication. Credentials never enter a worktree/runner/model."""

import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx
from sqlalchemy import select

from . import models as m
from .config import settings
from .db import now, uid
from .repositories import SECRET_NAMES, git
from .security import audit, check_agent, clean, digest
from .staffing import lock_org
from .workflows import project_authority


class PublicationError(ValueError):
    pass


class GitHub:
    def __init__(self, repository, client=None):
        allowed = {name.strip().lower() for name in settings().github_publication_repositories.split(",")}
        self.token = os.environ.get(settings().github_publication_token_env, "")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", repository)
            or repository.lower() not in allowed
        ):
            raise PublicationError("Repository is not enabled for generated draft publication")
        if not self.token:
            raise PublicationError("Scoped GitHub publication credential is not configured")
        self.repository, self.client = repository, client

    async def request(self, method, path, body=None, missing=False):
        client = self.client or httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
        try:
            async with client.stream(
                method,
                f"https://api.github.com/repos/{self.repository}" + ("/" + path if path else ""),
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
                json=body,
            ) as response:
                if missing and response.status_code == 404:
                    return None
                if not 200 <= response.status_code < 300:
                    raise PublicationError(f"GitHub HTTP {response.status_code}; reconcile before retrying")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise PublicationError("GitHub response exceeded limits")
                return json.loads(data)
        except (httpx.HTTPError, json.JSONDecodeError):
            raise PublicationError("GitHub response unavailable; reconcile before retrying") from None
        finally:
            if self.client is None:
                await client.aclose()


def candidate(session, task, *, nonproduction=False):
    """Default is strict publication. Only mock delivery uses the nonproduction path.

    That path accepts explicit fixture models but retains exact authority, Git
    integrity and dedicated Docker QA. Its package can never pass release.
    """
    from .engineering import passed_tests

    project = session.get(m.Project, task.project_id)
    project_authority(session, project)
    check_agent(session, session.get(m.Agent, task.assigned_agent_id), "read_context", project)
    approval = session.scalar(
        select(m.Approval).where(
            m.Approval.category == "repository_change",
            m.Approval.subject_id == task.id,
            m.Approval.org_id == task.org_id,
            m.Approval.version == task.version,
        )
    )
    evidence, draft = task.evidence, task.evidence.get("pull_request", {})
    execution_id = evidence.get("execution_id")
    execution = session.get(m.Execution, execution_id) if execution_id else None
    if (
        task.kind != "coding"
        or task.status != "completed"
        or task.payload.get("mode") != ("mock" if nonproduction else "live")
        or not approval
        or approval.expires_at <= now()
        or approval.subject_hash != digest(task.payload)
        or not evidence.get("reviewer_approved")
        or not evidence.get("reviews")
        or not execution
        or execution.task_id != task.id
        or execution.org_id != task.org_id
        or execution.status != "completed"
        or execution.exit_code != 0
        or evidence.get("build_exit_code") != 0
        or execution.agent_id == task.assigned_agent_id
        or evidence.get("runner_job_id") != execution.id
        or "dedicated Docker" not in execution.environment
        or not passed_tests(
            {
                "exit_code": execution.exit_code,
                "logs": execution.logs,
                "build": {"exit_code": evidence.get("build_exit_code")},
            },
            task.payload.get("test_suite", ""),
        )
    ):
        raise PublicationError(
            ("Completed nonproduction coding" if nonproduction else "Completed live coding")
            + ", exact scope, independent review and successful dedicated Docker QA/build are required"
        )
    for review in evidence["reviews"]:
        run = session.get(m.ModelRun, review["review_run_id"])
        author = session.get(m.ModelRun, review.get("author_run_id"))
        if (
            not run
            or run.org_id != task.org_id
            or run.task_id != task.id
            or run.status != "succeeded"
            or run.agent_id == task.assigned_agent_id
            or run.response.get("approved") is not True
            or not author
            or author.status != "succeeded"
            or author.agent_id != task.assigned_agent_id
            or author.task_id != task.id
            or author.org_id != task.org_id
            or not review.get("approved")
        ):
            raise PublicationError("Independent review evidence is invalid")
        for model_run in (run, author):
            model = session.get(m.ModelConfig, model_run.model_id)
            provider = session.get(m.Provider, model.provider_id) if model else None
            if not provider or (provider.kind == "mock" and not nonproduction):
                raise PublicationError("Deterministic reviews cannot authorize live publication")
            if nonproduction and provider.kind != "mock":
                raise PublicationError(
                    "Nonproduction fixture packaging requires explicit deterministic models"
                )
    root = settings().repository_root.resolve()
    requested = root / ".worktrees" / project.id / task.id
    if any(
        path.is_symlink() or path.is_junction()
        for path in (requested, *requested.parents)
        if path.is_relative_to(root)
    ):
        raise PublicationError("Linked workspaces cannot authorize publication")
    workspace = requested.resolve()
    if (
        not workspace.is_relative_to(root)
        or not workspace.is_dir()
        or workspace.is_symlink()
        or workspace.is_junction()
    ):
        raise PublicationError("Prepared workspace unavailable")
    if git(workspace, "status", "--porcelain") or git(workspace, "rev-parse", "HEAD") != draft.get(
        "head_commit"
    ):
        raise PublicationError("Prepared candidate changed after verification")
    tree = git(workspace, "rev-parse", "HEAD^{tree}")
    if tree != evidence.get("candidate_tree"):
        raise PublicationError("Candidate tree no longer matches independent QA")
    base, head = draft.get("base_commit", ""), draft.get("head_commit", "")
    if not re.fullmatch(r"[a-f0-9]{40}", base) or not re.fullmatch(r"[a-f0-9]{40}", head):
        raise PublicationError("SHA-1 base and head commits are required")
    diff = git(workspace, "diff", "--no-ext-diff", "--no-textconv", base, head)
    if not diff or len(diff.encode()) > 200000 or clean(diff) != diff:
        raise PublicationError("Diff empty, too large or contains sensitive material")
    return workspace, project, draft, tree, diff


def changes(workspace, base, head):
    paths = git(workspace, "diff", "--name-only", "-z", base, head, raw=True).decode("utf-8").split("\0")
    tree = {}
    for line in git(workspace, "ls-tree", "-r", "-z", head, raw=True).decode("utf-8").split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            mode, kind, sha = meta.split()
            tree[path] = (mode, kind, sha)
    result = []
    for path in filter(None, paths):
        parts = PurePosixPath(path).parts
        if (
            PurePosixPath(path).is_absolute()
            or any(p.lower() in {"..", ".git", ".github"} or p.lower().startswith(".env") for p in parts)
            or any(p.lower() in SECRET_NAMES for p in parts)
            or PurePosixPath(path).suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
        ):
            raise PublicationError("Publication path outside permitted source scope")
        if path not in tree:
            result.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        else:
            mode, kind, sha = tree[path]
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise PublicationError("Symlinks/submodules are not authorized for publication")
            content = git(workspace, "cat-file", "blob", sha, raw=True)
            if len(content) > 200000:
                raise PublicationError("Publication file exceeded limits")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                raise PublicationError("Only UTF-8 source files are authorized for publication") from None
            if "\0" in text or clean(text) != text:
                raise PublicationError("Binary or sensitive source files cannot be published")
            result.append({"path": path, "mode": mode, "type": "blob", "sha": sha})
    if not result or len(result) > 32:
        raise PublicationError("Publication must contain 1 to 32 changed paths")
    return result


def commit_spec(tree, base, record_id, task_id, local_head, timestamp):
    message = f"Aiventra approved task {task_id}\n\nSource commit: {local_head}\nPublication: {record_id}\n"
    name, email = "Aiventra approved publication", "aiventra@local.invalid"
    raw = f"tree {tree}\nparent {base}\nauthor {name} <{email}> {timestamp} +0000\ncommitter {name} <{email}> {timestamp} +0000\n\n{message}".encode()
    sha = hashlib.sha1(f"commit {len(raw)}\0".encode() + raw).hexdigest()
    person = {
        "name": name,
        "email": email,
        "date": datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return sha, {"message": message, "tree": tree, "parents": [base], "author": person, "committer": person}


async def preview(session, task, repository, base_ref, user, client=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]{0,99}", base_ref):
        raise PublicationError("Unsupported base branch name")
    workspace, project, draft, tree, diff = candidate(session, task)
    entries = changes(workspace, draft["base_commit"], draft["head_commit"])
    github = GitHub(repository, client)
    session.commit()  # No SQLite transaction across GitHub calls.
    repo = await github.request("GET", "")
    if not repo.get("permissions", {}).get("push"):
        raise PublicationError("Publication credential cannot write this repository")
    remote = await github.request("GET", "git/ref/heads/" + quote(base_ref, safe=""))
    if remote["object"]["sha"] != draft["base_commit"]:
        raise PublicationError("Remote base moved; rebase and independently verify a new candidate")
    record_id, timestamp = uid(), now()
    remote_head, commit = commit_spec(
        tree, draft["base_commit"], record_id, task.id, draft["head_commit"], timestamp
    )
    manifest = {
        "repository": repository,
        "base_ref": base_ref,
        "base_commit": draft["base_commit"],
        "local_head": draft["head_commit"],
        "head_commit": remote_head,
        "tree": tree,
        "branch": "aiventra/" + task.id + "-" + record_id,
        "task_id": task.id,
        "task_version": task.version,
        "scope_hash": digest(task.payload),
        "evidence_hash": digest(task.evidence),
        "diff_hash": digest(diff),
        "diff": diff,
        "entries": entries,
        "commit": commit,
        "execution_id": task.evidence["execution_id"],
        "review_run_ids": draft["review_run_ids"],
        "title": draft["title"],
        "body": draft["body"],
        "mode": "live",
        "draft": True,
    }
    # Recheck after the read-only network preview before saving the exact approval target.
    lock_org(session, task.org_id)
    session.refresh(task)
    _, _, current, current_tree, current_diff = candidate(session, task)
    if (
        current["head_commit"] != manifest["local_head"]
        or current_tree != tree
        or digest(current_diff) != manifest["diff_hash"]
    ):
        raise PublicationError("Candidate changed while previewing")
    identity = (
        "repository",
        "base_ref",
        "base_commit",
        "local_head",
        "task_id",
        "task_version",
        "scope_hash",
        "evidence_hash",
    )
    for existing in session.scalars(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == task.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "github_publication",
        )
    ):
        previous = existing.data.get("manifest", {})
        if any(previous.get(key) != manifest[key] for key in identity):
            continue
        approval = session.scalar(
            select(m.Approval).where(
                m.Approval.org_id == task.org_id,
                m.Approval.category == "github_publication",
                m.Approval.subject_id == existing.id,
                m.Approval.version == existing.version,
            )
        )
        if (
            existing.status in {"publishing", "needs_reconciliation"}
            and approval
            and approval.expires_at <= now()
        ):
            raise PublicationError(
                "Uncertain publication has expired approval; manually reconcile its existing branch/PR before replacing it"
            )
        if existing.status == "published" or not approval or approval.expires_at > now():
            session.commit()
            return existing
    record = m.BusinessRecord(
        id=record_id,
        org_id=task.org_id,
        project_id=project.id,
        kind="github_publication",
        title=draft["title"],
        status="prepared",
        data={"manifest": manifest, "manifest_hash": digest(manifest)},
    )
    session.add(record)
    audit(
        session,
        task.org_id,
        user.id,
        "publication.prepared",
        record.id,
        {"manifest_hash": digest(manifest), "repository": repository},
        project_id=project.id,
        task_id=task.id,
    )
    session.commit()
    return record


def authorized(session, record):
    manifest = record.data["manifest"]
    if digest(manifest) != record.data["manifest_hash"]:
        raise PublicationError("Publication manifest changed")
    approval = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == record.org_id,
            m.Approval.category == "github_publication",
            m.Approval.subject_id == record.id,
            m.Approval.version == record.version,
        )
    )
    if not approval or approval.expires_at <= now() or approval.subject_hash != record.data["manifest_hash"]:
        raise PublicationError("Current exact owner publication approval is required")
    return target(session, record)


def target(session, record):
    manifest = record.data["manifest"]
    if digest(manifest) != record.data["manifest_hash"]:
        raise PublicationError("Publication manifest changed")
    task = session.get(m.Task, manifest["task_id"])
    if (
        not task
        or task.org_id != record.org_id
        or task.project_id != record.project_id
        or task.version != manifest["task_version"]
        or digest(task.payload) != manifest["scope_hash"]
        or digest(task.evidence) != manifest["evidence_hash"]
    ):
        raise PublicationError("Approved task changed")
    workspace, _, draft, tree, diff = candidate(session, task)
    if (
        draft["head_commit"] != manifest["local_head"]
        or tree != manifest["tree"]
        or digest(diff) != manifest["diff_hash"]
    ):
        raise PublicationError("Approved publication candidate changed")
    return workspace, manifest


async def publish(session, record, user, client=None):
    lock_org(session, record.org_id)
    session.refresh(record)
    if record.status == "published":
        return record
    if record.status == "publishing" and record.data.get("lease_until", 0) > now():
        raise PublicationError("Publication in progress; reconcile after the current lease")
    workspace, manifest = authorized(session, record)
    github = GitHub(manifest["repository"], client)
    lease = uid()
    record.status, record.data = (
        "publishing",
        {**record.data, "lease_until": now() + 300, "lease_token": lease},
    )
    session.commit()

    def fence():
        session.refresh(record)
        if record.status != "publishing" or record.data.get("lease_token") != lease:
            raise PublicationError("Publication lease changed")
        authorized(session, record)
        if GitHub(manifest["repository"]).token != github.token:
            raise PublicationError("Publication credential changed")
        record.data = {**record.data, "lease_until": now() + 300}
        session.commit()

    try:
        remote = await github.request("GET", "git/ref/heads/" + quote(manifest["base_ref"], safe=""))
        if remote["object"]["sha"] != manifest["base_commit"]:
            raise PublicationError("Remote base moved; new independent verification required")
        branch = await github.request(
            "GET", "git/ref/heads/" + quote(manifest["branch"], safe=""), missing=True
        )
        if branch and branch["object"]["sha"] != manifest["head_commit"]:
            raise PublicationError("Remote branch conflict; force push is prohibited")
        if not branch:
            for entry in manifest["entries"]:
                if entry["sha"]:
                    fence()
                    data = git(workspace, "cat-file", "blob", entry["sha"], raw=True)
                    blob = await github.request(
                        "POST",
                        "git/blobs",
                        {"encoding": "base64", "content": base64.b64encode(data).decode()},
                    )
                    if blob["sha"] != entry["sha"]:
                        raise PublicationError("GitHub blob differs from approved content")
            fence()
            base = await github.request("GET", "git/commits/" + manifest["base_commit"])
            tree = await github.request(
                "POST", "git/trees", {"base_tree": base["tree"]["sha"], "tree": manifest["entries"]}
            )
            if tree["sha"] != manifest["tree"]:
                raise PublicationError("GitHub tree differs from approved candidate")
            fence()
            commit = await github.request("POST", "git/commits", manifest["commit"])
            if commit["sha"] != manifest["head_commit"]:
                raise PublicationError("GitHub commit differs from exact approved head; no branch published")
            fence()
            await github.request(
                "POST",
                "git/refs",
                {"ref": "refs/heads/" + manifest["branch"], "sha": manifest["head_commit"]},
            )
        fence()
        pulls = await github.request(
            "GET",
            "pulls?state=all&per_page=100&head="
            + quote(manifest["repository"].split("/")[0] + ":" + manifest["branch"], safe=""),
        )
        pull = next(
            (
                p
                for p in pulls
                if p.get("head", {}).get("sha") == manifest["head_commit"]
                and p.get("base", {}).get("ref") == manifest["base_ref"]
            ),
            None,
        )
        if pull is None:
            fence()
            pull = await github.request(
                "POST",
                "pulls",
                {
                    "title": manifest["title"],
                    "body": manifest["body"] + "\n\nPublication approval: " + record.data["manifest_hash"],
                    "head": manifest["branch"],
                    "base": manifest["base_ref"],
                    "draft": True,
                },
            )
        expected = f"https://github.com/{manifest['repository']}/pull/{pull['number']}"
        if (
            pull.get("html_url") != expected
            or pull.get("head", {}).get("sha") != manifest["head_commit"]
            or pull.get("draft") is not True
            or pull.get("state") != "open"
            or pull.get("base", {}).get("sha") != manifest["base_commit"]
        ):
            raise PublicationError("Remote pull request does not match an open approved draft")
        fence()
        record.status = "published"
        record.data = {
            **record.data,
            "lease_until": 0,
            "url": expected,
            "number": pull["number"],
            "error": "",
        }
        audit(
            session,
            record.org_id,
            user.id,
            "publication.published",
            record.id,
            {"url": expected, "head_commit": manifest["head_commit"]},
            project_id=record.project_id,
        )
        session.commit()
    except (ValueError, PermissionError, KeyError, TypeError) as exc:
        session.rollback()
        session.refresh(record)
        if record.data.get("lease_token") != lease:
            raise PublicationError("Publication lease changed; current operation must reconcile") from None
        record.status = "needs_reconciliation"
        record.data = {
            **record.data,
            "lease_until": 0,
            "error": clean(str(exc))[:1000]
            if isinstance(exc, (PublicationError, PermissionError))
            else "Local or remote publication verification failed; reconcile before retrying",
        }
        audit(
            session,
            record.org_id,
            user.id,
            "publication.reconciliation_required",
            record.id,
            project_id=record.project_id,
        )
        session.commit()
        raise PublicationError(record.data["error"]) from None
    return record


async def feedback(session, record, user, client=None):
    if record.status != "published":
        raise PublicationError("A verified published draft is required")
    manifest = record.data["manifest"]
    github = GitHub(manifest["repository"], client)
    session.commit()
    pull = await github.request("GET", f"pulls/{record.data['number']}")
    if pull["head"]["sha"] != manifest["head_commit"]:
        raise PublicationError("Remote head changed; feedback cannot be attributed to the approved commit")
    checks = await github.request("GET", f"commits/{manifest['head_commit']}/check-runs?per_page=100")
    status = await github.request("GET", f"commits/{manifest['head_commit']}/status?per_page=100")
    reviews = await github.request("GET", f"pulls/{record.data['number']}/reviews?per_page=100")
    comments = await github.request("GET", f"pulls/{record.data['number']}/comments?per_page=100")
    evidence = clean(
        {
            "head_commit": manifest["head_commit"],
            "checked_at": now(),
            "checks": [
                {k: r.get(k) for k in ("id", "name", "status", "conclusion")}
                for r in checks.get("check_runs", [])[:100]
            ],
            "status": status.get("state"),
            "reviews": [{k: r.get(k) for k in ("id", "state", "body", "commit_id")} for r in reviews[:100]],
            "comments": [
                {k: r.get(k) for k in ("id", "path", "line", "body", "commit_id")} for r in comments[:100]
            ],
            "partial": bool(
                checks.get("total_count", 0) > 100
                or len(reviews) >= 100
                or len(comments) >= 100
                or len(status.get("statuses", [])) >= 100
            ),
        }
    )
    session.refresh(record)
    record.data = {**record.data, "feedback": evidence, "feedback_hash": digest(evidence)}
    audit(
        session,
        record.org_id,
        user.id,
        "publication.feedback_checked",
        record.id,
        {"head_commit": manifest["head_commit"], "feedback_hash": digest(evidence)},
        project_id=record.project_id,
    )
    session.commit()
    return record


def repair(session, record, user, request_id, feedback_hash, objective):
    """Create at most two follow-up scopes; owner must approve each before any execution."""
    lock_org(session, record.org_id)
    session.refresh(record)
    manifest = record.data["manifest"]
    request_hash = digest({"publication": record.id, "feedback_hash": feedback_hash, "objective": objective})
    existing = session.get(m.Task, request_id)
    if existing:
        if existing.org_id != record.org_id or existing.payload.get("repair_request_hash") != request_hash:
            raise PublicationError("Repair request ID already used for another scope")
        return existing
    saved = record.data.get("feedback", {})
    requests = record.data.get("repair_requests", [])
    if (
        record.status != "published"
        or record.data.get("feedback_hash") != feedback_hash
        or not saved
        or now() - saved["checked_at"] > 3600
        or saved.get("partial")
        or len(requests) >= 2
    ):
        raise PublicationError(
            "Fresh complete exact feedback and fewer than two repair requests are required"
        )
    source = session.get(m.Task, manifest["task_id"])
    target(session, record)
    feedback_text = json.dumps(saved, ensure_ascii=False)[:6000]
    task = m.Task(
        id=request_id,
        org_id=source.org_id,
        project_id=source.project_id,
        assigned_agent_id=source.assigned_agent_id,
        kind="coding",
        status="awaiting_approval",
        objective=clean(objective),
        acceptance=list(source.acceptance),
        budget_micro=source.budget_micro,
        payload={
            "repository_id": source.payload["repository_id"],
            "baseline_commit": manifest["local_head"],
            "objective": clean(objective),
            "test_suite": source.payload["test_suite"],
            "mode": "live",
            "review_policy": source.payload.get("review_policy", "require_model"),
            "review_count": source.payload.get("review_count", 1),
            "repair_limit": min(source.payload.get("repair_limit", 1), 2),
            "publication_id": record.id,
            "feedback_hash": feedback_hash,
            "feedback": clean(feedback_text),
            "repair_request_hash": request_hash,
            "publication_repair_round": len(requests) + 1,
        },
    )
    session.add(task)
    session.add(m.Budget(org_id=source.org_id, scope=f"task:{task.id}", limit_micro=task.budget_micro))
    record.data = {**record.data, "repair_requests": [*requests, task.id]}
    audit(
        session,
        record.org_id,
        user.id,
        "publication.repair_scope_requested",
        record.id,
        {"task_id": task.id, "round": len(requests) + 1, "feedback_hash": feedback_hash},
        project_id=record.project_id,
    )
    session.commit()
    return task
