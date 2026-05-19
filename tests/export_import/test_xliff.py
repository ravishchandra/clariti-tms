"""Tests for the Phase 7 XLIFF 1.2 round-trip.

These are *pure* unit tests: they assemble :class:`ExportRow` fixtures in
memory, run them through :func:`export_to_xliff_bytes`, then parse the
result back through :func:`parse_xliff_bytes`. No DB.

What this file verifies (per Phase 7 spec):

  * Round-trip: a known set of rows survives export -> parse with no data
    loss on identity fields (UUID, key, source, status).
  * State mapping: each :class:`TranslationStatus` serialises to the
    expected XLIFF state and parses back to the expected XLSX
    ``reviewer_action`` vocabulary.
  * Placeholder preservation: ``{{name}}`` -> ``<ph>`` -> ``{{name}}``
    across both ``<source>`` and ``<target>``.
  * ICU plural: a plural source string round-trips into one trans-unit
    per CLDR category and the ``other`` category survives import.
  * Source-hash conflict signal: the per-row source hash is preserved
    so the import side's conflict detector can fire when the source
    text in the DB has changed since export.
  * XLIFF 2.0 / 2.1 documents are rejected with a clear error.

DB-touching paths (``fetch_export_rows``, ``preview_import``,
``commit_import``) are tested in the existing
``tests/export_import/test_import.py`` integration suite; this module
deliberately stays pure so it runs in any environment.
"""

from __future__ import annotations

import hashlib
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from app.export_import.export import ExportRequest, ExportRow
from app.export_import.parse import ImportParseError
from app.export_import.xliff_export import (
    CLARITI_NS,
    PLURAL_ID_SEPARATOR,
    XLIFF_NS,
    XLIFF_STATE_FINAL,
    XLIFF_STATE_NEEDS_TRANSLATION,
    XLIFF_STATE_NEW,
    XLIFF_STATE_REJECTED,
    XLIFF_STATE_TRANSLATED,
    export_to_xliff_bytes,
)
from app.export_import.xliff_export import (
    build_filename as build_xliff_filename,
)
from app.export_import.xliff_import import parse_xliff_bytes

# ---------------------------------------------------------------------------
# Fixtures — small in-memory rows, pinned UUIDs so assertions are stable.
# ---------------------------------------------------------------------------


_PROJECT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_TIMESTAMP = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)


def _row(
    key: str,
    *,
    internal_id: uuid.UUID,
    source_text: str = "Hello",
    current_translation: str | None = "Bonjour",
    mt_suggestion: str | None = None,
    status: str = "needs_review",
    component: str | None = "Greeting",
    screen: str | None = "home",
    max_length: int | None = 50,
    placeholders: list[str] | None = None,
    risk_class: str = "standard",
    description: str | None = "Welcome banner",
) -> ExportRow:
    return ExportRow(
        key=key,
        source_text=source_text,
        description=description,
        component=component,
        screen=screen,
        max_length=max_length,
        placeholders=list(placeholders) if placeholders is not None else [],
        risk_class=risk_class,
        current_translation=current_translation,
        mt_suggestion=mt_suggestion or current_translation,
        status=status,
        internal_id=internal_id,
    )


def _request(rows_by_locale: dict[str, list[ExportRow]], status_filter: str | None = "needs_review") -> ExportRequest:
    return ExportRequest(
        project_id=_PROJECT_ID,
        project_slug="clariti-web",
        status_filter=status_filter,
        exported_by_email="ravish@clariti.app",
        exported_by_user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        export_timestamp=_TIMESTAMP,
        rows_by_locale=rows_by_locale,
    )


# ---------------------------------------------------------------------------
# XML shape & structural assertions
# ---------------------------------------------------------------------------


