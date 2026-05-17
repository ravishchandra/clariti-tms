from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentKey
from app.api.v1.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.models import ApiKey

router = APIRouter()


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(body: ApiKeyCreate, db: DB, current_key: CurrentKey) -> ApiKeyCreated:
    # The new key always inherits the caller's organization — body cannot escalate
    # cross-tenant. Newly minted keys are never org-admin; an org-admin must be
    # bootstrapped via `loc api-key` or the seed script.
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        key_hash=key_hash,
        name=body.name,
        organization_id=current_key.organization_id,
        is_org_admin=False,
    )
    db.add(api_key)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="API key conflict")
    await db.refresh(api_key)
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        organization_id=api_key.organization_id,
        is_active=api_key.is_active,
        is_org_admin=api_key.is_org_admin,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        raw_key=raw_key,
    )


@router.get("", response_model=dict)
async def list_api_keys(db: DB, current_key: CurrentKey) -> dict:
    result = await db.execute(
        select(ApiKey).where(ApiKey.organization_id == current_key.organization_id)
    )
    keys = result.scalars().all()
    return {"items": [ApiKeyRead.model_validate(k) for k in keys], "total": len(keys)}


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: uuid.UUID, db: DB, current_key: CurrentKey) -> None:
    # Org-scoped lookup: a key in another org returns 404, not 403, to avoid
    # leaking existence.
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == current_key.organization_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.is_active = False
    await db.flush()
