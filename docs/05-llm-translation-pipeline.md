# 05 — LLM Translation Pipeline

## The principle

Translation quality for product UI is bounded by context fed to the model, not by the model itself. The pipeline composes a prompt that injects the full project context and all strings in a screen together — so the LLM translates as a coherent unit, not as isolated strings.

**The translation unit is the screen batch, not the string.** All strings in a component/screen go in one LLM call. This produces consistent register, balanced button pairs, and coherent emotional arc across a flow. Per-string calls produce technically correct but stylistically inconsistent output.

## Context hierarchy (injected in every batch prompt)

```
[PROJECT]    glossary (full, not just matched terms) · style guide · brand voice
[LOCALE]     locale_config: formality · register · locale-specific rules
[PLATFORM]   repository.context_notes: "Tap not Click" · naming conventions
[SCREEN]     component_context.description: what the user is doing · emotional state
[BATCH]      all source strings in this screen, in UX order
[TM]         approved translations from same platform (ranked first), then cross-platform
```

The developer contributes the screen description once. The project admin contributes the locale config once. The LLM gets everything it needs without per-string annotations.

## LLMProvider interface

Protocol (structural subtyping) as the contract — contributors implement the three methods without importing from this codebase. Optional `LLMProviderBase` ABC available for IDE autocomplete and definition-time enforcement. See `03-architecture.md` for the full interface definition.

Built-in implementations: `AnthropicProvider` (default), `OpenAIProvider` (fallback), `OllamaProvider` (local, no API key), `DeepLProvider` (plain-text locales only).

**Configuration — `tms.yml` + env var override:**

```yaml
llm:
  provider: anthropic
  fallback_provider: openai
  deepl_locales: [de, fr, nl, pt]
```

`TMS_LLM_PROVIDER` env var overrides `tms.yml`. Provider loaded at startup via dotted import path for community providers.

**Provider selection per batch:**

```python
def select_provider(batch: TranslationBatch, config: LLMConfig) -> LLMProvider:
    # Structural tags or ICU: LLM only (DeepL doesn't preserve syntax)
    if any(k.has_structural_tags or k.icu_shape != 'plain' for k in batch.keys):
        return registry.get(config.provider)
    # Plain text locales configured for DeepL
    if batch.locale in config.deepl_locales:
        return registry.get('deepl')
    return registry.get(config.provider)
```

Fallback chain: `TranslationError` → retry once → fallback provider → mark batch `needs_review`. Both attempts logged to `mt_runs`. Alert if fallback triggers more than 3 times per hour.

## Sampling temperature

Every LLM call — translate and evaluate — accepts a `temperature: float` keyword on the provider Protocol. Default: **`0.0`** (deterministic). Configured via env:

```bash
TRANSLATE_TEMPERATURE=0.0   # used by translate_batch
EVALUATE_TEMPERATURE=0.0    # used by run_eval and locale_consistency_eval
```

`back_translation_qa` always uses `temperature=0.0` regardless of config — its job is to produce a stable comparator, never to be creative. This is hard-coded, not configurable.

**Why 0.0 is the default:**

- **Eval baselines are reproducible.** Re-running `loc eval --prompt translate_v2 --reference …` produces the same scores. Without determinism, a regression of 0.02 BLEU could be noise from the same prompt sampling differently.
- **Regression debugging works.** When a reviewer says "this translation got worse since last week," we can re-run the exact prompt and reproduce. With non-zero temperature, the prompt that failed today might succeed tomorrow — and we'd chase a phantom.
- **TM doesn't accumulate noisy near-duplicates.** Same source, same context → same target. Otherwise the TM grows lots of stylistically-jittery variants of the same string.
- **Cost predictability.** Token counts at temperature 0 are tightly distributed; sampling at higher temperatures occasionally produces verbose explanations that blow output budgets.

**When to raise it (manual, per-run):**

Prompt iteration. When designing a new `translate_v3`, sweeping temperature 0.0 → 0.3 → 0.7 over a fixed eval set helps see whether the prompt's quality plateau depends on sampling diversity. Pass via the service-layer kwargs `translate_temperature=` / `evaluate_temperature=` on `translate_batch()`. The value used is persisted on every `mt_runs.temperature` row so post-hoc analysis can correlate quality with temperature.

