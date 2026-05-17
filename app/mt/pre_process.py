from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PreProcessResult:
    processed_strings: dict[str, str]
    tag_map: dict[str, dict[str, str]]  # key_id → {placeholder → original_tag}


def substitute_structural_tags(
    key: str, text: str, file_format: str
) -> tuple[str, dict[str, str]]:
    sub_map: dict[str, str] = {}

    if file_format == "i18next":
        # React Trans tags: <1>text</1> → {{link_1}}, <2>text</2> → {{link_2}}, etc.
        # Also handle self-closing: <br /> stays as-is (not a structural tag)
        def replace_trans_tag(m: re.Match) -> str:  # type: ignore[type-arg]
            idx = m.group(1)
            ph = f"{{{{link_{idx}}}}}"
            sub_map[ph] = m.group(0)
            return ph

        text = re.sub(r"<(\d+)>(.*?)</\1>", replace_trans_tag, text)

    elif file_format == "android-xml":
        # HTML tags → readable markers
        def replace_bold(m: re.Match) -> str:  # type: ignore[type-arg]
            content = m.group(1)
            ph = f"[BOLD:{content}]"
            sub_map[ph] = m.group(0)
            return ph

        def replace_italic(m: re.Match) -> str:  # type: ignore[type-arg]
            content = m.group(1)
            ph = f"[ITALIC:{content}]"
            sub_map[ph] = m.group(0)
            return ph

        text = re.sub(r"<b>(.*?)</b>", replace_bold, text, flags=re.IGNORECASE)
        text = re.sub(r"<i>(.*?)</i>", replace_italic, text, flags=re.IGNORECASE)

    return text, sub_map


def pre_process_batch(
    strings: dict[str, str],
    has_structural_tags_by_key: dict[str, bool],
    file_format: str,
) -> PreProcessResult:
    processed: dict[str, str] = {}
    tag_map: dict[str, dict[str, str]] = {}
    for key, text in strings.items():
        if has_structural_tags_by_key.get(key, False):
            clean, smap = substitute_structural_tags(key, text, file_format)
            processed[key] = clean
            tag_map[key] = smap
        else:
            processed[key] = text
            tag_map[key] = {}
    return PreProcessResult(processed_strings=processed, tag_map=tag_map)
