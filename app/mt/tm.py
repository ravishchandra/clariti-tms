from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


async def retrieve_tm_neighbors(
    db: AsyncSession,
    project_id: str,
    locale: str,
    batch_embedding: list[float],
    platform: str,
    exclude_key_ids: list[str],
    k: int = 10,
    min_similarity: float = 0.65,
) -> list[dict]:
    embedding_str = "[" + ",".join(str(x) for x in batch_embedding) + "]"
    rows = await db.execute(
        text("""
            SELECT source_text, target_text, platform,
                   1 - (source_embedding <=> :embedding::vector) AS similarity
            FROM translation_memory
            WHERE project_id = :project_id
              AND locale = :locale
              AND source_key_id != ALL(:exclude_ids::uuid[])
              AND 1 - (source_embedding <=> :embedding::vector) >= :min_sim
            ORDER BY (source_embedding <=> :embedding::vector)
                   - CASE WHEN platform = :platform THEN 0.15 ELSE 0 END
            LIMIT :k
        """),
        {
            "project_id": project_id,
            "locale": locale,
            "embedding": embedding_str,
            "exclude_ids": exclude_key_ids,
            "platform": platform,
            "min_sim": min_similarity,
            "k": k,
        },
    )
    return [
        {
            "source_text": r.source_text,
            "target_text": r.target_text,
            "platform": r.platform,
            "similarity": float(r.similarity),
        }
        for r in rows
    ]


async def store_tm_entry(
    db: AsyncSession,
    project_id: str,
    locale: str,
    source_key_id: str,
    source_text: str,
    target_text: str,
    platform: str,
    embedding: list[float],
) -> None:
    from app.models import TranslationMemory

    existing = await db.scalar(
        select(TranslationMemory).where(
            TranslationMemory.project_id == uuid.UUID(project_id),
            TranslationMemory.source_key_id == uuid.UUID(source_key_id),
            TranslationMemory.locale == locale,
        )
    )
    if existing:
        existing.target_text = target_text
        existing.source_embedding = embedding
    else:
        tm = TranslationMemory(
            project_id=uuid.UUID(project_id),
            locale=locale,
            source_key_id=uuid.UUID(source_key_id),
            source_text=source_text,
            target_text=target_text,
            platform=platform,
            source_embedding=embedding,
        )
        db.add(tm)
