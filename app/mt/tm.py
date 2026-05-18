from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


# =========================================================================
# Raw-SQL literal helpers (M1)
# =========================================================================
#
# Why raw SQL?
# -------------
# Both pgvector queries below go through asyncpg, and asyncpg has two
# pgvector-specific quirks that force us off the normal SQLAlchemy / named-
# parameter path. They are documented at
# ``~/.claude/projects/.../memory/project_pgvector_asyncpg.md``:
#
#   1. asyncpg can't parse ``::type`` casts attached to named parameters —
#      ``:embedding::vector`` is read as ``:embedding`` followed by garbage.
#   2. pgvector vector literals use square brackets — ``'[0.1, 0.2]'`` — not
#      Postgres-array curly braces.
#
# As a result, the embedding vector and the optional UUID exclude-array have
# to be inlined into the SQL string as **string literals**, not bound
# parameters. The classic SQL-injection pattern (string-concat user input
# into a query) and the pattern we're forced into here look identical from a
# distance, so the helpers below exist to enforce the only thing that makes
# our case safe: **typed, internal-only inputs**.
#
# Trust boundary contract
# -----------------------
# These helpers are NOT general-purpose SQL escapers. They accept *only*
# values that originate inside our own code (an embedding vector returned
# from an LLM provider's ``embed()`` call, or ``Key.id`` UUIDs loaded from
# our DB) and assume the caller has already produced typed Python values
# (``list[float]``, ``list[uuid.UUID]``). The type annotations are part of
# the contract — passing a ``list[str]`` of UUIDs sourced from external
# input would defeat the safety guarantee, so the helpers ``isinstance``-
# check at runtime and raise ``TypeError`` rather than silently coercing.
# Any new caller MUST construct the input values from typed sources
# (database rows, provider returns, internal config) — never from request
# bodies, query strings, file contents, or LLM outputs.

_EMBEDDING_MIN_LEN = 1
"""Lower bound for a sane pgvector embedding length.

pgvector itself enforces the column-defined dimension at insert/query time;
this constant is just to flag an obviously-broken empty embedding before
we even hit Postgres.
"""


def _vector_literal(embedding: list[float]) -> str:
    """Build a pgvector ``'[...]'`` string literal from a typed embedding.

    Returns an SQL fragment safe to splice into a ``text(...)`` query, e.g.
    ``'[0.1,0.2,0.3]'``. The caller must append the ``::vector`` cast.

    Contract (see module docstring): ``embedding`` must be a list of
    ``int``/``float`` values produced by our own code. We runtime-check the
    shape so a refactor that accidentally widens the type can't slip a
    string with an embedded quote through.

    Raises
    ------
    TypeError
        If ``embedding`` is not a list of numeric values.
    ValueError
        If ``embedding`` is empty.
    """
    if not isinstance(embedding, list):
        raise TypeError(
            f"embedding must be list[float], got {type(embedding).__name__}"
        )
    if len(embedding) < _EMBEDDING_MIN_LEN:
        raise ValueError("embedding must be non-empty")
    for v in embedding:
        # ``bool`` is a subclass of ``int`` in Python; allow it implicitly
        # since ``str(True) == 'True'`` would actually break the SQL, but
        # ``float(True) == 1.0`` works — we coerce via ``float()`` below
        # which raises on non-numeric anyway.
        if not isinstance(v, (int, float)):
            raise TypeError(
                "embedding elements must be int or float, got "
                f"{type(v).__name__}"
            )
    # ``repr(float(...))`` would round-trip safely but is more verbose than
    # needed; ``str(float(...))`` is sufficient because we've already
    # type-checked the inputs. ``float()`` coerces ``int`` cleanly.
    return "'[" + ",".join(str(float(v)) for v in embedding) + "]'"


def _uuid_array_exclude_clause(exclude_ids: list[uuid.UUID]) -> str:
    """Build the optional ``AND source_key_id != ALL(ARRAY[...]::uuid[])`` clause.

    Returns an empty string when ``exclude_ids`` is empty (the caller
    splices the result into a multi-line SQL template, so an empty
    return is just a no-op).

    Contract (see module docstring): ``exclude_ids`` must be a list of
    ``uuid.UUID`` instances, typically ``[k.id for k in keys_list]`` where
    ``k`` is a SQLAlchemy ``Key`` row. The runtime ``isinstance`` check
    rejects strings — passing string UUIDs from an external source would
    bypass the type guarantee. We never call ``str()`` on the input
    directly; the ``uuid.UUID.__str__`` representation is fixed-shape
    (8-4-4-4-12 lowercase hex) and cannot contain a quote or semicolon.

    Raises
    ------
    TypeError
        If ``exclude_ids`` is not a list of ``uuid.UUID``.
    """
    if not isinstance(exclude_ids, list):
        raise TypeError(
            f"exclude_ids must be list[uuid.UUID], got "
            f"{type(exclude_ids).__name__}"
        )
    if not exclude_ids:
        return ""
    for u in exclude_ids:
        if not isinstance(u, uuid.UUID):
            raise TypeError(
                "exclude_ids elements must be uuid.UUID, got "
                f"{type(u).__name__}"
            )
    # ``uuid.UUID.__str__`` always produces ``'xxxxxxxx-xxxx-...-xxxxxxxxxxxx'``
    # with no whitespace or special characters — safe to wrap in single quotes.
    inner = ",".join(f"'{u}'" for u in exclude_ids)
    return f"AND source_key_id != ALL(ARRAY[{inner}]::uuid[])"


async def retrieve_tm_neighbors(
    db: AsyncSession,
    project_id: str,
    locale: str,
    batch_embedding: list[float],
    platform: str,
    exclude_key_ids: list[uuid.UUID],
    k: int = 10,
    min_similarity: float = 0.65,
) -> list[dict]:
    """Retrieve TM neighbors for a batch via pgvector cosine similarity.

    The vector literal and UUID exclude clause are built with the typed
    helpers above (M1). They look like string interpolation but are
    constrained to internal-only typed inputs — see the module docstring
    for the trust boundary. All other parameters (``project_id``,
    ``locale``, ``platform``, ``k``, ``min_similarity``) go through normal
    named bind parameters because they don't trigger the pgvector quirks.
    """
    vec_literal = _vector_literal(batch_embedding)
    exclude_clause = _uuid_array_exclude_clause(exclude_key_ids)

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
    repository_id: str,
    locale: str,
    source_key_id: str,
    source_text: str,
    target_text: str,
    platform: str,
    embedding: list[float],
) -> None:
    """Insert or update a translation_memory row for (project, key, locale).

    M6 fix (2026-05): `repository_id` is now required so TM rows are linked
    back to their originating repository — see docs/04-data-model.md:302
    ("where this TM entry originated"). Existing rows whose repository_id is
    NULL are upgraded on the next update.
    """
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
        # Backfill repository_id on existing rows (was previously never set).
        existing.repository_id = uuid.UUID(repository_id)
    else:
        tm = TranslationMemory(
            project_id=uuid.UUID(project_id),
            repository_id=uuid.UUID(repository_id),
            locale=locale,
            source_key_id=uuid.UUID(source_key_id),
            source_text=source_text,
            target_text=target_text,
            platform=platform,
            source_embedding=embedding,
        )
        db.add(tm)
