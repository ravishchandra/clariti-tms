from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DB
from app.integrations.github.webhook import handle_github_push, verify_github_signature
from app.models import Repository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def receive_github_webhook(
    request: Request,
    db: DB,
    x_hub_signature_256: str | None = Header(None),
) -> dict:
    payload_bytes = await request.body()

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    full_name: str | None = payload.get("repository", {}).get("full_name")
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing repository.full_name")

    result = await db.execute(select(Repository).where(Repository.github_repo == full_name))
    repository = result.scalar_one_or_none()
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not registered")

    # Sanity: the resolved repository must have a project FK. NOT NULL enforces this
    # at the DB level, but assert here so any drift surfaces as a 500, not as
    # silently-misrouted writes against a foreign tenant.
    if repository.project_id is None:
        logger.error("github.webhook.repository_missing_project_id", extra={"repo_id": str(repository.id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Repository state inconsistent",
        )

    # TODO: decrypt webhook_secret_encrypted with Fernet before comparing
    secret = repository.webhook_secret_encrypted or ""
    if secret and not verify_github_signature(payload_bytes, x_hub_signature_256 or "", secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    await handle_github_push(db, payload, repository)
    return {"status": "ok"}
