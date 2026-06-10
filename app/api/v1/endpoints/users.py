from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedOrganization
from app.api.v1.schemas.common import ListResponse
from app.api.v1.schemas.users import UserCreate, UserRead, UserUpdate
from app.models import User

router = APIRouter()


@router.post("/{org_id}/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: DB, org: ScopedOrganization) -> UserRead:
    """Create a user in an organization.

    Users are attribution records (e.g. ``import_jobs.uploaded_by``); the API
    still authenticates with keys, not user sessions. ``ScopedOrganization``
    enforces that the caller's key owns this org (or is an org-admin key).

    Role is validated by ``UserCreate`` against ``UserRole`` (422 on a bad
    value). ``email`` is globally unique, so a duplicate raises 409.
    """
    user = User(
        organization_id=org.id,
        email=body.email,
        name=body.name,
        role=body.role,
        assigned_locales=body.assigned_locales,
        is_active=True,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {body.email!r} already exists.",
        )
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/{org_id}/users/{user_id}", response_model=UserRead)
async def update_user(user_id: uuid.UUID, body: UserUpdate, db: DB, org: ScopedOrganization) -> UserRead:
    """Soft-deactivate (``is_active``) or change a user's ``role``.

    Org-scoped: a user in another org returns 404 (not 403) to avoid leaking
    existence, matching the tenant-isolation contract. Deactivation is a soft
    flag — the row stays so attribution links (import_jobs.uploaded_by, history)
    don't dangle.
    """
    result = await db.execute(select(User).where(User.id == user_id, User.organization_id == org.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/{org_id}/users", response_model=ListResponse[UserRead])
async def list_users(db: DB, org: ScopedOrganization) -> dict:
    """List users in an organization, newest first."""
    result = await db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    return {"items": [UserRead.model_validate(u) for u in users], "total": len(users)}
