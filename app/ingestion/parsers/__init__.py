"""Platform parser package.

Public API
----------
``parse_file(content, filename, file_format) -> ParseResult``
    Single entry point for all callers.  Dispatches to the correct
    platform parser based on ``file_format`` and returns a ``ParseResult``.
"""

from __future__ import annotations

from .android import parse_android_file
from .ios import parse_ios_file
from .react import parse_react_file
from .types import ParsedKey, ParseResult

__all__ = [
    "ParsedKey",
    "ParseResult",
    "parse_file",
]

# Mapping from file_format string to (parser_fn, platform, canonical_format)
_DISPATCH: dict[str, tuple[object, str, str]] = {
    "ios-strings": (parse_ios_file, "ios", "ios-strings"),
    "ios-xcstrings": (parse_ios_file, "ios", "ios-xcstrings"),
    "ios-stringsdict": (parse_ios_file, "ios", "ios-stringsdict"),
    "android-xml": (parse_android_file, "android", "android-xml"),
    "i18next": (parse_react_file, "web", "i18next"),
    "icu": (parse_react_file, "web", "icu"),
    "flat-json": (parse_react_file, "web", "flat-json"),
}


def parse_file(content: str, filename: str, file_format: str) -> ParseResult:
    """Parse *content* as *file_format* and return a ``ParseResult``.

    Parameters
    ----------
    content:
        Raw file content as a string.  Callers are responsible for reading
        the file and decoding to str (UTF-8 is assumed for all formats).
    filename:
        Original file name (used for component inference and format dispatch).
        May be a bare name or a full path; only the basename and extension
        are used by parsers.
    file_format:
        One of: ``ios-strings``, ``ios-xcstrings``, ``ios-stringsdict``,
        ``android-xml``, ``i18next``, ``icu``, ``flat-json``.

    Raises
    ------
    ValueError
        If ``file_format`` is unknown.
    """
    entry = _DISPATCH.get(file_format)
    if entry is None:
        raise ValueError(f"Unknown file_format {file_format!r}. Valid formats: {sorted(_DISPATCH)}")

    parser_fn, platform, canonical_format = entry
    keys = parser_fn(content, filename)  # type: ignore[operator]

    return ParseResult(
        keys=keys,
        platform=platform,
        file_format=canonical_format,
        source_file=filename,
    )
