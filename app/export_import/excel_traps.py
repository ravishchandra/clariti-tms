"""Excel-specific input sanitization — the traps from docs/07:240-248.

These helpers are pure (no I/O) so they can be unit-tested without touching
openpyxl. The parser in :mod:`app.export_import.parse` applies them as the
final step before handing a row to the validator layer.

Traps handled here:

* Leading zeros / scientific-notation numerics — solved by *not* coercing
  numeric-looking strings; we always treat translation-text columns as text
  (openpyxl's `cell.value` honors the cell's stored format, which the
  exporter sets to `@` text format).
* `\r\n` -> `\n` newline normalization.
* Leading/trailing whitespace stripping (with an opt-out for callers who
  know the source had it — we don't have that knowledge here, so we always
  strip per the doc).
* Unicode NFC normalization on every text cell.

`.xlsm` rejection lives at the file-extension layer in :mod:`parse`, not
here, because it's a file-shape check rather than a cell-content fix.
"""

from __future__ import annotations

import unicodedata
from typing import Final

# Set of file suffixes we accept. Anything else (including `.xlsm`, `.csv`,
# `.xls`) is rejected at parse-time.
ACCEPTED_EXTENSIONS: Final[frozenset[str]] = frozenset({".xlsx"})

# Magic-number prefix for a real .xlsx (which is a ZIP archive). A CSV file
# renamed `.xlsx` will fail this check.
_ZIP_MAGIC: Final[bytes] = b"PK\x03\x04"
_ZIP_EMPTY_MAGIC: Final[bytes] = b"PK\x05\x06"
_ZIP_SPANNED_MAGIC: Final[bytes] = b"PK\x07\x08"


def is_zip_signature(head: bytes) -> bool:
    """Return True iff *head* starts with a ZIP local-file-header signature.

    A valid `.xlsx` is a ZIP archive, so the first 4 bytes must be one of
    the standard ZIP magic numbers. This is the cheapest robust defense
    against a `.csv` (or anything else) renamed to `.xlsx`.
    """
    if len(head) < 4:
        return False
    return head[:4] in (_ZIP_MAGIC, _ZIP_EMPTY_MAGIC, _ZIP_SPANNED_MAGIC)


def normalize_cell_text(value: object) -> str | None:
    """Normalize a raw cell value into a clean string.

    * ``None`` stays ``None``.
    * Numerics (int / float) are stringified verbatim — they're only ever
      seen here when the exporter put them in non-text columns (e.g.
      `max_length`). For text columns the exporter sets `@` format so
      openpyxl returns a `str` directly, preserving leading zeros.
    * `\r\n` and `\r` collapse to `\n`.
    * Leading / trailing whitespace stripped.
    * Unicode NFC-normalized.

    Returns an empty string for blank cells (`""`) to keep the caller
    code path simple; the caller decides whether `""` is treated as
    "blank" or "user wrote empty string".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool subclasses int, so it must be checked first.
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        # Be conservative — anything else (datetime, etc.) stringifies.
        text = str(value)
    else:
        text = value

    # \r\n -> \n; bare \r -> \n. Done in two passes so a lone \r is caught.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    text = unicodedata.normalize("NFC", text)
    return text


def normalize_int(value: object) -> int | None:
    """Coerce a cell value to int or ``None``. Empty / blank → ``None``.

    openpyxl returns ints natively for integer-formatted cells. A reviewer
    who manually retypes an int may produce a float — we accept that too.
    Anything else returns ``None`` (the value is treated as "no limit").
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None  # bools are not lengths
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Only accept floats that are whole numbers — anything else is a
        # data-quality issue we don't want to silently round.
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


__all__ = [
    "ACCEPTED_EXTENSIONS",
    "is_zip_signature",
    "normalize_cell_text",
    "normalize_int",
]