class TestXmlShape:
    def test_root_is_xliff_12(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("greeting.hello", internal_id=rid)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        assert root.tag == f"{{{XLIFF_NS}}}xliff"
        assert root.get("version") == "1.2"

    def test_one_file_per_locale(self) -> None:
        rid_a = uuid.uuid4()
        rid_b = uuid.uuid4()
        rows_fr = [_row("k1", internal_id=rid_a)]
        rows_de = [_row("k1", internal_id=rid_b)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows_fr, "de-DE": rows_de}))
        root = ET.fromstring(data)
        files = root.findall(f"{{{XLIFF_NS}}}file")
        assert len(files) == 2
        langs = {f.get("target-language") for f in files}
        assert langs == {"fr-FR", "de-DE"}
        # Source language constant.
        for f in files:
            assert f.get("source-language") == "en-US"

    def test_clariti_project_id_on_file(self) -> None:
        rows = [_row("k", internal_id=uuid.uuid4())]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        file_el = root.find(f"{{{XLIFF_NS}}}file")
        assert file_el is not None
        assert file_el.get(f"{{{CLARITI_NS}}}project-id") == str(_PROJECT_ID)

    def test_export_hash_attribute_present_and_deterministic(self) -> None:
        rid = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
        rows = [_row("k", internal_id=rid)]
        data1 = export_to_xliff_bytes(_request({"fr-FR": rows}))
        data2 = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root1 = ET.fromstring(data1)
        root2 = ET.fromstring(data2)
        h1 = root1.find(f"{{{XLIFF_NS}}}file").get(f"{{{CLARITI_NS}}}export-hash")  # type: ignore[union-attr]
        h2 = root2.find(f"{{{XLIFF_NS}}}file").get(f"{{{CLARITI_NS}}}export-hash")  # type: ignore[union-attr]
        assert h1 is not None
        assert h1 == h2
        assert len(h1) == 64

    def test_trans_unit_per_row(self) -> None:
        rids = [uuid.uuid4() for _ in range(3)]
        rows = [_row(f"k{i}", internal_id=rid) for i, rid in enumerate(rids)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        units = root.findall(f".//{{{XLIFF_NS}}}trans-unit")
        assert len(units) == 3
        observed_ids = {u.get("id") for u in units}
        assert observed_ids == {str(r) for r in rids}

    def test_xml_declaration_emitted(self) -> None:
        data = export_to_xliff_bytes(_request({"fr-FR": [_row("k", internal_id=uuid.uuid4())]}))
        # The very first bytes should be ``<?xml`` so lxml-based tools see
        # the declaration and apply the right encoding.
        assert data.startswith(b"<?xml")


# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------


class TestStateMapping:
    @pytest.mark.parametrize(
        "status,expected_state",
        [
            ("draft", XLIFF_STATE_NEW),
            ("mt_proposed", XLIFF_STATE_NEW),
            ("needs_review", XLIFF_STATE_NEEDS_TRANSLATION),
            ("needs_more_context", XLIFF_STATE_NEEDS_TRANSLATION),
            ("approved", XLIFF_STATE_TRANSLATED),
            ("published", XLIFF_STATE_FINAL),
            ("rejected", XLIFF_STATE_REJECTED),
        ],
    )
    def test_status_serialises_to_state(self, status: str, expected_state: str) -> None:
        rows = [_row("k", internal_id=uuid.uuid4(), status=status)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        target = root.find(f".//{{{XLIFF_NS}}}target")
        assert target is not None
        assert target.get("state") == expected_state

    def test_state_translated_parses_to_edit_when_target_present(self) -> None:
        # Spec: "Edited content with state ``translated`` => ``edit``".
        # XLIFF carries the translator's output as the ``<target>``, so
        # every accepted row routes through ``edit`` (which copies
        # edited_translation -> value) rather than ``yes`` (which copies
        # mt_suggestion -> value).
        rid = uuid.uuid4()
        rows = [
            _row("k", internal_id=rid, status="approved", current_translation="Bonjour"),
        ]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.reviewer_action == "edit"
        assert row.edited_translation == "Bonjour"

    def test_state_rejected_parses_to_no(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, status="rejected", current_translation="Bonjour")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.reviewer_action == "no"

    def test_state_needs_translation_parses_to_skip(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, status="needs_review", current_translation="Bonjour")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        # `None` reviewer_action classifies as a skip in the planner.
        assert row.reviewer_action is None

    def test_state_new_parses_to_skip(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, status="draft", current_translation=None)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.reviewer_action is None

    def test_state_translated_with_empty_target_skips(self) -> None:
        # Spec edge: state=translated but empty target -> treat as skip.
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, status="approved", current_translation="")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.reviewer_action is None


# ---------------------------------------------------------------------------
# Placeholder preservation
# ---------------------------------------------------------------------------


class TestPlaceholderRoundTrip:
    def test_i18next_placeholder_round_trips(self) -> None:
        rid = uuid.uuid4()
        rows = [
            _row(
                "pay",
                internal_id=rid,
                source_text="Pay {{amount}}",
                current_translation="Payer {{amount}}",
                status="approved",
            )
        ]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        # The XML carries the placeholder as a <ph> child, not raw text.
        root = ET.fromstring(data)
        source = root.find(f".//{{{XLIFF_NS}}}source")
        assert source is not None
        ph_elements = source.findall(f"{{{XLIFF_NS}}}ph")
        assert len(ph_elements) == 1
        assert ph_elements[0].text == "{{amount}}"
        assert ph_elements[0].get("ctype") == "x-icu-placeholder"

        # Round-trip: parsed text reassembles the bare {{amount}} syntax.
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.source_text == "Pay {{amount}}"
        # Approved -> state=translated -> reviewer_action=edit;
        # edited_translation carries the target text.
        assert row.edited_translation == "Payer {{amount}}"

    def test_multiple_placeholders_round_trip_in_order(self) -> None:
        rid = uuid.uuid4()
        rows = [
            _row(
                "msg",
                internal_id=rid,
                source_text="Hello {{name}}, you have {{count}} messages",
                current_translation="Bonjour {{name}}, vous avez {{count}} messages",
                status="approved",
            )
        ]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        source = root.find(f".//{{{XLIFF_NS}}}source")
        assert source is not None
        ph_elements = source.findall(f"{{{XLIFF_NS}}}ph")
        assert [p.text for p in ph_elements] == ["{{name}}", "{{count}}"]
        assert [p.get("id") for p in ph_elements] == ["1", "2"]

        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.source_text == "Hello {{name}}, you have {{count}} messages"

    def test_no_placeholders_passes_text_through(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, source_text="Hello", current_translation="Bonjour")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.source_text == "Hello"


# ---------------------------------------------------------------------------
# ICU plural round-trip
# ---------------------------------------------------------------------------


class TestIcuPluralRoundTrip:
    def test_plural_splits_into_one_unit_per_category(self) -> None:
        rid = uuid.uuid4()
        source = "{count, plural, one {# item} other {# items}}"
        target = "{count, plural, one {# article} other {# articles}}"
        rows = [
            _row(
                "items",
                internal_id=rid,
                source_text=source,
                current_translation=target,
                status="approved",
            )
        ]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        units = root.findall(f".//{{{XLIFF_NS}}}trans-unit")
        assert len(units) == 2

        # Ids carry the ``<uuid>:plural-<cat>`` suffix.
        observed_cats = []
        for u in units:
            unit_id = u.get("id", "")
            assert PLURAL_ID_SEPARATOR in unit_id, unit_id
            base, _, cat = unit_id.partition(PLURAL_ID_SEPARATOR)
            assert base == str(rid)
            observed_cats.append(cat)
        assert set(observed_cats) == {"one", "other"}

    def test_plural_other_category_imports_to_canonical_row(self) -> None:
        # For v1, only the ``other`` category becomes the import row;
        # other categories are observed but not applied.
        rid = uuid.uuid4()
        source = "{count, plural, one {# item} other {# items}}"
        target = "{count, plural, one {# article} other {# articles}}"
        rows = [
            _row(
                "items",
                internal_id=rid,
                source_text=source,
                current_translation=target,
                status="approved",
            )
        ]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        assert len(parsed.rows_by_locale["fr-FR"]) == 1
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.internal_id == rid

    def test_non_plural_string_emits_single_unit(self) -> None:
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, source_text="Hello")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        units = root.findall(f".//{{{XLIFF_NS}}}trans-unit")
        assert len(units) == 1
        # No plural suffix on the id.
        unit_id = units[0].get("id", "")
        assert PLURAL_ID_SEPARATOR not in unit_id


