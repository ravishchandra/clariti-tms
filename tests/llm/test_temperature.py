"""Temperature plumbing tests — the load-bearing verification.

Two questions the rest of the codebase relies on:

1. Does every LLM provider actually pass ``temperature`` to its SDK?
   If we forget to thread it through, deterministic mode silently
   becomes provider-default (1.0 for Anthropic and OpenAI) and the
   whole "reproducible eval" claim falls apart with no test catching it.

2. Does ``temperature=0.0`` produce identical output across repeated
   calls? This is the property eval baselines, regression debugging,
   and back-translation similarity all depend on.

These tests pin the contract at the unit level. End-to-end determinism
against a real LLM is a separate concern (live API integration tests).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from anthropic.types import TextBlock

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.deepl import DeepLProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider


def _anthropic_mock_response(text: str = "Bonjour", in_tokens: int = 1, out_tokens: int = 1):
    mock_content = MagicMock(spec=TextBlock)
    mock_content.text = text
    mock_usage = MagicMock()
    mock_usage.input_tokens = in_tokens
    mock_usage.output_tokens = out_tokens
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_response.usage = mock_usage
    return mock_response


def _openai_mock_response(text: str = "Bonjour", in_tokens: int = 1, out_tokens: int = 1):
    mock_msg = MagicMock()
    mock_msg.content = text
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = in_tokens
    mock_usage.completion_tokens = out_tokens
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    return mock_response


# ---------------------------------------------------------------------------
# Default temperature is 0.0
# ---------------------------------------------------------------------------


class TestAnthropicTemperatureWiring:
    def _make(self) -> AnthropicProvider:
        with patch("app.llm.providers.anthropic.anthropic.AsyncAnthropic"):
            return AnthropicProvider(api_key="test-key")

    @pytest.mark.asyncio
    async def test_translate_default_temperature_is_zero(self) -> None:
        provider = self._make()
        provider._client.messages.create = AsyncMock(return_value=_anthropic_mock_response())

        await provider.translate("Hello", "sys")

        assert provider._client.messages.create.call_args.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_translate_passes_explicit_temperature(self) -> None:
        provider = self._make()
        provider._client.messages.create = AsyncMock(return_value=_anthropic_mock_response())

        await provider.translate("Hello", "sys", temperature=0.7)

        assert provider._client.messages.create.call_args.kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_evaluate_default_temperature_is_zero(self) -> None:
        provider = self._make()
        provider._client.messages.create = AsyncMock(return_value=_anthropic_mock_response())

        await provider.evaluate("Score this")

        assert provider._client.messages.create.call_args.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_passes_explicit_temperature(self) -> None:
        provider = self._make()
        provider._client.messages.create = AsyncMock(return_value=_anthropic_mock_response())

        await provider.evaluate("Score this", temperature=0.5)

        assert provider._client.messages.create.call_args.kwargs["temperature"] == 0.5


class TestOpenAITemperatureWiring:
    def _make(self) -> OpenAIProvider:
        with patch("app.llm.providers.openai.openai.AsyncOpenAI"):
            return OpenAIProvider(api_key="test-key")

    @pytest.mark.asyncio
    async def test_translate_default_temperature_is_zero(self) -> None:
        provider = self._make()
        provider._client.chat.completions.create = AsyncMock(return_value=_openai_mock_response())

        await provider.translate("Hello", "sys")

        assert provider._client.chat.completions.create.call_args.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_translate_passes_explicit_temperature(self) -> None:
        provider = self._make()
        provider._client.chat.completions.create = AsyncMock(return_value=_openai_mock_response())

        await provider.translate("Hello", "sys", temperature=1.3)

        assert provider._client.chat.completions.create.call_args.kwargs["temperature"] == 1.3

    @pytest.mark.asyncio
    async def test_evaluate_default_temperature_is_zero(self) -> None:
        provider = self._make()
        provider._client.chat.completions.create = AsyncMock(return_value=_openai_mock_response())

        await provider.evaluate("Score this")

        assert provider._client.chat.completions.create.call_args.kwargs["temperature"] == 0.0


class TestOllamaTemperatureWiring:
    @pytest.mark.asyncio
    async def test_translate_passes_temperature_in_options_block(self) -> None:
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        with patch("app.llm.providers.ollama.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock(return_value=None)
            mock_resp.json.return_value = {
                "message": {"content": "Bonjour"},
                "prompt_eval_count": 1,
                "eval_count": 1,
            }
            mock_client.post = AsyncMock(return_value=mock_resp)

            await provider.translate("Hello", "sys", temperature=0.3)

            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["options"] == {"temperature": 0.3}

    @pytest.mark.asyncio
    async def test_translate_default_temperature_is_zero(self) -> None:
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        with patch("app.llm.providers.ollama.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock(return_value=None)
            mock_resp.json.return_value = {
                "message": {"content": "Bonjour"},
                "prompt_eval_count": 0,
                "eval_count": 0,
            }
            mock_client.post = AsyncMock(return_value=mock_resp)

            await provider.translate("Hello", "sys")

            assert mock_client.post.call_args.kwargs["json"]["options"] == {"temperature": 0.0}


class TestDeepLAcceptsAndIgnoresTemperature:
    @pytest.mark.asyncio
    async def test_translate_accepts_temperature_without_error(self) -> None:
        """DeepL is deterministic neural MT — temperature is irrelevant but
        the kwarg must be accepted to satisfy the LLMProvider Protocol."""
        provider = DeepLProvider(api_key="test-key", pro=False)

        with patch("app.llm.providers.deepl.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock(return_value=None)
            mock_resp.json.return_value = {"translations": [{"text": "Bonjour"}]}
            mock_client.post = AsyncMock(return_value=mock_resp)

            # Should not raise — temperature is accepted and ignored.
            text, _usage = await provider.translate('{"key": "Hello"}', "fr-FR", temperature=1.7)
            assert "Bonjour" in text

            # Confirm temperature was NOT forwarded to DeepL's API.
            posted_json = mock_client.post.call_args.kwargs["json"]
            assert "temperature" not in posted_json
            assert "options" not in posted_json

    @pytest.mark.asyncio
    async def test_evaluate_still_raises_not_implemented(self) -> None:
        provider = DeepLProvider(api_key="test-key", pro=False)
        with pytest.raises(NotImplementedError, match="DeepL does not support evaluation"):
            await provider.evaluate("anything", temperature=0.5)


# ---------------------------------------------------------------------------
# Reproducibility — the property the whole knob exists to enable.
# ---------------------------------------------------------------------------


class TestReproducibilityWithMockedSdk:
    """We can't prove temperature=0 produces identical output from a real LLM
    in a unit test (that's a live integration concern). What we CAN prove:
    when the SDK is deterministic, the wrapper is deterministic. If we
    accidentally introduced randomness in the wrapper (e.g. random.choice on
    fallback selection, time-based prompt assembly), this test catches it.
    """

    @pytest.mark.asyncio
    async def test_anthropic_two_identical_calls_with_temp_0_produce_identical_output(
        self,
    ) -> None:
        with patch("app.llm.providers.anthropic.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")

        # Deterministic mock: same response every call.
        provider._client.messages.create = AsyncMock(
            return_value=_anthropic_mock_response(text="Réponse", in_tokens=5, out_tokens=3)
        )

        text1, usage1 = await provider.translate("Hello", "sys", temperature=0.0)
        text2, usage2 = await provider.translate("Hello", "sys", temperature=0.0)

        assert text1 == text2
        assert usage1 == usage2

        # Both calls passed the same temperature.
        for call in provider._client.messages.create.call_args_list:
            assert call.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_openai_two_identical_calls_with_temp_0_produce_identical_output(
        self,
    ) -> None:
        with patch("app.llm.providers.openai.openai.AsyncOpenAI"):
            provider = OpenAIProvider(api_key="test-key")

        provider._client.chat.completions.create = AsyncMock(
            return_value=_openai_mock_response(text="Réponse", in_tokens=5, out_tokens=3)
        )

        text1, usage1 = await provider.translate("Hello", "sys", temperature=0.0)
        text2, usage2 = await provider.translate("Hello", "sys", temperature=0.0)

        assert text1 == text2
        assert usage1 == usage2


# ---------------------------------------------------------------------------
# Provider error paths still surface — temperature didn't accidentally
# swallow exceptions on the way through.
# ---------------------------------------------------------------------------


class TestTemperatureDoesNotSwallowProviderErrors:
    @pytest.mark.asyncio
    async def test_anthropic_propagates_rate_limit(self) -> None:
        with patch("app.llm.providers.anthropic.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key")

        # Simulate a 429 — the retry machinery upstream handles it; the
        # provider just propagates.
        request = httpx.Request("POST", "https://api.anthropic.com")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError("rate limited", request=request, response=response)
        provider._client.messages.create = AsyncMock(side_effect=error)

        with pytest.raises(httpx.HTTPStatusError):
            await provider.translate("Hello", "sys", temperature=0.0)
