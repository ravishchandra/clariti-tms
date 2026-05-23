"""Publication helpers: path resolution, format dispatch, and dict utilities.

All functions are pure — no DB access, no async.
"""

from __future__ import annotations

import os

from app.models import Repository
from app.publication.writers.android import serialize_android_xml
from app.publication.writers.flutter_arb import serialize_flutter_arb
from app.publication.writers.ios import serialize_strings, serialize_stringsdict, serialize_xcstrings
from app.publication.writers.react import serialize_react_json


def locale_file_path(repository: Repository, locale: str) -> str:
    """Return the relative path within the repo for a locale file.

    - ios-strings:     {github_path}{locale}.lproj/Localizable.strings
    - ios-xcstrings:   {github_path}Localizable.xcstrings  (single file, all locales)
    - ios-stringsdict: {github_path}{locale}.lproj/Localizable.stringsdict
    - android-xml:     {github_path}values-{android_locale_tag(locale)}/strings.xml
    - i18next:         {github_path}{locale}/{namespace_from_source_file(repository)}.json
    - icu/flat-json:   {github_path}{locale}.json
    - flutter-arb:     {github_path}app_{locale_underscore(locale)}.arb
    """
    base = repository.github_path or ""

    fmt = repository.file_format
    if fmt == "ios-strings":
        return f"{base}{locale}.lproj/Localizable.strings"
    if fmt == "ios-xcstrings":
        return f"{base}Localizable.xcstrings"
    if fmt == "ios-stringsdict":
        return f"{base}{locale}.lproj/Localizable.stringsdict"
    if fmt == "android-xml":
        tag = android_locale_tag(locale)
        return f"{base}values-{tag}/strings.xml"
    if fmt == "i18next":
        ns = namespace_from_source_file(repository)
        return f"{base}{locale}/{ns}.json"
    if fmt == "flutter-arb":
        return f"{base}app_{locale.replace('-', '_')}.arb"
    # icu, flat-json, and any unknown format
    return f"{base}{locale}.json"


def android_locale_tag(locale: str) -> str:
    """Convert BCP-47 to Android resource qualifier.

    - Simple two-part tags: fr-FR → fr-rFR
    - Three-part or script tags: zh-Hans-CN → b+zh+Hans+CN
    """
    parts = locale.split("-")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        lang, region = parts
        return f"{lang}-r{region}"
    # Three or more parts — use the extended BCP-47 qualifier syntax
    return "b+" + "+".join(parts)


def namespace_from_source_file(repository: Repository) -> str:
    """Extract namespace from source_file.

    'en/common.json' → 'common'
    'src/locales/en/messages.json' → 'messages'
    Falls back to 'translation' when source_file is absent or unparseable.
    """
    source_file = repository.source_file
    if not source_file:
        return "translation"
    basename = os.path.basename(source_file)
    stem, _, _ = basename.rpartition(".")
    return stem or "translation"


def serialize_locale_file(
    translations: dict[str, str],
    repository: Repository,
    locale: str,
    key_metadata: dict[str, dict] | None = None,
) -> str:
    """Dispatch to the correct writer based on repository.file_format.

    ``key_metadata`` maps source key → format-native metadata block (currently
    only consumed by the Flutter ARB writer to emit ``@key`` blocks). Other
    writers ignore it.
    """
    fmt = repository.file_format
    if fmt == "ios-strings":
        return serialize_strings(translations)
    if fmt == "ios-xcstrings":
        return serialize_xcstrings(translations, source_locale=locale)
    if fmt == "ios-stringsdict":
        return serialize_stringsdict(translations, locale=locale)
    if fmt == "android-xml":
        return serialize_android_xml(translations, locale=locale)
    if fmt in ("i18next", "icu", "flat-json"):
        return serialize_react_json(translations)
    if fmt == "flutter-arb":
        return serialize_flutter_arb(translations, locale=locale, metadata=key_metadata)
    raise ValueError(f"Unsupported file_format: {fmt!r}")


def build_nested(rows: list, file_format: str) -> dict[str, str]:
    """Build flat {key: value} dict from ORM rows with .key and .value attributes.

    The file_format argument is accepted for future format-specific logic but
    is not currently used — all formats share the same flat representation at
    this stage; nesting is deferred to the writer.
    """
    return {row.key: row.value for row in rows if row.value is not None}


def deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge updates into base. updates wins on conflicts."""
    result = dict(base)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
