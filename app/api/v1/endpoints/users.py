from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedOrganization
from app.api.v1.schemas.users import UserCreate, UserRead
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


@router.get("/{org_id}/users", response_model=dict)
async def list_users(db: DB, org: ScopedOrganization) -> dict:
    """List users in an organization, newest first."""
    result = await db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    return {"items": [UserRead.model_validate(u) for u in users], "total": len(users)}
