"""Unit tests for platform parsers.

All test data is inline — no external fixture files required.
Tests use plain pytest functions (no classes).
"""

from __future__ import annotations

import pytest

from app.ingestion.parsers import parse_file
from app.ingestion.parsers.android import parse_android_file, parse_strings_xml
from app.ingestion.parsers.common import (
    detect_icu_shape,
    detect_structural_tags,
    extract_placeholders,
    infer_component_from_key,
    infer_risk_class,
    infer_string_type,
)
from app.ingestion.parsers.flutter_arb import parse_flutter_arb
from app.ingestion.parsers.ios import (
    parse_ios_file,
    parse_strings_file,
    parse_stringsdict_file,
    parse_xcstrings_file,
)
from app.ingestion.parsers.react import (
    flatten_json,
    parse_namespace_json,
    parse_react_file,
)
from app.ingestion.parsers.types import ParseResult

# ===========================================================================
# Common utilities
# ===========================================================================


class TestExtractPlaceholders:
    # -----------------------------------------------------------------------
    # iOS
    # -----------------------------------------------------------------------
    def test_ios_percent_at(self):
        result = extract_placeholders("Hello %@", "ios-strings")
        assert result == ["%@"]

    def test_ios_percent_d(self):
        result = extract_placeholders("Count: %d items", "ios-strings")
        assert result == ["%d"]

    def test_ios_positional(self):
        result = extract_placeholders("%1$@ and %2$d", "ios-strings")
        assert result == ["%1$@", "%2$d"]

    def test_ios_deduplication(self):
        result = extract_placeholders("%@ foo %@", "ios-strings")
        assert result == ["%@"]

    def test_ios_xcstrings_same_as_strings(self):
        result = extract_placeholders("%1$@ done", "ios-xcstrings")
        assert result == ["%1$@"]

    # -----------------------------------------------------------------------
    # Android
    # -----------------------------------------------------------------------
    def test_android_positional(self):
        result = extract_placeholders("%1$s clicked %2$d times", "android-xml")
        assert result == ["%1$s", "%2$d"]

    def test_android_non_positional_not_extracted(self):
        # Android spec requires positional; bare %s is non-standard and skipped
        result = extract_placeholders("%s plain", "android-xml")
        assert result == []

    # -----------------------------------------------------------------------
    # i18next
    # -----------------------------------------------------------------------
    def test_i18next_double_curly(self):
        result = extract_placeholders("Hello {{name}}, you have {{count}} items", "i18next")
        assert result == ["{{name}}", "{{count}}"]

    def test_i18next_dedup(self):
        result = extract_placeholders("{{name}} and {{name}}", "i18next")
        assert result == ["{{name}}"]

    # -----------------------------------------------------------------------
    # ICU / flat-json
    # -----------------------------------------------------------------------
    def test_icu_simple_variable(self):
        result = extract_placeholders("Hello {name}", "icu")
        assert result == ["{name}"]

    def test_icu_plural_block_skipped(self):
        # Keyword blocks should not yield bare placeholder tokens
        text = "{count, plural, one {# item} other {# items}}"
        result = extract_placeholders(text, "icu")
        assert result == []

    def test_flat_json_simple_variable(self):
        result = extract_placeholders("Welcome {user}", "flat-json")
        assert result == ["{user}"]

    def test_unknown_format_returns_empty(self):
        result = extract_placeholders("%@ {{name}} {foo}", "gettext-po")
        assert result == []


class TestDetectStructuralTags:
    def test_i18next_trans_tag(self):
        assert detect_structural_tags("Click <1>here</1> to continue", "i18next") is True

    def test_i18next_no_trans_tag(self):
        assert detect_structural_tags("Click here to continue", "i18next") is False

    def test_icu_trans_tag(self):
        assert detect_structural_tags("Visit <2>our site</2>", "icu") is True

    def test_android_bold_tag(self):
        assert detect_structural_tags("Agree to <b>Terms</b>", "android-xml") is True

    def test_android_anchor_tag(self):
        assert detect_structural_tags('See <a href="x">Privacy</a>', "android-xml") is True

    def test_android_plain_text(self):
        assert detect_structural_tags("Plain text", "android-xml") is False

    def test_ios_ignores_tags(self):
        # iOS doesn't support inline HTML in .strings; should return False
        assert detect_structural_tags("<b>Bold</b>", "ios-strings") is False


