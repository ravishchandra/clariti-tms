from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentKey, ScopedTranslation, assert_project_in_org
from app.api.v1.schemas.translations import (
    TranslationHistoryRead,
    TranslationRead,
    TranslationUpdate,
)
from app.models import Key, Translation, TranslationHistory, TranslationStatus
from app.mt.transitions import (
    ALLOWED_REVIEWER_ACTIONS,
    IllegalTransitionError,
    InvalidReviewerActionError,
    apply_transition,
)

router = APIRouter()


@router.get("")
async def list_translations(
    db: DB,
    current_key: CurrentKey,
    project_id: uuid.UUID = Query(...),
    locale: str | None = Query(None),
    status: TranslationStatus | None = Query(None),
    key_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    # Org-scope by the project filter: a project belonging to a different org
    # returns 404 (same as a non-existent project).
    await assert_project_in_org(project_id, db, current_key)

    q = select(Translation).join(Key, Key.id == Translation.key_id).where(Key.project_id == project_id)

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
async def get_translation(translation: ScopedTranslation) -> TranslationRead:
    return TranslationRead.model_validate(translation)


@router.patch("/{translation_id}", response_model=TranslationRead)
async def update_translation(
    body: TranslationUpdate,
    db: DB,
    translation: ScopedTranslation,
) -> TranslationRead:
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
            if reviewer_action not in ALLOWED_REVIEWER_ACTIONS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"reviewer_action={reviewer_action!r} is not allowed. Valid: {sorted(ALLOWED_REVIEWER_ACTIONS)}"
                    ),
                )
            translation.reviewer_action = reviewer_action
        if reviewer_notes is not None:
            translation.reviewer_notes = reviewer_notes

    await db.commit()
    await db.refresh(translation)
    return TranslationRead.model_validate(translation)


@router.get("/{translation_id}/history", response_model=dict)
async def get_translation_history(
    db: DB,
    translation: ScopedTranslation,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Return the audit-log entries for a translation, newest first.

    Powers the Phase 6 key-detail page's history timeline. Rows are written
    automatically by the Postgres `record_translation_history()` trigger;
    the application never inserts here. Tenant scoping reuses
    `ScopedTranslation` so cross-org access returns 404 before any history
    leaks.
    """
    rows = await db.execute(
        select(TranslationHistory)
        .where(TranslationHistory.translation_id == translation.id)
        .order_by(TranslationHistory.changed_at.desc())
        .limit(limit)
    )
    items = [TranslationHistoryRead.model_validate(r) for r in rows.scalars().all()]
    return {"items": items, "total": len(items)}
