import hashlib

from sqlalchemy.orm import Session

from .config import settings
from .db import uid
from .models import Artifact
from .security import redact


def save_artifact(
    session: Session,
    org_id: str,
    name: str,
    content: str,
    kind="document",
    project_id=None,
    task_id=None,
    agent_id=None,
    conversation_id=None,
) -> Artifact:
    content = redact(content)
    artifact = Artifact(
        id=uid(),
        org_id=org_id,
        project_id=project_id,
        conversation_id=conversation_id,
        task_id=task_id,
        agent_id=agent_id,
        name=name[:200],
        kind=kind,
        content=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
    )
    # Private database copy is authoritative. Files are addressed only by generated IDs.
    key = f"{org_id}/{artifact.id}.txt"
    path = settings().artifact_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    artifact.storage_key = key
    if settings().s3_bucket:
        import boto3

        boto3.client("s3", endpoint_url=settings().s3_endpoint or None).put_object(
            Bucket=settings().s3_bucket,
            Key=key,
            Body=content.encode(),
            ContentType="text/plain",
            ServerSideEncryption="AES256",
        )
    session.add(artifact)
    session.flush()
    return artifact
