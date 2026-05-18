from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedLocaleConfig, ScopedProject
from app.api.v1.schemas.locale_configs import LocaleConfigCreate, LocaleConfigRead, LocaleConfigUpdate
from app.models import LocaleConfig

router = APIRouter()


def _assert_config_in_project(lc: LocaleConfig, project) -> None:
    if lc.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locale config not found")


@router.post(
    "/{project_id}/locale-configs",
    response_model=LocaleConfigRead,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_locale_config(body: LocaleConfigCreate, db: DB, project: ScopedProject) -> LocaleConfigRead:
    lc = LocaleConfig(
        project_id=project.id,
        locale=body.locale,
        formality=body.formality,
        register=body.register_value,
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
async def list_locale_configs(db: DB, project: ScopedProject) -> dict:
    total_result = await db.execute(
        select(func.count()).select_from(LocaleConfig).where(LocaleConfig.project_id == project.id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.project_id == project.id).order_by(LocaleConfig.locale)
    )
    configs = result.scalars().all()
    # `by_alias=True` keeps the JSON field as `register` per L2 alias contract.
    return {
        "items": [LocaleConfigRead.model_validate(lc).model_dump(by_alias=True) for lc in configs],
        "total": total,
    }


@router.get(
    "/{project_id}/locale-configs/{config_id}",
    response_model=LocaleConfigRead,
    response_model_by_alias=True,
)
async def get_locale_config(project: ScopedProject, lc: ScopedLocaleConfig) -> LocaleConfigRead:
    _assert_config_in_project(lc, project)
    return LocaleConfigRead.model_validate(lc)


@router.patch(
    "/{project_id}/locale-configs/{config_id}",
    response_model=LocaleConfigRead,
    response_model_by_alias=True,
)
async def update_locale_config(
    body: LocaleConfigUpdate, db: DB, project: ScopedProject, lc: ScopedLocaleConfig
) -> LocaleConfigRead:
    _assert_config_in_project(lc, project)
    # `register_value` is the Python attribute name on the schema (L2) but the
    # DB column is `register`; remap before applying.
    updates = body.model_dump(exclude_none=True)
    if "register_value" in updates:
        updates["register"] = updates.pop("register_value")
    for field, value in updates.items():
        setattr(lc, field, value)
    await db.flush()
    await db.refresh(lc)
    return LocaleConfigRead.model_validate(lc)


@router.delete("/{project_id}/locale-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_locale_config(db: DB, project: ScopedProject, lc: ScopedLocaleConfig) -> None:
    _assert_config_in_project(lc, project)
    await db.delete(lc)
    await db.flush()
