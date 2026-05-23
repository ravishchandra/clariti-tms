"""Flutter ARB platform writer.

Emits a Flutter ``.arb`` (Application Resource Bundle) file: JSON with a
``@@locale`` directive, translatable string keys, and optional ``@key``
metadata blocks.

All functions are pure — they take a translations dict and return a str.
No I/O, no DB access.
"""

from __future__ import annotations

import json
from typing import Any


def serialize_flutter_arb(
    translations: dict[str, str],
    locale: str,
    metadata: dict[str, dict[str, Any]] | None = None,
    indent: int = 2,
) -> str:
    """Emit a Flutter ``.arb`` file.

    - ``@@locale`` is always set to *locale*, overriding any source value.
    - For each translated key K, if ``metadata[K]`` is provided, the matching
      ``@K`` block is emitted verbatim immediately after the value entry.
    - Metadata for keys that are not in *translations* is dropped (orphaned
      ``@K`` blocks would point at nothing).
    - Output is JSON with insertion-ordered keys and a trailing newline.
    """
    result: dict[str, Any] = {"@@locale": locale}
    meta = metadata or {}

    for key, value in translations.items():
        result[key] = value
        if key in meta:
            result[f"@{key}"] = meta[key]

    return json.dumps(result, ensure_ascii=False, indent=indent) + "\n"
