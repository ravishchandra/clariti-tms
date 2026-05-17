from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.keys import KeyRead, KeyUpdate
from app.api.v1.schemas.translations import TranslationRead
from app.models import Key, Translation, TranslationStatus

router = APIRouter()


@router.get("")
async def list_keys(
    db: DB,
    _auth: CurrentKey,
    project_id: uuid.UUID = Query(...),
    repository_id: Optional[uuid.UUID] = Query(None),
    locale: Optional[str] = Query(None),
    status: Optional[TranslationStatus] = Query(None),
    component: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(Key).where(Key.project_id == project_id, Key.is_active.is_(True))

    if repository_id is not None:
        q = q.where(Key.repository_id == repository_id)

    if component is not None:
        q = q.where(Key.component == component)

    # When filtering by translation status we need a join. A missing translation
    # row means the key has no translation for that locale yet.
    if locale is not None and status is not None:
        q = q.join(Translation, (Translation.key_id == Key.id) & (Translation.locale == locale))
        q = q.where(Translation.status == status)
    elif locale is not None:
        q = q.join(Translation, (Translation.key_id == Key.id) & (Translation.locale == locale))
    elif status is not None:
        # status filter without locale is ambiguous — require locale; raise early.
        raise HTTPException(status_code=422, detail="'status' filter requires 'locale'")

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total: int = total_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = await db.execute(q)
    keys = rows.scalars().all()

    return {"items": [KeyRead.model_validate(k) for k in keys], "total": total}


@router.get("/{key_id}")
async def get_key(
    key_id: uuid.UUID,
    db: DB,
    _auth: CurrentKey,
) -> dict[str, Any]:
    result = await db.execute(
        select(Key).options(selectinload(Key.translations)).where(Key.id == key_id)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")

    return {
        **KeyRead.model_validate(key).model_dump(),
        "translations": [TranslationRead.model_validate(t) for t in key.translations],
    }


@router.patch("/{key_id}", response_model=KeyRead)
async def update_key(
    key_id: uuid.UUID,
    body: KeyUpdate,
    db: DB,
    _auth: CurrentKey,
) -> KeyRead:
    result = await db.execute(select(Key).where(Key.id == key_id))
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")

    patch = body.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(key, field, value)

    await db.commit()
    await db.refresh(key)
    return KeyRead.model_validate(key)
