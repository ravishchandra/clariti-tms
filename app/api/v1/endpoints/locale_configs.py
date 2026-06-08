from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedLocaleConfig, ScopedProject
from app.api.v1.schemas.common import ListResponse
from app.api.v1.schemas.locale_configs import (
    LocaleConfigActivationResult,
    LocaleConfigCreate,
    LocaleConfigRead,
    LocaleConfigUpdate,
)
from app.ingestion.service import FanOutValidationError, fan_out_locale
from app.models import LocaleConfig

router = APIRouter()


def _assert_config_in_project(lc: LocaleConfig, project) -> None:
    if lc.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locale config not found")


@router.post(
    "/{project_id}/locale-configs",
    response_model=LocaleConfigActivationResult,
    response_model_by_alias=True,
)
async def create_locale_config(
    body: LocaleConfigCreate,
    db: DB,
    project: ScopedProject,
    fan_out: bool = Query(
        False,
        description=(
            "Activate the locale: fan out draft Translation rows for every "
            "active key in the project and flip is_activated=true. "
            "Idempotent — re-running inserts zero rows for keys that already "
            "have a translation for this locale. Without fan_out, the endpoint "
            "only creates/finds the locale_config row (state 1: 'registered')."
        ),
    ),
) -> LocaleConfigActivationResult:
    """Upsert a locale_config row, optionally fanning out drafts.

    Returns 200 on both "row created" and "row already existed" paths.
    `already_existed` distinguishes the two for the UI. Plan v2 (docs/15)
    deliberately drops 409 here since both buttons (Add and Activate) call
    this endpoint and double-clicks should be quiet, not scary.
    """
    # Upsert semantics: pre-check, fall back on race. With ?fan_out=true the
    # caller wants this to be idempotent both at the locale_config layer AND
    # at the translations fan-out layer.
    existing = await db.scalar(
        select(LocaleConfig).where(
            LocaleConfig.project_id == project.id,
            LocaleConfig.locale == body.locale,
        )
    )

    if existing is None:
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
            # Race: another writer inserted the row between SELECT and INSERT.
            # Re-fetch and continue as if we found it.
            await db.rollback()
            refetched = await db.scalar(
                select(LocaleConfig).where(
                    LocaleConfig.project_id == project.id,
                    LocaleConfig.locale == body.locale,
                )
            )
            if refetched is None:  # genuinely failed — bubble up
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Locale config insert failed and re-fetch was empty.",
                )
            lc = refetched
            already_existed = True
        else:
            already_existed = False
    else:
        lc = existing
        already_existed = True

    drafts_created = 0
    if fan_out:
        try:
            drafts_created = await fan_out_locale(db, str(project.id), body.locale)
        except FanOutValidationError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": exc.code, "message": str(exc)},
            )
        # Once any drafts exist (or we re-confirmed there's nothing to add),
        # mark the locale as activated so the UI moves out of state 1.
        lc.is_activated = True
        await db.flush()

    await db.commit()
    await db.refresh(lc)

    return LocaleConfigActivationResult(
        locale_config=LocaleConfigRead.model_validate(lc),
        drafts_created=drafts_created,
        already_existed=already_existed,
    )


@router.get(
    "/{project_id}/locale-configs",
    response_model=ListResponse[LocaleConfigRead],
    response_model_by_alias=True,
)
async def list_locale_configs(db: DB, project: ScopedProject) -> dict:
    total_result = await db.execute(
        select(func.count()).select_from(LocaleConfig).where(LocaleConfig.project_id == project.id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(LocaleConfig).where(LocaleConfig.project_id == project.id).order_by(LocaleConfig.locale)
    )
    configs = result.scalars().all()
    # response_model_by_alias keeps the JSON field as `register` per L2 alias contract.
    return {
        "items": [LocaleConfigRead.model_validate(lc) for lc in configs],
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
    # DB column is `register`; remap before applying. `bootstrap_state` is
    # the only PATCH-able JSONB field — explicit null clears it (used when
    # the wizard finishes or the admin abandons it).
    #
    # We can't use exclude_none=True here because callers legitimately want
    # to clear bootstrap_state by sending `null`. Use exclude_unset so omitted
    # fields don't accidentally null out columns.
    updates = body.model_dump(exclude_unset=True, by_alias=False)
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
