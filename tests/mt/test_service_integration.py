"""Integration tests for ``app.mt.service.translate_batch``.

Covers the audit fixes in this branch:

* **H4** — DeepL routes through the per-string dict path, gets no QA, and
  flows through validators + structural-tag restoration.
* **H5** — ``LocaleConfig.is_bootstrapped = False`` forces ``needs_review``.
* **M2** — Retry + fallback chain logs every attempt to ``mt_runs`` and
  recovers on the fallback provider when the primary fails with a retryable
  error.
* **M6** — ``translation_memory.repository_id`` is populated.
* **D2** — ``mt_runs.input_tokens`` / ``output_tokens`` are populated from
  provider usage (not word-count estimates).

These tests assume a live Postgres at ``DATABASE_URL`` with the migrations
already applied (see ``tests/mt/conftest.py``).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select

from app.llm.protocol import LLMProvider
from app.models import (
    BatchStatus,
    MtRun,
    Translation,
    TranslationMemory,
    TranslationStatus,
)
from app.mt.service import translate_batch

# Every test in this module runs on the session-scoped event loop — see
# tests/mt/conftest.py for the rationale (asyncpg connections aren't safe
# across loops). The cosmetic asyncpg/SQLAlchemy teardown warning that the
# failure-path tests used to emit is handled at the source, in the
# ``db_session`` fixture teardown (see conftest.py) — not suppressed here.
pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0}
_DEFAULT_USAGE = {"input_tokens": 50, "output_tokens": 10}


def make_provider(
    *,
    name: str,
    model_id: str = "test-model",
    translate_return: str | None = None,
    translate_side_effect: Any = None,
    evaluate_return: str = '{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}',
    evaluate_side_effect: Any = None,
    embed_return: list[float] | None = None,
    embed_side_effect: Any = None,
    translate_usage: dict[str, int] | None = None,
    evaluate_usage: dict[str, int] | None = None,
) -> LLMProvider:
    """Build a ``MagicMock`` shaped like an LLMProvider.

    D2 — ``translate`` / ``evaluate`` now return ``(text, usage)`` tuples.
    Tests can override the usage dict per call; the defaults are non-zero
    for ``translate`` so assertions on ``mt_runs.input_tokens`` /
    ``output_tokens`` have something meaningful to check, and zero for
    ``evaluate`` since QA-call usage isn't currently aggregated.
    """
    p = MagicMock(spec=LLMProvider)
    p.provider_name = name
    p.model_id = model_id
    # M5 pricing — exercise the real-cost calculation in D2 by giving the
    # mock provider a non-zero rate. Anthropic-shaped (Sonnet) numbers
    # are convenient; the test doesn't care about the exact rate, just
    # that the multiplier flows through.
    p.price_per_1k_input = 0.003
    p.price_per_1k_output = 0.015
    if translate_side_effect is not None:
        p.translate = AsyncMock(side_effect=translate_side_effect)
    else:
        usage = translate_usage if translate_usage is not None else _DEFAULT_USAGE
        p.translate = AsyncMock(return_value=(translate_return or "", usage))
    eval_usage = evaluate_usage if evaluate_usage is not None else _ZERO_USAGE
    if evaluate_side_effect is not None:
        p.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    else:
        p.evaluate = AsyncMock(return_value=(evaluate_return, eval_usage))
    if embed_side_effect is not None:
        p.embed = AsyncMock(side_effect=embed_side_effect)
    else:
        p.embed = AsyncMock(return_value=embed_return or [0.1] * 1536)
    return p


# ---------------------------------------------------------------------------
# H4 — DeepL contract
# ---------------------------------------------------------------------------


class TestH4DeepLRouting:
    @pytest.mark.asyncio
    async def test_deepl_path_uses_per_string_dict(self, db_session, sample_batch):
        """DeepL must receive ``json.dumps({key: source})`` + the locale."""
        deepl_output = json.dumps({"hello": "Bonjour le monde"})
        deepl = make_provider(
            name="deepl",
            model_id="deepl",
            translate_return=deepl_output,
        )
        # OpenAI present for embeddings + would be primary fallback (unused here).
        openai = make_provider(name="openai", model_id="gpt-4o")

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"deepl": deepl, "openai": openai, "anthropic": openai},
            deepl_locales=["fr-FR"],
            config_provider="anthropic",
            embed_provider="openai",
        )

        # DeepL was called exactly once, with the per-string dict + locale.
        deepl.translate.assert_awaited_once()
        call_args = deepl.translate.await_args
        assert call_args is not None
        prompt_arg, system_arg = call_args.args[0], call_args.args[1]
        assert json.loads(prompt_arg) == {"hello": "Hello, world"}
        assert system_arg == "fr-FR"

        # evaluate() must never be called for DeepL (would raise NotImplementedError
        # in the real provider).
        deepl.evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deepl_path_writes_translation_and_mt_run(
        self,
        db_session,
        sample_batch,
    ):
        deepl_output = json.dumps({"hello": "Bonjour le monde"})
        deepl = make_provider(
            name="deepl",
            model_id="deepl",
            translate_return=deepl_output,
        )
        openai = make_provider(name="openai", model_id="gpt-4o")

        summary = await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"deepl": deepl, "openai": openai, "anthropic": openai},
            deepl_locales=["fr-FR"],
            config_provider="anthropic",
            embed_provider="openai",
        )

        # Translation got written.
        trans = await db_session.scalar(select(Translation).where(Translation.key_id == sample_batch["key"].id))
        assert trans is not None
        assert trans.value == "Bonjour le monde"
        assert trans.mt_value == "Bonjour le monde"
        assert trans.mt_model == "deepl"

        # QA columns explicitly None — DeepL doesn't run QA.
        assert trans.qa_naturalness is None
        assert trans.qa_consistency is None
        assert trans.qa_accuracy is None
        assert trans.back_translation is None
        assert trans.back_translation_similarity is None

        # An MtRun row exists.
        runs = (
            (await db_session.execute(select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id))).scalars().all()
        )
        assert len(runs) == 1
        assert runs[0].model == "deepl"

        # Summary returned the expected shape.
        assert summary["translated"] + summary["needs_review"] == 1


# ---------------------------------------------------------------------------
# H5 — is_bootstrapped enforcement
# ---------------------------------------------------------------------------


class TestH5BootstrapEnforcement:
    @pytest.mark.asyncio
    async def test_not_bootstrapped_forces_needs_review(
        self,
        db_session,
        sample_batch,
    ):
        # Flip locale to not-bootstrapped.
        sample_batch["locale_cfg"].is_bootstrapped = False
        await db_session.commit()

        # Provider returns the perfect translation with great QA scores —
        # but bootstrap-false should still force review.
        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            # Make back-translation similarity perfect; eval scores all 5.
            embed_return=[1.0] * 1536,
            evaluate_return=('{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}'),
        )

        summary = await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": anthropic},
            config_provider="anthropic",
            embed_provider="anthropic",
        )

        assert summary["needs_review"] == 1
        assert summary["translated"] == 0

        # Re-read batch status from DB.
        await db_session.refresh(sample_batch["batch"])
        assert sample_batch["batch"].status == BatchStatus.needs_review

        trans = await db_session.scalar(select(Translation).where(Translation.key_id == sample_batch["key"].id))
        assert trans is not None
        assert trans.status == TranslationStatus.needs_review

    @pytest.mark.asyncio
    async def test_bootstrapped_locale_follows_normal_qa_rules(
        self,
        db_session,
        sample_batch,
    ):
        # is_bootstrapped is True by default in the fixture; with auto_publish
        # risk class + good QA + good back-translation, we should land on
        # `approved`.
        sample_batch["locale_cfg"].is_bootstrapped = True
        await db_session.commit()

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            embed_return=[1.0] * 1536,
            evaluate_return=('{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}'),
        )

        summary = await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": anthropic},
            config_provider="anthropic",
            embed_provider="anthropic",
        )

        # auto_publish + good QA + bootstrap=True → approved.
        assert summary["translated"] == 1
        assert summary["needs_review"] == 0
        trans = await db_session.scalar(select(Translation).where(Translation.key_id == sample_batch["key"].id))
        assert trans is not None
        assert trans.status == TranslationStatus.approved


# ---------------------------------------------------------------------------
# §15e — a QA *failure* must force review, never silently auto-approve
# ---------------------------------------------------------------------------


class TestQaFailureForcesReview:
    @pytest.mark.asyncio
    async def test_qa_evaluate_failure_forces_review(self, db_session, sample_batch):
        """When evaluate() raises (e.g. provider 402), the translation must land
        in needs_review with NULL qa_* — not auto-approve via the .get(d,5)
        default. Regression for developer-packet §15e."""
        # Same setup as the happy path (auto_publish + bootstrap=True) so the
        # ONLY thing forcing review is the QA failure.
        sample_batch["locale_cfg"].is_bootstrapped = True
        await db_session.commit()

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            embed_return=[1.0] * 1536,
            # evaluate() blows up — simulates the OpenRouter 402 the integrator hit.
            evaluate_side_effect=httpx.HTTPStatusError(
                "402 Payment Required",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(402),
            ),
        )

        summary = await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": anthropic},
            config_provider="anthropic",
            embed_provider="anthropic",
        )

        assert summary["needs_review"] == 1
        assert summary["translated"] == 0
        trans = await db_session.scalar(select(Translation).where(Translation.key_id == sample_batch["key"].id))
        assert trans is not None
        assert trans.status == TranslationStatus.needs_review
        # QA never produced scores — they stay NULL, distinguishable from a pass.
        assert trans.qa_naturalness is None
        assert trans.qa_consistency is None
        assert trans.qa_accuracy is None


# ---------------------------------------------------------------------------
# M2 — retry + fallback
# ---------------------------------------------------------------------------


class TestM2RetryFallback:
    @pytest.mark.asyncio
    async def test_retryable_primary_failure_then_fallback_success(
        self,
        db_session,
        sample_batch,
        monkeypatch,
    ):
        """503 from primary (twice) → fallback succeeds → 3 mt_runs rows."""
        # Zero out the retry sleep so the test runs in milliseconds.
        monkeypatch.setattr("app.mt.service._RETRY_BACKOFF_SECONDS", 0)

        def make_503() -> httpx.HTTPStatusError:
            req = httpx.Request("POST", "http://example/anthropic")
            resp = httpx.Response(503, request=req)
            return httpx.HTTPStatusError("503", request=req, response=resp)

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_side_effect=[make_503(), make_503()],
            embed_return=[1.0] * 1536,
        )
        openai = make_provider(
            name="openai",
            model_id="gpt-4o",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            embed_return=[1.0] * 1536,
            evaluate_return=('{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}'),
        )

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": openai},
            config_provider="anthropic",
            embed_provider="openai",
        )

        # Primary called twice (initial + retry); fallback called once.
        assert anthropic.translate.await_count == 2
        assert openai.translate.await_count == 1

        # Three mt_runs rows — primary, retry, fallback.
        runs = (
            (
                await db_session.execute(
                    select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id).order_by(MtRun.ran_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(runs) == 3
        # The first two used the primary's model_id; the last used the fallback's.
        assert runs[0].model == "claude-test"
        assert runs[1].model == "claude-test"
        assert runs[2].model == "gpt-4o"
        # Failure rows record the error inline in output_text.
        assert "ERROR" in runs[0].output_text
        assert "ERROR" in runs[1].output_text
        assert "ERROR" not in runs[2].output_text

    @pytest.mark.asyncio
    async def test_all_providers_fail_marks_batch_needs_review(
        self,
        db_session,
        sample_batch,
        monkeypatch,
    ):
        monkeypatch.setattr("app.mt.service._RETRY_BACKOFF_SECONDS", 0)

        def make_503() -> httpx.HTTPStatusError:
            req = httpx.Request("POST", "http://example/x")
            resp = httpx.Response(503, request=req)
            return httpx.HTTPStatusError("503", request=req, response=resp)

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_side_effect=[make_503(), make_503()],
            embed_return=[1.0] * 1536,
        )
        openai = make_provider(
            name="openai",
            model_id="gpt-4o",
            translate_side_effect=[make_503()],
            embed_return=[1.0] * 1536,
        )

        summary = await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": openai},
            config_provider="anthropic",
            embed_provider="openai",
        )

        assert summary["translated"] == 0
        assert summary["needs_review"] == 1
        await db_session.refresh(sample_batch["batch"])
        assert sample_batch["batch"].status == BatchStatus.needs_review

        # Three failed attempts logged.
        runs = (
            (await db_session.execute(select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id))).scalars().all()
        )
        assert len(runs) == 3
        assert all("ERROR" in r.output_text for r in runs)

    @pytest.mark.asyncio
    async def test_non_retryable_error_skips_retry(
        self,
        db_session,
        sample_batch,
        monkeypatch,
    ):
        """A 401 is NOT in _RETRYABLE_HTTP_STATUS — primary fires once, then fallback."""
        monkeypatch.setattr("app.mt.service._RETRY_BACKOFF_SECONDS", 0)

        req = httpx.Request("POST", "http://example/x")
        # 401 is not retryable.
        unauth = httpx.HTTPStatusError(
            "401",
            request=req,
            response=httpx.Response(401, request=req),
        )

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_side_effect=[unauth],
            embed_return=[1.0] * 1536,
        )
        openai = make_provider(
            name="openai",
            model_id="gpt-4o",
            translate_return=json.dumps({"hello": "Bonjour"}),
            embed_return=[1.0] * 1536,
            evaluate_return=('{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}'),
        )

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": openai},
            config_provider="anthropic",
            embed_provider="openai",
        )

        # Primary called exactly once (no retry); fallback NOT called because
        # non-retryable errors short-circuit before fallback.
        assert anthropic.translate.await_count == 1
        assert openai.translate.await_count == 0

        # Just the one failure logged.
        runs = (
            (await db_session.execute(select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id))).scalars().all()
        )
        assert len(runs) == 1
        assert "ERROR" in runs[0].output_text


# ---------------------------------------------------------------------------
# D2 — mt_runs.input_tokens / output_tokens populated from provider usage
# ---------------------------------------------------------------------------


class TestD2TokenCounts:
    @pytest.mark.asyncio
    async def test_successful_translate_records_real_token_counts(
        self,
        db_session,
        sample_batch,
    ):
        """Successful translate path stamps ``mt_runs.input_tokens`` /
        ``output_tokens`` from the provider's usage dict — no more
        word-count × 1.3 estimate."""
        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            translate_usage={"input_tokens": 123, "output_tokens": 45},
            embed_return=[1.0] * 1536,
        )

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": anthropic},
            config_provider="anthropic",
            embed_provider="anthropic",
        )

        runs = (
            (await db_session.execute(select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id))).scalars().all()
        )
        assert len(runs) == 1
        assert runs[0].input_tokens == 123
        assert runs[0].output_tokens == 45
        # Cost = real tokens * price_per_1k. price_per_1k_input=0.003,
        # price_per_1k_output=0.015 (Anthropic-shaped defaults in
        # ``make_provider``). Expected: 123/1000*0.003 + 45/1000*0.015
        # = 0.000369 + 0.000675 = 0.001044.
        assert runs[0].cost_usd is not None
        assert float(runs[0].cost_usd) == pytest.approx(0.001044, abs=1e-6)

    @pytest.mark.asyncio
    async def test_failed_attempt_records_zero_tokens(
        self,
        db_session,
        sample_batch,
        monkeypatch,
    ):
        """Failed attempts can't read provider usage (the SDK raised before
        returning) — those rows record zeros, which is fine: the row's
        ``output_text`` carries ``ERROR: ...`` so a debugger can still tell
        a failed attempt from a successful one."""
        monkeypatch.setattr("app.mt.service._RETRY_BACKOFF_SECONDS", 0)

        def make_503() -> httpx.HTTPStatusError:
            req = httpx.Request("POST", "http://example/anthropic")
            resp = httpx.Response(503, request=req)
            return httpx.HTTPStatusError("503", request=req, response=resp)

        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_side_effect=[make_503(), make_503()],
            embed_return=[1.0] * 1536,
        )
        openai = make_provider(
            name="openai",
            model_id="gpt-4o",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            translate_usage={"input_tokens": 200, "output_tokens": 80},
            embed_return=[1.0] * 1536,
        )

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": openai},
            config_provider="anthropic",
            embed_provider="openai",
        )

        runs = (
            (
                await db_session.execute(
                    select(MtRun).where(MtRun.batch_id == sample_batch["batch"].id).order_by(MtRun.ran_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(runs) == 3
        # First two attempts raised before usage was knowable.
        assert runs[0].input_tokens == 0
        assert runs[0].output_tokens == 0
        assert runs[1].input_tokens == 0
        assert runs[1].output_tokens == 0
        # Fallback succeeded — its usage is recorded verbatim.
        assert runs[2].input_tokens == 200
        assert runs[2].output_tokens == 80


# ---------------------------------------------------------------------------
# M6 — repository_id populated
# ---------------------------------------------------------------------------


class TestM6TmRepositoryId:
    @pytest.mark.asyncio
    async def test_approved_translation_populates_repository_id(
        self,
        db_session,
        sample_batch,
    ):
        """When a translation lands on `approved`, the resulting TM row must
        have ``repository_id`` set."""
        anthropic = make_provider(
            name="anthropic",
            model_id="claude-test",
            translate_return=json.dumps({"hello": "Bonjour le monde"}),
            embed_return=[1.0] * 1536,
            evaluate_return=('{"naturalness": 5, "consistency": 5, "accuracy": 5, "issue": null}'),
        )

        await translate_batch(
            db=db_session,
            batch=sample_batch["batch"],
            providers={"anthropic": anthropic, "openai": anthropic},
            config_provider="anthropic",
            embed_provider="anthropic",
        )

        tm_row = await db_session.scalar(
            select(TranslationMemory).where(
                TranslationMemory.project_id == sample_batch["project"].id,
                TranslationMemory.locale == "fr-FR",
            )
        )
        assert tm_row is not None, "Approved translation should produce a TM row"
        assert tm_row.repository_id == sample_batch["repo"].id
        assert tm_row.target_text == "Bonjour le monde"
