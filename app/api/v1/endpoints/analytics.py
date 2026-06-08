"""Project analytics endpoint (docs/06:60, docs/14 §9 tab 8).

Read-only aggregate over ``mt_runs`` and ``translations`` for one project.
Cost runs are scoped to the project by joining each ``MtRun`` to its
``TranslationBatch`` (``mt_runs`` has no direct ``project_id``); review/QA
rows are scoped by joining each ``Translation`` to its ``Key``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, ScopedProject
from app.api.v1.schemas.analytics import AnalyticsSummary, CostByModel
from app.models import Key, MtRun, Translation, TranslationBatch

router = APIRouter()


def _to_float(value: float | Decimal | None) -> float | None:
    """SQL ``avg``/``sum`` come back as ``Decimal`` (or ``None`` on no rows)."""
    return float(value) if value is not None else None


@router.get("/{project_id}/analytics", response_model=AnalyticsSummary)
async def get_project_analytics(
    db: DB,
    project: ScopedProject,
    window_days: int = Query(
        30,
        ge=1,
        le=365,
        description=(
            "Trailing window in days for cost, edit-rate, and QA metrics. "
            "status_counts is always current-state and ignores this."
        ),
    ),
) -> AnalyticsSummary:
    """Aggregate MT cost, edit rate, and QA quality for a project."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # --- MT cost & throughput, grouped by model (mt_runs -> batch for scope) ---
    cost_rows = (
        await db.execute(
            select(
                MtRun.model,
                func.count(),
                func.coalesce(func.sum(MtRun.cost_usd), 0),
                func.coalesce(func.sum(MtRun.input_tokens), 0),
                func.coalesce(func.sum(MtRun.output_tokens), 0),
            )
            .join(TranslationBatch, MtRun.batch_id == TranslationBatch.id)
            .where(TranslationBatch.project_id == project.id, MtRun.ran_at >= cutoff)
            .group_by(MtRun.model)
            .order_by(func.coalesce(func.sum(MtRun.cost_usd), 0).desc())
        )
    ).all()

    cost_by_model = [
        CostByModel(
            model=row[0],
            runs=row[1],
            cost_usd=float(row[2]),
            input_tokens=int(row[3]),
            output_tokens=int(row[4]),
        )
        for row in cost_rows
    ]
    total_cost_usd = sum((c.cost_usd for c in cost_by_model), 0.0)
    total_runs = sum((c.runs for c in cost_by_model), 0)
    total_input_tokens = sum((c.input_tokens for c in cost_by_model), 0)
    total_output_tokens = sum((c.output_tokens for c in cost_by_model), 0)

    avg_latency_ms = await db.scalar(
        select(func.avg(MtRun.latency_ms))
        .join(TranslationBatch, MtRun.batch_id == TranslationBatch.id)
        .where(TranslationBatch.project_id == project.id, MtRun.ran_at >= cutoff)
    )

    # --- Review / edit rate (translations -> key for scope, windowed by reviewed_at) ---
    # reviewed_count counts only rows reviewed *within the window*: a row with
    # reviewer_action set but reviewed_at NULL (un-timestamped) falls in no
    # window and is excluded by design. The workflow sets both together.
    review_rows = (
        await db.execute(
            select(Translation.reviewer_action, func.count())
            .join(Key, Translation.key_id == Key.id)
            .where(
                Key.project_id == project.id,
                Translation.reviewer_action.is_not(None),
                Translation.reviewed_at >= cutoff,
            )
            .group_by(Translation.reviewer_action)
        )
    ).all()
    action_counts: dict[str, int] = {row[0]: row[1] for row in review_rows}
    edit_count = action_counts.get("edit", 0)
    accept_count = action_counts.get("accept", 0)
    reject_count = action_counts.get("reject", 0)
    needs_more_context_count = action_counts.get("needs_more_context", 0)
    reviewed_count = sum(action_counts.values())
    edit_rate = (edit_count / reviewed_count) if reviewed_count else None

    # --- Quality averages (windowed by mt_run_at) ---
    qa = (
        await db.execute(
            select(
                func.avg(Translation.qa_naturalness),
                func.avg(Translation.qa_consistency),
                func.avg(Translation.qa_accuracy),
                func.avg(Translation.back_translation_similarity),
            )
            .join(Key, Translation.key_id == Key.id)
            .where(Key.project_id == project.id, Translation.mt_run_at >= cutoff)
        )
    ).one()

    # --- Current-state volume by status (NOT windowed) ---
    status_rows = (
        await db.execute(
            select(Translation.status, func.count())
            .join(Key, Translation.key_id == Key.id)
            .where(Key.project_id == project.id)
            .group_by(Translation.status)
        )
    ).all()
    status_counts: dict[str, int] = {row[0]: row[1] for row in status_rows}

    return AnalyticsSummary(
        window_days=window_days,
        total_cost_usd=total_cost_usd,
        total_runs=total_runs,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        avg_latency_ms=_to_float(avg_latency_ms),
        cost_by_model=cost_by_model,
        reviewed_count=reviewed_count,
        edit_count=edit_count,
        accept_count=accept_count,
        reject_count=reject_count,
        needs_more_context_count=needs_more_context_count,
        edit_rate=edit_rate,
        avg_qa_naturalness=_to_float(qa[0]),
        avg_qa_consistency=_to_float(qa[1]),
        avg_qa_accuracy=_to_float(qa[2]),
        avg_back_translation_similarity=_to_float(qa[3]),
        status_counts=status_counts,
    )
