"""Unit tests for the MT pipeline logic layer.

All tests are pure — no DB, no LLM calls, no network I/O.
Async callables are faked with unittest.mock.AsyncMock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest  # noqa: I001

from app.mt.glossary import format_glossary_for_prompt
from app.mt.plural import get_cldr_categories, plural_prompt_instruction
from app.mt.post_process import parse_llm_json_output, restore_structural_tags
from app.mt.pre_process import pre_process_batch, substitute_structural_tags
from app.mt.qa import back_translation_qa, cosine_similarity, locale_consistency_eval
from app.mt.validators import validate_string

# ---------------------------------------------------------------------------
# pre_process
# ---------------------------------------------------------------------------


class TestSubstituteStructuralTagsI18next:
    def test_single_trans_tag(self):
        text = "Click <1>here</1> to continue"
        result, smap = substitute_structural_tags("k", text, "i18next")
        assert "{{link_1}}" in result
        assert smap["{{link_1}}"] == "<1>here</1>"
        assert "<1>" not in result

    def test_multiple_trans_tags(self):
        text = "<1>Bold</1> and <2>italic</2> text"
        result, smap = substitute_structural_tags("k", text, "i18next")
        assert "{{link_1}}" in result
        assert "{{link_2}}" in result
        assert smap["{{link_1}}"] == "<1>Bold</1>"
        assert smap["{{link_2}}"] == "<2>italic</2>"

    def test_no_trans_tags_unchanged(self):
        text = "Plain string with {{name}}"
        result, smap = substitute_structural_tags("k", text, "i18next")
        assert result == text
        assert smap == {}

    def test_self_closing_br_untouched(self):
        text = "Line one<br />Line two"
        result, smap = substitute_structural_tags("k", text, "i18next")
        # <br /> is not a numeric Trans tag — should be untouched
        assert "<br />" in result
        assert smap == {}


class TestSubstituteStructuralTagsAndroid:
    def test_bold_tag(self):
        text = "This is <b>important</b> text"
        result, smap = substitute_structural_tags("k", text, "android-xml")
        assert "[BOLD:important]" in result
        assert smap["[BOLD:important]"] == "<b>important</b>"

    def test_italic_tag(self):
        text = "This is <i>emphasized</i> text"
        result, smap = substitute_structural_tags("k", text, "android-xml")
        assert "[ITALIC:emphasized]" in result
        assert smap["[ITALIC:emphasized]"] == "<i>emphasized</i>"

    def test_bold_case_insensitive(self):
        text = "This is <B>bold</B> text"
        result, smap = substitute_structural_tags("k", text, "android-xml")
        assert "[BOLD:bold]" in result

    def test_no_html_tags_unchanged(self):
        text = "Plain %1$s string"
        result, smap = substitute_structural_tags("k", text, "android-xml")
        assert result == text
        assert smap == {}

    def test_unsupported_format_unchanged(self):
        text = "<b>bold</b>"
        result, smap = substitute_structural_tags("k", text, "ios-strings")
        assert result == text
        assert smap == {}


class TestPreProcessBatch:
    def test_batch_with_mixed_keys(self):
        strings = {
            "key_a": "<1>Click</1> here",
            "key_b": "Plain string",
        }
        has_tags = {"key_a": True, "key_b": False}
        result = pre_process_batch(strings, has_tags, "i18next")
        assert "{{link_1}}" in result.processed_strings["key_a"]
        assert result.processed_strings["key_b"] == "Plain string"
        assert result.tag_map["key_b"] == {}


# ---------------------------------------------------------------------------
# post_process
# ---------------------------------------------------------------------------


class TestRestoreStructuralTags:
    def test_single_placeholder_restored(self):
        tag_map = {"{{link_1}}": "<1>here</1>"}
        translated = "Klicken Sie {{link_1}} um fortzufahren"
        result = restore_structural_tags(translated, tag_map)
        assert "<1>here</1>" in result
        assert "{{link_1}}" not in result

    def test_multiple_placeholders_restored(self):
        tag_map = {
            "{{link_1}}": "<1>Bold</1>",
            "{{link_2}}": "<2>italic</2>",
        }
        translated = "{{link_1}} und {{link_2}} Text"
        result = restore_structural_tags(translated, tag_map)
        assert "<1>Bold</1>" in result
        assert "<2>italic</2>" in result

    def test_empty_tag_map(self):
        translated = "Hello world"
        result = restore_structural_tags(translated, {})
        assert result == "Hello world"


class TestParseLlmJsonOutput:
    def test_clean_json(self):
        raw = '{"key_a": "Bonjour", "key_b": "Monde"}'
        result = parse_llm_json_output(raw, ["key_a", "key_b"])
        assert result == {"key_a": "Bonjour", "key_b": "Monde"}

    def test_fenced_json(self):
        raw = '```json\n{"key_a": "Hola"}\n```'
        result = parse_llm_json_output(raw, ["key_a"])
        assert result == {"key_a": "Hola"}

    def test_fenced_no_lang(self):
        raw = '```\n{"key_a": "Ciao"}\n```'
        result = parse_llm_json_output(raw, ["key_a"])
        assert result == {"key_a": "Ciao"}

    def test_extra_keys_ignored(self):
        raw = '{"key_a": "Bonjour", "extra": "ignored"}'
        result = parse_llm_json_output(raw, ["key_a"])
        assert "extra" not in result
        assert result["key_a"] == "Bonjour"

    def test_missing_keys_raises(self):
        raw = '{"key_a": "Bonjour"}'
        with pytest.raises(ValueError, match="missing keys"):
            parse_llm_json_output(raw, ["key_a", "key_b"])

    def test_invalid_json_raises(self):
        raw = "not json at all"
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_llm_json_output(raw, ["key_a"])

    def test_values_cast_to_str(self):
        raw = '{"key_a": 42}'
        result = parse_llm_json_output(raw, ["key_a"])
        assert result["key_a"] == "42"
        assert isinstance(result["key_a"], str)


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------


class TestValidateString:
    def _base_kwargs(self, **overrides):
        defaults = dict(
            source="Hello {{name}}",
            translated="Bonjour {{name}}",
            key_icu_shape="plain",
            key_has_structural_tags=False,
            file_format="i18next",
            max_length=None,
            tag_map={},
            glossary_terms=[],
        )
        defaults.update(overrides)
        return defaults

    def test_clean_string_passes(self):
        result = validate_string(**self._base_kwargs())
        assert result.valid is True
        assert result.errors == []

    def test_placeholder_mismatch(self):
        result = validate_string(
            **self._base_kwargs(
                source="Hello {{name}}",
                translated="Bonjour",  # missing {{name}}
            )
        )
        assert result.valid is False
        assert any("Placeholder mismatch" in e for e in result.errors)

    def test_icu_plural_shape_failure(self):
        result = validate_string(
            **self._base_kwargs(
                source="{count, plural, one {# item} other {# items}}",
                translated="items traduction",  # not an ICU plural
                key_icu_shape="plural",
                file_format="icu",
            )
        )
        assert result.valid is False
        assert any("plural" in e.lower() for e in result.errors)

    def test_icu_plural_shape_passes(self):
        result = validate_string(
            **self._base_kwargs(
                source="{count, plural, one {# item} other {# items}}",
                translated="{count, plural, one {# élément} other {# éléments}}",
                key_icu_shape="plural",
                file_format="icu",
            )
        )
        assert result.valid is True

    def test_structural_tag_missing(self):
        tag_map = {"{{link_1}}": "<1>here</1>"}
        result = validate_string(
            **self._base_kwargs(
                source="Click {{link_1}} to go",
                translated="Cliquez ici",  # placeholder not preserved
                key_has_structural_tags=True,
                tag_map=tag_map,
            )
        )
        assert result.valid is False
        assert any("{{link_1}}" in e for e in result.errors)

    def test_structural_tag_present_passes(self):
        # Both source and translated are in pre-processed form when the
        # validator is called — structural tags have been replaced by
        # {{link_N}} placeholders in both strings.
        tag_map = {"{{link_1}}": "<1>here</1>"}
        result = validate_string(
            **self._base_kwargs(
                source="Click {{link_1}} to go",
                translated="Cliquez {{link_1}} pour continuer",
                key_has_structural_tags=True,
                tag_map=tag_map,
            )
        )
        assert result.valid is True

    def test_max_length_exceeded(self):
        result = validate_string(
            **self._base_kwargs(
                source="Hi",
                translated="A" * 50,
                max_length=10,
            )
        )
        assert result.valid is False
        assert any("max length" in e for e in result.errors)

    def test_max_length_exact_boundary_passes(self):
        result = validate_string(
            **self._base_kwargs(
                source="Hi",
                translated="A" * 10,
                max_length=10,
            )
        )
        assert result.valid is True

    def test_do_not_translate_violation(self):
        # Brand term "ClaritiTMS" must appear verbatim — translating it is a violation
        glossary = [
            {
                "source_term": "ClaritiTMS",
                "target_term": "",
                "do_not_translate": True,
            }
        ]
        result = validate_string(
            **self._base_kwargs(
                source="Welcome to ClaritiTMS",
                translated="Bienvenue dans notre application",  # "ClaritiTMS" missing
                glossary_terms=glossary,
            )
        )
        assert result.valid is False
        assert any("ClaritiTMS" in e for e in result.errors)

    def test_do_not_translate_present_passes(self):
        # Brand term preserved verbatim → valid
        glossary = [
            {
                "source_term": "ClaritiTMS",
                "target_term": "",
                "do_not_translate": True,
            }
        ]
        result = validate_string(
            **self._base_kwargs(
                source="Welcome to ClaritiTMS",
                translated="Bienvenue dans ClaritiTMS",
                glossary_terms=glossary,
            )
        )
        assert result.valid is True

    def test_multiple_errors_accumulate(self):
        result = validate_string(
            **self._base_kwargs(
                source="Hello {{name}}",
                translated="X" * 5,  # missing placeholder + exceeds length=3
                max_length=3,
            )
        )
        assert result.valid is False
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# qa — cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(0.0)

    def test_partial_similarity(self):
        # [1, 0] vs [0.6, 0.8]: dot=0.6, |a|=1, |b|=1 → 0.6
        result = cosine_similarity([1.0, 0.0], [0.6, 0.8])
        assert result == pytest.approx(0.6, abs=1e-6)

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_both_zero_vectors(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0}


class TestBackTranslationQa:
    @pytest.mark.asyncio
    async def test_returns_back_and_similarity(self):
        # ``evaluate_fn`` now returns ``(text, usage)`` per D2; qa.py
        # discards the usage portion.
        evaluate_fn = AsyncMock(return_value=("Hello world", _ZERO_USAGE))
        embed_fn = AsyncMock(
            side_effect=[
                [1.0, 0.0],  # source embedding
                [0.6, 0.8],  # back-translation embedding
            ]
        )
        back, sim = await back_translation_qa(
            source="Hello world",
            translated="Hallo Welt",
            locale="de-DE",
            evaluate_fn=evaluate_fn,
            embed_fn=embed_fn,
        )
        assert back == "Hello world"
        assert sim == pytest.approx(0.6, abs=1e-6)
        evaluate_fn.assert_called_once()
        assert embed_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_identical_embeddings_give_similarity_one(self):
        evaluate_fn = AsyncMock(return_value=("Same", _ZERO_USAGE))
        embed_fn = AsyncMock(return_value=[1.0, 0.0])
        _, sim = await back_translation_qa(
            source="Same",
            translated="Même",
            locale="fr-FR",
            evaluate_fn=evaluate_fn,
            embed_fn=embed_fn,
        )
        assert sim == pytest.approx(1.0)


class TestLocaleConsistencyEval:
    @pytest.mark.asyncio
    async def test_valid_json_response(self):
        raw = '{"naturalness": 5, "consistency": 4, "accuracy": 5, "issue": null}'
        evaluate_fn = AsyncMock(return_value=(raw, _ZERO_USAGE))
        result = await locale_consistency_eval(
            source="Save",
            translated="Enregistrer",
            locale="fr-FR",
            domain_description="SaaS project management tool",
            locale_notes=None,
            tm_neighbors=[],
            evaluate_fn=evaluate_fn,
        )
        assert result["naturalness"] == 5
        assert result["consistency"] == 4
        assert result["accuracy"] == 5
        assert result["issue"] is None

    @pytest.mark.asyncio
    async def test_fenced_json_response(self):
        raw = '```json\n{"naturalness": 4, "consistency": 3, "accuracy": 4, "issue": "register mismatch"}\n```'
        evaluate_fn = AsyncMock(return_value=(raw, _ZERO_USAGE))
        result = await locale_consistency_eval(
            source="Delete",
            translated="Löschen",
            locale="de-DE",
            domain_description="TMS",
            locale_notes="Use formal Sie",
            tm_neighbors=[{"source_text": "Save", "target_text": "Speichern"}],
            evaluate_fn=evaluate_fn,
        )
        assert result["consistency"] == 3
        assert result["issue"] == "register mismatch"

    @pytest.mark.asyncio
    async def test_malformed_json_returns_fallback(self):
        evaluate_fn = AsyncMock(return_value=("not json at all", _ZERO_USAGE))
        result = await locale_consistency_eval(
            source="Cancel",
            translated="Annuler",
            locale="fr-FR",
            domain_description="TMS",
            locale_notes=None,
            tm_neighbors=[],
            evaluate_fn=evaluate_fn,
        )
        assert result["naturalness"] == 3
        assert result["consistency"] == 3
        assert result["accuracy"] == 3
        assert result["issue"] == "parse error"


# ---------------------------------------------------------------------------
# plural
# ---------------------------------------------------------------------------


class TestGetCldrCategories:
    def test_english(self):
        assert get_cldr_categories("en-US") == ["one", "other"]

    def test_english_exact(self):
        assert get_cldr_categories("en") == ["one", "other"]

    def test_japanese_single_form(self):
        assert get_cldr_categories("ja") == ["other"]

    def test_arabic_six_forms(self):
        cats = get_cldr_categories("ar")
        assert "zero" in cats
        assert "few" in cats
        assert len(cats) == 6

    def test_russian_four_forms(self):
        cats = get_cldr_categories("ru")
        assert "few" in cats
        assert "many" in cats

    def test_french_via_prefix(self):
        # fr-CA should match "fr" prefix
        cats = get_cldr_categories("fr-CA")
        assert "one" in cats

    def test_pt_br_override(self):
        # pt-BR differs from pt-PT
        assert get_cldr_categories("pt-BR") == ["one", "other"]

    def test_pt_pt_override(self):
        assert get_cldr_categories("pt-PT") == ["one", "many", "other"]

    def test_unknown_locale_fallback(self):
        cats = get_cldr_categories("xx-XX")
        assert cats == ["one", "other"]


class TestPluralPromptInstruction:
    def test_none_when_no_format(self):
        assert plural_prompt_instruction("en-US", None) is None
        assert plural_prompt_instruction("en-US", "") is None

    def test_icu_format_contains_categories(self):
        instr = plural_prompt_instruction("en-US", "icu")
        assert instr is not None
        assert "one" in instr
        assert "other" in instr
        assert "ICU" in instr

    def test_i18next_suffix_format(self):
        instr = plural_prompt_instruction("en-US", "i18next-suffix")
        assert instr is not None
        assert "one" in instr
        assert "other" in instr

    def test_android_xml_format(self):
        instr = plural_prompt_instruction("en-US", "android-xml")
        assert instr is not None
        assert "quantity" in instr

    def test_stringsdict_format(self):
        instr = plural_prompt_instruction("ja", "stringsdict")
        assert instr is not None
        assert "other" in instr

    def test_arabic_icu_has_all_forms(self):
        instr = plural_prompt_instruction("ar", "icu")
        assert instr is not None
        assert "zero" in instr
        assert "few" in instr
        assert "many" in instr

    def test_unknown_format_generic(self):
        instr = plural_prompt_instruction("en-US", "custom-format")
        assert instr is not None
        assert "plural" in instr.lower()


# ---------------------------------------------------------------------------
# glossary — format_glossary_for_prompt
# ---------------------------------------------------------------------------


class TestFormatGlossaryForPrompt:
    def test_empty_terms(self):
        result = format_glossary_for_prompt([])
        assert result == "No glossary entries for this locale."

    def test_regular_term(self):
        terms = [
            {
                "source_term": "Save",
                "target_term": "Enregistrer",
                "do_not_translate": False,
                "notes": None,
            }
        ]
        result = format_glossary_for_prompt(terms)
        assert '"Save" → "Enregistrer"' in result

    def test_do_not_translate_term(self):
        terms = [
            {
                "source_term": "ClaritiTMS",
                "target_term": "",
                "do_not_translate": True,
                "notes": None,
            }
        ]
        result = format_glossary_for_prompt(terms)
        assert '"ClaritiTMS" → DO NOT TRANSLATE' in result

    def test_term_with_notes(self):
        terms = [
            {
                "source_term": "Dashboard",
                "target_term": "Tableau de bord",
                "do_not_translate": False,
                "notes": "keep lowercase",
            }
        ]
        result = format_glossary_for_prompt(terms)
        assert "[keep lowercase]" in result

    def test_multiple_terms(self):
        terms = [
            {
                "source_term": "Save",
                "target_term": "Speichern",
                "do_not_translate": False,
                "notes": None,
            },
            {
                "source_term": "Cancel",
                "target_term": "Abbrechen",
                "do_not_translate": False,
                "notes": None,
            },
        ]
        result = format_glossary_for_prompt(terms)
        lines = result.split("\n")
        assert len(lines) == 2

    def test_do_not_translate_ignores_notes(self):
        terms = [
            {
                "source_term": "API",
                "target_term": "API",
                "do_not_translate": True,
                "notes": "technical term",
            }
        ]
        result = format_glossary_for_prompt(terms)
        # notes should not appear for do-not-translate (only the DO NOT TRANSLATE marker)
        assert "DO NOT TRANSLATE" in result
        assert "[technical term]" not in result
