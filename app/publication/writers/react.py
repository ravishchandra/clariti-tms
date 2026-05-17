"""React / TypeScript platform writer.

Handles i18next namespace JSON (i18next format):
- Rebuilds nested structure from dot-notation keys
- i18next suffix plural keys (key_one / key_other) remain as flat siblings
- Output is valid JSON with configurable indent

All functions are pure — they take a translations dict and return a str.
No I/O, no DB access.
"""

from __future__ import annotations

import json

_PLURAL_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")


def _is_plural_suffix_key(key: str) -> bool:
    """Return True if the leaf segment of a dot-notation key ends with a plural suffix."""
    leaf = key.split(".")[-1]
    return any(leaf.endswith(suffix) for suffix in _PLURAL_SUFFIXES)


def _set_nested(obj: dict, parts: list[str], value: str) -> None:
    """Recursively set a value in a nested dict given a list of key segments."""
    for part in parts[:-1]:
        if part not in obj or not isinstance(obj[part], dict):
            obj[part] = {}
        obj = obj[part]
    obj[parts[-1]] = value


def serialize_react_json(translations: dict[str, str], indent: int = 2) -> str:
    """Emit i18next namespace JSON.

    - Rebuilds nesting from dot-notation keys: "button.confirm" → {"button": {"confirm": "..."}}
    - Preserves insertion order
    - i18next suffix plural keys (key_one / key_other) stay as flat sibling keys
      under their parent namespace, not further split on the suffix
    - Output is valid JSON with indent=2
    """
    result: dict = {}

    for key, value in translations.items():
        parts = key.split(".")

        if len(parts) > 1 and _is_plural_suffix_key(key):
            # The last segment contains a plural suffix — do not split the suffix off.
            # Nest up to the parent, then set the full leaf (including suffix) as the key.
            parent_parts = parts[:-1]
            leaf = parts[-1]
            parent: dict = result
            for part in parent_parts:
                if part not in parent or not isinstance(parent[part], dict):
                    parent[part] = {}
                parent = parent[part]
            parent[leaf] = value
        else:
            _set_nested(result, parts, value)

    return json.dumps(result, ensure_ascii=False, indent=indent) + "\n"