# ---------------------------------------------------------------------------
# Source-hash propagation (conflict-detection signal)
# ---------------------------------------------------------------------------


class TestSourceHashPropagation:
    def test_source_hash_note_present_on_each_unit(self) -> None:
        rid = uuid.uuid4()
        source = "Hello world"
        rows = [_row("k", internal_id=rid, source_text=source)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        root = ET.fromstring(data)
        unit = root.find(f".//{{{XLIFF_NS}}}trans-unit")
        assert unit is not None
        # Find the hash note.
        notes = unit.findall(f"{{{XLIFF_NS}}}note")
        hash_notes = [n.text for n in notes if (n.text or "").startswith("hash:")]
        assert len(hash_notes) == 1
        assert hash_notes[0] is not None

    def test_hash_round_trips_into_parsed_row(self) -> None:
        rid = uuid.uuid4()
        source = "Hello world"
        rows = [_row("k", internal_id=rid, source_text=source)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        # Hash is sha256 of the NFC-normalised source text.
        expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert row.source_hash_at_export == expected

    def test_source_changed_detection_signal(self) -> None:
        # Simulate the import-time scenario where the DB's source text has
        # changed since export. Conflict detection runs at the
        # ``app.export_import.conflicts`` layer; what we verify here is
        # that the per-row hash IS preserved so the conflict detector has
        # a stable signal to compare against.
        rid = uuid.uuid4()
        rows = [_row("k", internal_id=rid, source_text="Hello world")]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        row = parsed.rows_by_locale["fr-FR"][0]
        assert row.source_hash_at_export is not None

        # Now compute the hash of a *different* current source text — this
        # is what the DB-side would have after a source-change. The two
        # hashes must differ, which is precisely what
        # ``detect_conflicts`` keys on.
        new_source_hash = hashlib.sha256(b"Hello world!").hexdigest()
        assert new_source_hash != row.source_hash_at_export


# ---------------------------------------------------------------------------
# Version rejection — XLIFF 2.0 / 2.1
# ---------------------------------------------------------------------------


class TestVersionRejection:
    def test_xliff_20_rejected_with_clear_error(self) -> None:
        # Hand-craft a minimal XLIFF 2.0 document (different namespace +
        # version). The parser must reject before doing any data extraction.
        xliff_20 = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" '
            b'srcLang="en-US" trgLang="fr-FR">'
            b'<file id="f1"><unit id="u1"><segment><source>Hi</source>'
            b"<target>Salut</target></segment></unit></file>"
            b"</xliff>"
        )
        with pytest.raises(ImportParseError, match="Unsupported XLIFF version"):
            parse_xliff_bytes(xliff_20)

    def test_xliff_21_rejected(self) -> None:
        xliff_21 = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<xliff version="2.1" xmlns="urn:oasis:names:tc:xliff:document:2.0" '
            b'srcLang="en-US" trgLang="fr-FR">'
            b"<file><unit><segment><source>Hi</source>"
            b"<target>Salut</target></segment></unit></file>"
            b"</xliff>"
        )
        with pytest.raises(ImportParseError, match="Unsupported XLIFF version"):
            parse_xliff_bytes(xliff_21)

    def test_non_xliff_root_rejected(self) -> None:
        not_xliff = b'<?xml version="1.0"?><tmx version="1.4"><body/></tmx>'
        with pytest.raises(ImportParseError, match="Expected root element 'xliff'"):
            parse_xliff_bytes(not_xliff)

    def test_empty_bytes_rejected(self) -> None:
        with pytest.raises(ImportParseError, match="Empty file"):
            parse_xliff_bytes(b"")

    def test_malformed_xml_rejected(self) -> None:
        with pytest.raises(ImportParseError, match="XLIFF parse error"):
            parse_xliff_bytes(b"<xliff version='1.2'><file><body><trans-unit></file>")

    def test_unsupported_extension_rejected_in_path_api(self, tmp_path: object) -> None:
        # Path-API rejects extensions outside .xlf / .xliff. Use a real
        # tmp dir via the pytest fixture so the file-not-found path doesn't
        # interfere.
        from pathlib import Path

        from app.export_import.xliff_import import parse_xliff_path

        target = Path(str(tmp_path)) / "evil.docx"
        target.write_bytes(b"<xliff version='1.2'/>")
        with pytest.raises(ImportParseError, match="Unsupported file extension"):
            parse_xliff_path(target)


