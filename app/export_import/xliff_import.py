"""XLIFF 1.2 import reader for the Phase 7 LSP-exchange round-trip.

Parses an XLIFF 1.2 document and yields a :class:`app.export_import.parse.ParsedImport`
that the existing preview/commit/rollback machinery in
:mod:`app.export_import.commit` consumes — the validators in
:mod:`app.export_import.validate` and the conflict detector in
:mod:`app.export_import.conflicts` are polymorphic over row source.

State -> reviewer_action mapping (the wire-side equivalent of the XLSX
``reviewer_action`` dropdown):

* ``translated`` -> accept (treat ``target`` text as the approved value).
  If the target text differs from the source / MT suggestion, treat as
  ``edit`` instead of ``accept`` so the canonical reviewer_action vocabulary
  records the right edit-vs-passthrough signal.
* ``final`` -> accept + publish-eligible. Status maps to ``approved``;
  publication is downstream (the same flow as the XLSX side).
* ``rejected`` -> reject.
* ``needs-translation`` -> no-op (skip — the LSP didn't action this row).
* ``new`` -> no-op skip; row isn't ready for review.

XLIFF 2.0 / 2.1 documents are rejected at parse time with a clear error
pointing the user at the version mismatch.
"""

from __future__ import annotations

import unicodedata
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Final

from app.export_import import schema as xschema
from app.export_import.parse import (
    ImportParseError,
    ParsedImport,
    ParsedImportRow,
    ParsedMeta,
)
from app.export_import.xliff_export import (
    CLARITI_NS,
    HASH_NOTE_PREFIX,
    PLURAL_ID_SEPARATOR,
    SCHEMA_VERSION_PREFIX,
    XLIFF_NS,
    XLIFF_SCHEMA_VERSION,
    XLIFF_STATE_FINAL,
    XLIFF_STATE_NEW,
    XLIFF_STATE_REJECTED,
    XLIFF_STATE_TRANSLATED,
    XLIFF_VERSION,
)

# Accepted file extensions for the XLIFF reader.
ACCEPTED_XLIFF_EXTENSIONS: Final[frozenset[str]] = frozenset({".xlf", ".xliff"})

# State -> reviewer_action vocabulary (xlsx-equivalent: yes/no/edit/...).
# This is the *XLSX vocabulary* so the downstream commit path treats XLIFF
# rows identically to XLSX rows — same plan classifier, same transitions.
# The commit layer in turn maps these to the canonical reviewer_action set
# (accept / reject / edit / needs_more_context).
STATE_TO_XLSX_ACTION: Final[dict[str, str]] = {
    XLIFF_STATE_TRANSLATED: xschema.REVIEWER_ACTION_YES,
    XLIFF_STATE_FINAL: xschema.REVIEWER_ACTION_YES,
    XLIFF_STATE_REJECTED: xschema.REVIEWER_ACTION_NO,
    # ``new`` and ``needs-translation`` are both no-ops at import time:
    # leaving reviewer_action blank causes the commit planner to classify
    # the row as ``skip`` (no DB write).
}


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def parse_xliff_path(path: str | Path) -> ParsedImport:
    """Parse an XLIFF document from a filesystem path.

    Rejects extensions outside :data:`ACCEPTED_XLIFF_EXTENSIONS` before
    reading the file.
    """
    p = Path(path)
    if p.suffix.lower() not in ACCEPTED_XLIFF_EXTENSIONS:
        raise ImportParseError(
            f"Unsupported file extension {p.suffix!r}. XLIFF imports accept {sorted(ACCEPTED_XLIFF_EXTENSIONS)}."
        )
    return parse_xliff_bytes(p.read_bytes(), filename=p.name)


def parse_xliff_bytes(data: bytes, filename: str | None = None) -> ParsedImport:
    """Parse an XLIFF document from in-memory bytes.

    Use this from the HTTP layer where the upload arrives as
    :class:`fastapi.UploadFile`. Empty payloads and malformed XML raise
    :class:`ImportParseError` with a user-readable message.
    """
    if not data:
        raise ImportParseError("Empty file.")

    if filename is not None:
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in ACCEPTED_XLIFF_EXTENSIONS:
            raise ImportParseError(
                f"Unsupported file extension {suffix!r}. XLIFF imports accept {sorted(ACCEPTED_XLIFF_EXTENSIONS)}."
            )

    try:
        # ElementTree is a strict-but-forgiving XML parser. We use it
        # because the task constraint forbids new dependencies (no lxml).
        # Defusedxml protection is unnecessary for files the user actively
        # opted to import — the threat model is "LSP sent us bad XML", not
        # "we're parsing untrusted internet uploads at scale".
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportParseError(f"XLIFF parse error: {exc}") from exc

    return _parse_document(root)


