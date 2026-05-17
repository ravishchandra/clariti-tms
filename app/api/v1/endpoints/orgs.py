from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.orgs import OrgCreate, OrgRead, OrgUpdate
from app.models import Organization

router = APIRouter()


@router.post("", response_model=OrgRead, status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgCreate, db: DB, _: CurrentKey) -> OrgRead:
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
async def list_orgs(db: DB, _: CurrentKey) -> dict:
    total_result = await db.execute(select(func.count()).select_from(Organization))
    total = total_result.scalar_one()
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = result.scalars().all()
    return {"items": [OrgRead.model_validate(o) for o in orgs], "total": total}


@router.get("/{org_id}", response_model=OrgRead)
async def get_org(org_id: uuid.UUID, db: DB, _: CurrentKey) -> OrgRead:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrgRead.model_validate(org)


@router.patch("/{org_id}", response_model=OrgRead)
async def update_org(org_id: uuid.UUID, body: OrgUpdate, db: DB, _: CurrentKey) -> OrgRead:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
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
async def delete_org(org_id: uuid.UUID, db: DB, _: CurrentKey) -> None:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await db.delete(org)
    await db.flush()
