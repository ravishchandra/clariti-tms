"""TMX export and import for translation memory exchange."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TranslationMemory


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


async def export_tmx(
    db: AsyncSession,
    project_id: str,
    locale: str,
    output_path: Path,
    source_locale: str = "en-US",
) -> int:
    """Export TM entries for *locale* to a TMX file. Returns entry count."""
    rows = await db.scalars(
        select(TranslationMemory).where(
            TranslationMemory.project_id == uuid.UUID(project_id),
            TranslationMemory.locale == locale,
        )
    )
    entries = list(rows)

    root = ET.Element("tmx", version="1.4")
    header = ET.SubElement(
        root,
        "header",
        creationtool="clariti-tms",
        creationtoolversion="1.0",
        datatype="PlainText",
        segtype="phrase",
        adminlang="en-US",
        srclang=source_locale,
        o_tmf="clariti",
    )
    header.set("creationdate", _now_iso())

    body = ET.SubElement(root, "body")
    for entry in entries:
        tu = ET.SubElement(body, "tu")
        tu.set("creationdate", _now_iso())

        tuv_src = ET.SubElement(tu, "tuv")
        tuv_src.set("{http://www.w3.org/XML/1998/namespace}lang", source_locale)
        ET.SubElement(tuv_src, "seg").text = entry.source_text

        tuv_tgt = ET.SubElement(tu, "tuv")
        tuv_tgt.set("{http://www.w3.org/XML/1998/namespace}lang", locale)
        ET.SubElement(tuv_tgt, "seg").text = entry.target_text

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    output_path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return len(entries)


async def import_tmx(
    db: AsyncSession,
    project_id: str,
    tmx_path: Path,
    platform: str = "web",
) -> dict[str, int]:
    """Import TM entries from a TMX file. Returns {imported, skipped}."""
    tree = ET.parse(tmx_path)
    root = tree.getroot()

    imported = 0
    skipped = 0

    for tu in root.findall(".//tu"):
        tuvs = tu.findall("tuv")
        src_text: str | None = None
        tgt_text: str | None = None
        tgt_locale: str | None = None

        for tuv in tuvs:
            lang = tuv.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            seg = tuv.find("seg")
            if seg is None or not seg.text:
                continue
            # First non-source lang is treated as target
            if lang.lower().startswith("en"):
                src_text = seg.text.strip()
            else:
                tgt_text = seg.text.strip()
                tgt_locale = lang

        if not src_text or not tgt_text or not tgt_locale:
            skipped += 1
            continue

        existing = await db.scalar(
            select(TranslationMemory).where(
                TranslationMemory.project_id == uuid.UUID(project_id),
                TranslationMemory.locale == tgt_locale,
                TranslationMemory.source_text == src_text,
            )
        )
        if existing:
            existing.target_text = tgt_text
        else:
            db.add(
                TranslationMemory(
                    project_id=uuid.UUID(project_id),
                    locale=tgt_locale,
                    source_text=src_text,
                    target_text=tgt_text,
                    platform=platform,
                )
            )
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped}
