"""MT worker — polls pending batches and runs translate_batch().

This is a simple polling loop backed by the translation_batches table.
It behaves like a pgmq consumer: claim a batch (set status=mt_running),
process it, release. Safe to run multiple workers concurrently — the
UPDATE ... WHERE status='pending' RETURNING is atomic on Postgres.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.llm.protocol import LLMProvider
from app.models import BatchStatus, TranslationBatch
from app.mt.service import translate_batch

logger = logging.getLogger(__name__)


async def _claim_next_batch(db: AsyncSession) -> TranslationBatch | None:
    """Atomically claim the oldest pending batch."""
    result = await db.execute(
        select(TranslationBatch)
        .where(TranslationBatch.status == BatchStatus.pending)
        .order_by(TranslationBatch.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


async def run_worker(
    providers: dict[str, LLMProvider],
    *,
    poll_interval: float = 5.0,
    max_batches: int | None = None,
    config_provider: str = "anthropic",
    embed_provider: str = "openai",
    deepl_locales: list[str] | None = None,
) -> None:
    """Run the MT worker loop.

    Polls for pending batches every *poll_interval* seconds.
    Set *max_batches* to stop after N batches (useful for tests/CLI one-shot).
    """
    processed = 0
    logger.info("MT worker started (poll_interval=%.1fs)", poll_interval)

    while max_batches is None or processed < max_batches:
        async with AsyncSessionLocal() as db:
            batch = await _claim_next_batch(db)
            if batch is None:
                if max_batches is not None:
                    break
                await asyncio.sleep(poll_interval)
                continue

            logger.info(
                "Processing batch %s (locale=%s, component=%s)",
                batch.id, batch.locale, batch.component,
            )
            try:
                summary = await translate_batch(
                    db=db,
                    batch=batch,
                    providers=providers,
                    deepl_locales=deepl_locales,
                    config_provider=config_provider,
                    embed_provider=embed_provider,
                )
                logger.info("Batch %s complete: %s", batch.id, summary)
            except Exception as exc:
                logger.error("Batch %s failed: %s", batch.id, exc, exc_info=True)
                batch.status = BatchStatus.needs_review
                await db.commit()

            processed += 1

    logger.info("MT worker stopped after %d batches", processed)