**Provider-specific ranges:**

- Anthropic: `[0.0, 1.0]`
- OpenAI: `[0.0, 2.0]`
- Ollama: model-dependent (most models: `[0.0, 2.0]`)
- DeepL: temperature kwarg is accepted and ignored — DeepL's neural MT is deterministic by construction and exposes no sampling control.

**If you change the default**, treat it like a prompt-version bump: all stored eval baselines are now from a different distribution and must be regenerated. The runtime won't stop you, but downstream comparisons against pre-change baselines are no longer apples-to-apples.

## Pre-processing (before MT)

Some string types require transformation before the LLM sees them.

**Structural tag substitution** (strings where `has_structural_tags = true`):

React Trans component strings contain index-based tags that are meaningless without source code context:
```
Input:  "By confirming, you agree to our <1>Terms of Service</1> and <3>Privacy Policy</3>"
Output: "By confirming, you agree to our {{termsLink}} and {{privacyLink}}"
```

Android HTML strings are shown as rendered text with structural markers:
```
Input:  "By confirming, you agree to our <b>Terms of Service</b>"
Output: "By confirming, you agree to our [BOLD:Terms of Service]"
```

The substitution map is stored and reversed in post-processing. The LLM and human reviewer both see clean, named references.

**Format specifier normalization** (for cross-platform consistency in the prompt):

Platform specifiers are documented clearly in the prompt — the LLM is told exactly what to preserve:
- iOS: `%@`, `%d`, `%1$@` (positional — order can change, presence cannot)
- Android: `%1$s`, `%2$d` (same rules)
- i18next: `{{name}}` (must not be translated)
- ICU: `{name}` (preserve structure, translate only message values)

## Batch prompt structure (`translate_v1`)

```
SYSTEM:
You are translating the {screen_name} screen of {project_name} ({domain_description})
from {source_locale} to {target_locale}.

--- PROJECT STYLE ---
{project.style_guide}

--- LOCALE RULES ({target_locale}) ---
Formality: {locale_config.formality}
Register: {locale_config.register}
{locale_config.notes}

--- PLATFORM ({repository.platform}) ---
{repository.context_notes}

--- FULL GLOSSARY (follow exactly) ---
{all glossary_terms for this project + locale}
Format: "source_term" → "target_term" [notes if any]

--- APPROVED TRANSLATIONS (match their style) ---
Same platform, same project:
{top TM neighbors, platform-matched, with component tag}

Other platforms, same project:
{top TM neighbors, cross-platform, with platform tag}

--- SCREEN CONTEXT ---
{component_context.description}
{component_context.notes}

USER:
Translate the following strings as a coherent set. They all appear on the same screen
in the order shown. Maintain consistent register, formality, and voice across all of them.

Platform format rules:
- Preserve all format specifiers exactly: {format_specifier_list}
- {platform-specific placeholder rules}
- Output ONLY the translated strings as JSON. No explanation.

Strings to translate:
{
  "key_1": "Confirm payment",
  "key_2": "Cancel",
  "key_3": "Edit payment method",
  "key_4": "Total",
  "key_5": "By confirming, you agree to our {{termsLink}}",
  "key_6": "Processing your payment…",
  "key_7": "Payment confirmed!",
  "key_8": "Your card was declined."
}
```

Output: JSON object `{"key_1": "...", "key_2": "...", ...}`. If the model returns anything other than valid JSON, retry once, then mark the batch `needs_review` with a `validator_error` note.

## TM retrieval (per batch, not per string)

Embed the concatenated source texts of the batch once. Retrieve TM neighbors for the batch as a whole, ranked by platform match:

```python
async def retrieve_tm_neighbors(batch, locale, k=10):
    batch_embedding = await provider.embed(
        ' '.join(k.source_text for k in batch.keys)
    )
    rows = await db.fetch_all("""
        SELECT source_text, target_text, platform, context,
               1 - (source_embedding <=> $3) AS similarity,
               CASE WHEN platform = $5 THEN 0.15 ELSE 0 END AS platform_boost
        FROM translation_memory
        WHERE project_id = $1 AND locale = $2
          AND source_key_id != ALL($4)   -- exclude this batch's own keys
        ORDER BY (source_embedding <=> $3) - platform_boost
        LIMIT $6
    """, batch.project_id, locale, batch_embedding,
         [k.id for k in batch.keys], batch.repository.platform, k)
    return [r for r in rows if r.similarity >= 0.65]
```