# ---------------------------------------------------------------------------
# Full round-trip — the headline acceptance criterion
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_known_set_survives_export_then_parse(self) -> None:
        rid_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
        rid_b = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
        rid_c = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")

        rows = [
            _row(
                "greeting.hello",
                internal_id=rid_a,
                source_text="Hello {{name}}",
                current_translation="Bonjour {{name}}",
                status="approved",
            ),
            _row(
                "checkout.button",
                internal_id=rid_b,
                source_text="Pay",
                current_translation=None,
                status="draft",
            ),
            _row(
                "error.network",
                internal_id=rid_c,
                source_text="Network error",
                current_translation="Erreur réseau",
                status="rejected",
            ),
        ]

        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)

        # Meta survives.
        assert parsed.meta.project_id == _PROJECT_ID
        assert parsed.meta.export_timestamp is not None
        assert parsed.meta.export_hash is not None

        # All three rows landed in the right locale tab.
        out_rows = parsed.rows_by_locale["fr-FR"]
        assert len(out_rows) == 3
        by_id = {r.internal_id: r for r in out_rows}
        assert set(by_id.keys()) == {rid_a, rid_b, rid_c}

        # Approved row -> reviewer_action=edit, edited_translation set.
        assert by_id[rid_a].reviewer_action == "edit"
        assert by_id[rid_a].edited_translation == "Bonjour {{name}}"
        assert by_id[rid_a].source_text == "Hello {{name}}"

        # Draft row -> no-op skip.
        assert by_id[rid_b].reviewer_action is None

        # Rejected row -> "no".
        assert by_id[rid_c].reviewer_action == "no"

    def test_total_rows_count_matches(self) -> None:
        rows = [_row(f"k{i}", internal_id=uuid.uuid4()) for i in range(7)]
        data = export_to_xliff_bytes(_request({"fr-FR": rows}))
        parsed = parse_xliff_bytes(data)
        assert parsed.total_rows == 7

    def test_empty_locale_round_trips(self) -> None:
        # Edge case: a locale present in the request but with no rows.
        data = export_to_xliff_bytes(_request({"fr-FR": []}))
        parsed = parse_xliff_bytes(data)
        assert "fr-FR" in parsed.rows_by_locale
        assert parsed.rows_by_locale["fr-FR"] == []


