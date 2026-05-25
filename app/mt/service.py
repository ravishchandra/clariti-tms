"""MT service — translate a single TranslationBatch end-to-end.

This module is the orchestrator for the LLM-driven translation pipeline. It is
intentionally a long, linear flow — each stage's job is documented in
``docs/05-llm-translation-pipeline.md``.

Audit fixes applied in this revision (2026-05):

* **H4** — DeepL no longer receives the rendered Jinja batch prompt. The
  service detects ``provider_name == "deepl"`` and routes through
  :func:`_translate_via_deepl`, which calls DeepL with the per-string dict it
  actually expects. DeepL output skips back-translation QA and the locale
  consistency eval (DeepL does not implement ``evaluate``) but still flows
  through the validator suite + structural-tag restoration.
* **H5** — :class:`~app.models.LocaleConfig.is_bootstrapped` is now enforced
  in the review policy: a locale that has not been bootstrapped (50-string
  native-speaker review per ``docs/06:109``) forces every batch to
  ``needs_review``.
* **M2** — Retry + fallback chain implemented per ``docs/05:52``. Each LLM
  attempt writes its own ``mt_runs`` row (primary, primary-retry, fallback)
  so post-mortem analysis can see every call. The fallback chain is
  configured in :func:`app.llm.registry.select_fallback_provider`.
* **M6** — :func:`app.mt.tm.store_tm_entry` now requires
  ``repository_id``; the caller here passes it from the loaded
  :class:`~app.models.Repository`.
* **D2** — ``mt_runs.input_tokens`` / ``output_tokens`` are populated from
  each SDK's real usage block (``response.usage``) instead of the M5-era
  word-count × 1.3 estimate. ``cost_usd`` falls out of those tokens via
  :func:`_cost_from_usage` and each provider's
  ``price_per_1k_input`` / ``price_per_1k_output``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.llm.protocol import LLMProvider, TokenUsage
from app.llm.registry import RoutingContext, select_fallback_provider, select_provider
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
from app.mt.errors import TranslationError
from app.mt.glossary import format_glossary_for_prompt, load_glossary
from app.mt.plural import plural_prompt_instruction
from app.mt.post_process import parse_llm_json_output, restore_structural_tags
from app.mt.pre_process import PreProcessResult, pre_process_batch
from app.mt.qa import back_translation_qa, locale_consistency_eval
from app.mt.tm import retrieve_tm_neighbors, store_tm_entry
from app.mt.transitions import apply_transition
from app.mt.validators import validate_string

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_JINJA_ENV = Environment(loader=FileSystemLoader(str(_PROMPT_DIR)), autoescape=False)

PROMPT_VERSION = "translate_v1"


async def enqueue_batch_for_mt(db: AsyncSession, batch: TranslationBatch) -> bool:
    """Enqueue a single batch for MT processing.

    Returns ``True`` if the batch transitioned from a queueable state to
    :class:`BatchStatus.pending` (and so the MT worker will pick it up on its
    next sweep), ``False`` if the batch was already in flight or in a state
    that doesn't accept re-triggering (``mt_running``).

    Used by both ``POST /batches/{batch_id}/trigger-mt`` (per-batch path)
    and ``POST /projects/{project_id}/trigger-mt`` (bulk path per docs/15
    F3). The bulk endpoint counts ``True`` returns as ``queued`` and ``False``
    as ``skipped``.

    The actual translation work happens out of band in :mod:`app.mt.worker`;
    this helper only flips the status flag. Idempotent at the worker layer
    (the worker dedupes by batch id).

    The caller is responsible for committing the session — the per-batch
    route does so itself; the bulk route commits once after iterating.
    """
    if batch.status == BatchStatus.mt_running:
        return False
    batch.status = BatchStatus.pending
    return True

# Per-1K-token pricing now lives on the LLMProvider Protocol (M5); real
# token counts come back with every `translate()` / `evaluate()` call as a
# `TokenUsage` dict (D2). See `app/llm/protocol.py` and each provider in
# `app/llm/providers/`.

# HTTP status codes worth retrying. 429 = rate limit; 5xx = transient server
# failures. Anything outside this set (auth, 4xx client errors) is treated as
# non-retryable so we fail fast.
_RETRYABLE_HTTP_STATUS: tuple[int, ...] = (429, 500, 502, 503, 504)

# Backoff between the primary attempt and its single retry. Deliberately
# small — we want the *fallback provider* to be the heavyweight recovery, not
# a long sleep.
_RETRY_BACKOFF_SECONDS = 1.0


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


# Anthropic and OpenAI SDKs raise their own exception types (not httpx
# exceptions) for rate limits and 5xx — we recognize them by class name to
# avoid coupling on the SDK imports. PyJWT-style duck-typing.
_RETRYABLE_SDK_EXC_NAMES: Final[frozenset[str]] = frozenset(
    {
        "RateLimitError",  # anthropic, openai
        "InternalServerError",  # anthropic, openai
        "APITimeoutError",  # openai
        "APIConnectionError",  # openai
        "APIStatusError",  # both — only retryable if status_code matches
        "OverloadedError",  # anthropic
        "ServiceUnavailableError",  # anthropic
    }
)


def _is_retryable(exc: BaseException) -> bool:
    """Whether *exc* matches our retry / fallback policy.

    See docs/05-llm-translation-pipeline.md:52. We retry on:

    * :class:`TranslationError` — provider raised a transient failure shape we
      defined ourselves (e.g. JSON parse failure that may be flaky LLM output).
    * :class:`httpx.RequestError` — network-level failure (DNS, connection
      refused, timeout).
    * :class:`httpx.HTTPStatusError` with a status in
      :data:`_RETRYABLE_HTTP_STATUS`.
    * Anthropic / OpenAI SDK exceptions whose class name matches
      :data:`_RETRYABLE_SDK_EXC_NAMES`, OR which carry a ``status_code`` /
      ``status`` attribute matching :data:`_RETRYABLE_HTTP_STATUS`. The
      providers in ``app/llm/providers/`` call the SDKs directly rather than
      raw ``httpx``, so without this branch SDK-side rate limits and 5xx would
      slip through as non-retryable.

    Auth errors, 4xx client errors, and unexpected programmer bugs fall
    through to ``False`` and bypass retries entirely.
    """
    if isinstance(exc, TranslationError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_HTTP_STATUS
    if isinstance(exc, httpx.RequestError):
        return True
    # SDK exceptions — duck-type by class name + status attribute.
    name = type(exc).__name__
    if name in _RETRYABLE_SDK_EXC_NAMES:
        # Distinguish 429/5xx (retryable) from 4xx (not). If the SDK didn't
        # set a status_code, default to retryable — the common case for the
        # listed names is rate-limit or transient.
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status is None:
            return True
        return isinstance(status, int) and status in _RETRYABLE_HTTP_STATUS
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and status in _RETRYABLE_HTTP_STATUS:
        return True
    return False


def _record_mt_run(
    db: AsyncSession,
    batch: TranslationBatch,
    *,
    model: str,
    prompt_text: str,
    output_text: str,
    string_count: int | None,
    latency_ms: int,
    validators_passed: bool | None = None,
    validator_errors: dict | None = None,
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    temperature: float | None = None,
) -> MtRun:
    """Insert an ``mt_runs`` row for a single LLM attempt.

    Called for every attempt (primary, primary-retry, fallback) so we can
    audit each call separately — required by docs/05:52.

    ``ran_at`` is set client-side via :func:`datetime.now` so each row gets
    a distinct timestamp. The schema default ``func.now()`` resolves to
    Postgres ``current_timestamp``, which is constant across a single
    transaction — that would tie ORDER BY ran_at when we write multiple
    attempts for one batch.

    ``input_tokens`` / ``output_tokens`` are populated from the provider's
    own usage block (D2). Zeros are written for failed attempts (the
    provider raised before usage was available) and for providers that
    don't expose per-call usage (DeepL — billed per character; Ollama
    when the model runner omits ``prompt_eval_count``).
    """
    mt_run = MtRun(
        batch_id=batch.id,
        prompt_version=PROMPT_VERSION,
        model=model,
        prompt_text=prompt_text,
        output_text=output_text,
        validators_passed=validators_passed,
        validator_errors=validator_errors,
        string_count=string_count,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        temperature=temperature,
        ran_at=datetime.now(tz=UTC),
    )
    db.add(mt_run)
    return mt_run


def _cost_from_usage(provider: LLMProvider, usage: TokenUsage) -> float:
    """Compute USD cost from real token counts and the provider's pricing (D2).

    Replaces the M5-era word-count × 1.3 fudge. Returns 0.0 when either
    usage is zero or the provider's per-1K-token price is 0.0 (Ollama:
    local; DeepL: per-character; OpenRouter: rate varies per model).
    """
    return round(
        (usage["input_tokens"] / 1000) * provider.price_per_1k_input
        + (usage["output_tokens"] / 1000) * provider.price_per_1k_output,
        6,
    )


async def _attempt_translation(
    provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    expected_keys: list[str],
    *,
    temperature: float,
) -> tuple[dict[str, str], str, TokenUsage]:
    """Single LLM call + JSON parse.

    Returns ``(translations_dict, raw_output_text, usage)``. Raises whatever
    the provider raises (``httpx.HTTPStatusError``, ``httpx.RequestError``,
    auth errors, etc.) and converts JSON parse failures into
    :class:`TranslationError` so the retry/fallback machinery picks them up.
    """
    raw_output, usage = await provider.translate(
        user_prompt,
        system_prompt,
        cache_system=True,
        temperature=temperature,
    )
    try:
        translations_out = parse_llm_json_output(raw_output, expected_keys)
    except ValueError as exc:
        # Wrap so this is retryable — LLMs occasionally emit malformed JSON
        # that succeeds on a retry.
        raise TranslationError(f"LLM output parse failure: {exc}") from exc
    return translations_out, raw_output, usage


async def _translate_with_retry_and_fallback(
    db: AsyncSession,
    batch: TranslationBatch,
    providers: dict[str, LLMProvider],
    primary_name: str,
    system_prompt: str,
    user_prompt: str,
    expected_keys: list[str],
    *,
    temperature: float,
) -> tuple[dict[str, str] | None, str | None, str | None, str]:
    """Run primary → retry-once → fallback per docs/05:52.

    Each attempt writes its own ``mt_runs`` row regardless of outcome (the
    error message is stored in ``output_text`` when the call raises).

    Returns ``(translations_out, raw_output, error_message, provider_used)``.
    On total failure, ``translations_out`` and ``raw_output`` are ``None`` and
    ``error_message`` carries the last error.

    Fallback emissions are logged as the structured event
    ``mt.fallback_triggered`` (F7); the rate-of-3/hour alarm from docs/05:52
    is enforced at the log sink, not in-process.
    """
    last_error: str | None = None
    last_provider_used: str = primary_name

    # ---- Attempt 1: primary provider --------------------------------------
    primary_provider = providers[primary_name]
    t0 = time.monotonic()
    try:
        translations_out, raw_output, usage = await _attempt_translation(
            primary_provider, system_prompt, user_prompt, expected_keys, temperature=temperature
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=primary_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=raw_output,
            string_count=len(translations_out),
            latency_ms=latency_ms,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=_cost_from_usage(primary_provider, usage),
            temperature=temperature,
        )
        return translations_out, raw_output, None, primary_name
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=primary_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=f"ERROR: {exc}",
            string_count=None,
            latency_ms=latency_ms,
            temperature=temperature,
        )
        if not _is_retryable(exc):
            logger.error(
                "MT primary attempt failed (non-retryable) for batch %s: %s",
                batch.id,
                exc,
            )
            return None, None, str(exc), primary_name
        logger.warning(
            "MT primary attempt failed (retryable) for batch %s: %s — retrying",
            batch.id,
            exc,
        )
        last_error = str(exc)

    # ---- Attempt 2: retry primary -----------------------------------------
    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
    t0 = time.monotonic()
    try:
        translations_out, raw_output, usage = await _attempt_translation(
            primary_provider, system_prompt, user_prompt, expected_keys, temperature=temperature
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=primary_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=raw_output,
            string_count=len(translations_out),
            latency_ms=latency_ms,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=_cost_from_usage(primary_provider, usage),
            temperature=temperature,
        )
        return translations_out, raw_output, None, primary_name
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=primary_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=f"ERROR (retry): {exc}",
            string_count=None,
            latency_ms=latency_ms,
            temperature=temperature,
        )
        last_error = str(exc)
        # Codex follow-up: don't proceed to fallback for non-retryable
        # exceptions (auth failures, 4xx). Symmetric with attempt 1's check.
        if not _is_retryable(exc):
            logger.error(
                "MT primary retry failed (non-retryable) for batch %s: %s",
                batch.id,
                exc,
            )
            return None, None, last_error, primary_name
        logger.warning(
            "MT primary retry failed (retryable) for batch %s: %s — attempting fallback",
            batch.id,
            exc,
        )

    # ---- Attempt 3: fallback provider -------------------------------------
    fallback_name = select_fallback_provider(primary_name)
    if fallback_name is None or fallback_name not in providers:
        logger.error(
            "MT no fallback available for batch %s after primary='%s' failed",
            batch.id,
            primary_name,
        )
        return None, None, last_error, primary_name

    fallback_provider = providers[fallback_name]
    last_provider_used = fallback_name
    t0 = time.monotonic()
    # F7 — structured `mt.fallback_triggered` event for the sink-side rate
    # alarm (docs/05:52: alert if fallback fires > 3 times/hour). Logged
    # before the attempt so the event is captured even if the fallback
    # itself raises.
    logger.warning(
        "mt.fallback_triggered",
        extra={
            "primary": primary_name,
            "fallback": fallback_name,
            "batch_id": str(batch.id),
            "error": last_error,
        },
    )
    try:
        translations_out, raw_output, usage = await _attempt_translation(
            fallback_provider, system_prompt, user_prompt, expected_keys, temperature=temperature
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=fallback_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=raw_output,
            string_count=len(translations_out),
            latency_ms=latency_ms,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=_cost_from_usage(fallback_provider, usage),
            temperature=temperature,
        )
        logger.info(
            "MT fallback to '%s' succeeded for batch %s",
            fallback_name,
            batch.id,
        )
        return translations_out, raw_output, None, fallback_name
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        _record_mt_run(
            db,
            batch,
            model=fallback_provider.model_id,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            output_text=f"ERROR (fallback): {exc}",
            string_count=None,
            latency_ms=latency_ms,
            temperature=temperature,
        )
        logger.error(
            "MT fallback '%s' also failed for batch %s: %s",
            fallback_name,
            batch.id,
            exc,
        )
        return None, None, str(exc), last_provider_used


async def _translate_via_deepl(
    db: AsyncSession,
    batch: TranslationBatch,
    provider: LLMProvider,
    pre: PreProcessResult,
) -> tuple[dict[str, str] | None, str | None]:
    """DeepL-specific translate path (H4).

    DeepL doesn't accept the rendered Jinja prompt — it expects a JSON dict of
    ``{key: source_text}`` as ``prompt`` and the target locale as ``system``.
    We hand it exactly that shape, then return the parsed translations in the
    same form the JSON-LLM path uses.

    DeepL also doesn't implement ``evaluate`` or ``embed`` — that's why this
    branch exists at all. Back-translation + locale-consistency QA are
    skipped at the call site; the validator suite still runs.

    Retries once on a retryable failure (codex follow-up) — DeepL's
    free/pro endpoints return 429 / 5xx under load. No fallback to LLM
    providers: the prompt shapes are different and LLM-as-DeepL-fallback
    would mean re-rendering the Jinja prompt with the same provider
    pool we're already routing away from. Each attempt logged to mt_runs.
    """
    deepl_input = json.dumps(pre.processed_strings, ensure_ascii=False)

    async def _attempt() -> tuple[str, TokenUsage, int]:
        t0_inner = time.monotonic()
        raw, usage = await provider.translate(deepl_input, batch.locale)
        return raw, usage, int((time.monotonic() - t0_inner) * 1000)

    # ---- Attempt 1
    try:
        raw_output, usage, latency_ms = await _attempt()
    except Exception as exc:
        latency_ms = 0  # we don't know how long it ran before raising
        _record_mt_run(
            db,
            batch,
            model=provider.model_id,
            prompt_text=f"DEEPL input ({batch.locale}):\n{deepl_input}",
            output_text=f"ERROR: {exc}",
            string_count=None,
            latency_ms=latency_ms,
        )
        if not _is_retryable(exc):
            logger.error("DeepL call failed (non-retryable) for batch %s: %s", batch.id, exc)
            return None, str(exc)
        # Retry once.
        logger.warning("DeepL call failed (retryable) for batch %s: %s — retrying", batch.id, exc)
        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
        try:
            raw_output, usage, latency_ms = await _attempt()
        except Exception as exc2:
            _record_mt_run(
                db,
                batch,
                model=provider.model_id,
                prompt_text=f"DEEPL input ({batch.locale}):\n{deepl_input}",
                output_text=f"ERROR (retry): {exc2}",
                string_count=None,
                latency_ms=0,
            )
            logger.error("DeepL retry also failed for batch %s: %s", batch.id, exc2)
            return None, str(exc2)

    # `latency_ms` / `usage` are set by the successful `_attempt()` call above.
    try:
        translations_out = parse_llm_json_output(raw_output, list(pre.processed_strings.keys()))
    except ValueError as exc:
        _record_mt_run(
            db,
            batch,
            model=provider.model_id,
            prompt_text=f"DEEPL input ({batch.locale}):\n{deepl_input}",
            output_text=raw_output,
            string_count=None,
            latency_ms=latency_ms,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )
        logger.warning("DeepL output parse failure for batch %s: %s", batch.id, exc)
        return None, str(exc)

    _record_mt_run(
        db,
        batch,
        model=provider.model_id,
        prompt_text=f"DEEPL input ({batch.locale}):\n{deepl_input}",
        output_text=raw_output,
        string_count=len(translations_out),
        latency_ms=latency_ms,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=_cost_from_usage(provider, usage),
    )
    return translations_out, None


async def translate_batch(
    db: AsyncSession,
    batch: TranslationBatch,
    providers: dict[str, LLMProvider],
    deepl_locales: list[str] | None = None,
    config_provider: str = "anthropic",
    embed_provider: str = "openai",
    translate_temperature: float | None = None,
    evaluate_temperature: float | None = None,
) -> dict:
    """Translate all draft translations in *batch*.

    `translate_temperature` and `evaluate_temperature` control sampling for
    the translation and QA-evaluation LLM calls respectively. ``None`` (the
    default) falls back to the settings defaults
    (``TRANSLATE_TEMPERATURE`` / ``EVALUATE_TEMPERATURE``). Both default to
    0.0 (deterministic) so eval baselines and TM stay consistent — see
    docs/05 "Determinism & reproducibility". Back-translation QA always
    runs at 0.0 regardless; see `app.mt.qa.back_translation_qa`.

    Returns a summary dict with counts and cost.
    """
    settings = get_settings()
    translate_temp = translate_temperature if translate_temperature is not None else settings.TRANSLATE_TEMPERATURE
    evaluate_temp = evaluate_temperature if evaluate_temperature is not None else settings.EVALUATE_TEMPERATURE

    deepl_locales = deepl_locales or []

    # Mark batch running
    batch.status = BatchStatus.mt_running
    await db.flush()

    # Load project, repo, locale config. project and repo are guaranteed
    # non-None by FK constraints on TranslationBatch — assertions narrow the
    # type for mypy and surface the impossible case if it ever happens.
    project = await db.get(Project, batch.project_id)
    repo = await db.get(Repository, batch.repository_id)
    if project is None or repo is None:
        raise RuntimeError(
            f"Batch {batch.id} references missing project={batch.project_id} "
            f"or repository={batch.repository_id} — FK constraint violated."
        )
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
        RoutingContext(
            batch_has_structural_tags=has_structural,
            batch_has_icu=has_icu,
            locale=batch.locale,
            config_provider=config_provider,
            deepl_locales=tuple(deepl_locales),
        )
    )
    provider = providers[provider_name]
    embed_prov = providers.get(embed_provider, provider)
    is_deepl = provider_name == "deepl"

    # Glossary
    glossary = await load_glossary(db, str(batch.project_id), batch.locale)

    # TM neighbors — embed batch source texts together. DeepL doesn't embed,
    # so we use the embed provider directly (already not the DeepL one).
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
            exclude_key_ids=[k.id for k in keys_list],
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

    # Translation dispatch -------------------------------------------------
    #
    # Two paths:
    #   1. DeepL (plain-text-only locales): build per-string dict, hand it to
    #      DeepL with the locale as `system`. No Jinja prompt. No retry/fallback
    #      (DeepL is a peer of the LLM providers, not a fallback target).
    #   2. LLM (anthropic/openai/ollama/openrouter/community): render the
    #      Jinja batch prompt, attempt primary → retry → fallback.
    translations_out: dict[str, str] | None
    error_message: str | None
    provider_used: str = provider_name

    if is_deepl:
        translations_out, error_message = await _translate_via_deepl(
            db=db,
            batch=batch,
            provider=provider,
            pre=pre,
        )
        if translations_out is None:
            batch.status = BatchStatus.needs_review
            await db.commit()
            return {
                "translated": 0,
                "needs_review": len(pairs),
                "cost_usd": 0.0,
                "error": error_message,
            }
    else:
        # Render the Jinja batch prompt for the LLM path only.
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

        (
            translations_out,
            _raw_output,
            error_message,
            provider_used,
        ) = await _translate_with_retry_and_fallback(
            db=db,
            batch=batch,
            providers=providers,
            primary_name=provider_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            expected_keys=list(pre.processed_strings.keys()),
            temperature=translate_temp,
        )
        if translations_out is None:
            batch.status = BatchStatus.needs_review
            await db.commit()
            return {
                "translated": 0,
                "needs_review": len(pairs),
                "cost_usd": 0.0,
                "error": error_message,
            }
        # Swap to the provider that actually succeeded so the model_id we
        # record and the per-string evaluate() calls below come from the
        # provider that actually produced these translations. The embedding
        # provider (used for TM neighbor retrieval) is independent — leave
        # ``embed_prov`` alone.
        provider = providers[provider_used]

    # Process each string ---------------------------------------------------
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

        # QA — back-translation + locale-consistency eval.
        #
        # DeepL doesn't implement ``evaluate`` (it raises NotImplementedError)
        # and skipping QA for the DeepL path is the documented trade-off
        # (H4). All three QA scores remain None so the review-policy
        # disjunction below uses its safe default (5) and does NOT force
        # review on missing scores.
        back_text: str | None = None
        back_sim: float | None = None
        qa_scores: dict = {}

        if not is_deepl and batch_embedding is not None:
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

            try:
                qa_scores = await locale_consistency_eval(
                    source=key.source_text,
                    translated=translated_text,
                    locale=batch.locale,
                    domain_description=project.style_guide or "A professional application.",
                    locale_notes=locale_cfg.notes if locale_cfg else None,
                    tm_neighbors=tm_neighbors,
                    evaluate_fn=provider.evaluate,
                    temperature=evaluate_temp,
                )
            except Exception as exc:
                logger.warning("QA eval failed for key %s: %s", key_str, exc)

        # Risk-class routing — see docs/06-human-review-workflow.md:100-113.
        review_forced = (
            not val_result.valid
            or key.risk_class in ("high_risk", "human_only")
            or (key.risk_class == "standard")
            or (back_sim is not None and back_sim < 0.80)
            or any(qa_scores.get(d, 5) < 3 for d in ("naturalness", "consistency", "accuracy"))
            # docs/06:109 — force review until native-speaker bootstrap complete
            or (locale_cfg is not None and not locale_cfg.is_bootstrapped)
        )
        new_status = TranslationStatus.needs_review if review_forced else TranslationStatus.approved

        # Write translation row. Status moves via the canonical state-machine
        # path `draft -> mt_proposed -> {needs_review, approved}` so every
        # edge is validated by `apply_transition`. SQLAlchemy collapses the
        # two ORM writes into one UPDATE on commit.
        translation.value = translated_text
        translation.mt_value = translated_text
        apply_transition(translation, TranslationStatus.mt_proposed)
        apply_transition(translation, new_status)
        translation.mt_model = provider.model_id
        translation.mt_prompt_version = PROMPT_VERSION
        translation.mt_run_at = datetime.now(tz=UTC)
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

        # Store TM entry if approved. DeepL output can also feed TM as long as
        # we have an embedding provider available — TM is keyed by source
        # text similarity, so the origin provider is irrelevant.
        if new_status == TranslationStatus.approved and batch_embedding is not None:
            try:
                key_embedding = await embed_prov.embed(key.source_text)
                await store_tm_entry(
                    db=db,
                    project_id=str(batch.project_id),
                    repository_id=str(repo.id),
                    locale=batch.locale,
                    source_key_id=str(key.id),
                    source_text=key.source_text,
                    target_text=translated_text,
                    platform=repo.platform,
                    embedding=key_embedding,
                )
            except Exception as exc:
                logger.warning("TM store failed for key %s: %s", key_str, exc)

    # Update batch
    batch.status = BatchStatus.needs_review if summary["needs_review"] > 0 else BatchStatus.mt_complete
    batch.mt_model = provider.model_id
    batch.mt_prompt_version = PROMPT_VERSION

    # Codex follow-up: attach validator results to the successful attempt's
    # mt_run row. We pick the most recent mt_run for this batch — that's the
    # one that produced `translations_out`. Earlier rows are failed attempts
    # whose `validators_passed` legitimately stays NULL.
    last_run = await db.scalar(select(MtRun).where(MtRun.batch_id == batch.id).order_by(MtRun.ran_at.desc()).limit(1))
    if last_run is not None:
        last_run.validators_passed = len(validator_errors_all) == 0
        last_run.validator_errors = validator_errors_all or None

    # Sum cost across all mt_runs we recorded for this batch (each attempt has
    # its own row now under M2). This avoids re-estimating and double-counting.
    cost_rows = await db.execute(select(MtRun.cost_usd).where(MtRun.batch_id == batch.id))
    summary["cost_usd"] = round(
        float(sum(c or 0 for (c,) in cost_rows.all())),
        6,
    )

    await db.commit()
    logger.info(
        "Batch %s done: %d translated, %d needs_review, $%.4f (provider=%s)",
        batch.id,
        summary["translated"],
        summary["needs_review"],
        summary["cost_usd"],
        provider_used,
    )
    return summary
