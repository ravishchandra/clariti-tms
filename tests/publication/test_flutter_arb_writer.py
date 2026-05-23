"""Tests for the Flutter ARB writer.

Focuses on round-trip behavior: writing a translated dict and re-parsing the
result with the A1 parser should preserve keys, values, and metadata.
"""

from __future__ import annotations

import json

from app.ingestion.parsers.flutter_arb import parse_flutter_arb
from app.publication.writers.flutter_arb import serialize_flutter_arb


class TestSerializeFlutterArb:
    def test_minimal_output_with_locale(self):
        out = serialize_flutter_arb({}, locale="fr-FR")
        loaded = json.loads(out)
        assert loaded == {"@@locale": "fr-FR"}

    def test_keys_emitted_in_insertion_order(self):
        out = serialize_flutter_arb({"a": "Alpha", "b": "Bravo", "c": "Charlie"}, locale="es-ES")
        loaded = json.loads(out)
        # @@locale first, then translations in given order
        assert list(loaded.keys()) == ["@@locale", "a", "b", "c"]
        assert loaded["a"] == "Alpha"
        assert loaded["b"] == "Bravo"
        assert loaded["c"] == "Charlie"

    def test_locale_overrides_source_locale(self):
        out = serialize_flutter_arb({"label": "Salut"}, locale="fr-FR")
        loaded = json.loads(out)
        assert loaded["@@locale"] == "fr-FR"

    def test_metadata_block_emitted_after_value(self):
        meta = {
            "greeting": {
                "description": "Welcome greeting on the home screen",
                "placeholders": {"name": {"type": "String"}},
            }
        }
        out = serialize_flutter_arb({"greeting": "Bonjour, {name}!"}, locale="fr-FR", metadata=meta)
        loaded = json.loads(out)
        assert loaded["greeting"] == "Bonjour, {name}!"
        assert loaded["@greeting"] == meta["greeting"]

    def test_orphan_metadata_keys_dropped(self):
        meta = {"missing": {"description": "no matching value"}}
        out = serialize_flutter_arb({"label": "Hi"}, locale="en", metadata=meta)
        loaded = json.loads(out)
        assert "@missing" not in loaded

    def test_trailing_newline(self):
        out = serialize_flutter_arb({"k": "v"}, locale="en")
        assert out.endswith("\n")


class TestRoundTrip:
    def test_simple_keys_round_trip(self):
        translations = {"title": "Settings", "save": "Save", "cancel": "Cancel"}
        out = serialize_flutter_arb(translations, locale="fr-FR")
        parsed = parse_flutter_arb(out, "app_fr.arb")
        by_key = {k.key: k.source_text for k in parsed}
        assert by_key == translations

    def test_metadata_preserved_through_round_trip(self):
        translations = {"greeting": "Bonjour, {name}!"}
        meta = {
            "greeting": {
                "description": "Welcome greeting on the home screen",
                "placeholders": {"name": {"type": "String", "example": "Jane"}},
            }
        }
        out = serialize_flutter_arb(translations, locale="fr-FR", metadata=meta)
        parsed = parse_flutter_arb(out, "app_fr.arb")
        assert len(parsed) == 1
        pk = parsed[0]
        assert pk.key == "greeting"
        assert pk.source_text == "Bonjour, {name}!"
        # Description survives parse
        assert pk.description == "Welcome greeting on the home screen"
        # Placeholders re-extracted from the value
        assert pk.placeholders == ["{name}"]

    def test_icu_plural_round_trip(self):
        translations = {"itemCount": "{count, plural, =0{Aucun} =1{1 article} other{{count} articles}}"}
        meta = {
            "itemCount": {
                "description": "Number of items in cart",
                "placeholders": {"count": {"type": "int"}},
            }
        }
        out = serialize_flutter_arb(translations, locale="fr-FR", metadata=meta)
        parsed = parse_flutter_arb(out, "app_fr.arb")
        assert parsed[0].icu_shape == "plural"
        assert parsed[0].description == "Number of items in cart"

    def test_multiple_keys_with_partial_metadata(self):
        translations = {
            "title": "Réglages",
            "greeting": "Salut, {name}",
            "save": "Enregistrer",
        }
        meta = {"greeting": {"description": "Greeting on home"}}
        out = serialize_flutter_arb(translations, locale="fr-FR", metadata=meta)
        parsed = parse_flutter_arb(out, "app_fr.arb")
        by_key = {k.key: k for k in parsed}
        assert set(by_key) == {"title", "greeting", "save"}
        assert by_key["greeting"].description == "Greeting on home"
        assert by_key["title"].description is None
        assert by_key["save"].description is None

    def test_empty_dict_round_trip(self):
        out = serialize_flutter_arb({}, locale="de-DE")
        parsed = parse_flutter_arb(out, "app_de.arb")
        assert parsed == []
        # And the file is still valid JSON with the locale directive
        assert json.loads(out) == {"@@locale": "de-DE"}