class TestDetectIcuShape:
    def test_plain(self):
        assert detect_icu_shape("Hello world", "i18next") == "plain"

    def test_plural(self):
        assert detect_icu_shape("{count, plural, one {# item} other {# items}}", "icu") == "plural"

    def test_select(self):
        assert detect_icu_shape("{gender, select, male {his} female {her} other {their}}", "icu") == "select"

    def test_stringsdict_always_plural(self):
        assert detect_icu_shape("anything", "ios-stringsdict") == "plural"

    def test_ios_strings_plain(self):
        assert detect_icu_shape("Confirm payment", "ios-strings") == "plain"


class TestInferStringType:
    def test_button_key(self):
        assert infer_string_type("checkout_confirm_btn", "Confirm") == "button"

    def test_button_full_word(self):
        assert infer_string_type("submit_button", "Submit") == "button"

    def test_title_key(self):
        assert infer_string_type("screen_title", "My Screen") == "title"

    def test_label_key(self):
        assert infer_string_type("email_label", "Email") == "label"

    def test_placeholder_key(self):
        assert infer_string_type("search_placeholder", "Search…") == "placeholder"

    def test_error_key(self):
        assert infer_string_type("network_error", "Network failed") == "error"

    def test_error_prefix(self):
        assert infer_string_type("err_invalid_email", "Invalid email") == "error"

    def test_success_key(self):
        assert infer_string_type("payment_success", "Payment confirmed") == "success"

    def test_notification_key(self):
        assert infer_string_type("push_notification_body", "You have a message") == "notification"

    def test_permission_key(self):
        assert infer_string_type("camera_permission", "Allow camera") == "permission"

    def test_trans_component(self):
        assert infer_string_type("generic_key", "text", has_structural_tags=True) == "trans_component"

    def test_other_fallback(self):
        assert infer_string_type("random_key", "Random text") == "other"

    def test_help_key(self):
        assert infer_string_type("field_help_text", "Enter your name") == "help_text"


class TestInferRiskClass:
    def test_legal_key_human_only(self):
        assert infer_risk_class("terms_of_service", "...", "other") == "human_only"

    def test_privacy_key_human_only(self):
        assert infer_risk_class("privacy_policy_link", "Privacy Policy", "other") == "human_only"

    def test_tos_key_human_only(self):
        assert infer_risk_class("accept_tos", "Accept Terms", "other") == "human_only"

    def test_eula_key_human_only(self):
        assert infer_risk_class("eula_text", "End User License...", "other") == "human_only"

    def test_error_type_high_risk(self):
        assert infer_risk_class("network_issue", "Network failed", "error") == "high_risk"

    def test_permission_type_high_risk(self):
        assert infer_risk_class("location_access", "Allow location", "permission") == "high_risk"

    def test_delete_key_high_risk(self):
        assert infer_risk_class("confirm_delete_account", "Delete account?", "button") == "high_risk"

    def test_payment_key_high_risk(self):
        assert infer_risk_class("payment_summary", "Total: $10", "label") == "high_risk"

    def test_short_button_auto_publish(self):
        # "ok_btn" has no high-risk tokens and is a short button → auto_publish
        assert infer_risk_class("ok_btn", "OK", "button", placeholders=[]) == "auto_publish"

    def test_long_button_not_auto_publish(self):
        # >20 chars → standard (key has no risk tokens so falls through to standard)
        result = infer_risk_class("submit_btn", "Please submit your action here today", "button", placeholders=[])
        assert result == "standard"

    def test_button_with_placeholder_not_auto_publish(self):
        result = infer_risk_class("greet_btn", "Hi", "button", placeholders=["%@"])
        assert result != "auto_publish"

    def test_standard_fallback(self):
        assert infer_risk_class("screen_title", "My Screen", "title") == "standard"

    def test_legal_beats_error(self):
        # legal key + error type → human_only wins
        assert infer_risk_class("legal_error_notice", "...", "error") == "human_only"


