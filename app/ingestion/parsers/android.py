"""Android platform parser.

Handles ``strings.xml`` (android-xml format) with:
- Plain ``<string>`` elements
- ``translatable="false"`` skipping
- Inline HTML tag detection (``<b>``, ``<i>``, ``<a>``, etc.)
- ``<plurals>`` plural groups

All functions are pure — they take ``content: str`` and return ``list[ParsedKey]``.
No I/O, no DB access.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

from .common import (
    detect_structural_tags,
    extract_placeholders,
    infer_component_from_key,
    infer_risk_class,
    infer_string_type,
)
from .types import ParsedKey

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stem(filename: str) -> str:
    base = os.path.basename(filename)
    name, _, _ = base.rpartition(".")
    return name or base


def _component_from_path(filename: str) -> str | None:
    """Infer component from the Android resource path.

    ``res/layout/activity_checkout.xml`` → ``checkout``
    ``res/values/strings.xml``           → None (no grouping from path)
    """
    parts = filename.replace("\\", "/").split("/")
    for part in parts:
        lower = part.lower()
        # activity_checkout.xml → checkout
        for prefix in ("activity_", "fragment_", "dialog_"):
            if lower.startswith(prefix):
                stem_name = part[len(prefix) :]
                # strip extension
                stem_name = stem_name.rsplit(".", 1)[0]
                return stem_name.capitalize() if stem_name else None
    return None


# Regex to detect HTML / XML tags within string content
_RE_HTML_INLINE = re.compile(r"<[a-zA-Z/]")


def _inner_xml_text(element: ET.Element) -> str:
    """Return the raw inner content of an XML element including child tags
    and their attributes.

    ElementTree's tostring preserves attributes on child elements, which we
    need so that format specifiers inside href="" values are captured.

    Strategy: serialise the full element to a unicode string, then strip the
    outermost tag (e.g. ``<string name="...">...</string>``) to get the inner
    content.
    """
    raw = ET.tostring(element, encoding="unicode")
    # Strip the outermost tag: everything from the first '>' to the last '<'.
    # Works for both '<string name="x">content</string>' and mixed content.
    first_gt = raw.find(">")
    last_lt = raw.rfind("<")
    if first_gt != -1 and last_lt > first_gt:
        return raw[first_gt + 1 : last_lt]
    # Self-closing element (no text content at all)
    return element.text or ""


def _collect_text(element: ET.Element) -> str:
    """Collect all text content recursively, preserving child tag text."""
    parts = [element.text or ""]
    for child in element:
        parts.append(f"<{child.tag}>")
        parts.append(_collect_text(child))
        parts.append(f"</{child.tag}>")
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_strings_xml(content: str, filename: str) -> list[ParsedKey]:
    """Parse an Android ``strings.xml`` resource file.

    Rules applied:
    - ``translatable="false"`` → skip entirely
    - Inline HTML tags in value → ``has_structural_tags=True``
    - ``<plurals>`` → ``icu_shape='plural'``, ``plural_format='android-xml'``,
      ``source_text`` = the ``other`` quantity value
    - ``%1$s``, ``%2$d`` placeholders extracted
    - Component inferred from filename path, then key prefix as fallback
    """
    file_format = "android-xml"

    path_component = _component_from_path(filename)

    try:
        # Some strings.xml files use HTML entities not declared in a DTD;
        # wrap in a root to be safe and use a lenient parse.
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid strings.xml in {filename}: {exc}") from exc

    results: list[ParsedKey] = []

    for child in root:
        tag = child.tag

        if tag == "string":
            pk = _parse_string_element(child, file_format, path_component, filename)
            if pk is not None:
                results.append(pk)

        elif tag == "plurals":
            pk = _parse_plurals_element(child, file_format, path_component, filename)
            if pk is not None:
                results.append(pk)

        # Ignore <string-array>, <declare-styleable>, comments, etc.

    return results


def _parse_string_element(
    element: ET.Element,
    file_format: str,
    path_component: str | None,
    filename: str,
) -> ParsedKey | None:
    """Parse a ``<string>`` element.  Returns None for translatable=false."""
    name = element.get("name", "").strip()
    if not name:
        return None

    # translatable="false" → skip
    if element.get("translatable", "true").lower() == "false":
        return None

    # Preserve raw inner XML so we capture HTML tags
    source_text = _inner_xml_text(element).strip()
    if not source_text:
        return None

    placeholders = extract_placeholders(source_text, file_format)
    # Use our common detector but also check raw text for HTML
    has_tags = detect_structural_tags(source_text, file_format) or bool(
        _RE_HTML_INLINE.search(source_text)
    )

    stype = infer_string_type(name, source_text, has_structural_tags=has_tags)
    risk = infer_risk_class(name, source_text, stype, placeholders=placeholders)

    component = path_component
    if component is None:
        component, _ = infer_component_from_key(name)

    return ParsedKey(
        key=name,
        source_text=source_text,
        component=component,
        placeholders=placeholders,
        has_structural_tags=has_tags,
        icu_shape="plain",
        plural_format=None,
        string_type=stype,
        risk_class=risk,
    )


def _parse_plurals_element(
    element: ET.Element,
    file_format: str,
    path_component: str | None,
    filename: str,
) -> ParsedKey | None:
    """Parse a ``<plurals>`` element.

    ``source_text`` = the ``other`` quantity value (canonical form).
    Falls back to the first available quantity if ``other`` is absent.
    """
    name = element.get("name", "").strip()
    if not name:
        return None

    if element.get("translatable", "true").lower() == "false":
        return None

    # Collect quantity → text
    quantities: dict[str, str] = {}
    for item in element.findall("item"):
        qty = item.get("quantity", "")
        text = _inner_xml_text(item).strip()
        if qty and text:
            quantities[qty] = text

    if not quantities:
        return None

    # Canonical source_text = "other" quantity
    source_text = quantities.get("other") or next(iter(quantities.values()))

    placeholders = extract_placeholders(source_text, file_format)
    has_tags = detect_structural_tags(source_text, file_format) or bool(
        _RE_HTML_INLINE.search(source_text)
    )

    stype = infer_string_type(name, source_text, has_structural_tags=has_tags)
    risk = infer_risk_class(name, source_text, stype, placeholders=placeholders)

    component = path_component
    if component is None:
        component, _ = infer_component_from_key(name)

    return ParsedKey(
        key=name,
        source_text=source_text,
        component=component,
        placeholders=placeholders,
        has_structural_tags=has_tags,
        icu_shape="plural",
        plural_format="android-xml",
        string_type=stype,
        risk_class=risk,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def parse_android_file(content: str, filename: str) -> list[ParsedKey]:
    """Dispatch Android file parsing.

    Layout XML grouping (``res/layout/activity_*.xml`` → key associations)
    is deferred to Phase 7.  For now all Android files are ``strings.xml``.
    """
    return parse_strings_xml(content, filename)