## Glossary matching

Full project glossary loaded once per batch (not per string). Included in the system prompt so the LLM has complete terminology in working context:

```python
async def load_glossary(project_id, locale):
    return await db.fetch_all("""
        SELECT source_term, target_term, do_not_translate, notes
        FROM glossary_terms
        WHERE project_id = $1 AND locale = $2
        ORDER BY length(source_term) DESC  -- longer terms first, avoids partial matches
    """, project_id, locale)
```

## Post-processing (after MT output)

1. Parse JSON output. Validate all expected keys are present.
2. Restore structural tags: reverse the substitution map from pre-processing.
3. Run validators (see below).
4. Run back-translation QA.
5. Run locale consistency eval.
6. Write `translations` rows and `mt_runs` row.

## Validators

Run on every string in the batch output before storing:

```python
def validate_string(source, translated, key, locale, pre_processing_map):
    errors = []

    # 1. Format specifiers preserved (platform-specific extraction)
    src_ph = sorted(extract_placeholders(source, key.repository.file_format))
    tgt_ph = sorted(extract_placeholders(translated, key.repository.file_format))
    if src_ph != tgt_ph:
        errors.append(f"Placeholder mismatch: expected {src_ph}, got {tgt_ph}")

    # 2. ICU shape preserved
    if key.icu_shape == 'plural' and not parses_as_icu_plural(translated):
        errors.append("ICU plural structure broken")

    # 3. Structural tags restored correctly
    if key.has_structural_tags:
        for placeholder, original_tag in pre_processing_map.items():
            if placeholder not in translated:
                errors.append(f"Structural placeholder {placeholder} missing from output")

    # 4. Max length
    if key.max_length and len(translated) > key.max_length:
        errors.append(f"Length {len(translated)} exceeds limit {key.max_length}")

    # 5. Do-not-translate glossary terms present
    for term in glossary_terms:
        if term.do_not_translate and term.source_term not in translated:
            errors.append(f"Brand term '{term.source_term}' missing")

    return errors
```

Any string with validator errors: `status = needs_review`, errors recorded in `qa_issue`. The batch can still have other strings move to `approved` — validation is per-string within the batch.

## Back-translation QA

After MT, run a second LLM call to translate the output back to the source locale:

```python
async def back_translation_qa(source, translated, locale, provider):
    back = await provider.evaluate(f"""
        Translate this {locale} text back to English.
        Output only the English translation. No explanation.

        Text: {translated}
    """)
    similarity = cosine_similarity(
        await provider.embed(source),
        await provider.embed(back)
    )
    return back, similarity
```

If `similarity < 0.80`: flag `needs_review` regardless of risk class. Store `back_translation` and `back_translation_similarity` on the translation row for debugging.

## Locale consistency eval

A third LLM call scores the translation on three dimensions:

```python
async def locale_consistency_eval(source, translated, locale, locale_config, tm_neighbors, provider):
    result = await provider.evaluate(f"""
        You are a {locale} language quality evaluator for {project.domain_description}.

        Source (en-US): "{source}"
        Translation ({locale}): "{translated}"

        Style guide: {locale_config.notes}
        Approved examples from this project:
        {format_tm_examples(tm_neighbors)}

        Score each dimension 1-5:
        1. Naturalness: sounds like a native {locale} speaker wrote it
        2. Consistency: matches the register and terminology of the examples
        3. Accuracy: preserves the full meaning of the source

        If any score < 4, explain in one sentence what's wrong.
        Output JSON only: {{"naturalness": N, "consistency": N, "accuracy": N, "issue": "..." or null}}
    """)
    return parse_qa_scores(result)
```

If any score < 3: force `needs_review`. Scores stored as `qa_naturalness`, `qa_consistency`, `qa_accuracy`, `qa_issue` on the translation row.

## Plural generation

For locales that need more than `one`/`other` plural categories, the prompt explicitly requests all required CLDR categories:

