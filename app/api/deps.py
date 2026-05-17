from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import (
    ApiKey,
    ComponentContext,
    GlossaryTerm,
    Key,
    LocaleConfig,
    Organization,
    Project,
    Repository,
    Translation,
    TranslationBatch,
)

DB = Annotated[AsyncSession, Depends(get_db)]


async def _get_api_key(
    db: DB,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ApiKey:
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if api_key is None or not api_key.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    return api_key


CurrentKey = Annotated[ApiKey, Depends(_get_api_key)]


# ---------------------------------------------------------------------------
# Tenant-scoping helpers.
#
# Every endpoint that takes a resource UUID in its path MUST depend on one of
# these helpers instead of fetching the resource directly. The helper looks the
# resource up, walks the hierarchy to its owning organization, compares it to
# the calling API key's org, and returns either the resource or 404.
#
# 404 (not 403) is deliberate — leaking "this resource exists but you can't see
# it" is itself an information disclosure.
#
# For list endpoints (which filter by an FK in a query parameter), use the
# `assert_*_in_org` async helpers below — they raise the same 404 inline.
# ---------------------------------------------------------------------------


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def scoped_organization(
    org_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Organization:
    """Fetch an org if it equals the caller's org, or it the caller is an org admin.

    Regular keys can only see / modify their own org.
    Org-admin keys can see / modify any org (used for POST and DELETE on orgs).
    """
    if not current_key.is_org_admin and org_id != current_key.organization_id:
        raise _not_found("Organization not found")
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise _not_found("Organization not found")
    return org


async def scoped_project(
    project_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Project:
    """Return the project iff it belongs to the caller's org; else 404."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise _not_found("Project not found")
    return project


async def scoped_repository(
    repo_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Repository:
    """Return the repository iff its parent project belongs to the caller's org."""
    result = await db.execute(
        select(Repository)
        .join(Project, Repository.project_id == Project.id)
        .where(
            Repository.id == repo_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise _not_found("Repository not found")
    return repo


async def scoped_key(
    key_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Key:
    """Return the key iff its (denormalized) project belongs to the caller's org."""
    result = await db.execute(
        select(Key)
        .join(Project, Key.project_id == Project.id)
        .where(
            Key.id == key_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise _not_found("Key not found")
    return key


async def scoped_translation(
    translation_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Translation:
    """Return the translation iff its key's project belongs to the caller's org."""
    result = await db.execute(
        select(Translation)
        .join(Key, Translation.key_id == Key.id)
        .join(Project, Key.project_id == Project.id)
        .where(
            Translation.id == translation_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise _not_found("Translation not found")
    return translation


async def scoped_batch(
    batch_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> TranslationBatch:
    """Return the batch iff its project belongs to the caller's org."""
    result = await db.execute(
        select(TranslationBatch)
        .join(Project, TranslationBatch.project_id == Project.id)
        .where(
            TranslationBatch.id == batch_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise _not_found("Batch not found")
    return batch


async def scoped_glossary_term(
    term_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> GlossaryTerm:
    """Return the glossary term iff its project belongs to the caller's org."""
    result = await db.execute(
        select(GlossaryTerm)
        .join(Project, GlossaryTerm.project_id == Project.id)
        .where(
            GlossaryTerm.id == term_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    term = result.scalar_one_or_none()
    if term is None:
        raise _not_found("Glossary term not found")
    return term


async def scoped_locale_config(
    config_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> LocaleConfig:
    """Return the locale config iff its project belongs to the caller's org."""
    result = await db.execute(
        select(LocaleConfig)
        .join(Project, LocaleConfig.project_id == Project.id)
        .where(
            LocaleConfig.id == config_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    lc = result.scalar_one_or_none()
    if lc is None:
        raise _not_found("Locale config not found")
    return lc


async def scoped_component_context(
    ctx_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> ComponentContext:
    """Return the component context iff its repo's project belongs to the caller's org."""
    result = await db.execute(
        select(ComponentContext)
        .join(Repository, ComponentContext.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .where(
            ComponentContext.id == ctx_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise _not_found("Component context not found")
    return ctx


# ---------------------------------------------------------------------------
# Inline assertion helpers — for list endpoints that filter by an FK passed
# as a query parameter (`project_id=...`, `repository_id=...`). Returning the
# resource isn't useful in these cases (the endpoint already filters by the
# foreign key), so the helpers just raise on mismatch.
# ---------------------------------------------------------------------------


async def assert_project_in_org(
    project_id: uuid.UUID,
    db: AsyncSession,
    current_key: ApiKey,
) -> None:
    """Raise 404 if the project does not belong to the caller's org."""
    result = await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise _not_found("Project not found")


async def assert_repository_in_org(
    repository_id: uuid.UUID,
    db: AsyncSession,
    current_key: ApiKey,
) -> None:
    """Raise 404 if the repository's parent project does not belong to the caller's org."""
    result = await db.execute(
        select(Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .where(
            Repository.id == repository_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise _not_found("Repository not found")


def require_org_admin(current_key: CurrentKey) -> ApiKey:
    """Dep for endpoints that require an org-admin key (POST/DELETE on orgs)."""
    if not current_key.is_org_admin:
        raise _forbidden("Operation requires an organization-admin API key")
    return current_key


# Convenience type aliases (parallel to CurrentKey / DB).
ScopedOrganization = Annotated[Organization, Depends(scoped_organization)]
ScopedProject = Annotated[Project, Depends(scoped_project)]
ScopedRepository = Annotated[Repository, Depends(scoped_repository)]
ScopedKey = Annotated[Key, Depends(scoped_key)]
ScopedTranslation = Annotated[Translation, Depends(scoped_translation)]
ScopedBatch = Annotated[TranslationBatch, Depends(scoped_batch)]
ScopedGlossaryTerm = Annotated[GlossaryTerm, Depends(scoped_glossary_term)]
ScopedLocaleConfig = Annotated[LocaleConfig, Depends(scoped_locale_config)]
ScopedComponentContext = Annotated[ComponentContext, Depends(scoped_component_context)]
OrgAdminKey = Annotated[ApiKey, Depends(require_org_admin)]