# ---------------------------------------------------------------------------
# Filename helper
# ---------------------------------------------------------------------------


class TestBuildFilename:
    def test_single_locale_filename(self) -> None:
        name = build_xliff_filename("clariti-web", ["fr-FR"], "needs_review", _TIMESTAMP)
        assert name == "clariti-web_fr-FR_2026-05-18_needs-review.xlf"

    def test_multi_locale_collapses_to_multi(self) -> None:
        name = build_xliff_filename("clariti-web", ["fr-FR", "de-DE"], "needs_review", _TIMESTAMP)
        assert name == "clariti-web_multi_2026-05-18_needs-review.xlf"

    def test_no_status_filter_renders_all(self) -> None:
        name = build_xliff_filename("clariti-web", ["fr-FR"], None, _TIMESTAMP)
        assert name == "clariti-web_fr-FR_2026-05-18_all.xlf"


# ---------------------------------------------------------------------------
# Format auto-detection (the commit-side dispatcher)
# ---------------------------------------------------------------------------


class TestFormatAutoDetect:
    def test_xlf_extension_routes_to_xliff(self) -> None:
        from app.export_import.commit import FORMAT_XLIFF, _detect_format

        assert _detect_format(filename="out.xlf", file_path=None) == FORMAT_XLIFF

    def test_xliff_extension_routes_to_xliff(self) -> None:
        from app.export_import.commit import FORMAT_XLIFF, _detect_format

        assert _detect_format(filename="out.xliff", file_path=None) == FORMAT_XLIFF

    def test_xlsx_extension_routes_to_xlsx(self) -> None:
        from app.export_import.commit import FORMAT_XLSX, _detect_format

        assert _detect_format(filename="review.xlsx", file_path=None) == FORMAT_XLSX

    def test_unknown_extension_defaults_to_xlsx(self) -> None:
        from app.export_import.commit import FORMAT_XLSX, _detect_format

        # No / unknown extension -> XLSX (preserves Phase-5 behaviour).
        assert _detect_format(filename="weird.bin", file_path=None) == FORMAT_XLSX
        assert _detect_format(filename=None, file_path=None) == FORMAT_XLSX

    def test_file_path_used_when_filename_missing(self) -> None:
        from app.export_import.commit import FORMAT_XLIFF, _detect_format

        assert _detect_format(filename=None, file_path="/tmp/example.xlf") == FORMAT_XLIFF