class TestInferComponentFromKey:
    def test_common_prefix(self):
        component, screen = infer_component_from_key("common.cancel")
        assert component == "shared"
        assert screen is None

    def test_shared_prefix(self):
        component, screen = infer_component_from_key("shared.ok_button")
        assert component == "shared"

    def test_global_prefix(self):
        component, screen = infer_component_from_key("global.app_name")
        assert component == "shared"

    def test_dot_separated(self):
        component, screen = infer_component_from_key("checkout.confirm_button")
        assert component == "checkout"
        assert screen is None

    def test_underscore_separated(self):
        component, screen = infer_component_from_key("checkout_confirm_button")
        assert component == "checkout"

    def test_short_prefix_ignored(self):
        component, screen = infer_component_from_key("btn_ok")
        assert component is None

    def test_skip_prefix_lbl(self):
        component, screen = infer_component_from_key("lbl_name")
        assert component is None

    def test_no_separator(self):
        component, screen = infer_component_from_key("mykey")
        assert component is None


# ===========================================================================
# iOS parser
# ===========================================================================


class TestStringsParser:
    BASIC = """
/* Confirm button on checkout screen */
"checkout_confirm_button" = "Confirm payment";

/* No comment provided by engineer. */
"checkout_cancel" = "Cancel";
"""

    def test_basic_key_value(self):
        keys = parse_strings_file(self.BASIC, "Localizable.strings")
        key_map = {k.key: k for k in keys}
        assert "checkout_confirm_button" in key_map
        assert key_map["checkout_confirm_button"].source_text == "Confirm payment"

    def test_comment_becomes_description(self):
        keys = parse_strings_file(self.BASIC, "Localizable.strings")
        key_map = {k.key: k for k in keys}
        assert key_map["checkout_confirm_button"].description == "Confirm button on checkout screen"

    def test_generic_comment_stripped(self):
        keys = parse_strings_file(self.BASIC, "Localizable.strings")
        key_map = {k.key: k for k in keys}
        # "No comment provided by engineer." should be discarded
        assert key_map["checkout_cancel"].description is None

    def test_localizable_has_no_component(self):
        keys = parse_strings_file(self.BASIC, "Localizable.strings")
        # Component may be inferred from key prefix, but file_component should
        # be None for Localizable.strings
        # checkout_confirm_button → component = "checkout" via key prefix
        key_map = {k.key: k for k in keys}
        assert key_map["checkout_confirm_button"].component == "checkout"

    def test_named_file_sets_component(self):
        content = '"pay_title" = "Payment";'
        keys = parse_strings_file(content, "Checkout.strings")
        assert keys[0].component == "Checkout"

    def test_infoplist_keys_risk_class(self):
        content = '"NSCameraUsageDescription" = "We need camera access";'
        keys = parse_strings_file(content, "InfoPlist.strings")
        assert keys[0].risk_class == "high_risk"
        assert keys[0].string_type == "permission"

    def test_placeholder_extracted(self):
        content = '"greeting" = "Hello %@";'
        keys = parse_strings_file(content, "Localizable.strings")
        assert "%@" in keys[0].placeholders

    def test_positional_placeholder(self):
        content = '"order_status" = "%1$@ has %2$d items";'
        keys = parse_strings_file(content, "Localizable.strings")
        assert "%1$@" in keys[0].placeholders
        assert "%2$d" in keys[0].placeholders

    def test_escape_sequences_unescaped(self):
        content = r'"msg" = "Line1\nLine2";'
        keys = parse_strings_file(content, "Localizable.strings")
        assert "\n" in keys[0].source_text

    def test_two_keys_parsed(self):
        content = '"a" = "Alpha";\n"b" = "Beta";'
        keys = parse_strings_file(content, "Localizable.strings")
        assert len(keys) == 2


