from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentKey, ScopedBatch, assert_project_in_org
from app.api.v1.schemas.batches import BatchRead, BatchTrigger
from app.models import BatchStatus, Translation, TranslationBatch, TranslationStatus
from app.mt.transitions import IllegalTransitionError, apply_transition

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_batches(
    db: DB,
    current_key: CurrentKey,
    project_id: uuid.UUID = Query(...),
    locale: str | None = Query(None),
    status: BatchStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    # Org-scope by the project filter — a cross-tenant project returns 404.
    await assert_project_in_org(project_id, db, current_key)

    q = select(TranslationBatch).where(TranslationBatch.project_id == project_id)

    if locale is not None:
        q = q.where(TranslationBatch.locale == locale)
    if status is not None:
        q = q.where(TranslationBatch.status == status)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total: int = total_result.scalar_one()

    q = q.order_by(TranslationBatch.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = await db.execute(q)
    batches = rows.scalars().all()

    return {"items": [BatchRead.model_validate(b) for b in batches], "total": total}


@router.get("/{batch_id}")
async def get_batch(batch: ScopedBatch, db: DB) -> dict[str, Any]:
    stats_result = await db.execute(
        select(Translation.status, func.count(Translation.id))
        .where(Translation.batch_id == batch.id)
        .group_by(Translation.status)
    )
    status_counts: dict[str, int] = {row[0]: row[1] for row in stats_result.all()}

    total_keys = sum(status_counts.values())
    translated = sum(v for k, v in status_counts.items() if k != TranslationStatus.draft)
    approved = status_counts.get(TranslationStatus.approved, 0)
    needs_review = status_counts.get(TranslationStatus.needs_review, 0)

    return {
        **BatchRead.model_validate(batch).model_dump(),
        "stats": {
            "total_keys": total_keys,
            "translated": translated,
            "approved": approved,
            "needs_review": needs_review,
        },
    }


@router.post("/{batch_id}/trigger-mt")
async def trigger_mt(
    body: BatchTrigger,
    db: DB,
    batch: ScopedBatch,
) -> dict[str, Any]:
    if batch.status == BatchStatus.mt_running:
        raise HTTPException(status_code=409, detail="MT is already running for this batch")

    batch.status = BatchStatus.pending
    await db.commit()
    await db.refresh(batch)

    return {"batch_id": str(batch.id), "status": batch.status, "provider": body.provider}


@router.post("/{batch_id}/approve")
async def approve_batch(batch: ScopedBatch, db: DB) -> dict[str, Any]:
    rows = await db.execute(
        select(Translation).where(
            Translation.batch_id == batch.id,
            Translation.status == TranslationStatus.needs_review,
        )
    )
    translations = rows.scalars().all()

    approved_count = 0
    skipped_count = 0
    for t in translations:
        try:
            apply_transition(t, TranslationStatus.approved, reviewer_action="accept")
            approved_count += 1
        except IllegalTransitionError as exc:
            # Pre-filtered by status == needs_review, so an IllegalTransition
            # here means the row changed between SELECT and the transition
            # (concurrent write). Log loudly and continue — better partial
            # success than a 500 that loses the rest of the batch.
            skipped_count += 1
            logger.warning(
                "batch.approve.skipped_illegal_transition",
                extra={
                    "translation_id": str(t.id),
                    "batch_id": str(batch.id),
                    "transition_error": str(exc),
                },
            )

    batch.status = BatchStatus.approved
    await db.commit()

    return {
        "batch_id": str(batch.id),
        "approved": approved_count,
        "skipped": skipped_count,
    }


@router.post("/{batch_id}/reject")
async def reject_batch(batch: ScopedBatch, db: DB) -> dict[str, Any]:
    rows = await db.execute(
        select(Translation).where(
            Translation.batch_id == batch.id,
            Translation.status == TranslationStatus.needs_review,
        )
    )
    translations = rows.scalars().all()

    rejected_count = 0
    skipped_count = 0
    for t in translations:
        try:
            apply_transition(t, TranslationStatus.rejected, reviewer_action="reject")
            rejected_count += 1
        except IllegalTransitionError as exc:
            skipped_count += 1
            logger.warning(
                "batch.reject.skipped_illegal_transition",
                extra={
                    "translation_id": str(t.id),
                    "batch_id": str(batch.id),
                    "transition_error": str(exc),
                },
            )

    # BatchStatus has no explicit "rejected" value; revert to pending so the batch
    # can be re-triggered after the reviewer rejects its translations.
    batch.status = BatchStatus.pending
    await db.commit()

    return {
        "batch_id": str(batch.id),
        "rejected": rejected_count,
        "skipped": skipped_count,
    }
