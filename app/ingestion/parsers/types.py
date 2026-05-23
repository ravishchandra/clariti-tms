"""Shared output types for all platform parsers.

Every parser returns a list[ParsedKey] wrapped in a ParseResult. No parser
imports SQLAlchemy — these are pure data containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedKey:
    """Normalised representation of one source string.

    Mirrors the columns on the ``keys`` table that parsers can populate.
    Callers are responsible for persisting these into the DB.
    """

    key: str
    source_text: str
    component: str | None = None
    screen: str | None = None
    # Format-native placeholders preserved verbatim (%@, {{name}}, {name}, %1$s …)
    placeholders: list[str] = field(default_factory=list)
    has_structural_tags: bool = False
    # "plain" | "plural" | "select"
    icu_shape: str = "plain"
    # "icu" | "stringsdict" | "android-xml" | "i18next-suffix" | None
    plural_format: str | None = None
    # matches string_type ENUM in data model
    string_type: str = "other"
    # "auto_publish" | "standard" | "high_risk" | "human_only"
    risk_class: str = "standard"
    # Free-text description (xcstrings comment, developer annotation, …)
    description: str | None = None
    # Format-native per-key metadata (Flutter ``@key`` block, future xcstrings
    # extras). Stored verbatim so the writer can round-trip the locale file
    # without losing developer-authored hints (placeholder types, context).
    source_metadata: dict[str, Any] | None = None


@dataclass
class ParseResult:
    """Top-level result returned by ``parse_file``."""

    keys: list[ParsedKey]
    # "ios" | "android" | "web"
    platform: str
    # "ios-strings" | "ios-xcstrings" | "android-xml" | "i18next" | "icu"
    file_format: str
    # Original filename passed by the caller
    source_file: str
