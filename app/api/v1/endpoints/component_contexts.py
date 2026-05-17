from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedComponentContext, ScopedRepository
from app.api.v1.schemas.component_contexts import (
    ComponentContextCreate,
    ComponentContextRead,
    ComponentContextUpdate,
)
from app.models import ComponentContext

router = APIRouter()


def _assert_ctx_in_repo(ctx: ComponentContext, repo) -> None:
    if ctx.repository_id != repo.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component context not found")


@router.post(
    "/{repo_id}/component-contexts",
    response_model=ComponentContextRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_component_context(
    body: ComponentContextCreate, db: DB, repo: ScopedRepository
) -> ComponentContextRead:
    ctx = ComponentContext(
        repository_id=repo.id,
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
async def list_component_contexts(db: DB, repo: ScopedRepository) -> dict:
    total_result = await db.execute(
        select(func.count()).select_from(ComponentContext).where(ComponentContext.repository_id == repo.id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(ComponentContext)
        .where(ComponentContext.repository_id == repo.id)
        .order_by(ComponentContext.component, ComponentContext.screen)
    )
    contexts = result.scalars().all()
    return {"items": [ComponentContextRead.model_validate(c) for c in contexts], "total": total}


@router.get("/{repo_id}/component-contexts/{ctx_id}", response_model=ComponentContextRead)
async def get_component_context(
    repo: ScopedRepository, ctx: ScopedComponentContext
) -> ComponentContextRead:
    _assert_ctx_in_repo(ctx, repo)
    return ComponentContextRead.model_validate(ctx)


@router.patch("/{repo_id}/component-contexts/{ctx_id}", response_model=ComponentContextRead)
async def update_component_context(
    body: ComponentContextUpdate, db: DB, repo: ScopedRepository, ctx: ScopedComponentContext
) -> ComponentContextRead:
    _assert_ctx_in_repo(ctx, repo)
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
    db: DB, repo: ScopedRepository, ctx: ScopedComponentContext
) -> None:
    _assert_ctx_in_repo(ctx, repo)
    await db.delete(ctx)
    await db.flush()