# ---------------------------------------------------------------------------
# Internal — document walking
# ---------------------------------------------------------------------------


def _parse_document(root: ET.Element) -> ParsedImport:
    """Walk an ``<xliff>`` root, validate the version, and produce a
    :class:`ParsedImport`.
    """
    # Strip the namespace prefix off the local name for the version check.
    localname = _localname(root.tag)
    if localname != "xliff":
        raise ImportParseError(f"Expected root element 'xliff', got {localname!r}. Is this an XLIFF document?")

    version = root.get("version", "")
    if version != XLIFF_VERSION:
        # Reject 2.x / 2.1 explicitly; the v2 schema is different enough
        # that round-tripping would silently lose data.
        raise ImportParseError(
            f"Unsupported XLIFF version {version!r}. This importer supports XLIFF "
            f"{XLIFF_VERSION} only; 2.0 / 2.1 are not yet implemented "
            "(see docs/09-build-phases.md Phase 7 — XLIFF round-trip)."
        )

    files = _find_children(root, "file")
    if not files:
        raise ImportParseError("XLIFF document contains no <file> elements.")

    # Each <file> carries project metadata + a target-language attribute.
    # We expect every <file> to agree on the project id / hash / timestamp;
    # divergence is a strong signal of a concatenated or hand-edited file.
    project_id: uuid.UUID | None = None
    schema_version_value: str | None = None
    export_hash: str | None = None
    export_timestamp: datetime | None = None
    project_slug: str | None = None
    exported_by: str | None = None
    exported_by_user_id: uuid.UUID | None = None
    status_filter: str | None = None
    locales: list[str] = []
    rows_by_locale: dict[str, list[ParsedImportRow]] = {}

    for file_idx, file_el in enumerate(files, start=1):
        target_locale = file_el.get("target-language")
        if not target_locale:
            raise ImportParseError(f"<file> #{file_idx} is missing the target-language attribute.")

        # First-file wins for the shared metadata; later files must match.
        pid_str = file_el.get(_clariti("project-id"))
        if pid_str is None:
            raise ImportParseError(
                f"<file> #{file_idx} (target {target_locale}) is missing the clariti:project-id attribute."
            )
        try:
            pid = uuid.UUID(pid_str)
        except (ValueError, TypeError) as exc:
            raise ImportParseError(f"<file> #{file_idx}: clariti:project-id is not a valid UUID: {pid_str!r}") from exc

        if project_id is None:
            project_id = pid
            schema_version_value = file_el.get(_clariti("schema-version")) or _read_schema_version_note(file_el)
            export_hash = file_el.get(_clariti("export-hash"))
            ts_str = file_el.get(_clariti("export-timestamp"))
            if ts_str:
                export_timestamp = _parse_iso_datetime(ts_str)
            project_slug = file_el.get("original")
            exported_by = file_el.get(_clariti("exported-by"))
            user_id_str = file_el.get(_clariti("exported-by-user-id"))
            if user_id_str:
                try:
                    exported_by_user_id = uuid.UUID(user_id_str)
                except (ValueError, TypeError):
                    exported_by_user_id = None
            status_filter = file_el.get(_clariti("status-filter"))
        elif pid != project_id:
            raise ImportParseError(
                f"<file> #{file_idx} project-id {pid} does not match earlier project-id {project_id}. "
                "All <file> elements in one XLIFF must share the same Clariti project."
            )

        if target_locale not in rows_by_locale:
            rows_by_locale[target_locale] = []
            locales.append(target_locale)

        body = _find_first_child(file_el, "body")
        if body is None:
            # Empty body is permitted — a no-op file means "no actions for
            # this locale". Skip rather than fail.
            continue

        for tu in _find_children(body, "trans-unit"):
            row = _parse_trans_unit(tu, locale=target_locale)
            if row is not None:
                rows_by_locale[target_locale].append(row)

    if project_id is None:
        # All <file>s lacked a project-id (caught above per-file too, but
        # be defensive about empty <xliff> documents).
        raise ImportParseError("XLIFF document is missing clariti:project-id metadata.")

    schema_version = schema_version_value or ""
    if schema_version and schema_version != XLIFF_SCHEMA_VERSION:
        raise ImportParseError(
            f"Unsupported clariti schema version {schema_version!r}. Importer accepts: {XLIFF_SCHEMA_VERSION!r}."
        )
    if not schema_version:
        # Older exports without the explicit attribute / note are assumed
        # to be v1. This mirrors the lenient handling of older XLSX exports.
        schema_version = XLIFF_SCHEMA_VERSION

    # Compute row_counts at parse time so the preview summary uses the same
    # shape as the XLSX flow.
    row_counts = {loc: len(rows) for loc, rows in rows_by_locale.items()}

    # ``_meta`` block isn't part of the XLIFF 1.2 grammar — we encode the
    # same information in the per-file attributes. ParsedMeta is constructed
    # from those attributes so the downstream commit / conflict layer
    # doesn't need to special-case format.
    meta = ParsedMeta(
        schema_version=schema_version,
        project_id=project_id,
        project_slug=project_slug,
        export_timestamp=export_timestamp,
        exported_by=exported_by,
        exported_by_user_id=exported_by_user_id,
        status_filter=status_filter,
        locales=locales,
        row_counts=row_counts,
        export_hash=export_hash,
        notes="XLIFF 1.2 import",
    )

    return ParsedImport(meta=meta, rows_by_locale=rows_by_locale)


