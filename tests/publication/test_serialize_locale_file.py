"""Dispatcher-level tests for `serialize_locale_file`.

The publication pipeline glue: given a `Repository` (file_format-bearing) and
a translations dict, emit the right serialised locale file. Most of the
heavy lifting lives in the per-format writers — this file pins the dispatch
contract and the metadata pass-through for Flutter ARB (the only format
that consumes per-key metadata today).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.publication.helpers import serialize_locale_file


@dataclass
class _RepoStub:
    """Minimal stand-in for app.models.Repository — only the fields the
    helpers touch. Avoids dragging in SQLAlchemy + a real session."""
    file_format: str
    github_path: str | None = ""
    source_file: str | None = None
    id: uuid.UUID = uuid.uuid4()


def test_flutter_arb_metadata_passes_through():
    """When key_metadata is supplied for a Flutter repo, the emitted ARB
    contains the matching `@key` block. This is the round-trip fix —
    without this, published .arb files lose every developer-authored
    description, placeholder type hint, and x-extension on publish.
    """
    repo = _RepoStub(file_format="flutter-arb")
    translations = {"greeting": "Bonjour, {name}!", "items": "Articles"}
    metadata = {
        "greeting": {
            "description": "Welcome greeting on the home screen",
            "placeholders": {"name": {"type": "String"}},
        }
    }

    out = serialize_locale_file(translations, repo, "fr-FR", key_metadata=metadata)
    decoded = json.loads(out)

    assert decoded["@@locale"] == "fr-FR"
    assert decoded["greeting"] == "Bonjour, {name}!"
    assert decoded["@greeting"] == metadata["greeting"]
    assert decoded["items"] == "Articles"
    # No metadata for `items` → no `@items` block emitted.
    assert "@items" not in decoded


def test_flutter_arb_without_metadata_still_works():
    """Backwards-compat: a Flutter repo with no metadata supplied still
    produces a valid (if minimal) ARB file."""
    repo = _RepoStub(file_format="flutter-arb")
    out = serialize_locale_file({"label": "Bonjour"}, repo, "fr-FR")
    decoded = json.loads(out)
    assert decoded == {"@@locale": "fr-FR", "label": "Bonjour"}


def test_metadata_ignored_by_non_flutter_writers():
    """key_metadata is a Flutter-specific concept today. Passing it to a
    non-Flutter writer must not raise — the writer just ignores it."""
    repo = _RepoStub(file_format="i18next", source_file="en/common.json")
    out = serialize_locale_file(
        {"label": "Bonjour"},
        repo,
        "fr-FR",
        key_metadata={"label": {"description": "ignored for i18next"}},
    )
    # i18next output doesn't have any concept of @key metadata —
    # the call just succeeds and emits the JSON.
    decoded = json.loads(out)
    assert decoded == {"label": "Bonjour"}
