"""React / TypeScript platform parser.

Handles:
- i18next namespace JSON (``{{name}}`` interpolation, ``key_one``/``key_other`` suffix plurals)
- ICU MessageFormat flat JSON (``{name}`` single-curly, inline plural/select)

All functions are pure — they take ``content: str`` and return ``list[ParsedKey]``.
No I/O, no DB access.
"""

from __future__ import annotations

import json
import os
import re

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
# JSON flattening
# ---------------------------------------------------------------------------


def flatten_json(obj: dict, prefix: str = "") -> dict[str, str]:
    """Recursively flatten a nested dict to dot-notation keys.

    Only leaf values that are strings are included.  Nested dicts are
    traversed; arrays are ignored (not standard i18next structure).

    Example::

        {"button": {"confirm": "Confirm"}} → {"button.confirm": "Confirm"}
    """
    result: dict[str, str] = {}
    for k, v in obj.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(flatten_json(v, full_key))
        elif isinstance(v, str):
            result[full_key] = v
        # Non-string leaf (number, bool, null, array) → silently skip
    return result


# ---------------------------------------------------------------------------
# i18next plural suffix detection
# ---------------------------------------------------------------------------

# i18next v4 standard suffixes (also supports _zero, _one, _two, _few, _many)
_PLURAL_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")
# The canonical key is the base (without suffix). We prefer "_other" as the
# representative text, consistent with what parsers do for other platforms.
_CANONICAL_SUFFIX = "_other"


def _split_plural_suffix(key: str) -> tuple[str, str] | None:
    """If *key* ends with a known i18next plural suffix, return (base, suffix).

    Returns None if the key has no plural suffix.
    """
    for suffix in _PLURAL_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)], suffix
    return None


# ---------------------------------------------------------------------------
# Format detection helpers
# ---------------------------------------------------------------------------

_RE_I18NEXT_VAR = re.compile(r"\{\{[^}]+\}\}")
_RE_ICU_KEYWORD = re.compile(r"\{\s*\w+\s*,\s*(plural|select|selectordinal)\s*,")
_RE_ICU_SIMPLE = re.compile(r"\{[^}]+\}")


def _detect_format(value: str) -> str:
    """Return 'i18next' or 'icu' based on placeholder style in *value*."""
    if _RE_I18NEXT_VAR.search(value):
        return "i18next"
    if _RE_ICU_KEYWORD.search(value) or _RE_ICU_SIMPLE.search(value):
        return "icu"
    return "i18next"  # default


# ---------------------------------------------------------------------------
# Component from filename
# ---------------------------------------------------------------------------


def _stem(filename: str) -> str:
    base = os.path.basename(filename)
    name, _, _ = base.rpartition(".")
    return name or base


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_namespace_json(content: str, filename: str) -> list[ParsedKey]:
    """Parse an i18next namespace JSON or ICU flat JSON file.

    Steps:
    1. Flatten nested JSON to dot-notation keys.
    2. Group i18next plural suffix keys (``key_one`` + ``key_other`` → base key).
    3. Detect format per key (i18next vs ICU).
    4. Detect placeholders, structural tags, ICU shape.
    5. Return one ``ParsedKey`` per logical string.

    Component = filename stem (e.g. ``checkout.json`` → ``"checkout"``).
    """
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {filename}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Top-level JSON must be an object in {filename}")

    flat = flatten_json(raw)
    component = _stem(filename)
    # Normalise common shared-file names
    if component.lower() in ("common", "shared", "global"):
        component = "shared"

    # --- Group plural suffix keys ---
    # plural_groups: base_key → {suffix: value}
    plural_groups: dict[str, dict[str, str]] = {}
    plain_keys: dict[str, str] = {}

    for key, value in flat.items():
        split = _split_plural_suffix(key)
        if split is not None:
            base, suffix = split
            plural_groups.setdefault(base, {})[suffix] = value
        else:
            plain_keys[key] = value

    results: list[ParsedKey] = []

    # --- Process plain keys ---
    for key, value in plain_keys.items():
        # A plain key whose name matches a plural-group base is already
        # covered; skip if it will be emitted as plural.
        if key in plural_groups:
            continue
        pk = _build_parsed_key(key, value, component)
        results.append(pk)

    # --- Process plural groups ---
    for base_key, variants in plural_groups.items():
        # canonical source_text = "_other" variant; fall back to first available
        source_text = variants.get("_other") or next(iter(variants.values()))
        pk = _build_parsed_key(
            base_key,
            source_text,
            component,
            force_plural=True,
            plural_format="i18next-suffix",
        )
        results.append(pk)

    return results


def _build_parsed_key(
    key: str,
    value: str,
    component: str | None,
    *,
    force_plural: bool = False,
    plural_format: str | None = None,
) -> ParsedKey:
    file_format = _detect_format(value)
    placeholders = extract_placeholders(value, file_format)
    has_tags = detect_structural_tags(value, file_format)

    if force_plural:
        icu_shape = "plural"
    else:
        icu_shape = detect_icu_shape(value, file_format)
        # If ICU inline plural detected, set plural_format to "icu"
        if icu_shape == "plural" and plural_format is None:
            plural_format = "icu"

    stype = infer_string_type(key, value, has_structural_tags=has_tags)
    risk = infer_risk_class(key, value, stype, placeholders=placeholders)

    inferred_component = component
    if inferred_component is None:
        inferred_component, _ = infer_component_from_key(key)

    return ParsedKey(
        key=key,
        source_text=value,
        component=inferred_component,
        placeholders=placeholders,
        has_structural_tags=has_tags,
        icu_shape=icu_shape,
        plural_format=plural_format,
        string_type=stype,
        risk_class=risk,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def parse_react_file(content: str, filename: str) -> list[ParsedKey]:
    """Dispatch React file parsing (always namespace JSON for Phase 1)."""
    return parse_namespace_json(content, filename)