class TestXcstringsParser:
    BASIC_XCSTRINGS = """{
  "sourceLanguage": "en",
  "strings": {
    "checkout_confirm_button": {
      "comment": "Final confirm on payment screen",
      "localizations": {
        "en": { "stringUnit": { "state": "new", "value": "Confirm payment" } }
      }
    },
    "no_comment_key": {
      "localizations": {
        "en": { "stringUnit": { "state": "new", "value": "Plain text" } }
      }
    }
  }
}"""

    PLURAL_XCSTRINGS = """{
  "sourceLanguage": "en",
  "strings": {
    "items_count": {
      "localizations": {
        "en": {
          "variations": {
            "plural": {
              "one": { "stringUnit": { "state": "new", "value": "%d item" } },
              "other": { "stringUnit": { "state": "new", "value": "%d items" } }
            }
          }
        }
      }
    }
  }
}"""

    def test_basic_key_parsed(self):
        keys = parse_xcstrings_file(self.BASIC_XCSTRINGS, "Localizable.xcstrings")
        key_map = {k.key: k for k in keys}
        assert "checkout_confirm_button" in key_map
        assert key_map["checkout_confirm_button"].source_text == "Confirm payment"

    def test_comment_becomes_description(self):
        keys = parse_xcstrings_file(self.BASIC_XCSTRINGS, "Localizable.xcstrings")
        key_map = {k.key: k for k in keys}
        assert key_map["checkout_confirm_button"].description == "Final confirm on payment screen"

    def test_no_comment_description_is_none(self):
        keys = parse_xcstrings_file(self.BASIC_XCSTRINGS, "Localizable.xcstrings")
        key_map = {k.key: k for k in keys}
        assert key_map["no_comment_key"].description is None

    def test_plural_detected(self):
        keys = parse_xcstrings_file(self.PLURAL_XCSTRINGS, "Localizable.xcstrings")
        assert len(keys) == 1
        pk = keys[0]
        assert pk.icu_shape == "plural"
        assert pk.plural_format == "stringsdict"

    def test_plural_source_text_is_other(self):
        keys = parse_xcstrings_file(self.PLURAL_XCSTRINGS, "Localizable.xcstrings")
        assert keys[0].source_text == "%d items"

    def test_named_file_component(self):
        keys = parse_xcstrings_file(self.BASIC_XCSTRINGS, "Checkout.xcstrings")
        for k in keys:
            assert k.component == "Checkout"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid xcstrings"):
            parse_xcstrings_file("not json", "Localizable.xcstrings")


class TestStringsdictParser:
    SIMPLE_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>checkout_items_count</key>
    <dict>
        <key>NSStringLocalizedFormatKey</key>
        <string>%#@count@</string>
        <key>count</key>
        <dict>
            <key>NSStringFormatSpecTypeKey</key>
            <string>NSStringPluralRuleType</string>
            <key>NSStringFormatValueTypeKey</key>
            <string>d</string>
            <key>one</key>
            <string>%d item</string>
            <key>other</key>
            <string>%d items</string>
        </dict>
    </dict>
