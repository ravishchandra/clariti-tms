"""Flutter ARB (Application Resource Bundle) parser.

ARB is JSON with single-curly ICU placeholders. Top-level keys split into:
- ``@@``-prefixed directives (``@@locale``, ``@@last_modified``, …) — skipped.
- ``@``-prefixed metadata blocks (``@greeting``) — attached to the matching
  plain key as ``description``.
- Plain string keys — translatable.

All functions are pure — they take ``content: str`` and return ``list[ParsedKey]``.
No I/O, no DB access.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .common import (
    detect_icu_shape,
    detect_structural_tags,
    extract_placeholders,
    infer_component_from_key,
    infer_risk_class,
    infer_string_type,
)
from .types import ParsedKey


def _stem(filename: str) -> str:
    base = os.path.basename(filename)
    name, _, _ = base.rpartition(".")
    return name or base


def _strip_locale_suffix(stem: str) -> str:
    # app_en, app_en_US → app. intl_messages_fr → intl_messages.
    parts = stem.split("_")
    while len(parts) > 1 and len(parts[-1]) in (2, 3) and parts[-1].isalpha():
        parts.pop()
    return "_".join(parts) if parts else stem


def parse_flutter_arb(content: str, filename: str) -> list[ParsedKey]:
    """Parse a Flutter ``.arb`` file into ParsedKey rows.

    Steps:
    1. Decode JSON; reject non-object roots.
    2. Skip ``@@``-prefixed directives entirely.
    3. For each plain string key K, pull description from ``@K.description``.
    4. Detect placeholders + ICU shape using the shared ICU helpers.
    """
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {filename}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Top-level JSON must be an object in {filename}")

    # Partition into plain keys, metadata blocks, and directives.
    plain_keys: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for key, value in raw.items():
        if key.startswith("@@"):
            continue  # directive — never translatable
        if key.startswith("@"):
            if isinstance(value, dict):
                metadata[key[1:]] = value
            continue
        if isinstance(value, str):
            plain_keys[key] = value
        # Non-string leaves (numbers, bools, arrays) are silently skipped —
        # not a valid ARB shape for a translatable entry.

    stem = _stem(filename)
    component_from_file = _strip_locale_suffix(stem)
    if component_from_file.lower() in ("common", "shared", "global", "app", "intl", "intl_messages"):
        component_from_file = "shared"

    results: list[ParsedKey] = []
    for key, value in plain_keys.items():
        meta = metadata.get(key) or {}
        description = meta.get("description") if isinstance(meta.get("description"), str) else None

        placeholders = extract_placeholders(value, "icu")
        has_tags = detect_structural_tags(value, "icu")
        icu_shape = detect_icu_shape(value, "icu")
        plural_format = "icu" if icu_shape == "plural" else None

        string_type = infer_string_type(key, value, has_structural_tags=has_tags)
        risk = infer_risk_class(key, value, string_type, placeholders=placeholders)

        # Prefer key-derived component when the key itself encodes one
        # (e.g. "checkout.confirm"); fall back to the filename-derived value.
        inferred_component, _ = infer_component_from_key(key)
        component = inferred_component or component_from_file

        # Carry the whole ``@key`` block through so the writer can emit it
        # back verbatim on publish. We keep description as a separate column
        # because reviewers may edit it; everything else (placeholders,
        # context, x-* extensions) is read-only metadata.
        source_metadata = meta if meta else None

        results.append(
            ParsedKey(
                key=key,
                source_text=value,
                component=component,
                placeholders=placeholders,
                has_structural_tags=has_tags,
                icu_shape=icu_shape,
                plural_format=plural_format,
                string_type=string_type,
                risk_class=risk,
                description=description,
                source_metadata=source_metadata,
            )
        )

    return results