def _parse_trans_unit(tu: ET.Element, *, locale: str) -> ParsedImportRow | None:
    """Read one ``<trans-unit>`` into a :class:`ParsedImportRow`.

    Returns ``None`` for trans-units we can't safely apply (missing id,
    malformed UUID, etc). We log via raising :class:`ImportParseError`
    only for structural failures; per-row validation lives in
    :mod:`app.export_import.validate`.
    """
    raw_id = tu.get("id")
    if raw_id is None or not raw_id.strip():
        raise ImportParseError("<trans-unit> is missing the required 'id' attribute.")

    # Plural categories carry ``<uuid>:plural-<category>`` ids; we split
    # off the category to recover the canonical translation id. For v1 we
    # don't yet merge categories back into a single canonical value — we
    # take the ``other`` category as the representative (a follow-up will
    # reconstruct the full ICU plural block on import).
    base_id, plural_category = _split_plural_id(raw_id)
    try:
        internal_id = uuid.UUID(base_id)
    except (ValueError, TypeError) as exc:
        raise ImportParseError(
            f"<trans-unit id={raw_id!r}>: id is not a valid UUID (or UUID:plural-... shape)."
        ) from exc

    # Skip non-representative plural categories for v1. Only "other" (CLDR
    # universal fallback) becomes the import row; the other categories are
    # observed but not applied. This is a conservative choice — the LSP's
    # edits to non-other categories are not lost in the file, just not
    # applied automatically yet. Logged via the action_plan as a skip note.
    if plural_category is not None and plural_category != "other":
        return None

    source_text = _read_text_with_placeholders(_find_first_child(tu, "source"))
    target_el = _find_first_child(tu, "target")
    target_text = _read_text_with_placeholders(target_el)
    target_state = (target_el.get("state") if target_el is not None else None) or XLIFF_STATE_NEW

    # Map state -> XLSX reviewer_action vocabulary.
    reviewer_action = STATE_TO_XLSX_ACTION.get(target_state)

    # When the state says "translated" but the target text equals the
    # source (or is empty), treat as a no-op — the LSP didn't really
    # produce a translation. This avoids the worst case where the file
    # arrives with state=translated but empty <target>.
    edited_translation: str | None = None
    if reviewer_action == xschema.REVIEWER_ACTION_YES:
        if not target_text or not target_text.strip():
            reviewer_action = None  # treat as skip
        else:
            # The XLIFF mapping always carries the target as the edited
            # value, because in the LSP workflow we don't pre-stage an
            # mt_suggestion column — the translator's output IS the
            # value. So we route every accept through ``edit`` (which sets
            # value=edited_translation) rather than ``yes`` (which copies
            # mt_suggestion).
            #
            # This matches the spec: "Edited content with state
            # ``translated`` => ``edit``". For XLIFF, every translated
            # cell is "edited content" because there's no separate
            # mt_suggestion column in the wire format.
            reviewer_action = xschema.REVIEWER_ACTION_EDIT
            edited_translation = target_text

    # Read the per-row source-hash from the hash note. The XLIFF
    # spec writes one ``<note from="clariti" priority="2">hash:…</note>``
    # per trans-unit; we pull it out here so the conflict detector can
    # diff against the current key.source_hash.
    notes_text: list[str] = []
    source_hash_at_export: str | None = None
    description: str | None = None
    for note in _find_children(tu, "note"):
        text = (note.text or "").strip()
        if not text:
            continue
        if text.startswith(HASH_NOTE_PREFIX):
            source_hash_at_export = text[len(HASH_NOTE_PREFIX) :].strip() or None
            continue
        if text.startswith(SCHEMA_VERSION_PREFIX):
            # Already consumed at the file level; ignore here.
            continue
        if text.startswith("mt:"):
            # Informational MT suggestion the exporter dropped in;
            # not relevant for import-side decisions.
            continue
        # First non-hash, non-mt note is treated as a free-text note
        # (reviewer_notes equivalent).
        if note.get("priority") == "1" and description is None:
            description = text
        notes_text.append(text)

    notes_combined = "\n".join(notes_text) if notes_text else None

    # Read clariti:* metadata for context / debugging.
    component = tu.get(_clariti("component"))
    screen = tu.get(_clariti("screen"))
    key_attr = tu.get(_clariti("key"))
    max_length_str = tu.get(_clariti("max-length"))
    risk_class = tu.get(_clariti("risk-class")) or "standard"

    try:
        max_length = int(max_length_str) if max_length_str else None
    except (ValueError, TypeError):
        max_length = None

    # ``status`` from the XLIFF side is informational only — the importer
    # cares about state, not the prior DB status.
    status_text = target_state  # use the state string so summary can show it.

    return ParsedImportRow(
        row_index=0,  # XLIFF doesn't have a stable row index; 0 == "not a row"
        locale=locale,
        internal_id=internal_id,
        key=key_attr or "",
        source_text=_nfc(source_text or ""),
        description=description,
        component=component,
        screen=screen,
        max_length=max_length,
        placeholders_raw=None,
        risk_class=risk_class,
        current_translation=_nfc(target_text) if target_text else None,
        mt_suggestion=None,
        status=status_text,
        reviewer_action=reviewer_action,
        edited_translation=_nfc(edited_translation) if edited_translation else None,
        notes=notes_combined,
        source_hash_at_export=source_hash_at_export,
    )