```python
CLDR_CATEGORIES = {
    'ar': ['zero', 'one', 'two', 'few', 'many', 'other'],
    'ru': ['one', 'few', 'many', 'other'],
    'pl': ['one', 'few', 'many', 'other'],
    'fr': ['one', 'other'],
    'de': ['one', 'other'],
    'ja': ['other'],
}

def plural_prompt_instruction(locale, plural_format):
    categories = CLDR_CATEGORIES.get(locale, ['one', 'other'])
    if plural_format == 'android-xml':
        return f"Generate all required Android plural categories for {locale}: {categories}"
    elif plural_format == 'stringsdict':
        return f"Generate all required stringsdict plural categories for {locale}: {categories}"
    elif plural_format == 'icu':
        return f"Use ICU plural syntax with categories: {categories}"
```

## Risk-class routing (per batch)

After MT, QA, and validators complete, the batch routes to the next state:

| Risk class | QA passes | Validators pass | Result |
|---|---|---|---|
| `auto_publish` | Yes | Yes | → `approved` |
| `auto_publish` | No | Any | → `needs_review` |
| `standard` | Any | Any | → `needs_review` |
| `high_risk` | Any | Any | → `needs_review` (mandatory) |
| `human_only` | n/a (no MT run) | n/a | → `needs_review` |

Batch status reflects the worst-case string within it. One `high_risk` string in a batch sends the whole batch to review.

## Bootstrap sample for new locales

When a locale is added for the first time (`locale_config.is_bootstrapped = false`):

1. Select a representative sample: 50 strings across all risk classes and string types.
2. Run MT on the sample.
3. Export as XLSX with a note: "Native speaker review required before this locale goes live."
4. After human review and import, set `is_bootstrapped = true`.
5. All approved strings from the sample become TM seed entries.

The bootstrap review is the one moment that requires a human who speaks the target language. It's a one-time 2-hour investment per locale. After bootstrapping, the TM anchors all subsequent translations.

## Prompt versioning

Current version: `translate_v1`. When the prompt template changes:

- Bump to `translate_v2`
- Keep `translate_v1` available for re-runs and debugging
- A query to identify where v1 and v2 differ on the same strings:

```sql
SELECT t.locale, k.source_text, r1.output_text AS v1_output, r2.output_text AS v2_output
FROM mt_runs r1
JOIN mt_runs r2 ON r1.batch_id = r2.batch_id AND r2.prompt_version = 'translate_v2'
JOIN translation_batches b ON r1.batch_id = b.id
JOIN translations t ON t.batch_id = b.id
JOIN keys k ON t.key_id = k.id
WHERE r1.prompt_version = 'translate_v1'
ORDER BY t.locale, k.source_text;
```

## Eval harness

A standalone eval suite runs against a fixed test set of source strings with known-good reference translations. Run whenever the prompt template changes:

```bash
loc eval --prompt translate_v2 --reference evals/fr-FR-reference.json
```

Output: per-string scores, aggregate BLEU/semantic similarity, comparison against `translate_v1` baseline. Regressions block the prompt version bump.

## Cost math (updated)

Typical screen batch: 15–20 strings, ~1,200 input tokens (glossary + context + strings), ~200 output tokens.

Plus back-translation call: ~300 input tokens, ~100 output tokens.
Plus QA eval call: ~500 input tokens, ~50 output tokens.

Total per batch: ~2,000 input, ~350 output.

- Claude Sonnet (current pricing): ~$0.018 per batch of 15 strings → ~$0.0012 per string
- With prompt caching (system prompt cached across batches for same locale): 60–70% input token reduction → ~$0.0005 per string

Use Sonnet for `standard` and `auto_publish`. Use Opus only for `human_only` strings where MT quality sets the baseline for a human translator. Prompt caching should be enabled by default — the system prompt (glossary + locale config + style guide) is identical across all batches for a given project/locale pair.

## When MT re-runs

Re-runs for a key:
- `source_hash` changed (source text was updated)
- Reviewer rejected the translation
- Glossary entry changed that affects this key (queued for re-run)
- Admin triggers manual re-run

Does not re-run:
- Reviewer edited the MT output — the edited value stays, MT value preserved in `mt_value`
- New TM entry added — only affects future translations
