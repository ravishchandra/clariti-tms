from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, ScopedRepository
from app.core.settings import get_settings
from app.publication.service import publish_repository

router = APIRouter()


@router.post("/repositories/{repo_id}/publish")
async def trigger_publication(db: DB, repository: ScopedRepository) -> dict:
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
