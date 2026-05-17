from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.locale_configs import LocaleConfigCreate, LocaleConfigRead, LocaleConfigUpdate
from app.models import LocaleConfig, Project

router = APIRouter()


@router.post("/{project_id}/locale-configs", response_model=LocaleConfigRead, status_code=status.HTTP_201_CREATED)
async def create_locale_config(
    project_id: uuid.UUID, body: LocaleConfigCreate, db: DB, _: CurrentKey
) -> LocaleConfigRead:
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    lc = LocaleConfig(
        project_id=project_id,
        locale=body.locale,
        formality=body.formality,
        register=body.register,
        notes=body.notes,
        is_bootstrapped=body.is_bootstrapped,
    )
    db.add(lc)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Locale config already exists for this locale")
    await db.refresh(lc)
    return LocaleConfigRead.model_validate(lc)


@router.get("/{project_id}/locale-configs", response_model=dict)
async def list_locale_configs(project_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    total_result = await db.execute(
        select(func.count()).select_from(LocaleConfig).where(LocaleConfig.project_id == project_id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.project_id == project_id).order_by(LocaleConfig.locale)
    )
    configs = result.scalars().all()
    return {"items": [LocaleConfigRead.model_validate(lc) for lc in configs], "total": total}


@router.get("/{project_id}/locale-configs/{config_id}", response_model=LocaleConfigRead)
async def get_locale_config(
    project_id: uuid.UUID, config_id: uuid.UUID, db: DB, _: CurrentKey
) -> LocaleConfigRead:
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.id == config_id, LocaleConfig.project_id == project_id)
    )
    lc = result.scalar_one_or_none()
    if lc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locale config not found")
    return LocaleConfigRead.model_validate(lc)


@router.patch("/{project_id}/locale-configs/{config_id}", response_model=LocaleConfigRead)
async def update_locale_config(
    project_id: uuid.UUID, config_id: uuid.UUID, body: LocaleConfigUpdate, db: DB, _: CurrentKey
) -> LocaleConfigRead:
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.id == config_id, LocaleConfig.project_id == project_id)
    )
    lc = result.scalar_one_or_none()
    if lc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locale config not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(lc, field, value)
    await db.flush()
    await db.refresh(lc)
    return LocaleConfigRead.model_validate(lc)


@router.delete("/{project_id}/locale-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_locale_config(
    project_id: uuid.UUID, config_id: uuid.UUID, db: DB, _: CurrentKey
) -> None:
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.id == config_id, LocaleConfig.project_id == project_id)
    )
    lc = result.scalar_one_or_none()
    if lc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locale config not found")
    await db.delete(lc)
    await db.flush()