</dict>
</plist>"""

    SIMPLE_PLIST_NO_FORMAT_KEY = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>simple_plural</key>
    <dict>
        <key>one</key>
        <string>%d apple</string>
        <key>other</key>
        <string>%d apples</string>
    </dict>
</dict>
</plist>"""

    def test_plural_key_parsed(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Localizable.stringsdict")
        assert len(keys) == 1
        assert keys[0].key == "checkout_items_count"

    def test_source_text_is_other_variant(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Localizable.stringsdict")
        assert keys[0].source_text == "%d items"

    def test_icu_shape_is_plural(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Localizable.stringsdict")
        assert keys[0].icu_shape == "plural"

    def test_plural_format_is_stringsdict(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Localizable.stringsdict")
        assert keys[0].plural_format == "stringsdict"

    def test_placeholder_extracted(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Localizable.stringsdict")
        assert "%d" in keys[0].placeholders

    def test_simple_structure_without_format_key(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST_NO_FORMAT_KEY, "Localizable.stringsdict")
        assert len(keys) == 1
        assert keys[0].source_text == "%d apples"

    def test_named_file_component(self):
        keys = parse_stringsdict_file(self.SIMPLE_PLIST, "Checkout.stringsdict")
        assert keys[0].component == "Checkout"


class TestIosDispatcher:
    def test_dispatches_strings(self):
        content = '"k" = "v";'
        result = parse_ios_file(content, "Localizable.strings")
        assert isinstance(result, list)
        assert result[0].key == "k"

    def test_dispatches_xcstrings(self):
        content = (
            '{"sourceLanguage":"en","strings":{"k":'
            '{"localizations":{"en":{"stringUnit":{"state":"new","value":"v"}}}}}}'
        )
        result = parse_ios_file(content, "Localizable.xcstrings")
        assert result[0].key == "k"

    def test_dispatches_stringsdict(self):
        content = """<?xml version="1.0"?>
<plist><dict>
  <key>pl</key>
  <dict>
    <key>one</key><string>%d item</string>
    <key>other</key><string>%d items</string>
  </dict>
</dict></plist>"""
        result = parse_ios_file(content, "Localizable.stringsdict")
        assert result[0].icu_shape == "plural"


# ===========================================================================
# Android parser
# ===========================================================================


class TestAndroidParser:
    STRINGS_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="checkout_confirm_button">Confirm payment</string>
    <string name="brand_name" translatable="false">ClaritiTMS</string>
    <string name="rich_text">Agree to <b>Terms</b> and <a href="%1$s">Privacy</a></string>
    <plurals name="items_count">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>"""

    def test_basic_key_parsed(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_map = {k.key: k for k in keys}
        assert "checkout_confirm_button" in key_map
        assert key_map["checkout_confirm_button"].source_text == "Confirm payment"

    def test_translatable_false_excluded(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_names = [k.key for k in keys]
        assert "brand_name" not in key_names

    def test_html_tags_detected(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_map = {k.key: k for k in keys}
        assert key_map["rich_text"].has_structural_tags is True

    def test_plurals_icu_shape(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_map = {k.key: k for k in keys}
        assert key_map["items_count"].icu_shape == "plural"

    def test_plurals_format(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_map = {k.key: k for k in keys}
        assert key_map["items_count"].plural_format == "android-xml"

    def test_plurals_source_text_is_other(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        key_map = {k.key: k for k in keys}
        assert key_map["items_count"].source_text == "%d items"

    def test_android_placeholder_extracted(self):
        content = """<resources>
            <string name="link_text">Visit <a href="%1$s">here</a></string>
        </resources>"""
        keys = parse_strings_xml(content, "strings.xml")
        assert "%1$s" in keys[0].placeholders

    def test_plain_string_no_structural_tags(self):
        content = """<resources>
            <string name="simple_key">Plain text</string>
        </resources>"""
        keys = parse_strings_xml(content, "strings.xml")
        assert keys[0].has_structural_tags is False

    def test_format_specifier_in_plural(self):
        content = """<resources>
            <plurals name="file_count">
                <item quantity="one">%1$s file</item>
                <item quantity="other">%1$s files</item>
            </plurals>
        </resources>"""
        keys = parse_strings_xml(content, "strings.xml")
        assert "%1$s" in keys[0].placeholders

    def test_multiple_keys_count(self):
        keys = parse_strings_xml(self.STRINGS_XML, "res/values/strings.xml")
        # brand_name excluded; remaining: confirm_button, rich_text, items_count
        assert len(keys) == 3

    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError, match="Invalid strings.xml"):
            parse_strings_xml("not xml <<>>", "strings.xml")

    def test_translatable_false_plurals_excluded(self):
        content = """<resources>
            <plurals name="count" translatable="false">
                <item quantity="other">%d items</item>
            </plurals>
        </resources>"""
        keys = parse_strings_xml(content, "strings.xml")
        assert len(keys) == 0

    def test_dispatcher_calls_parse_strings_xml(self):
        keys = parse_android_file(self.STRINGS_XML, "strings.xml")
        assert len(keys) == 3


# ===========================================================================
# React / TypeScript parser
# ===========================================================================


class TestFlattenJson:
    def test_flat_dict(self):
        result = flatten_json({"a": "A", "b": "B"})
        assert result == {"a": "A", "b": "B"}

    def test_nested_one_level(self):
        result = flatten_json({"button": {"confirm": "Confirm"}})
        assert result == {"button.confirm": "Confirm"}

    def test_nested_two_levels(self):
        result = flatten_json({"a": {"b": {"c": "deep"}}})
        assert result == {"a.b.c": "deep"}

    def test_mixed_flat_and_nested(self):
        result = flatten_json({"title": "My App", "nav": {"home": "Home"}})
        assert "title" in result
        assert "nav.home" in result

    def test_non_string_leaves_skipped(self):
        result = flatten_json({"key": "val", "num": 42, "flag": True})
        assert "key" in result
        assert "num" not in result
        assert "flag" not in result

    def test_empty_dict(self):
        assert flatten_json({}) == {}


class TestReactParser:
    CHECKOUT_JSON = """{
  "title": "Checkout",
  "button": {
    "confirm": "Confirm payment",
    "cancel": "Cancel"
  },
  "greeting": "Hello {{name}}, your total is {{amount}}"
}"""

    PLURAL_JSON = """{
  "confirm_one": "Confirm {{count}} item",
  "confirm_other": "Confirm {{count}} items"
}"""

    TRANS_JSON = """{
  "tos_agreement": "Please read <1>our Terms</1> before continuing"
}"""

    ICU_JSON = """{
  "items_count": "{count, plural, one {# item} other {# items}}"
}"""

    def test_nested_keys_flattened(self):
        keys = parse_namespace_json(self.CHECKOUT_JSON, "checkout.json")
        key_names = [k.key for k in keys]
        assert "button.confirm" in key_names
        assert "button.cancel" in key_names
        assert "title" in key_names

    def test_component_from_filename(self):
        keys = parse_namespace_json(self.CHECKOUT_JSON, "checkout.json")
        for k in keys:
            assert k.component == "checkout"

    def test_i18next_placeholder_extracted(self):
        keys = parse_namespace_json(self.CHECKOUT_JSON, "checkout.json")
        key_map = {k.key: k for k in keys}
        assert "{{name}}" in key_map["greeting"].placeholders
        assert "{{amount}}" in key_map["greeting"].placeholders

    def test_plural_suffix_keys_grouped(self):
        keys = parse_namespace_json(self.PLURAL_JSON, "checkout.json")
        key_names = [k.key for k in keys]
        # Should emit "confirm" not "confirm_one" / "confirm_other"
        assert "confirm" in key_names
        assert "confirm_one" not in key_names
        assert "confirm_other" not in key_names

    def test_plural_suffix_plural_format(self):
        keys = parse_namespace_json(self.PLURAL_JSON, "checkout.json")
        assert len(keys) == 1
        pk = keys[0]
        assert pk.plural_format == "i18next-suffix"
        assert pk.icu_shape == "plural"

    def test_plural_source_text_is_other(self):
        keys = parse_namespace_json(self.PLURAL_JSON, "checkout.json")
        # _other variant = "Confirm {{count}} items"
        assert keys[0].source_text == "Confirm {{count}} items"

    def test_trans_component_tags_detected(self):
        keys = parse_namespace_json(self.TRANS_JSON, "checkout.json")
        assert keys[0].has_structural_tags is True

    def test_trans_component_string_type(self):
        keys = parse_namespace_json(self.TRANS_JSON, "checkout.json")
        # tos_agreement contains "tos" → human_only risk; string type may vary
        assert keys[0].risk_class == "human_only"

    def test_icu_plural_detected(self):
        keys = parse_namespace_json(self.ICU_JSON, "common.json")
        assert keys[0].icu_shape == "plural"

    def test_common_filename_maps_to_shared(self):
        keys = parse_namespace_json('{"ok": "OK"}', "common.json")
        assert keys[0].component == "shared"

    def test_shared_filename_maps_to_shared(self):
        keys = parse_namespace_json('{"ok": "OK"}', "shared.json")
        assert keys[0].component == "shared"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_namespace_json("not json", "checkout.json")

    def test_non_object_json_raises(self):
        with pytest.raises(ValueError, match="Top-level JSON"):
            parse_namespace_json('["a", "b"]', "checkout.json")

    def test_dispatcher_works(self):
        result = parse_react_file('{"key": "value"}', "checkout.json")
        assert isinstance(result, list)
        assert result[0].key == "key"


# ===========================================================================
# Flutter ARB parser
# ===========================================================================


class TestFlutterArbParser:
    BASIC_ARB = """{
  "@@locale": "en",
  "@@last_modified": "2024-01-15T10:30:00Z",
  "greeting": "Hello, {name}!",
  "@greeting": {
    "description": "Welcome greeting on the home screen",
    "placeholders": {"name": {"type": "String", "example": "Jane"}}
  },
  "itemCount": "{count, plural, =0{No items} =1{1 item} other{{count} items}}",
  "@itemCount": {
    "description": "Number of items in cart",
    "placeholders": {"count": {"type": "int"}}
  },
  "simpleLabel": "Settings"
}"""

    def test_plain_key_no_metadata(self):
        keys = parse_flutter_arb('{"simpleLabel": "Settings"}', "app_en.arb")
        assert len(keys) == 1
        assert keys[0].key == "simpleLabel"
        assert keys[0].source_text == "Settings"
        assert keys[0].description is None
        assert keys[0].source_metadata is None

    def test_metadata_populates_description(self):
        keys = parse_flutter_arb(self.BASIC_ARB, "app_en.arb")
        by_key = {k.key: k for k in keys}
        assert by_key["greeting"].description == "Welcome greeting on the home screen"
        assert by_key["itemCount"].description == "Number of items in cart"
        assert by_key["simpleLabel"].description is None

    def test_source_metadata_preserved_full_at_key_block(self):
        """The whole `@key` block is carried verbatim on ParsedKey.source_metadata
        so the publication writer can round-trip it back into the locale file.
        """
        keys = parse_flutter_arb(self.BASIC_ARB, "app_en.arb")
        by_key = {k.key: k for k in keys}
        assert by_key["greeting"].source_metadata == {
            "description": "Welcome greeting on the home screen",
            "placeholders": {"name": {"type": "String", "example": "Jane"}},
        }
        assert by_key["itemCount"].source_metadata == {
            "description": "Number of items in cart",
            "placeholders": {"count": {"type": "int"}},
        }
        assert by_key["simpleLabel"].source_metadata is None

    def test_locale_directive_skipped(self):
        keys = parse_flutter_arb(self.BASIC_ARB, "app_en.arb")
        key_names = [k.key for k in keys]
        assert "@@locale" not in key_names
        assert "@@last_modified" not in key_names

    def test_directives_skipped_in_general(self):
        content = '{"@@locale": "en", "@@x_custom": "anything", "label": "Hi"}'
        keys = parse_flutter_arb(content, "app_en.arb")
        assert len(keys) == 1
        assert keys[0].key == "label"

    def test_at_metadata_blocks_skipped(self):
        keys = parse_flutter_arb(self.BASIC_ARB, "app_en.arb")
        key_names = [k.key for k in keys]
        # @greeting and @itemCount should not be emitted as their own keys
        assert "@greeting" not in key_names
        assert "@itemCount" not in key_names

    def test_single_curly_placeholders_extracted(self):
        keys = parse_flutter_arb('{"hello": "Hi {name}, age {age}"}', "app_en.arb")
        assert keys[0].placeholders == ["{name}", "{age}"]

    def test_multiple_placeholders_dedup(self):
        keys = parse_flutter_arb('{"x": "{a} and {b} and {a}"}', "app_en.arb")
        assert keys[0].placeholders == ["{a}", "{b}"]

    def test_icu_plural_inline_detected(self):
        keys = parse_flutter_arb(self.BASIC_ARB, "app_en.arb")
        by_key = {k.key: k for k in keys}
        assert by_key["itemCount"].icu_shape == "plural"
        assert by_key["itemCount"].plural_format == "icu"

    def test_plain_string_icu_shape(self):
        keys = parse_flutter_arb('{"label": "Hello"}', "app_en.arb")
        assert keys[0].icu_shape == "plain"
        assert keys[0].plural_format is None

    def test_component_from_filename(self):
        keys = parse_flutter_arb('{"label": "Hi"}', "checkout_en.arb")
        # checkout_en → strip locale suffix → checkout
        assert keys[0].component == "checkout"

    def test_component_app_filename_maps_to_shared(self):
        keys = parse_flutter_arb('{"label": "Hi"}', "app_en.arb")
        assert keys[0].component == "shared"

    def test_component_from_dotted_key_overrides_filename(self):
        keys = parse_flutter_arb('{"checkout.confirm": "Confirm"}', "app_en.arb")
        assert keys[0].component == "checkout"

    def test_malformed_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_flutter_arb("not json", "app_en.arb")

    def test_non_object_root_raises(self):
        with pytest.raises(ValueError, match="Top-level JSON"):
            parse_flutter_arb('["a", "b"]', "app_en.arb")

    def test_empty_arb(self):
        keys = parse_flutter_arb("{}", "app_en.arb")
        assert keys == []

    def test_only_directives_no_keys(self):
        keys = parse_flutter_arb('{"@@locale": "en", "@@author": "ops"}', "app_en.arb")
        assert keys == []

    def test_orphan_metadata_block_silently_ignored(self):
        # @greeting has no matching plain `greeting` key
        keys = parse_flutter_arb(
            '{"@greeting": {"description": "no match"}, "label": "Hi"}',
            "app_en.arb",
        )
        assert len(keys) == 1
        assert keys[0].key == "label"
        assert keys[0].description is None


# ===========================================================================
# Top-level parse_file dispatcher
# ===========================================================================


class TestParseFileDispatcher:
    def test_ios_strings_dispatched(self):
        result = parse_file('"k" = "v";', "Localizable.strings", "ios-strings")
        assert isinstance(result, ParseResult)
        assert result.platform == "ios"
        assert result.file_format == "ios-strings"
        assert result.keys[0].key == "k"

    def test_android_xml_dispatched(self):
        content = '<resources><string name="app_name">MyApp</string></resources>'
        result = parse_file(content, "strings.xml", "android-xml")
        assert result.platform == "android"
        assert result.keys[0].key == "app_name"

    def test_i18next_dispatched(self):
        result = parse_file('{"title": "Hello"}', "checkout.json", "i18next")
        assert result.platform == "web"
        assert result.file_format == "i18next"

    def test_icu_dispatched(self):
        result = parse_file('{"greeting": "Hello {name}"}', "common.json", "icu")
        assert result.platform == "web"

    def test_flutter_arb_dispatched(self):
        result = parse_file('{"label": "Hi"}', "app_en.arb", "flutter-arb")
        assert result.platform == "flutter"
        assert result.file_format == "flutter-arb"
        assert result.keys[0].key == "label"

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown file_format"):
            parse_file("content", "file.po", "gettext-po")

    def test_source_file_preserved(self):
        result = parse_file('"k" = "v";', "path/to/Localizable.strings", "ios-strings")
        assert result.source_file == "path/to/Localizable.strings"
