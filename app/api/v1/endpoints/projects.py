from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from app.models import Organization, Project

router = APIRouter()


@router.post("/{org_id}/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(org_id: uuid.UUID, body: ProjectCreate, db: DB, _: CurrentKey) -> ProjectRead:
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    project = Project(
        organization_id=org_id,
        name=body.name,
        slug=body.slug,
        source_locale=body.source_locale,
        target_locales=body.target_locales,
        style_guide=body.style_guide,
    )
    db.add(project)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{org_id}/projects", response_model=dict)
async def list_projects(org_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    total_result = await db.execute(
        select(func.count()).select_from(Project).where(Project.organization_id == org_id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(Project).where(Project.organization_id == org_id).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return {"items": [ProjectRead.model_validate(p) for p in projects], "total": total}


@router.get("/{org_id}/projects/{project_id}", response_model=ProjectRead)
async def get_project(org_id: uuid.UUID, project_id: uuid.UUID, db: DB, _: CurrentKey) -> ProjectRead:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == org_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.patch("/{org_id}/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    org_id: uuid.UUID, project_id: uuid.UUID, body: ProjectUpdate, db: DB, _: CurrentKey
) -> ProjectRead:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == org_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{org_id}/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(org_id: uuid.UUID, project_id: uuid.UUID, db: DB, _: CurrentKey) -> None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == org_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.delete(project)
    await db.flush()
