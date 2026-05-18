"""iOS platform writers.

Handles:
- .strings  (ios-strings)
- .xcstrings (ios-xcstrings, Xcode 15+ String Catalogs)
- .stringsdict (ios-stringsdict, Apple plural format)

All functions are pure — they take a translations dict and return a str.
No I/O, no DB access.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from app.mt.plural import get_cldr_categories


def _escape_strings_value(value: str) -> str:
    """Escape a value for use inside an Apple .strings quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def serialize_strings(translations: dict[str, str]) -> str:
    """Emit Apple .strings format. Handles escaping of quotes and newlines."""
    lines: list[str] = []
    for key, value in translations.items():
        escaped_key = _escape_strings_value(key)
        escaped_val = _escape_strings_value(value)
        lines.append(f'"{escaped_key}" = "{escaped_val}";')
    return "\n".join(lines) + ("\n" if lines else "")


def serialize_xcstrings(translations: dict[str, str], source_locale: str = "en") -> str:
    """Emit Xcode 15 .xcstrings JSON.

    Each key gets a stringUnit.value under the target locale. The target locale
    is determined by the keys in translations — callers pass a single-locale
    dict. source_locale is stored in the top-level sourceLanguage field only.
    """
    strings: dict[str, dict] = {}
    for key, value in translations.items():
        # Detect plural JSON values — xcstrings uses variations.plural for those
        plural_map = _try_parse_plural(value)
        if plural_map:
            localizations: dict = {
                source_locale: {
                    "variations": {
                        "plural": {
                            category: {"stringUnit": {"state": "translated", "value": cat_val}}
                            for category, cat_val in plural_map.items()
                        }
                    }
                }
            }
        else:
            localizations = {
                source_locale: {
                    "stringUnit": {
                        "state": "translated",
                        "value": value,
                    }
                }
            }
        strings[key] = {"localizations": localizations}

    catalog = {
        "sourceLanguage": source_locale,
        "strings": strings,
        "version": "1.0",
    }
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def serialize_stringsdict(translations: dict[str, str], locale: str) -> str:
    """Emit .stringsdict plist XML for plural keys.

    Only includes keys whose value is a JSON object with plural categories.
    Each entry gets NSStringLocalizedFormatKey = %#@value@ and a value dict
    with NSStringFormatSpecTypeKey, NSStringFormatValueTypeKey, and one item
    per CLDR category required by the locale.
    """
    required_categories = get_cldr_categories(locale)

    root = ET.Element("plist", version="1.0")
    outer_dict = ET.SubElement(root, "dict")

    has_entries = False

    for key, value in translations.items():
        plural_map = _try_parse_plural(value)
        if not plural_map:
            continue

        has_entries = True

        ET.SubElement(outer_dict, "key").text = key

        entry_dict = ET.SubElement(outer_dict, "dict")

        ET.SubElement(entry_dict, "key").text = "NSStringLocalizedFormatKey"
        ET.SubElement(entry_dict, "string").text = "%#@value@"

        ET.SubElement(entry_dict, "key").text = "value"
        value_dict = ET.SubElement(entry_dict, "dict")

        ET.SubElement(value_dict, "key").text = "NSStringFormatSpecTypeKey"
        ET.SubElement(value_dict, "string").text = "NSStringPluralRuleType"

        ET.SubElement(value_dict, "key").text = "NSStringFormatValueTypeKey"
        ET.SubElement(value_dict, "string").text = "d"

        for category in required_categories:
            cat_value = plural_map.get(category) or plural_map.get("other", "")
            ET.SubElement(value_dict, "key").text = category
            ET.SubElement(value_dict, "string").text = cat_value

    if not has_entries:
        return (  # noqa: E501 — Apple PLIST DOCTYPE URL must remain on a single line per spec
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict/>\n</plist>\n'
        )

    ET.indent(root, space="    ")
    xml_body = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        + xml_body
        + "\n"
    )


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