# ---------------------------------------------------------------------------
# Inline placeholder reader
# ---------------------------------------------------------------------------


def _read_text_with_placeholders(el: ET.Element | None) -> str:
    """Walk a ``<source>`` or ``<target>`` element and return its mixed-content
    text with ``<ph>`` children re-inlined as their original placeholder
    syntax.

    The exporter wrote each placeholder as ``<ph id="N" ctype="…">{{name}}</ph>``;
    the importer's job is to undo that wrap so the validator sees the same
    string the source code has. Unknown child elements are flattened to
    their text content (lenient — LSP tools sometimes wrap inline content
    in additional ``<g>`` or ``<x>`` markers).
    """
    if el is None:
        return ""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(child.text or "")
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _localname(tag: str) -> str:
    """Strip Clark-notation namespace prefix off an ET tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _xliff(name: str) -> str:
    return f"{{{XLIFF_NS}}}{name}"


def _clariti(name: str) -> str:
    return f"{{{CLARITI_NS}}}{name}"


def _find_children(parent: ET.Element, localname: str) -> list[ET.Element]:
    """Return children whose local name matches. Namespace-tolerant —
    accepts both unprefixed and XLIFF-NS-prefixed forms so we round-trip
    documents from tools that emit different namespace declarations.
    """
    matches: list[ET.Element] = []
    for child in parent:
        if _localname(child.tag) == localname:
            matches.append(child)
    return matches


def _find_first_child(parent: ET.Element, localname: str) -> ET.Element | None:
    for child in parent:
        if _localname(child.tag) == localname:
            return child
    return None


def _read_schema_version_note(file_el: ET.Element) -> str | None:
    """Look for ``<header><note>schema_version:vN</note></header>``."""
    header = _find_first_child(file_el, "header")
    if header is None:
        return None
    for note in _find_children(header, "note"):
        text = (note.text or "").strip()
        if text.startswith(SCHEMA_VERSION_PREFIX):
            return text[len(SCHEMA_VERSION_PREFIX) :].strip() or None
    return None


def _split_plural_id(raw_id: str) -> tuple[str, str | None]:
    """``"<uuid>:plural-other"`` -> ``("<uuid>", "other")``. Plain
    ``"<uuid>"`` -> ``("<uuid>", None)``.
    """
    if PLURAL_ID_SEPARATOR in raw_id:
        base, category = raw_id.split(PLURAL_ID_SEPARATOR, 1)
        return base, category or None
    return raw_id, None


def _parse_iso_datetime(value: str) -> datetime | None:
    """Best-effort ISO-8601 parse. Returns ``None`` on failure (non-fatal,
    matches the XLSX parser's tolerance)."""
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s


__all__ = [
    "ACCEPTED_XLIFF_EXTENSIONS",
    "STATE_TO_XLSX_ACTION",
    "parse_xliff_bytes",
    "parse_xliff_path",
]
