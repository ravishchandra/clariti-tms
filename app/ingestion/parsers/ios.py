"""iOS platform parsers.

Handles:
- .strings  (ios-strings)
- .xcstrings (ios-xcstrings, Xcode 15+ String Catalogs)
- .stringsdict (ios-stringsdict, Apple plural format)

All functions are pure — they take ``content: str`` and return ``list[ParsedKey]``.
No I/O, no DB access.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

from .common import (
    detect_icu_shape,
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

# Matches:  "key" = "value";
# Groups:   (comment_block | None) is handled separately; here we only grab key/value.
_RE_STRINGS_PAIR = re.compile(
    r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)

# Comment block: /* ... */
_RE_STRINGS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _stem(filename: str) -> str:
    """Return the filename stem without extension or directory."""
    base = os.path.basename(filename)
    name, _, _ = base.rpartition(".")
    return name or base


def _is_infoplist(filename: str) -> bool:
    return os.path.basename(filename).lower() == "infoplist.strings"


def _build_key(
    key: str,
    source_text: str,
    file_format: str,
    component: str | None,
    description: str | None = None,
    *,
    force_high_risk: bool = False,
    force_permission: bool = False,
) -> ParsedKey:
    """Shared final assembly for all iOS parsers."""
    placeholders = extract_placeholders(source_text, file_format)
    has_tags = detect_structural_tags(source_text, file_format)
    icu_shape = detect_icu_shape(source_text, file_format)

    stype = infer_string_type(key, source_text, has_structural_tags=has_tags)
    if force_permission:
        stype = "permission"

    risk = infer_risk_class(key, source_text, stype, placeholders=placeholders)
    if force_high_risk and risk not in ("human_only",):
        risk = "high_risk"

    if component is None:
        component, _ = infer_component_from_key(key)

    return ParsedKey(
        key=key,
        source_text=source_text,
        component=component,
        placeholders=placeholders,
        has_structural_tags=has_tags,
        icu_shape=icu_shape,
        plural_format=None,
        string_type=stype,
        risk_class=risk,
        description=description,
    )


# ---------------------------------------------------------------------------
# .strings parser
# ---------------------------------------------------------------------------


def parse_strings_file(content: str, filename: str) -> list[ParsedKey]:
    """Parse an Apple ``.strings`` file (key-value text format).

    Handles:
    - ``/* comment */`` blocks immediately before a key-value pair → description
    - Escaped characters inside quoted strings (``\\"`` etc.)
    - Multi-line values (rare but valid)
    - InfoPlist.strings keys → risk_class=high_risk, string_type=permission
    """
    file_format = "ios-strings"
    infoplist = _is_infoplist(filename)

    stem = _stem(filename)
    # Localizable.strings has no meaningful component; named files do.
    file_component: str | None = None if stem.lower() == "localizable" else stem

    # Split the content into tokens: comments and key=value pairs.
    # We walk through comment blocks and pair matches together to associate
    # the immediately preceding comment with a pair.
    results: list[ParsedKey] = []

    # Build a list of (position, type, text) events
    events: list[tuple[int, str, str]] = []
    for m in _RE_STRINGS_COMMENT.finditer(content):
        events.append((m.start(), "comment", m.group()))
    for m in _RE_STRINGS_PAIR.finditer(content):
        events.append((m.start(), "pair", m.group()))
    events.sort(key=lambda e: e[0])

    last_comment: str | None = None
    last_comment_end: int = -1

    for pos, kind, text in events:
        if kind == "comment":
            last_comment = text[2:-2].strip()  # strip /* and */
            last_comment_end = pos + len(text)
            # Ignore "No comment provided by engineer."
            if last_comment.lower() in (
                "no comment provided by engineer.",
                "no comment provided by engineer",
            ):
                last_comment = None
        else:
            # It's a pair — find key and value from the match
            m2 = _RE_STRINGS_PAIR.match(text)
            if not m2:
                last_comment = None
                continue
            raw_key = m2.group(1)
            raw_value = m2.group(2)

            # Unescape standard escape sequences
            key = _unescape(raw_key)
            source_text = _unescape(raw_value)

            # Use last_comment as description only if it immediately preceded this pair
            # (allow intervening whitespace but no other pairs)
            description: str | None = last_comment if last_comment else None
            last_comment = None  # consume

            pk = _build_key(
                key,
                source_text,
                file_format,
                file_component,
                description,
                force_high_risk=infoplist,
                force_permission=infoplist,
            )
            results.append(pk)

    return results


def _unescape(s: str) -> str:
    """Unescape common .strings escape sequences."""
    return (
        s.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
        .replace("\\'", "'")
    )


# ---------------------------------------------------------------------------
# .xcstrings parser
# ---------------------------------------------------------------------------


def parse_xcstrings_file(content: str, filename: str) -> list[ParsedKey]:
    """Parse an Xcode 15+ ``.xcstrings`` String Catalog file (JSON format).

    Structure::

        {
          "sourceLanguage": "en",
          "strings": {
            "<key>": {
              "comment": "optional",
              "localizations": {
                "en": {
                  "stringUnit": { "state": "new", "value": "Source text" }
                }
              }
            }
          }
        }

    Plural keys use ``localizations.en.variations.plural`` instead of
    ``stringUnit``.
    """
    file_format = "ios-xcstrings"
    stem = _stem(filename)
    file_component: str | None = None if stem.lower() == "localizable" else stem

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid xcstrings JSON in {filename}: {exc}") from exc

    source_lang = data.get("sourceLanguage", "en")
    strings_dict = data.get("strings", {})

    results: list[ParsedKey] = []

    for key, entry in strings_dict.items():
        if not isinstance(entry, dict):
            continue

        description: str | None = entry.get("comment") or None
        localizations = entry.get("localizations", {})
        src_loc = localizations.get(source_lang, {})

        # Determine if this is a plural key
        is_plural = False
        source_text = ""

        if "variations" in src_loc:
            # Plural / device variation key
            plural_map = src_loc["variations"].get("plural", {})
            if plural_map:
                is_plural = True
                # Use "other" as canonical; fall back to first available
                other = plural_map.get("other", {})
                source_text = (
                    other.get("stringUnit", {}).get("value", "")
                    or _first_variation_value(plural_map)
                )
        elif "stringUnit" in src_loc:
            source_text = src_loc["stringUnit"].get("value", "")
        else:
            # Entry exists in catalog but has no localizations yet — skip
            continue

        if not source_text:
            continue

        placeholders = extract_placeholders(source_text, file_format)
        has_tags = detect_structural_tags(source_text, file_format)
        icu_shape = "plural" if is_plural else detect_icu_shape(source_text, file_format)
        plural_format: str | None = "stringsdict" if is_plural else None

        stype = infer_string_type(key, source_text, has_structural_tags=has_tags)
        risk = infer_risk_class(key, source_text, stype, placeholders=placeholders)

        component = file_component
        if component is None:
            component, _ = infer_component_from_key(key)

        results.append(
            ParsedKey(
                key=key,
                source_text=source_text,
                component=component,
                placeholders=placeholders,
                has_structural_tags=has_tags,
                icu_shape=icu_shape,
                plural_format=plural_format,
                string_type=stype,
                risk_class=risk,
                description=description,
            )
        )

    return results


def _first_variation_value(plural_map: dict) -> str:
    """Return the value of the first plural category available."""
    for category in ("other", "one", "few", "many", "two", "zero"):
        entry = plural_map.get(category, {})
        val = entry.get("stringUnit", {}).get("value", "")
        if val:
            return val
    return ""


# ---------------------------------------------------------------------------
# .stringsdict parser
# ---------------------------------------------------------------------------

# Expected plist structure (abbreviated):
#
# <plist><dict>
#   <key>KEY_NAME</key>
#   <dict>
#     <key>NSStringLocalizedFormatKey</key>
#     <string>%#@count@</string>
#     <key>count</key>
#     <dict>
#       <key>NSStringFormatSpecTypeKey</key><string>NSStringPluralRuleType</string>
#       <key>NSStringFormatValueTypeKey</key><string>d</string>
#       <key>one</key><string>%d item</string>
#       <key>other</key><string>%d items</string>
#     </dict>
#   </dict>
# </plist>
#
# Simplified structure (also valid):
#
# <plist><dict>
#   <key>SIMPLE_PLURAL_KEY</key>
#   <dict>
#     <key>one</key><string>%d item</string>
#     <key>other</key><string>%d items</string>
#   </dict>
# </plist>


def parse_stringsdict_file(content: str, filename: str) -> list[ParsedKey]:
    """Parse an Apple ``.stringsdict`` XML file (plural format).

    Each top-level key in the outer ``<dict>`` becomes a ``ParsedKey`` with
    ``icu_shape='plural'`` and ``plural_format='stringsdict'``.
    ``source_text`` is set to the ``other`` plural category value.
    """
    file_format = "ios-stringsdict"
    stem = _stem(filename)
    file_component: str | None = None if stem.lower() == "localizable" else stem

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid stringsdict XML in {filename}: {exc}") from exc

    # The root element may be <plist> wrapping a <dict>, or bare <dict>.
    outer_dict = root if root.tag == "dict" else root.find("dict")
    if outer_dict is None:
        return []

    results: list[ParsedKey] = []
    children = list(outer_dict)
    i = 0
    while i < len(children) - 1:
        key_el = children[i]
        val_el = children[i + 1]
        i += 2

        if key_el.tag != "key":
            continue
        top_key = (key_el.text or "").strip()
        if not top_key or val_el.tag != "dict":
            continue

        source_text = _extract_stringsdict_other(val_el)
        if not source_text:
            continue

        placeholders = extract_placeholders(source_text, file_format)
        has_tags = detect_structural_tags(source_text, file_format)

        stype = infer_string_type(top_key, source_text, has_structural_tags=has_tags)
        risk = infer_risk_class(top_key, source_text, stype, placeholders=placeholders)

        component = file_component
        if component is None:
            component, _ = infer_component_from_key(top_key)

        results.append(
            ParsedKey(
                key=top_key,
                source_text=source_text,
                component=component,
                placeholders=placeholders,
                has_structural_tags=has_tags,
                icu_shape="plural",
                plural_format="stringsdict",
                string_type=stype,
                risk_class=risk,
                description=None,
            )
        )

    return results


def _extract_stringsdict_other(entry_dict: ET.Element) -> str:
    """Extract the 'other' value from a stringsdict entry dict.

    Tries direct ``other`` key first (simple structure), then walks into
    the nested ``NSStringFormatSpecTypeKey`` sub-dict structure.
    """
    children = list(entry_dict)
    values: dict[str, str] = {}
    sub_dicts: list[ET.Element] = []

    i = 0
    while i < len(children) - 1:
        k_el = children[i]
        v_el = children[i + 1]
        i += 2
        if k_el.tag != "key":
            continue
        k = (k_el.text or "").strip()
        if v_el.tag == "string":
            values[k] = (v_el.text or "").strip()
        elif v_el.tag == "dict":
            sub_dicts.append(v_el)

    # Direct plural categories at this level (simplified format)
    if "other" in values:
        return values["other"]

    # Nested format: look inside sub-dicts for plural categories
    for sub in sub_dicts:
        nested = _extract_stringsdict_other(sub)
        if nested:
            return nested

    # Fallback to any string value that isn't a format spec key
    _FORMAT_SPEC_KEYS = {
        "NSStringFormatSpecTypeKey",
        "NSStringFormatValueTypeKey",
        "NSStringLocalizedFormatKey",
        "NSStringPluralRuleType",
    }
    for k, v in values.items():
        if k not in _FORMAT_SPEC_KEYS and v:
            return v

    return ""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def parse_ios_file(content: str, filename: str) -> list[ParsedKey]:
    """Dispatch to the correct iOS parser based on filename extension."""
    lower = filename.lower()
    if lower.endswith(".xcstrings"):
        return parse_xcstrings_file(content, filename)
    if lower.endswith(".stringsdict"):
        return parse_stringsdict_file(content, filename)
    # Default: .strings
    return parse_strings_file(content, filename)
