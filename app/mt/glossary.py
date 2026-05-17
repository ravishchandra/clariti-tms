from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GlossaryTerm


async def load_glossary(
    db: AsyncSession, project_id: str, locale: str
) -> list[dict]:
    rows = await db.scalars(
        select(GlossaryTerm)
        .where(
            GlossaryTerm.project_id == uuid.UUID(project_id),
            GlossaryTerm.locale == locale,
        )
        .order_by(func.length(GlossaryTerm.source_term).desc())
    )
    return [
        {
            "source_term": r.source_term,
            "target_term": r.target_term,
            "do_not_translate": r.do_not_translate,
            "notes": r.notes,
        }
        for r in rows
    ]


def format_glossary_for_prompt(terms: list[dict]) -> str:
    if not terms:
        return "No glossary entries for this locale."
    lines = []
    for t in terms:
        if t["do_not_translate"]:
            line = f'"{t["source_term"]}" → DO NOT TRANSLATE'
        else:
            line = f'"{t["source_term"]}" → "{t["target_term"]}"'
            if t.get("notes"):
                line += f' [{t["notes"]}]'
        lines.append(line)
    return "\n".join(lines)
