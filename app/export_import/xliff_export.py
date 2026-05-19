"""XLIFF 1.2 export writer for the Phase 7 LSP-exchange round-trip.

XLIFF (XML Localisation Interchange File Format) 1.2 is the OASIS standard
most Language Service Providers (LSPs) still consume. This module mirrors
the shape of :mod:`app.export_import.export` (the XLSX writer) so the two
formats share the same DB-read path and ``ExportRequest`` semantics, just
with a different on-disk serialisation. 2.0 / 2.1 support is deferred —
see ``docs/09-build-phases.md`` Phase 7.

Wire shape (per OASIS XLIFF 1.2)
--------------------------------

::

    <xliff version="1.2"
           xmlns="urn:oasis:names:tc:xliff:document:1.2"
           xmlns:clariti="urn:clariti:tms:1">
      <file original="clariti-web" datatype="plaintext"
            source-language="en-US" target-language="fr-FR"
            clariti:project-id="<uuid>" clariti:export-hash="<sha>"
            clariti:export-timestamp="<iso>">
        <header>
          <tool tool-id="clariti-tms" tool-name="Clariti TMS"
                tool-version="0.x" />
          <note from="clariti" priority="2">schema_version:v1</note>
          <!-- ... other custom notes ... -->
        </header>
        <body>
          <trans-unit id="<translation-uuid>"
                      clariti:risk-class="standard"
                      clariti:max-length="50"
                      clariti:component="CheckoutButton"
                      clariti:screen="checkout"
                      clariti:key="checkout.button.pay"
                      approved="no">
            <source>Pay <ph id="1" ctype="x-icu-placeholder">{{amount}}</ph></source>
            <target state="needs-translation">Payer <ph id="1" ctype="x-icu-placeholder">{{amount}}</ph></target>
            <note from="clariti" priority="2">hash:abc123…</note>
            <note from="clariti" priority="3">description: Pay button label</note>
          </trans-unit>
        </body>
      </file>
    </xliff>

State mapping (``<target state="…">``)
-------------------------------------

Translation status -> XLIFF state:

* ``draft`` / ``mt_proposed`` -> ``new``
* ``needs_review`` / ``needs_more_context`` -> ``needs-translation``
* ``approved`` -> ``translated``
* ``published`` -> ``final``
* ``rejected`` -> ``rejected`` (XLIFF 1.2 allows this state value)

Plural convention
-----------------

ICU plurals serialise as one ``<trans-unit>`` per CLDR plural category. The
``id`` attribute uses the form ``<translation-uuid>:plural-<category>`` so
the import side can correlate categories back to a single translation row.
At v1 we only emit the categories present in the source ICU string; we do
not expand to the full set of CLDR categories for the target locale (a
follow-up; for now the LSP edits the categories we send).

Placeholders
------------

i18next-style ``{{name}}``, ICU bare ``{name}``, iOS ``%@`` / ``%1$d``,
Android ``%1$s``, and printf-family tokens are wrapped in
``<ph id="N" ctype="x-icu-placeholder">…</ph>`` elements. LSPs see the
placeholder as an inline tag rather than as raw text, which avoids them
"translating" it.

The hash custom note (``<note from="clariti" priority="2">hash:…</note>``)
carries the source ``source_hash`` at export time so the import side can
detect ``source_changed`` conflicts (mirrors the XLSX
``_source_hash_at_export`` column).

Conventions
-----------

* All strings are NFC-normalised on the way out.
* All datetimes are rendered ISO-8601 UTC with a trailing ``Z``.
* The XML declaration is included on the first line so the file
  round-trips through `lxml`-based LSP tooling.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Final

from app.export_import.export import (
    ExportRequest,
    ExportRow,
    _iso_utc,
    compute_export_hash,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Namespaces & constants
# ---------------------------------------------------------------------------

XLIFF_VERSION: Final[str] = "1.2"
XLIFF_NS: Final[str] = "urn:oasis:names:tc:xliff:document:1.2"
CLARITI_NS: Final[str] = "urn:clariti:tms:1"

# XLIFF 1.2 ``<target state="…">`` values used by this exporter.
# https://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#state
XLIFF_STATE_NEW: Final[str] = "new"
XLIFF_STATE_NEEDS_TRANSLATION: Final[str] = "needs-translation"
XLIFF_STATE_TRANSLATED: Final[str] = "translated"
XLIFF_STATE_FINAL: Final[str] = "final"
XLIFF_STATE_REJECTED: Final[str] = "rejected"

# Translation status -> XLIFF state. Symmetric with
# :data:`app.export_import.xliff_import.STATE_TO_STATUS`.
STATUS_TO_STATE: Final[dict[str, str]] = {
    "draft": XLIFF_STATE_NEW,
    "mt_proposed": XLIFF_STATE_NEW,
    "needs_review": XLIFF_STATE_NEEDS_TRANSLATION,
    "needs_more_context": XLIFF_STATE_NEEDS_TRANSLATION,
    "approved": XLIFF_STATE_TRANSLATED,
    "published": XLIFF_STATE_FINAL,
    "rejected": XLIFF_STATE_REJECTED,
}

# ctype value used for every placeholder we wrap. ``x-`` prefix marks it as
# a custom (non-XLIFF-canonical) ctype, which is the correct OASIS
# convention for tool-specific placeholder kinds.
CLARITI_PH_CTYPE: Final[str] = "x-icu-placeholder"

# Hash-note prefix written into the ``<note priority="2" from="clariti">``
# child of each ``<trans-unit>``. The import side strips this prefix to
# recover the per-row source-hash-at-export.
HASH_NOTE_PREFIX: Final[str] = "hash:"
SCHEMA_VERSION_PREFIX: Final[str] = "schema_version:"

# XLIFF schema version we emit. Bumping this is a wire-breaking change
# (mirrors the XLSX SCHEMA_VERSION discipline in
# :mod:`app.export_import.schema`).
XLIFF_SCHEMA_VERSION: Final[str] = "v1"

# Suffix added to the ``id`` attribute on per-category plural trans-units.
# Convention: ``<translation-uuid>:plural-<cldr-category>`` (e.g.
# ``…:plural-one``, ``…:plural-other``). The import side splits on the
# colon to recover the canonical translation id.
PLURAL_ID_SEPARATOR: Final[str] = ":plural-"


# ---------------------------------------------------------------------------
# Placeholder extraction
# ---------------------------------------------------------------------------

# Order matters: try the most-specific pattern first so we don't double-
# match. Each pattern is a compiled regex; the wrapper iterates them in
# order and replaces matched spans with ``<ph>`` markers.

# i18next double-curly is the most common in this codebase.
_RE_I18NEXT: Final[re.Pattern[str]] = re.compile(r"\{\{[^}]+\}\}")
# iOS / printf positional and unnumbered placeholders.
_RE_PRINTF_POS: Final[re.Pattern[str]] = re.compile(r"%\d+\$[@dsfilu]")
_RE_PRINTF: Final[re.Pattern[str]] = re.compile(r"%[@dsfilu]")
# ICU bare-variable inside a string. We deliberately do not match the
# enclosing ICU plural / select block; the plural-splitting path handles
# those at the per-category level. Inside a category the variables are
# bare ``{name}``.
_RE_ICU_BARE: Final[re.Pattern[str]] = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")

# Pattern union evaluated in priority order. The first regex to match a
# span wins; the consumer string-walks left-to-right and skips past matched
# spans.
_PLACEHOLDER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    _RE_I18NEXT,
    _RE_PRINTF_POS,
    _RE_PRINTF,
    _RE_ICU_BARE,
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def export_to_xliff_bytes(request: ExportRequest) -> bytes:
    """Build an XLIFF 1.2 document from an :class:`ExportRequest` and
    serialise it to bytes.

    Pure / deterministic given the same input. The DB-read step (turning a
    project + locales into :class:`ExportRow` instances) is the same
    :func:`app.export_import.export.fetch_export_rows` the XLSX writer
    uses; callers handle that before invoking us.
    """
    root = _build_xliff_document(request)
    # ``short_empty_elements=False`` keeps ``<target></target>`` rather than
    # the ``<target />`` self-closing form, which a handful of LSP tools
    # parse more reliably (especially older Trados versions).
    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=False,
    )


def build_filename(
    project_slug: str,
    locales: list[str],
    status_filter: str | None,
    export_timestamp: datetime,
) -> str:
    """``{slug}_{locales}_{YYYY-MM-DD}_{status}.xlf``.

    Mirrors :func:`app.export_import.export.build_filename` but produces an
    ``.xlf`` extension (the conventional XLIFF 1.2 suffix; some tools also
    accept ``.xliff``, but ``.xlf`` is the most widely-supported short
    form).
    """
    date_part = export_timestamp.strftime("%Y-%m-%d")
    locale_part = locales[0] if len(locales) == 1 else "multi"
    status_part = (status_filter or "all").replace("_", "-")
    return f"{project_slug}_{locale_part}_{date_part}_{status_part}.xlf"


# ---------------------------------------------------------------------------
# Internal — XML builders
# ---------------------------------------------------------------------------


def _build_xliff_document(request: ExportRequest) -> ET.Element:
    """Build the root ``<xliff>`` element. One ``<file>`` child per locale."""
    # ElementTree uses Clark notation ``{namespace}localname`` for namespaced
    # element names. We register the prefixes once so the serialised output
    # uses readable ``xmlns:clariti="…"`` declarations rather than the
    # auto-generated ``ns0``/``ns1`` prefixes ET picks otherwise.
    ET.register_namespace("", XLIFF_NS)
    ET.register_namespace("clariti", CLARITI_NS)

    root = ET.Element(f"{{{XLIFF_NS}}}xliff", attrib={"version": XLIFF_VERSION})

    # Compute the export hash up front — the same algorithm + inputs as the
    # XLSX exporter, so the same import-side hash check works.
    locales = list(request.rows_by_locale.keys())
    export_hash = compute_export_hash(
        project_id=request.project_id,
        export_timestamp=request.export_timestamp,
        row_ids=[row.internal_id for locale in locales for row in request.rows_by_locale[locale]],
    )

    for locale in locales:
        rows = [r.normalised() for r in request.rows_by_locale[locale]]
        file_el = _build_file_element(
            request=request,
            target_locale=locale,
            rows=rows,
            export_hash=export_hash,
        )
        root.append(file_el)

    return root


def _build_file_element(
    *,
    request: ExportRequest,
    target_locale: str,
    rows: list[ExportRow],
    export_hash: str,
) -> ET.Element:
    """Build one ``<file>`` element (one per locale)."""
    # ``original`` is the conventional "source filename" field; we use the
    # project slug because XLIFF imports often surface this to translators.
    # ``datatype="plaintext"`` is the XLIFF 1.2 catch-all for app strings
    # (we lose per-format nuance, but no LSP tooling does anything useful
    # with the more specific datatypes for software localisation today).
    attribs: dict[str, str] = {
        "original": request.project_slug,
        "datatype": "plaintext",
        "source-language": "en-US",
        "target-language": target_locale,
        f"{{{CLARITI_NS}}}project-id": str(request.project_id),
        f"{{{CLARITI_NS}}}export-hash": export_hash,
        f"{{{CLARITI_NS}}}export-timestamp": _iso_utc(request.export_timestamp),
        f"{{{CLARITI_NS}}}schema-version": XLIFF_SCHEMA_VERSION,
    }
    if request.status_filter:
        attribs[f"{{{CLARITI_NS}}}status-filter"] = request.status_filter
    if request.exported_by_email:
        attribs[f"{{{CLARITI_NS}}}exported-by"] = request.exported_by_email
    if request.exported_by_user_id is not None:
        attribs[f"{{{CLARITI_NS}}}exported-by-user-id"] = str(request.exported_by_user_id)

    file_el = ET.Element(f"{{{XLIFF_NS}}}file", attrib=attribs)

    # ---- <header> with a single <tool> + schema_version note ---------------
    header = ET.SubElement(file_el, f"{{{XLIFF_NS}}}header")
    ET.SubElement(
        header,
        f"{{{XLIFF_NS}}}tool",
        attrib={
            "tool-id": "clariti-tms",
            "tool-name": "Clariti TMS",
            "tool-version": "0.x",
        },
    )
    _add_note(header, f"{SCHEMA_VERSION_PREFIX}{XLIFF_SCHEMA_VERSION}", priority="2")

    # ---- <body> with one <trans-unit> per row (per plural category) -------
    body = ET.SubElement(file_el, f"{{{XLIFF_NS}}}body")
    for row in rows:
        for unit in _build_trans_units_for_row(row):
            body.append(unit)

    return file_el


def _build_trans_units_for_row(row: ExportRow) -> list[ET.Element]:
    """Emit one or more ``<trans-unit>`` elements for an :class:`ExportRow`.

    Most rows produce exactly one trans-unit. Rows whose source / target
    is an ICU plural block (``{count, plural, …}``) are split into one
    trans-unit per CLDR category present in the source, with the category
    suffixed onto the trans-unit id.
    """
    source_text = row.source_text or ""
    target_text = row.current_translation or ""

    source_plural = _split_icu_plural(source_text)
    if source_plural is not None:
        target_plural = _split_icu_plural(target_text)
        return _build_plural_trans_units(row, source_plural, target_plural)

    return [_build_single_trans_unit(row, source_text, target_text, plural_category=None)]


def _build_single_trans_unit(
    row: ExportRow,
    source_text: str,
    target_text: str,
    *,
    plural_category: str | None,
) -> ET.Element:
    """Build a single ``<trans-unit>`` for a non-plural row (or one category
    of a plural row).
    """
    unit_id = str(row.internal_id)
    if plural_category is not None:
        unit_id = f"{unit_id}{PLURAL_ID_SEPARATOR}{plural_category}"

    attribs: dict[str, str] = {
        "id": unit_id,
        # ``approved="yes"`` is XLIFF's hint for "translator may not need to
        # re-touch this" and pairs with state="translated"/"final".
        "approved": "yes" if row.status in ("approved", "published") else "no",
        f"{{{CLARITI_NS}}}risk-class": row.risk_class,
    }
    if row.component:
        attribs[f"{{{CLARITI_NS}}}component"] = row.component
    if row.screen:
        attribs[f"{{{CLARITI_NS}}}screen"] = row.screen
    if row.key:
        attribs[f"{{{CLARITI_NS}}}key"] = row.key
    if row.max_length is not None:
        attribs[f"{{{CLARITI_NS}}}max-length"] = str(row.max_length)
    if plural_category is not None:
        attribs[f"{{{CLARITI_NS}}}plural-category"] = plural_category

    unit = ET.Element(f"{{{XLIFF_NS}}}trans-unit", attrib=attribs)

    # ---- <source> -------------------------------------------------------
    source_el = ET.SubElement(unit, f"{{{XLIFF_NS}}}source")
    _write_text_with_placeholders(source_el, source_text)

    # ---- <target state="…"> ---------------------------------------------
    target_state = STATUS_TO_STATE.get(row.status, XLIFF_STATE_NEW)
    target_el = ET.SubElement(
        unit,
        f"{{{XLIFF_NS}}}target",
        attrib={"state": target_state},
    )
    _write_text_with_placeholders(target_el, target_text)

    # ---- <note> children -----------------------------------------------
    # Hash carries the source_hash_at_export the importer needs to detect
    # the ``source_changed`` conflict. We use priority="2" (mid) so LSP UIs
    # surface it but not in the most-prominent position.
    source_hash = _hash_for_row(row, plural_category=plural_category)
    if source_hash:
        _add_note(unit, f"{HASH_NOTE_PREFIX}{source_hash}", priority="2", from_attr="clariti")

    # Description is high-priority for translators (it's the "context note"
    # they actually read), so priority="1".
    if row.description:
        _add_note(unit, row.description, priority="1")

    # mt_suggestion (raw MT output) — included for translators who want to
    # see what the machine produced before any edits. Marked priority="3"
    # (low) — informational.
    if row.mt_suggestion and row.mt_suggestion != target_text:
        _add_note(unit, f"mt:{row.mt_suggestion}", priority="3")

    return unit


def _build_plural_trans_units(
    row: ExportRow,
    source_categories: dict[str, str],
    target_categories: dict[str, str] | None,
) -> list[ET.Element]:
    """One ``<trans-unit>`` per plural category. Source categories drive
    the emission set (the target may be missing a category if the row is
    still draft / partial).
    """
    units: list[ET.Element] = []
    for category, source_text in source_categories.items():
        target_text = (target_categories or {}).get(category, "")
        units.append(
            _build_single_trans_unit(
                row,
                source_text,
                target_text,
                plural_category=category,
            )
        )
    return units


def _hash_for_row(row: ExportRow, *, plural_category: str | None) -> str:
    """Return the source-hash-at-export string to embed in the trans-unit.

    For v1 we compute a SHA-256 of the (normalised) source text. The XLSX
    side stores this in ``_source_hash_at_export``; we re-derive it from
    ``source_text`` so the export path doesn't need a DB query for a
    pre-computed hash.

    Plural categories don't get separate hashes — the source-hash check is
    "did the whole key change?", not "did this category change?".
    """
    del plural_category  # hashing strategy is row-level, not per-category
    if not row.source_text:
        return ""
    # Note: ``row`` has already been ``.normalised()`` by ``build_workbook``
    # / ``_build_xliff_document``, so source_text is NFC-normalised.
    return hashlib.sha256(row.source_text.encode("utf-8")).hexdigest()


def _add_note(
    parent: ET.Element,
    text: str,
    *,
    priority: str = "2",
    from_attr: str = "clariti",
) -> ET.Element:
    """Append a ``<note from="clariti" priority="N">…</note>``."""
    note = ET.SubElement(
        parent,
        f"{{{XLIFF_NS}}}note",
        attrib={"priority": priority, "from": from_attr},
    )
    note.text = _nfc(text)
    return note


# ---------------------------------------------------------------------------
# Inline placeholder writer
# ---------------------------------------------------------------------------


def _write_text_with_placeholders(parent: ET.Element, text: str) -> None:
    """Write ``text`` into ``parent`` as text + ``<ph>`` mixed content.

    Each detected placeholder becomes a ``<ph id="N" ctype="x-icu-placeholder">…</ph>``
    child. Numbering is 1-based and resets per parent element.

    ``text`` is NFC-normalised before scanning; the original placeholder
    syntax (``{{name}}``, ``%@``, ``{count}``) is preserved verbatim inside
    the ``<ph>`` element so :func:`app.export_import.xliff_import` can
    round-trip it without any format-specific knowledge.
    """
    normalised = _nfc(text or "")
    spans = _find_placeholder_spans(normalised)

    if not spans:
        parent.text = normalised
        return

    cursor = 0
    last_child: ET.Element | None = None
    for ph_index, (start, end) in enumerate(spans, start=1):
        head = normalised[cursor:start]
        if last_child is None:
            parent.text = (parent.text or "") + head
        else:
            last_child.tail = (last_child.tail or "") + head

        ph_text = normalised[start:end]
        ph = ET.SubElement(
            parent,
            f"{{{XLIFF_NS}}}ph",
            attrib={"id": str(ph_index), "ctype": CLARITI_PH_CTYPE},
        )
        ph.text = ph_text
        last_child = ph
        cursor = end

    trailing = normalised[cursor:]
    if last_child is not None and trailing:
        last_child.tail = (last_child.tail or "") + trailing


def _find_placeholder_spans(text: str) -> list[tuple[int, int]]:
    """Walk ``text`` left-to-right and return non-overlapping placeholder
    spans, picking the earliest match across all patterns at each position.

    The pattern union is small enough that a linear scan is faster (and
    simpler) than building a combined alternation regex.
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    n = len(text)
    while pos < n:
        best: tuple[int, int] | None = None
        for pattern in _PLACEHOLDER_PATTERNS:
            m = pattern.search(text, pos)
            if m is None:
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), m.end())
        if best is None:
            break
        spans.append(best)
        pos = best[1]
    return spans


