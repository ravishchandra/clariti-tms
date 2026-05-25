from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentKey, ScopedBatch, ScopedProject, assert_project_in_org
from app.api.v1.schemas.batches import BatchRead, BatchTrigger, MtRunRead
from app.models import BatchStatus, MtRun, Translation, TranslationBatch, TranslationStatus
from app.mt.service import enqueue_batch_for_mt
from app.mt.transitions import IllegalTransitionError, apply_transition

logger = logging.getLogger(__name__)

router = APIRouter()

# Companion router for project-scoped batch operations (docs/15 F3).
# Mounted in router.py under `/projects` so the path resolves to
# `POST /projects/{project_id}/trigger-mt` — alongside the existing
# locale-configs / glossary endpoints that already live under that prefix.
project_router = APIRouter()


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
    queued = await enqueue_batch_for_mt(db, batch)
    if not queued:
        raise HTTPException(status_code=409, detail="MT is already running for this batch")

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


@project_router.post("/{project_id}/trigger-mt")
async def trigger_project_mt(
    project: ScopedProject,
    db: DB,
    locale: str | None = Query(
        None,
        description=(
            "Restrict to batches in this BCP-47 locale (e.g. 'de-DE'). "
            "Omitting fans out across every locale in the project."
        ),
    ),
    status_filter: str = Query(
        "pending",
        alias="status",
        description=(
            "Batch status to enqueue. Default 'pending' covers the typical "
            "'Translate N pending' flow. Pass 'mt_proposed' to retry batches "
            "whose primary MT call failed and need re-running."
        ),
    ),
) -> dict[str, Any]:
    """Bulk-enqueue every matching batch in *project* for MT (docs/15 F3).

    Per the plan, this avoids the N-auth-checks / N-network-round-trips path
    the client-side fan-out would otherwise take. One auth check, one DB
    transaction, returns counts. Idempotent at the worker layer — the MT
    worker dedupes by batch id, so re-running this immediately produces a
    fully-skipped result rather than double-translating anything.
    """
    # Validate the status string against the enum. We accept the literal
    # `BatchStatus` values; anything else is a 422.
    try:
        target_status = BatchStatus(status_filter)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid batch status '{status_filter}'. Use 'pending', 'mt_running', "
                "'mt_complete', 'needs_review', or 'approved'."
            ),
        ) from exc

    q = select(TranslationBatch).where(
        TranslationBatch.project_id == project.id,
        TranslationBatch.status == target_status,
    )
    if locale is not None:
        q = q.where(TranslationBatch.locale == locale)

    rows = await db.execute(q)
    batches = rows.scalars().all()

    queued = 0
    skipped = 0
    for batch in batches:
        # `enqueue_batch_for_mt` already short-circuits batches that are
        # mt_running; everything else passes (the default `status=pending`
        # query already excludes them, but the helper double-guards in case
        # callers pass a different `status` filter that could include them).
        if await enqueue_batch_for_mt(db, batch):
            queued += 1
        else:
            skipped += 1

    await db.commit()
    logger.info(
        "bulk-mt enqueued for project %s: queued=%d skipped=%d (locale=%s, status=%s)",
        project.id,
        queued,
        skipped,
        locale,
        status_filter,
    )

    return {"queued": queued, "skipped": skipped}


@router.get("/{batch_id}/mt-runs", response_model=dict)
async def list_mt_runs(
    db: DB,
    batch: ScopedBatch,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Return MT-run rows for a batch, newest first.

    Powers the Phase 6 key-detail MT-run inspector. Each row is one LLM
    attempt (primary / retry / fallback per docs/05:52). The full
    `prompt_text` and `output_text` are included for forensic debugging
    of bad translations.
    """
    rows = await db.execute(select(MtRun).where(MtRun.batch_id == batch.id).order_by(MtRun.ran_at.desc()).limit(limit))
    items = [MtRunRead.model_validate(r) for r in rows.scalars().all()]
    return {"items": items, "total": len(items)}
