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
    # Interpolate embedding and exclude list as SQL literals — asyncpg does not
    # support ::type casts on named parameters, and array params need special handling.
    # Both values originate from our own code (never user input), so this is safe.
    vec_literal = "'[" + ",".join(str(x) for x in batch_embedding) + "]'"
    if exclude_key_ids:
        exclude_clause = "AND source_key_id != ALL(ARRAY[{}]::uuid[])".format(
            ",".join(f"'{eid}'" for eid in exclude_key_ids)
        )
    else:
        exclude_clause = ""

    sql = text(f"""
        SELECT source_text, target_text, platform,
               1 - (source_embedding <=> {vec_literal}::vector) AS similarity
        FROM translation_memory
        WHERE project_id = :project_id
          AND locale = :locale
          {exclude_clause}
          AND 1 - (source_embedding <=> {vec_literal}::vector) >= :min_sim
        ORDER BY (source_embedding <=> {vec_literal}::vector)
               - CASE WHEN platform = :platform THEN 0.15 ELSE 0 END
        LIMIT :k
    """)
    rows = await db.execute(
        sql,
        {"project_id": project_id, "locale": locale, "platform": platform, "min_sim": min_similarity, "k": k},
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
