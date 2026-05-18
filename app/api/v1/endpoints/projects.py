from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentKey, ScopedOrganization, ScopedProject
from app.api.v1.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from app.models import Project

router = APIRouter()


@router.post("/{org_id}/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, db: DB, org: ScopedOrganization) -> ProjectRead:
    project = Project(
        organization_id=org.id,
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
async def list_projects(db: DB, org: ScopedOrganization) -> dict:
    total_result = await db.execute(select(func.count()).select_from(Project).where(Project.organization_id == org.id))
    total = total_result.scalar_one()
    result = await db.execute(
        select(Project).where(Project.organization_id == org.id).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return {"items": [ProjectRead.model_validate(p) for p in projects], "total": total}


# NB: ScopedProject already restricts to the caller's org by JOIN against
# Project.organization_id. The {org_id} path segment is therefore only a
# routing convenience — if it doesn't match the project's actual org the
# scoped helper returns 404.
@router.get("/{org_id}/projects/{project_id}", response_model=ProjectRead)
async def get_project(project: ScopedProject, _: CurrentKey) -> ProjectRead:
    return ProjectRead.model_validate(project)


@router.patch("/{org_id}/projects/{project_id}", response_model=ProjectRead)
async def update_project(body: ProjectUpdate, db: DB, project: ScopedProject) -> ProjectRead:
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
async def delete_project(db: DB, project: ScopedProject) -> None:
    await db.delete(project)
    await db.flush()
