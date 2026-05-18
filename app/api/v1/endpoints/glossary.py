from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, ScopedGlossaryTerm, ScopedProject
from app.api.v1.schemas.glossary import GlossaryTermCreate, GlossaryTermRead, GlossaryTermUpdate
from app.models import GlossaryTerm

router = APIRouter()


@router.post("/{project_id}/glossary", response_model=GlossaryTermRead, status_code=status.HTTP_201_CREATED)
async def create_glossary_term(body: GlossaryTermCreate, db: DB, project: ScopedProject) -> GlossaryTermRead:
    term = GlossaryTerm(
        project_id=project.id,
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
async def list_glossary_terms(db: DB, project: ScopedProject) -> dict:
    total_result = await db.execute(
        select(func.count()).select_from(GlossaryTerm).where(GlossaryTerm.project_id == project.id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.project_id == project.id)
        .order_by(GlossaryTerm.locale, GlossaryTerm.source_term)
    )
    terms = result.scalars().all()
    return {"items": [GlossaryTermRead.model_validate(t) for t in terms], "total": total}


# For per-term routes the URL pins both `project_id` and `term_id`. ScopedProject
# verifies the project belongs to the caller's org, and ScopedGlossaryTerm verifies
# the term belongs to (some project in) the caller's org. We then assert the term
# is the one under the URL-pinned project, preserving the original URL semantics.
def _assert_term_in_project(term: GlossaryTerm, project) -> None:
    if term.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")


@router.get("/{project_id}/glossary/{term_id}", response_model=GlossaryTermRead)
async def get_glossary_term(project: ScopedProject, term: ScopedGlossaryTerm) -> GlossaryTermRead:
    _assert_term_in_project(term, project)
    return GlossaryTermRead.model_validate(term)


@router.patch("/{project_id}/glossary/{term_id}", response_model=GlossaryTermRead)
async def update_glossary_term(
    body: GlossaryTermUpdate, db: DB, project: ScopedProject, term: ScopedGlossaryTerm
) -> GlossaryTermRead:
    _assert_term_in_project(term, project)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(term, field, value)
    await db.flush()
    await db.refresh(term)
    return GlossaryTermRead.model_validate(term)


@router.delete("/{project_id}/glossary/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_glossary_term(db: DB, project: ScopedProject, term: ScopedGlossaryTerm) -> None:
    _assert_term_in_project(term, project)
    await db.delete(term)
    await db.flush()
