"""Public read API for the MT module.

Other modules (notably publication) must never query the ``translations``
table directly — they call the functions exposed here instead. This keeps
the module boundary explicit and enforced.

This file only exposes *read* operations needed by callers outside ``mt/``.
Internal MT machinery (translate_batch, TM, validators, etc.) is reached
through their respective modules.

See CLAUDE.md and docs/03-architecture.md for the cross-module DB rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Key, Project, Repository, Translation, TranslationStatus
from app.mt.transitions import IllegalTransitionError, apply_transition


async def list_approved_translations(
    db: AsyncSession,
    repository_id: uuid.UUID | str,
    locale: str | None = None,
    status_filter: TranslationStatus = TranslationStatus.approved,
) -> list[tuple[Translation, Key]]:
    """List publishable translations for a repository.

    A translation is publishable when:

    * its status matches ``status_filter`` (default: ``approved``)
    * it has a non-NULL ``value``
    * the parent :class:`Key` lives in the given repository

    Parameters
    ----------
    db:
        Active async session.
    repository_id:
        Repository UUID. Strings are accepted for ergonomics.
    locale:
        Optional BCP-47 locale filter (e.g. ``"fr-FR"``).  When ``None``
        all locales are returned.
    status_filter:
        Which translation status to filter on. Defaults to ``approved``
        (publication's pre-push view). Phase 7 OTA passes ``published``
        to read the post-merge, shippable set.

    Returns
    -------
    list[tuple[Translation, Key]]
        ``(translation, key)`` pairs, in arbitrary order.
    """
    stmt = (
        select(Translation, Key)
        .join(Key, Translation.key_id == Key.id)
        .where(
            Key.repository_id == repository_id,
            Key.is_active.is_(True),
            Translation.status == status_filter,
            Translation.value.is_not(None),
        )
    )
    if locale is not None:
        stmt = stmt.where(Translation.locale == locale)

    rows = await db.execute(stmt)
    return [(t, k) for t, k in rows.all()]


async def list_published_translations_by_project_slug(
    db: AsyncSession,
    project_slug: str,
    locale: str,
) -> list[tuple[Translation, Key, Repository]]:
    """List published translations for an entire project, by slug.

    Aggregates across every :class:`Repository` belonging to the project.
    Phase 7's OTA endpoint is project-scoped (not repo-scoped) because a
    client app fetches one locale file regardless of how many platform
    repos contributed to it.

    Returns ``(translation, key, repository)`` triples so callers can
    select a platform-appropriate serializer per row if they need to.
    The current OTA endpoint flattens to ``{key: value}`` and only needs
    the repository when serializing as a platform-specific file (e.g.
    ``?platform=ios``).

    Returns an empty list when the slug does not exist — callers must
    distinguish "no project" from "no published translations" themselves
    (the OTA endpoint does this with a separate slug-existence check).
    """
    stmt = (
        select(Translation, Key, Repository)
        .join(Key, Translation.key_id == Key.id)
        .join(Repository, Key.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .where(
            Project.slug == project_slug,
            Key.is_active.is_(True),
            Translation.locale == locale,
            Translation.status == TranslationStatus.published,
            Translation.value.is_not(None),
        )
    )
    rows = await db.execute(stmt)
    return [(t, k, r) for t, k, r in rows.all()]


async def project_exists_by_slug(db: AsyncSession, project_slug: str) -> bool:
    """Return True iff a project with the given slug exists.

    Public read used by the OTA endpoint to distinguish 404-"no such
    project" from 404-"project exists but no published translations
    in that locale yet". Both surface as 404 to the client, but the
    detail message differs (useful for operator triage in CDN logs).
    """
    result = await db.execute(select(Project.id).where(Project.slug == project_slug))
    return result.scalar_one_or_none() is not None


async def mark_translations_published(
    db: AsyncSession,
    translation_ids: list[uuid.UUID],
    published_at: datetime,
) -> None:
    """Transition a set of translations to ``published``.

    Used by publication after a successful PR has been opened.  This stays
    inside ``mt/`` because translation status transitions are part of MT's
    state machine — publication must not write to the ``translations``
    table directly.

    The state-machine guard (`approved -> published` is the only legal
    edge here) is enforced by :func:`app.mt.transitions.apply_transition`.
    Rows whose current status is not ``approved`` are silently skipped — the
    caller treats this bulk path as "best-effort publish what's publishable".

    The ``published_at`` parameter is accepted for API compatibility but is
    no longer authoritative: ``apply_transition`` stamps ``published_at``
    with ``now(tz=UTC)`` at the moment of the edge. If a caller really needs
    to backdate, they should write per-row outside this helper.

    Parameters
    ----------
    db:
        Active async session. The caller is responsible for committing.
    translation_ids:
        UUIDs of translations to publish.
    published_at:
        Retained for backward compatibility; ignored.
    """
    del published_at  # see docstring — apply_transition stamps its own.
    if not translation_ids:
        return
    rows = await db.execute(select(Translation).where(Translation.id.in_(translation_ids)))
    for translation in rows.scalars():
        try:
            apply_transition(translation, TranslationStatus.published)
        except IllegalTransitionError:
            # Not in `approved` — skip, matching the prior WHERE-filter semantics.
            continue


async def fetch_translations_by_ids(
    db: AsyncSession,
    translation_ids: list[uuid.UUID],
) -> list[Translation]:
    """Load a set of translations by id, in arbitrary order.

    Public reader for cross-module use. The Excel-import module uses this
    instead of selecting from ``translations`` directly so the module-
    boundary rule (CLAUDE.md, "Module boundaries") stays enforceable in
    review: any other module reading translation rows must do it through
    here.
    """
    if not translation_ids:
        return []
    result = await db.execute(select(Translation).where(Translation.id.in_(translation_ids)))
    return list(result.scalars().all())
