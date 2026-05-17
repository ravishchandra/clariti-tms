from __future__ import annotations

import json
import re


def restore_structural_tags(translated: str, tag_map: dict[str, str]) -> str:
    for placeholder, original in tag_map.items():
        translated = translated.replace(placeholder, original)
    return translated


def parse_llm_json_output(raw: str, expected_keys: list[str]) -> dict[str, str]:
    # Strip markdown fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM output is not valid JSON: {e}\nRaw: {raw[:200]}"
        ) from e
    missing = [k for k in expected_keys if k not in data]
    if missing:
        raise ValueError(f"LLM output missing keys: {missing}")
    return {k: str(v) for k, v in data.items() if k in expected_keys}
