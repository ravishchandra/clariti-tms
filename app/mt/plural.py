from __future__ import annotations

# CLDR plural categories per locale (subset of most commonly used locales).
# Source: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
#
# Each entry maps a locale tag (or language prefix) to its ordered CLDR categories.
# The lookup uses exact match first, then language-prefix match (e.g. "fr" for "fr-CA").

CLDR_CATEGORIES: dict[str, list[str]] = {
    # --- 1-form (no distinction) ---
    "ja": ["other"],
    "zh": ["other"],
    "ko": ["other"],
    "vi": ["other"],
    "th": ["other"],
    "id": ["other"],
    "ms": ["other"],
    "tr": ["other"],
    # --- 2-form (one / other) ---
    "en": ["one", "other"],
    "de": ["one", "other"],
    "nl": ["one", "other"],
    "sv": ["one", "other"],
    "nb": ["one", "other"],
    "da": ["one", "other"],
    "fi": ["one", "other"],
    "et": ["one", "other"],
    "hu": ["one", "other"],
    "el": ["one", "other"],
    "he": ["one", "many", "other"],
    "it": ["one", "many", "other"],
    "pt": ["one", "many", "other"],
    "es": ["one", "many", "other"],
    "fr": ["one", "many", "other"],
    "ca": ["one", "many", "other"],
    # --- 3-form ---
    "ru": ["one", "few", "many", "other"],
    "uk": ["one", "few", "many", "other"],
    "pl": ["one", "few", "many", "other"],
    "cs": ["one", "few", "many", "other"],
    "sk": ["one", "few", "many", "other"],
    "hr": ["one", "few", "other"],
    "sr": ["one", "few", "other"],
    "bs": ["one", "few", "other"],
    "ro": ["one", "few", "other"],
    # --- Arabic (6-form) ---
    "ar": ["zero", "one", "two", "few", "many", "other"],
}

# Locale-tag overrides (full BCP 47 tags that differ from their language prefix)
_LOCALE_OVERRIDES: dict[str, list[str]] = {
    "pt-BR": ["one", "other"],
    "pt-PT": ["one", "many", "other"],
    "zh-TW": ["other"],
    "zh-HK": ["other"],
    "zh-CN": ["other"],
}


def get_cldr_categories(locale: str) -> list[str]:
    """Return the ordered CLDR plural categories for *locale*.

    Lookup order:
    1. Exact match in ``_LOCALE_OVERRIDES``
    2. Exact match in ``CLDR_CATEGORIES``
    3. Language-prefix match (``fr`` from ``fr-CA``)
    4. Fallback: ``["one", "other"]``
    """
    if locale in _LOCALE_OVERRIDES:
        return _LOCALE_OVERRIDES[locale]
    if locale in CLDR_CATEGORIES:
        return CLDR_CATEGORIES[locale]
    lang = locale.split("-")[0].lower()
    if lang in CLDR_CATEGORIES:
        return CLDR_CATEGORIES[lang]
    return ["one", "other"]


def plural_prompt_instruction(locale: str, plural_format: str | None) -> str | None:
    """Return a prompt instruction string for plural handling, or None.

    Returns None when the string does not use plurals (``plural_format`` is
    falsy / None), so callers can omit the instruction entirely.

    Args:
        locale: BCP 47 locale tag for the target language.
        plural_format: The plural convention used in this repository, e.g.
            ``"icu"``, ``"i18next-suffix"``, ``"android-xml"``, ``"stringsdict"``.
            Pass ``None`` or ``""`` for non-plural strings.
    """
    if not plural_format:
        return None

    categories = get_cldr_categories(locale)
    cat_list = ", ".join(categories)

    if plural_format == "icu":
        return (
            f"This string uses ICU plural syntax. "
            f"The target locale ({locale}) requires these CLDR categories: {cat_list}. "
            f"Output a valid ICU plural message covering all required categories, e.g.: "
            f"{{count, plural, {' '.join(f'{c} {{…}}' for c in categories)}}}"
        )

    if plural_format == "i18next-suffix":
        suffix_keys = " / ".join(f"key_{c}" for c in categories)
        return (
            f"This string uses i18next plural suffixes. "
            f"The target locale ({locale}) requires these CLDR categories: {cat_list}. "
            f"Return a JSON object with one key per category using underscore suffixes: "
            f"{suffix_keys}."
        )

    if plural_format == "android-xml":
        qty_items = " ".join(f'<item quantity="{c}">…</item>' for c in categories)
        return (
            f"This string uses Android XML plurals. "
            f"The target locale ({locale}) requires these CLDR categories: {cat_list}. "
            f"Return a <plurals> block with one <item> per required quantity: "
            f"{qty_items}"
        )

    if plural_format == "stringsdict":
        return (
            f"This string uses iOS .stringsdict plural rules. "
            f"The target locale ({locale}) requires these CLDR categories: {cat_list}. "
            f"Provide translations for each category: {cat_list}."
        )

    # Unknown format — generic instruction
    return (
        f"This string requires plural forms. "
        f"The target locale ({locale}) uses these CLDR categories: {cat_list}. "
        f"Provide a translation for each category."
    )
