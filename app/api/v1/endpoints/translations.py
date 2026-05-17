from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.translations import TranslationRead, TranslationUpdate
from app.models import Key, Translation, TranslationHistory, TranslationStatus

router = APIRouter()


@router.get("")
async def list_translations(
    db: DB,
    _auth: CurrentKey,
    project_id: uuid.UUID = Query(...),
    locale: Optional[str] = Query(None),
    status: Optional[TranslationStatus] = Query(None),
    key_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    q = (
        select(Translation)
        .join(Key, Key.id == Translation.key_id)
        .where(Key.project_id == project_id)
    )

    if locale is not None:
        q = q.where(Translation.locale == locale)
    if status is not None:
        q = q.where(Translation.status == status)
    if key_id is not None:
        q = q.where(Translation.key_id == key_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total: int = total_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = await db.execute(q)
    translations = rows.scalars().all()

    return {"items": [TranslationRead.model_validate(t) for t in translations], "total": total}


@router.get("/{translation_id}", response_model=TranslationRead)
async def get_translation(
    translation_id: uuid.UUID,
    db: DB,
    _auth: CurrentKey,
) -> TranslationRead:
    result = await db.execute(select(Translation).where(Translation.id == translation_id))
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(status_code=404, detail="Translation not found")
    return TranslationRead.model_validate(translation)


@router.patch("/{translation_id}", response_model=TranslationRead)
async def update_translation(
    translation_id: uuid.UUID,
    body: TranslationUpdate,
    db: DB,
    _auth: CurrentKey,
) -> TranslationRead:
    result = await db.execute(select(Translation).where(Translation.id == translation_id))
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(status_code=404, detail="Translation not found")

    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return TranslationRead.model_validate(translation)

    old_value = translation.value
    old_status = translation.status

    for field, value in patch.items():
        setattr(translation, field, value if not hasattr(value, "value") else value.value)

    translation.updated_at = datetime.now(tz=timezone.utc)

    history = TranslationHistory(
        translation_id=translation.id,
        prev_value=old_value,
        new_value=translation.value,
        prev_status=old_status,
        new_status=translation.status,
        change_source="api",
    )
    db.add(history)

    await db.commit()
    await db.refresh(translation)
    return TranslationRead.model_validate(translation)