# ---------------------------------------------------------------------------
# ICU plural splitter
# ---------------------------------------------------------------------------

# Match the opening of an ICU plural / selectordinal block: ``{name, plural,``.
_RE_ICU_PLURAL_OPEN: Final[re.Pattern[str]] = re.compile(
    r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(plural|selectordinal)\s*,",
)


def _split_icu_plural(text: str) -> dict[str, str] | None:
    """Parse a string that is exactly an ICU plural block and return its
    ``{category: pattern}`` map. Return ``None`` if the string isn't an
    ICU plural.

    Example input: ``{count, plural, one {# item} other {# items}}``.
    Result: ``{"one": "# item", "other": "# items"}``.

    The parser is depth-aware so nested braces inside a category's pattern
    (which are legal in ICU MessageFormat) don't break the split.
    """
    if not text:
        return None
    stripped = text.strip()
    m = _RE_ICU_PLURAL_OPEN.match(stripped)
    if m is None:
        return None

    # Skip the head (``{var, plural,``). Walk the categories.
    pos = m.end()
    n = len(stripped)
    categories: dict[str, str] = {}

    while pos < n:
        # Skip whitespace.
        while pos < n and stripped[pos].isspace():
            pos += 1
        if pos >= n:
            break
        # End-of-block: the final closing brace of the whole plural.
        if stripped[pos] == "}":
            pos += 1
            break

        # Read the category keyword. Accept CLDR keywords + ``=N`` explicit
        # cases (e.g. ``=0 {No items}``).
        cat_start = pos
        if stripped[pos] == "=":
            pos += 1
            while pos < n and stripped[pos].isdigit():
                pos += 1
        else:
            while pos < n and (stripped[pos].isalnum() or stripped[pos] == "_"):
                pos += 1
        category = stripped[cat_start:pos]
        if not category:
            return None

        # Skip whitespace.
        while pos < n and stripped[pos].isspace():
            pos += 1
        if pos >= n or stripped[pos] != "{":
            # Malformed — bail and let the caller treat as non-plural.
            return None
        pos += 1
        # Walk to the matching '}'.
        pattern_start = pos
        depth = 1
        while pos < n and depth > 0:
            ch = stripped[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        if depth != 0:
            return None
        categories[category] = stripped[pattern_start:pos]
        pos += 1  # skip the '}'

    if not categories:
        return None
    return categories


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s


__all__ = [
    "CLARITI_NS",
    "CLARITI_PH_CTYPE",
    "HASH_NOTE_PREFIX",
    "PLURAL_ID_SEPARATOR",
    "STATUS_TO_STATE",
    "XLIFF_NS",
    "XLIFF_SCHEMA_VERSION",
    "XLIFF_STATE_FINAL",
    "XLIFF_STATE_NEEDS_TRANSLATION",
    "XLIFF_STATE_NEW",
    "XLIFF_STATE_REJECTED",
    "XLIFF_STATE_TRANSLATED",
    "XLIFF_VERSION",
    "build_filename",
    "export_to_xliff_bytes",
]
