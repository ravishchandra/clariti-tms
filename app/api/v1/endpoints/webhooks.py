from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/github")
async def github_webhook(request: Request) -> dict[str, str]:
    return {"status": "stub", "message": "GitHub webhook receiver — Phase 4"}


@router.post("/contentful")
async def contentful_webhook(request: Request) -> dict[str, str]:
    return {"status": "stub", "message": "Contentful webhook receiver — Phase 4"}
