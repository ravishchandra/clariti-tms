"""Eval harness — compare a prompt version against a reference set.

Usage:
    loc eval --prompt translate_v2 --reference evals/fr-FR-reference.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.mt.qa import cosine_similarity


def _bleu_unigram(reference: str, hypothesis: str) -> float:
    """Unigram BLEU precision (no brevity penalty) as a quick proxy metric."""
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    if not hyp_tokens:
        return 0.0
    ref_counts: dict[str, int] = {}
    for t in ref_tokens:
        ref_counts[t] = ref_counts.get(t, 0) + 1
    clip_count = 0
    hyp_counts: dict[str, int] = {}
    for t in hyp_tokens:
        hyp_counts[t] = hyp_counts.get(t, 0) + 1
    for t, cnt in hyp_counts.items():
        clip_count += min(cnt, ref_counts.get(t, 0))
    return clip_count / len(hyp_tokens)


async def run_eval(
    reference_path: Path,
    prompt_version: str,
    translate_fn: Any,
    embed_fn: Any,
) -> dict:
    """Run eval against a reference JSON file.

    Reference format:
    [
      {"key": "nav.home", "source": "Home", "reference": "Accueil", "locale": "fr-FR"},
      ...
    ]

    Returns aggregate metrics and per-string results.
    """
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    results = []
    bleu_scores: list[float] = []
    sim_scores: list[float] = []

    for item in reference:
        source = item["source"]
        ref_translation = item["reference"]
        locale = item.get("locale", "fr-FR")

        # Translate source string
        try:
            hypothesis = await translate_fn(
                prompt=json.dumps({item["key"]: source}),
                system=f"Translate to {locale}. Output only JSON with the same key.",
            )
            parsed = json.loads(hypothesis)
            hyp_text = parsed.get(item["key"], "")
        except Exception as exc:
            hyp_text = f"ERROR: {exc}"

        bleu = _bleu_unigram(ref_translation, hyp_text)
        bleu_scores.append(bleu)

        # Semantic similarity
        sim = 0.0
        try:
            ref_emb = await embed_fn(ref_translation)
            hyp_emb = await embed_fn(hyp_text)
            sim = cosine_similarity(ref_emb, hyp_emb)
        except Exception:
            pass
        sim_scores.append(sim)

        results.append(
            {
                "key": item["key"],
                "source": source,
                "reference": ref_translation,
                "hypothesis": hyp_text,
                "bleu": round(bleu, 4),
                "semantic_similarity": round(sim, 4),
            }
        )

    n = len(results) or 1
    return {
        "prompt_version": prompt_version,
        "string_count": len(results),
        "avg_bleu": round(sum(bleu_scores) / n, 4),
        "avg_semantic_similarity": round(sum(sim_scores) / n, 4),
        "results": results,
    }
