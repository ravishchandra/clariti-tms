from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentKey, DB
from app.api.v1.schemas.glossary import GlossaryTermCreate, GlossaryTermRead, GlossaryTermUpdate
from app.models import GlossaryTerm, Project

router = APIRouter()


@router.post("/{project_id}/glossary", response_model=GlossaryTermRead, status_code=status.HTTP_201_CREATED)
async def create_glossary_term(
    project_id: uuid.UUID, body: GlossaryTermCreate, db: DB, current_key: CurrentKey
) -> GlossaryTermRead:
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    term = GlossaryTerm(
        project_id=project_id,
        source_term=body.source_term,
        locale=body.locale,
        target_term=body.target_term,
        case_sensitive=body.case_sensitive,
        do_not_translate=body.do_not_translate,
        notes=body.notes,
    )
    db.add(term)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Glossary term already exists for this source_term/locale",
        )
    await db.refresh(term)
    return GlossaryTermRead.model_validate(term)


@router.get("/{project_id}/glossary", response_model=dict)
async def list_glossary_terms(project_id: uuid.UUID, db: DB, _: CurrentKey) -> dict:
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    total_result = await db.execute(
        select(func.count()).select_from(GlossaryTerm).where(GlossaryTerm.project_id == project_id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.project_id == project_id)
        .order_by(GlossaryTerm.locale, GlossaryTerm.source_term)
    )
    terms = result.scalars().all()
    return {"items": [GlossaryTermRead.model_validate(t) for t in terms], "total": total}


@router.get("/{project_id}/glossary/{term_id}", response_model=GlossaryTermRead)
async def get_glossary_term(
    project_id: uuid.UUID, term_id: uuid.UUID, db: DB, _: CurrentKey
) -> GlossaryTermRead:
    result = await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.id == term_id, GlossaryTerm.project_id == project_id)
    )
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")
    return GlossaryTermRead.model_validate(term)


@router.patch("/{project_id}/glossary/{term_id}", response_model=GlossaryTermRead)
async def update_glossary_term(
    project_id: uuid.UUID, term_id: uuid.UUID, body: GlossaryTermUpdate, db: DB, _: CurrentKey
) -> GlossaryTermRead:
    result = await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.id == term_id, GlossaryTerm.project_id == project_id)
    )
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(term, field, value)
    await db.flush()
    await db.refresh(term)
    return GlossaryTermRead.model_validate(term)


@router.delete("/{project_id}/glossary/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_glossary_term(
    project_id: uuid.UUID, term_id: uuid.UUID, db: DB, _: CurrentKey
) -> None:
    result = await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.id == term_id, GlossaryTerm.project_id == project_id)
    )
    term = result.scalar_one_or_none()
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")
    await db.delete(term)
    await db.flush()
