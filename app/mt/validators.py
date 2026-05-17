from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.parsers.common import extract_placeholders


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_string(
    source: str,
    translated: str,
    key_icu_shape: str,
    key_has_structural_tags: bool,
    file_format: str,
    max_length: int | None,
    tag_map: dict[str, str],
    glossary_terms: list[dict],
) -> ValidationResult:
    """Validate a single translated string against the source.

    Returns a ValidationResult with valid=True when all checks pass, or
    valid=False with a list of error messages describing each failure.
    """
    errors: list[str] = []

    # 1. Placeholder match
    src_placeholders = sorted(extract_placeholders(source, file_format))
    tgt_placeholders = sorted(extract_placeholders(translated, file_format))
    if src_placeholders != tgt_placeholders:
        errors.append(
            f"Placeholder mismatch: source has {src_placeholders}, "
            f"translated has {tgt_placeholders}"
        )

    # 2. ICU shape check
    if key_icu_shape == "plural":
        if "{" not in translated or "plural," not in translated:
            errors.append(
                "ICU plural shape required: translated string must contain "
                '"{" and "plural,"'
            )

    # 3. Structural tag placeholders
    if key_has_structural_tags:
        for placeholder in tag_map:
            if placeholder not in translated:
                errors.append(
                    f"Structural tag placeholder missing in translation: {placeholder!r}"
                )

    # 4. Max length
    if max_length is not None and len(translated) > max_length:
        errors.append(
            f"Translation exceeds max length: {len(translated)} > {max_length}"
        )

    # 5. Do-not-translate terms must appear verbatim in the translation
    for term in glossary_terms:
        if term.get("do_not_translate") and term["source_term"] not in translated:
            errors.append(
                f"Brand term must appear verbatim: {term['source_term']!r} missing from translation"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors)
