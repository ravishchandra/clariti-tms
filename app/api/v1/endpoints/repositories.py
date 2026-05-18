from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedProject, ScopedRepository
from app.api.v1.schemas.repositories import RepositoryCreate, RepositoryRead, RepositoryUpdate
from app.core.crypto import encrypt
from app.models import Repository

router = APIRouter()

# Map of write-only secret fields on the input schema -> Repository column name.
# Anything in this map is encrypted at the API boundary, never persisted plain.
_SECRET_FIELD_TO_COLUMN: dict[str, str] = {
    "webhook_secret": "webhook_secret_encrypted",
    "contentful_token": "contentful_token_encrypted",
    "contentful_webhook_secret": "contentful_webhook_secret_encrypted",
}


@router.post("/{project_id}/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepositoryCreate, db: DB, project: ScopedProject
) -> RepositoryRead:
    repo = Repository(
        project_id=project.id,
        name=body.name,
        platform=body.platform,
        file_format=body.file_format,
        plural_convention=body.plural_convention,
        github_repo=body.github_repo,
        github_path=body.github_path,
        github_installation_id=body.github_installation_id,
        source_file=body.source_file,
        context_notes=body.context_notes,
        contentful_space_id=body.contentful_space_id,
        contentful_env=body.contentful_env,
        default_branch=body.default_branch,
        # Encrypt incoming secrets before they touch the DB. `encrypt(None) == None`.
        webhook_secret_encrypted=encrypt(body.webhook_secret),
        contentful_token_encrypted=encrypt(body.contentful_token),
        contentful_webhook_secret_encrypted=encrypt(body.contentful_webhook_secret),
    )
    db.add(repo)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository name already exists in project",
        )
    await db.refresh(repo)
    return RepositoryRead.model_validate(repo)


@router.get("/{project_id}/repositories", response_model=dict)
async def list_repositories(db: DB, project: ScopedProject) -> dict:
    total_result = await db.execute(
        select(func.count()).select_from(Repository).where(Repository.project_id == project.id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(Repository).where(Repository.project_id == project.id).order_by(Repository.created_at.desc())
    )
    repos = result.scalars().all()
    return {"items": [RepositoryRead.model_validate(r) for r in repos], "total": total}


@router.get("/{project_id}/repositories/{repo_id}", response_model=RepositoryRead)
async def get_repository(repo: ScopedRepository) -> RepositoryRead:
    return RepositoryRead.model_validate(repo)


@router.patch("/{project_id}/repositories/{repo_id}", response_model=RepositoryRead)
async def update_repository(
    body: RepositoryUpdate, db: DB, repo: ScopedRepository
) -> RepositoryRead:
    # F5: use `exclude_unset=True` (not `exclude_none=True`) so the handler can
    # distinguish "field omitted" from "field explicitly set to null". Omitted
    # fields stay as-is; explicit null on a nullable column clears it. Explicit
    # null on a NOT NULL column is rejected at schema validation time (see
    # `_reject_null_on_required` in RepositoryUpdate) so we never reach a NOT
    # NULL violation at flush.
    updates = body.model_dump(exclude_unset=True)
    # C3 + F5: pull off any incoming secret fields, encrypt, and route to the
    # *_encrypted column. `encrypt(None)` returns None, so an explicit JSON
    # null clears the secret column (F5). Empty/whitespace strings are
    # rejected earlier by the `_reject_blank_secret` schema validator.
    for field, column in _SECRET_FIELD_TO_COLUMN.items():
        if field in updates:
            setattr(repo, column, encrypt(updates.pop(field)))
    for field, value in updates.items():
        setattr(repo, field, value)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository name already exists in project",
        )
    await db.refresh(repo)
    return RepositoryRead.model_validate(repo)


@router.delete("/{project_id}/repositories/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(db: DB, repo: ScopedRepository) -> None:
    await db.delete(repo)
    await db.flush()
