"""Shared utilities used by every platform parser.

All functions are pure — no I/O, no DB access, no side effects.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Placeholder extraction
# ---------------------------------------------------------------------------

# iOS/macOS printf-style: %@, %d, %f, %s, %1$@, %2$d, etc.
_RE_IOS_PLACEHOLDER = re.compile(r"%(\d+\$)?[@dfs]")

# Android printf-style: %1$s, %2$d (positional required in Android)
_RE_ANDROID_PLACEHOLDER = re.compile(r"%\d+\$[sd]")

# i18next double-curly: {{name}}, {{count}}
_RE_I18NEXT_PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")

# ICU single-curly simple variables: {name} — but NOT ICU keyword blocks
# We match only bare identifiers, not "name, plural, ..." constructs.
_RE_ICU_SIMPLE = re.compile(r"\{([^},\s]+)\}")

# ICU keyword blocks to exclude from simple-variable extraction
_RE_ICU_KEYWORD_BLOCK = re.compile(r"\{\s*\w+\s*,\s*(plural|select|selectordinal)\s*,")


def extract_placeholders(text: str, file_format: str) -> list[str]:
    """Return deduplicated, order-preserving list of placeholders in *text*.

    Format-specific rules:
    - ios-strings / ios-xcstrings : ``%@``, ``%d``, ``%1$@``, etc.
    - android-xml                 : ``%1$s``, ``%2$d`` (positional only)
    - i18next                     : ``{{name}}`` double-curly
    - icu / flat-json             : ``{name}`` single-curly, keyword blocks excluded
    """
    seen: dict[str, None] = {}  # ordered set via insertion-ordered dict

    if file_format in ("ios-strings", "ios-xcstrings", "ios-stringsdict"):
        for m in _RE_IOS_PLACEHOLDER.finditer(text):
            seen.setdefault(m.group(), None)

    elif file_format == "android-xml":
        for m in _RE_ANDROID_PLACEHOLDER.finditer(text):
            seen.setdefault(m.group(), None)

    elif file_format == "i18next":
        for m in _RE_I18NEXT_PLACEHOLDER.finditer(text):
            seen.setdefault(m.group(), None)

    elif file_format in ("icu", "flat-json"):
        # Skip the entire string if it contains an ICU keyword block; we only
        # want the bare {variable} tokens that are not part of plural/select.
        if not _RE_ICU_KEYWORD_BLOCK.search(text):
            for m in _RE_ICU_SIMPLE.finditer(text):
                seen.setdefault(m.group(), None)
        else:
            # Walk token by token — collect bare {name} that appear outside
            # keyword blocks.  Simple approach: strip the keyword-block spans
            # first, then scan the remainder.
            spans = [m.span() for m in _RE_ICU_KEYWORD_BLOCK.finditer(text)]
            # Build a mask of "safe" indices
            safe = bytearray(b"\x01" * len(text))
            for start, end in spans:
                for i in range(start, min(end, len(text))):
                    safe[i] = 0
            # Scan only safe positions
            for m in _RE_ICU_SIMPLE.finditer(text):
                if safe[m.start()]:
                    seen.setdefault(m.group(), None)

    return list(seen)


# ---------------------------------------------------------------------------
# Structural tag detection
# ---------------------------------------------------------------------------

# React Trans component index tags: <1>, <2>, <10>, etc.
_RE_TRANS_TAG = re.compile(r"<\d+>")

# Android / HTML inline tags
_RE_HTML_TAG = re.compile(r"</?(?:b|i|u|em|strong|a|span|br|sub|sup)\b", re.IGNORECASE)


def detect_structural_tags(text: str, file_format: str) -> bool:
    """Return True if *text* contains structural tags that require pre-processing.

    - i18next / icu : React Trans ``<1>``, ``<2>`` index tags
    - android-xml   : inline HTML tags ``<b>``, ``<i>``, ``<a …>``, etc.
    """
    if file_format in ("i18next", "icu", "flat-json"):
        return bool(_RE_TRANS_TAG.search(text))
    if file_format == "android-xml":
        return bool(_RE_HTML_TAG.search(text))
    return False


# ---------------------------------------------------------------------------
# ICU shape detection
# ---------------------------------------------------------------------------

_RE_ICU_PLURAL = re.compile(r"\{[^}]+,\s*plural\s*,")
_RE_ICU_SELECT = re.compile(r"\{[^}]+,\s*select\s*,")


def detect_icu_shape(text: str, file_format: str) -> str:
    """Return 'plural', 'select', or 'plain'.

    For stringsdict keys the caller should pass ``file_format='ios-stringsdict'``
    and this function returns 'plural' immediately since stringsdict is always
    plural by definition.
    """
    if file_format == "ios-stringsdict":
        return "plural"
    if _RE_ICU_PLURAL.search(text):
        return "plural"
    if _RE_ICU_SELECT.search(text):
        return "select"
    return "plain"


# ---------------------------------------------------------------------------
# String-type inference
# ---------------------------------------------------------------------------

# Each tuple: (substring(s) to check in key.lower(), string_type value)
# Checked in order — first match wins.
_STRING_TYPE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("btn", "button", "cta", "action"), "button"),
    (("title", "heading", "header"), "title"),
    (("label",), "label"),
    (("placeholder", "hint"), "placeholder"),
    (("error", "err_", "_err", "failure", "failed"), "error"),
    (("success", "confirmed", "complete"), "success"),
    (("help", "tooltip", "hint"), "help_text"),
    (("notification", "push", "alert"), "notification"),
    (("permission", "perm_", "_permission"), "permission"),
]


def infer_string_type(
    key: str,
    source_text: str,  # noqa: ARG001 — reserved for future heuristics
    *,
    has_structural_tags: bool = False,
) -> str:
    """Heuristic string-type classification based on key name."""
    lower = key.lower()
    for tokens, string_type in _STRING_TYPE_RULES:
        if any(tok in lower for tok in tokens):
            return string_type
    if has_structural_tags:
        return "trans_component"
    return "other"


# ---------------------------------------------------------------------------
# Risk-class inference
# ---------------------------------------------------------------------------

_HUMAN_ONLY_TOKENS = ("legal", "terms", "privacy", "tos", "eula", "disclaimer")
_HIGH_RISK_TOKENS = (
    "confirm",
    "delete",
    "payment",
    "charge",
    "price",
    "amount",
    "fee",
)


def infer_risk_class(
    key: str,
    source_text: str,
    string_type: str,
    *,
    placeholders: list[str] | None = None,
) -> str:
    """Heuristic risk-class assignment.

    Priority order (highest → lowest):
    1. human_only  — legal / privacy language
    2. high_risk   — error/permission types or financial/destructive keys
    3. auto_publish — short button text with no placeholders
    4. standard    — everything else
    """
    lower = key.lower()

    if any(tok in lower for tok in _HUMAN_ONLY_TOKENS):
        return "human_only"

    if string_type in ("error", "permission") or any(
        tok in lower for tok in _HIGH_RISK_TOKENS
    ):
        return "high_risk"

    if (
        string_type == "button"
        and len(source_text) < 20
        and not (placeholders or [])
    ):
        return "auto_publish"

    return "standard"


# ---------------------------------------------------------------------------
# Component inference from key prefix
# ---------------------------------------------------------------------------

# Short functional prefixes that are NOT meaningful screen names
_SKIP_PREFIXES = frozenset(
    {
        "btn",
        "lbl",
        "txt",
        "msg",
        "err",
        "str",
        "key",
        "val",
        "fmt",
        "ic",
        "img",
        "the",
        "and",
        "for",
        "new",
        "get",
        "set",
        "add",
        "all",
        "any",
        "one",
        "two",
        "yes",
        "no",
    }
)

# Keys starting with these prefixes map to the "shared" component
_SHARED_PREFIXES = ("common.", "shared.", "global.")


def infer_component_from_key(key: str) -> tuple[str | None, str | None]:
    """Derive (component, screen) from the key name.

    Screen is always None — real screen grouping requires AST analysis (Phase 7).
    Component is the first meaningful segment of the key.

    Returns (None, None) when no meaningful prefix can be identified.
    """
    lower = key.lower()
    for prefix in _SHARED_PREFIXES:
        if lower.startswith(prefix):
            return ("shared", None)

    # Split on first dot or underscore
    sep_dot = key.find(".")
    sep_us = key.find("_")

    # Find the first separator
    candidates = [s for s in (sep_dot, sep_us) if s > 0]
    if not candidates:
        return (None, None)

    first_sep = min(candidates)
    prefix = key[:first_sep]

    if len(prefix) < 4:
        return (None, None)

    if prefix.lower() in _SKIP_PREFIXES:
        return (None, None)

    return (prefix, None)
