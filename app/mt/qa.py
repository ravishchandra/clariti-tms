from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def back_translation_qa(
    source: str,
    translated: str,
    locale: str,
    evaluate_fn: Callable[[str], Awaitable[str]],
    embed_fn: Callable[[str], Awaitable[list[float]]],
) -> tuple[str, float]:
    back = await evaluate_fn(
        f"Translate this {locale} text back to English.\n"
        f"Output only the English translation. No explanation.\n\n"
        f"Text: {translated}"
    )
    source_emb, back_emb = await embed_fn(source), await embed_fn(back)
    return back, cosine_similarity(source_emb, back_emb)


async def locale_consistency_eval(
    source: str,
    translated: str,
    locale: str,
    domain_description: str,
    locale_notes: str | None,
    tm_neighbors: list[dict],
    evaluate_fn: Callable[[str], Awaitable[str]],
) -> dict:
    examples = "\n".join(
        f'  {n["source_text"]} → {n["target_text"]}' for n in tm_neighbors[:5]
    ) or "  (none yet)"
    raw = await evaluate_fn(
        f"You are a {locale} language quality evaluator for {domain_description}.\n\n"
        f'Source (en-US): "{source}"\n'
        f'Translation ({locale}): "{translated}"\n\n'
        f"Style guide: {locale_notes or 'none'}\n"
        f"Approved examples from this project:\n{examples}\n\n"
        f"Score each dimension 1-5:\n"
        f"1. Naturalness: sounds like a native {locale} speaker wrote it\n"
        f"2. Consistency: matches the register and terminology of the examples\n"
        f"3. Accuracy: preserves the full meaning of the source\n\n"
        f"If any score < 4, explain in one sentence what is wrong.\n"
        "Output JSON only: "
        '{"naturalness": N, "consistency": N, "accuracy": N, "issue": "..." or null}'
    )
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, KeyError):
        return {"naturalness": 3, "consistency": 3, "accuracy": 3, "issue": "parse error"}
