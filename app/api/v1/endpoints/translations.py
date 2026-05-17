from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentKey
from app.api.v1.schemas.translations import TranslationRead, TranslationUpdate
from app.models import Key, Translation, TranslationStatus
from app.mt.transitions import (
    IllegalTransitionError,
    InvalidReviewerActionError,
    apply_transition,
)

router = APIRouter()


@router.get("")
async def list_translations(
    db: DB,
    _auth: CurrentKey,
    project_id: uuid.UUID = Query(...),
    locale: str | None = Query(None),
    status: TranslationStatus | None = Query(None),
    key_id: uuid.UUID | None = Query(None),
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

    # H1: status changes go through the state-machine helper so illegal edges
    # (e.g. draft -> approved, published -> draft) return 422 instead of
    # silently corrupting workflow invariants.
    # H2: do NOT insert TranslationHistory here — the Postgres trigger
    # record_translation_history() on every UPDATE is the canonical audit path
    # (docs/04-data-model.md:427). The prior manual insert created duplicate
    # rows on every PATCH.
    new_status = patch.pop("status", None)
    reviewer_action = patch.pop("reviewer_action", None)
    reviewer_notes = patch.pop("reviewer_notes", None)

    for field, value in patch.items():
        setattr(translation, field, value)

    if new_status is not None:
        try:
            apply_transition(
                translation,
                new_status,
                reviewer_action=reviewer_action,
                reviewer_notes=reviewer_notes,
            )
        except IllegalTransitionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except InvalidReviewerActionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    else:
        # No status change, but the caller may still be setting reviewer
        # fields (leaving a note before approving, etc.). Validate the
        # reviewer_action whitelist here too — same check apply_transition
        # would apply.
        translation.updated_at = datetime.now(tz=UTC)
        if reviewer_action is not None:
            from app.mt.transitions import ALLOWED_REVIEWER_ACTIONS

            if reviewer_action not in ALLOWED_REVIEWER_ACTIONS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"reviewer_action={reviewer_action!r} is not allowed. "
                        f"Valid: {sorted(ALLOWED_REVIEWER_ACTIONS)}"
                    ),
                )
            translation.reviewer_action = reviewer_action
        if reviewer_notes is not None:
            translation.reviewer_notes = reviewer_notes

    await db.commit()
    await db.refresh(translation)
    return TranslationRead.model_validate(translation)
