from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentKey, DB
from app.core.settings import get_settings
from app.models import Repository
from app.publication.service import publish_repository

router = APIRouter()


@router.post("/repositories/{repo_id}/publish")
async def trigger_publication(repo_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repository = result.scalar_one_or_none()
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    if not repository.github_repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Repository has no GitHub integration configured",
        )

    # TODO: load per-installation token from GitHub App credentials
    settings = get_settings()
    github_token = settings.GITHUB_WEBHOOK_SECRET  # TODO: replace with proper installation token

    pr_url = await publish_repository(db, repository, github_token)
    if pr_url is None:
        return {"status": "no_op", "pr_url": None, "detail": "No approved translations to publish"}

    return {"status": "ok", "pr_url": pr_url}
