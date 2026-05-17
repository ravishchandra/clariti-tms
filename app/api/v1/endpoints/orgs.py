from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentKey, OrgAdminKey, ScopedOrganization
from app.api.v1.schemas.orgs import OrgCreate, OrgRead, OrgUpdate
from app.models import Organization

router = APIRouter()


@router.post("", response_model=OrgRead, status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgCreate, db: DB, _: OrgAdminKey) -> OrgRead:
    """Create a new organization. Restricted to org-admin keys (403 otherwise).

    The bootstrap admin key is created out of band by `loc api-key` or the seed
    script; ordinary keys created via `POST /api-keys` are not org admins.
    """
    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    await db.refresh(org)
    return OrgRead.model_validate(org)


@router.get("", response_model=dict)
async def list_orgs(db: DB, current_key: CurrentKey) -> dict:
    """List organizations visible to the caller.

    Regular keys see exactly one org (their own). Org-admin keys see every org.
    """
    q = select(Organization).order_by(Organization.created_at.desc())
    if not current_key.is_org_admin:
        q = q.where(Organization.id == current_key.organization_id)
    result = await db.execute(q)
    orgs = list(result.scalars().all())
    return {"items": [OrgRead.model_validate(o) for o in orgs], "total": len(orgs)}


@router.get("/{org_id}", response_model=OrgRead)
async def get_org(org: ScopedOrganization) -> OrgRead:
    return OrgRead.model_validate(org)


@router.patch("/{org_id}", response_model=OrgRead)
async def update_org(body: OrgUpdate, db: DB, org: ScopedOrganization) -> OrgRead:
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(org, field, value)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    await db.refresh(org)
    return OrgRead.model_validate(org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(org_id: uuid.UUID, db: DB, _: OrgAdminKey) -> None:
    """Delete an organization. Restricted to org-admin keys (403 otherwise)."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.delete(org)
    await db.flush()
