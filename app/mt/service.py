"""MT service — translate a single TranslationBatch end-to-end."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.protocol import LLMProvider
from app.llm.registry import select_provider
from app.models import (
    BatchStatus,
    ComponentContext,
    Key,
    LocaleConfig,
    MtRun,
    Project,
    Repository,
    Translation,
    TranslationBatch,
    TranslationStatus,
)
from app.mt.glossary import format_glossary_for_prompt, load_glossary
from app.mt.plural import plural_prompt_instruction
from app.mt.post_process import parse_llm_json_output, restore_structural_tags
from app.mt.pre_process import pre_process_batch
from app.mt.qa import back_translation_qa, locale_consistency_eval
from app.mt.tm import retrieve_tm_neighbors, store_tm_entry
from app.mt.validators import validate_string

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_JINJA_ENV = Environment(loader=FileSystemLoader(str(_PROMPT_DIR)), autoescape=False)

PROMPT_VERSION = "translate_v1"

# Cost per 1k tokens (USD) — Sonnet pricing, updated manually
_COST_PER_1K_INPUT = 0.003
_COST_PER_1K_OUTPUT = 0.015


def _platform_format_specifiers(platform: str) -> list[str]:
    if platform == "ios":
        return [
            "Preserve all format specifiers exactly: %@, %d, %f, %1$@, %2$d",
            "Positional specifiers like %1$@ may be reordered but must all be present",
        ]
    if platform == "android":
        return [
            "Preserve all format specifiers exactly: %1$s, %2$d, %3$f",
            "Positional specifiers must all be present (order may change)",
        ]
    return [
        "Preserve all i18next placeholders exactly: {{name}}, {{count}}",
        "ICU placeholders like {name} must remain untranslated",
        "Do not translate content inside {{ }} or { }",
    ]


async def translate_batch(
    db: AsyncSession,
    batch: TranslationBatch,
    providers: dict[str, LLMProvider],
    deepl_locales: list[str] | None = None,
    config_provider: str = "anthropic",
    embed_provider: str = "openai",
) -> dict:
    """Translate all draft translations in *batch*.

    Returns a summary dict with counts and cost.
    """
    deepl_locales = deepl_locales or []
    t0 = time.monotonic()

    # Mark batch running
    batch.status = BatchStatus.mt_running
    await db.flush()

    # Load project, repo, locale config
    project = await db.get(Project, batch.project_id)
    repo = await db.get(Repository, batch.repository_id)
    locale_cfg = await db.scalar(
        select(LocaleConfig).where(
            LocaleConfig.project_id == batch.project_id,
            LocaleConfig.locale == batch.locale,
        )
    )

    # Load component context if available
    ctx = await db.scalar(
        select(ComponentContext).where(
            ComponentContext.repository_id == batch.repository_id,
            ComponentContext.component == batch.component,
            ComponentContext.screen == batch.screen,
        )
    )

    # Load all draft translations + their keys for this batch
    rows = await db.execute(
        select(Translation, Key)
        .join(Key, Translation.key_id == Key.id)
        .where(
            Translation.batch_id == batch.id,
            Translation.status == TranslationStatus.draft,
        )
    )
    pairs = rows.all()
    if not pairs:
        batch.status = BatchStatus.mt_complete
        await db.flush()
        return {"translated": 0, "needs_review": 0, "cost_usd": 0.0}

    translations_by_key = {key.key: (translation, key) for translation, key in pairs}
    keys_list = [key for _, key in pairs]

    # Provider selection
    has_structural = any(k.has_structural_tags for k in keys_list)
    has_icu = any(k.icu_shape != "plain" for k in keys_list)
    provider_name = select_provider(
        has_structural, has_icu, batch.locale, config_provider, deepl_locales
    )
    provider = providers[provider_name]
    embed_prov = providers.get(embed_provider, provider)

    # Glossary
    glossary = await load_glossary(db, str(batch.project_id), batch.locale)

    # TM neighbors — embed batch source texts together
    raw_strings = {k.key: k.source_text for k in keys_list}
    batch_text = " ".join(raw_strings.values())
    try:
        batch_embedding = await embed_prov.embed(batch_text)
        tm_neighbors = await retrieve_tm_neighbors(
            db=db,
            project_id=str(batch.project_id),
            locale=batch.locale,
            batch_embedding=batch_embedding,
            platform=repo.platform,
            exclude_key_ids=[str(k.id) for k in keys_list],
        )
    except NotImplementedError:
        batch_embedding = None
        tm_neighbors = []

    # Pre-processing
    has_structural_by_key = {k.key: k.has_structural_tags for k in keys_list}
    pre = pre_process_batch(raw_strings, has_structural_by_key, repo.file_format)

    # Plural instruction (use first key's plural_format if any)
    plural_format = next((k.plural_format for k in keys_list if k.plural_format), None)
    plural_instr = plural_prompt_instruction(batch.locale, plural_format)

    # Render prompt
    template = _JINJA_ENV.get_template("translate_v1.j2")
    rendered = template.render(
        screen_name=batch.screen or batch.component,
        project_name=project.name,
        domain_description=project.style_guide or "A professional application.",
        source_locale="en-US",
        target_locale=batch.locale,
        style_guide=project.style_guide,
        locale_config=locale_cfg,
        repository_platform=repo.platform,
        platform_notes=repo.context_notes,
        formatted_glossary=format_glossary_for_prompt(glossary),
        tm_neighbors=tm_neighbors,
        screen_context=(ctx.description if ctx else None),
        strings=pre.processed_strings,
        format_specifiers=_platform_format_specifiers(repo.platform),
        plural_instruction=plural_instr,
    )
    parts = rendered.split("===USER===", 1)
    system_prompt = parts[0].replace("===SYSTEM===", "").strip()
    user_prompt = parts[1].strip() if len(parts) > 1 else rendered.strip()

    # LLM call
    try:
        raw_output = await provider.translate(user_prompt, system_prompt, cache_system=True)
    except Exception as exc:
        logger.error("MT failed for batch %s: %s", batch.id, exc)
        batch.status = BatchStatus.needs_review
        await db.flush()
        return {"translated": 0, "needs_review": len(pairs), "cost_usd": 0.0, "error": str(exc)}

    # Parse output
    try:
        translations_out = parse_llm_json_output(raw_output, list(pre.processed_strings.keys()))
    except ValueError as exc:
        logger.warning("JSON parse error for batch %s: %s", batch.id, exc)
        batch.status = BatchStatus.needs_review
        await db.flush()
        return {"translated": 0, "needs_review": len(pairs), "cost_usd": 0.0, "error": str(exc)}

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Process each string
    summary = {"translated": 0, "needs_review": 0, "cost_usd": 0.0}
    validator_errors_all: dict[str, list[str]] = {}

    for key_str, translated_text in translations_out.items():
        translation, key = translations_by_key[key_str]

        # Restore structural tags
        tag_map = pre.tag_map.get(key_str, {})
        translated_text = restore_structural_tags(translated_text, tag_map)

        # Validate
        val_result = validate_string(
            source=key.source_text,
            translated=translated_text,
            key_icu_shape=key.icu_shape,
            key_has_structural_tags=key.has_structural_tags,
            file_format=repo.file_format,
            max_length=None,
            tag_map=tag_map,
            glossary_terms=glossary,
        )
        if not val_result.valid:
            validator_errors_all[key_str] = val_result.errors

        # Back-translation QA
        back_text: str | None = None
        back_sim: float | None = None
        if batch_embedding is not None:
            try:
                back_text, back_sim = await back_translation_qa(
                    source=key.source_text,
                    translated=translated_text,
                    locale=batch.locale,
                    evaluate_fn=provider.evaluate,
                    embed_fn=embed_prov.embed,
                )
            except Exception as exc:
                logger.warning("Back-translation failed for key %s: %s", key_str, exc)

        # Locale consistency eval
        qa_scores: dict = {}
        try:
            qa_scores = await locale_consistency_eval(
                source=key.source_text,
                translated=translated_text,
                locale=batch.locale,
                domain_description=project.style_guide or "A professional application.",
                locale_notes=locale_cfg.notes if locale_cfg else None,
                tm_neighbors=tm_neighbors,
                evaluate_fn=provider.evaluate,
            )
        except Exception as exc:
            logger.warning("QA eval failed for key %s: %s", key_str, exc)

        # Risk-class routing
        review_forced = (
            not val_result.valid
            or key.risk_class in ("high_risk", "human_only")
            or (key.risk_class == "standard")
            or (back_sim is not None and back_sim < 0.80)
            or any(qa_scores.get(d, 5) < 3 for d in ("naturalness", "consistency", "accuracy"))
        )
        new_status = (
            TranslationStatus.needs_review if review_forced else TranslationStatus.approved
        )

        # Write translation row
        translation.value = translated_text
        translation.mt_value = translated_text
        translation.status = new_status
        translation.mt_model = provider.model_id
        translation.mt_prompt_version = PROMPT_VERSION
        translation.source_hash_at_translation = key.source_hash
        translation.back_translation = back_text
        translation.back_translation_similarity = back_sim
        translation.qa_naturalness = qa_scores.get("naturalness")
        translation.qa_consistency = qa_scores.get("consistency")
        translation.qa_accuracy = qa_scores.get("accuracy")
        translation.qa_issue = qa_scores.get("issue")

        if new_status == TranslationStatus.needs_review:
            summary["needs_review"] += 1
        else:
            summary["translated"] += 1

        # Store TM entry if approved
        if new_status == TranslationStatus.approved and batch_embedding is not None:
            try:
                key_embedding = await embed_prov.embed(key.source_text)
                await store_tm_entry(
                    db=db,
                    project_id=str(batch.project_id),
                    locale=batch.locale,
                    source_key_id=str(key.id),
                    source_text=key.source_text,
                    target_text=translated_text,
                    platform=repo.platform,
                    embedding=key_embedding,
                )
            except Exception as exc:
                logger.warning("TM store failed for key %s: %s", key_str, exc)

    # Rough cost estimate (input tokens unknown without instrumentation — estimate)
    estimated_input = len(system_prompt.split()) * 1.3 + len(user_prompt.split()) * 1.3
    estimated_output = len(raw_output.split()) * 1.3
    cost = (
        (estimated_input / 1000 * _COST_PER_1K_INPUT)
        + (estimated_output / 1000 * _COST_PER_1K_OUTPUT)
    )
    summary["cost_usd"] = round(cost, 6)

    # Log MtRun
    mt_run = MtRun(
        batch_id=batch.id,
        prompt_version=PROMPT_VERSION,
        model=provider.model_id,
        prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
        output_text=raw_output,
        validators_passed=len(validator_errors_all) == 0,
        validator_errors=validator_errors_all or None,
        string_count=len(translations_out),
        latency_ms=latency_ms,
        cost_usd=cost,
    )
    db.add(mt_run)

    # Update batch
    batch.status = (
        BatchStatus.needs_review if summary["needs_review"] > 0 else BatchStatus.mt_complete
    )
    batch.mt_model = provider.model_id
    batch.mt_prompt_version = PROMPT_VERSION

    await db.commit()
    logger.info(
        "Batch %s done: %d translated, %d needs_review, $%.4f",
        batch.id, summary["translated"], summary["needs_review"], cost,
    )
    return summary
