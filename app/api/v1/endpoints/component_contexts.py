from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.component_contexts import (
    ComponentContextCreate,
    ComponentContextRead,
    ComponentContextUpdate,
)
from app.models import ComponentContext, Repository

router = APIRouter()


@router.post(
    "/{repo_id}/component-contexts",
    response_model=ComponentContextRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_component_context(
    repo_id: uuid.UUID, body: ComponentContextCreate, db: DB, _: CurrentKey
) -> ComponentContextRead:
    repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
    if repo_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    ctx = ComponentContext(
        repository_id=repo_id,
        component=body.component,
        screen=body.screen,
        description=body.description,
        default_risk_class=body.default_risk_class,
        default_max_length=body.default_max_length,
        notes=body.notes,
    )
    db.add(ctx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Component context already exists for this component/screen",
        )
    await db.refresh(ctx)
    return ComponentContextRead.model_validate(ctx)


@router.get("/{repo_id}/component-contexts", response_model=dict)
async def list_component_contexts(repo_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
    if repo_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    total_result = await db.execute(
        select(func.count()).select_from(ComponentContext).where(ComponentContext.repository_id == repo_id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(ComponentContext)
        .where(ComponentContext.repository_id == repo_id)
        .order_by(ComponentContext.component, ComponentContext.screen)
    )
    contexts = result.scalars().all()
    return {"items": [ComponentContextRead.model_validate(c) for c in contexts], "total": total}


@router.get("/{repo_id}/component-contexts/{ctx_id}", response_model=ComponentContextRead)
async def get_component_context(
    repo_id: uuid.UUID, ctx_id: uuid.UUID, db: DB, _: CurrentKey
) -> ComponentContextRead:
    result = await db.execute(
        select(ComponentContext).where(
            ComponentContext.id == ctx_id, ComponentContext.repository_id == repo_id
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component context not found")
    return ComponentContextRead.model_validate(ctx)


@router.patch("/{repo_id}/component-contexts/{ctx_id}", response_model=ComponentContextRead)
async def update_component_context(
    repo_id: uuid.UUID, ctx_id: uuid.UUID, body: ComponentContextUpdate, db: DB, _: CurrentKey
) -> ComponentContextRead:
    result = await db.execute(
        select(ComponentContext).where(
            ComponentContext.id == ctx_id, ComponentContext.repository_id == repo_id
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component context not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(ctx, field, value)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Component context already exists for this component/screen",
        )
    await db.refresh(ctx)
    return ComponentContextRead.model_validate(ctx)


@router.delete("/{repo_id}/component-contexts/{ctx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component_context(
    repo_id: uuid.UUID, ctx_id: uuid.UUID, db: DB, _: CurrentKey
) -> None:
    result = await db.execute(
        select(ComponentContext).where(
            ComponentContext.id == ctx_id, ComponentContext.repository_id == repo_id
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component context not found")
    await db.delete(ctx)
    await db.flush()
