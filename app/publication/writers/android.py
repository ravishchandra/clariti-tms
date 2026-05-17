"""Android platform writer.

Handles strings.xml (android-xml format):
- Plain <string> elements
- HTML content written as-is (no extra escaping of HTML tags)
- Plural keys (<plurals>) with CLDR categories per locale
- Android-required escaping: apostrophes → \' and double quotes → \"

All functions are pure — they take a translations dict and return a str.
No I/O, no DB access.
"""

from __future__ import annotations

import json
import re

from app.mt.plural import get_cldr_categories

_RE_HTML_TAG = re.compile(r"<[a-zA-Z/]")


def _escape_android(value: str) -> str:
    """Apply Android string resource escaping rules.

    HTML-tagged content is written raw; only apostrophes and double-quotes
    in the surrounding text nodes need escaping.
    """
    # Android requires \' and \" in string values to avoid XML attribute confusion.
    # We do NOT escape < > & because HTML content must remain valid markup.
    return value.replace("'", "\\'").replace('"', '\\"')


def _try_parse_plural(value: str) -> dict[str, str] | None:
    """Return parsed plural dict if value is a JSON object, else None."""
    stripped = value.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, dict) and all(isinstance(v, str) for v in parsed.values()):
        return parsed
    return None


def _has_html(value: str) -> bool:
    return bool(_RE_HTML_TAG.search(value))


def serialize_android_xml(translations: dict[str, str], locale: str) -> str:
    """Emit Android strings.xml.

    - Plain strings → <string name="key">value</string>
    - HTML content → written as-is inside the element (no CDATA, no extra escaping of tags)
    - Plural keys (value is JSON dict) → <plurals name="key"> with one <item quantity=Q>
      per CLDR category for the locale.
    - Apostrophes → \\' and double quotes → \\" in string values (Android requirement).
    """
    required_categories = get_cldr_categories(locale)
    lines: list[str] = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]

    for key, value in translations.items():
        plural_map = _try_parse_plural(value)
        if plural_map:
            lines.append(f'    <plurals name="{key}">')
            for category in required_categories:
                cat_value = plural_map.get(category) or plural_map.get("other", "")
                escaped = _escape_android(cat_value) if not _has_html(cat_value) else cat_value
                lines.append(f'        <item quantity="{category}">{escaped}</item>')
            lines.append("    </plurals>")
        else:
            escaped = _escape_android(value) if not _has_html(value) else value
            lines.append(f'    <string name="{key}">{escaped}</string>')

    lines.append("</resources>")
    return "\n".join(lines) + "\n"
