from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.registry import (
    LLMRegistry,
    RoutingContext,
    select_fallback_provider,
    select_provider,
)

# ---------------------------------------------------------------------------
# select_provider routing
# ---------------------------------------------------------------------------


class TestSelectProvider:
    def test_structural_tags_always_use_config_provider(self) -> None:
        result = select_provider(
            RoutingContext(
                batch_has_structural_tags=True,
                batch_has_icu=False,
                locale="fr-FR",
                config_provider="anthropic",
                deepl_locales=("fr-FR",),
            )
        )
        assert result == "anthropic"
        assert result != "deepl"

    def test_icu_always_use_config_provider(self) -> None:
        result = select_provider(
            RoutingContext(
                batch_has_structural_tags=False,
                batch_has_icu=True,
                locale="fr-FR",
                config_provider="anthropic",
                deepl_locales=("fr-FR",),
            )
        )
        assert result == "anthropic"
        assert result != "deepl"

    def test_plain_text_in_deepl_locales_returns_deepl(self) -> None:
        result = select_provider(
            RoutingContext(
                batch_has_structural_tags=False,
                batch_has_icu=False,
                locale="fr-FR",
                config_provider="anthropic",
                deepl_locales=("fr-FR", "de-DE"),
            )
        )
        assert result == "deepl"

    def test_plain_text_not_in_deepl_locales_returns_config_provider(self) -> None:
        result = select_provider(
            RoutingContext(
                batch_has_structural_tags=False,
                batch_has_icu=False,
                locale="ja-JP",
                config_provider="anthropic",
                deepl_locales=("fr-FR", "de-DE"),
            )
        )
        assert result == "anthropic"


# ---------------------------------------------------------------------------
# select_fallback_provider (M2 — docs/05:52)
# ---------------------------------------------------------------------------


class TestSelectFallbackProvider:
    def test_anthropic_primary_falls_back_to_openai(self) -> None:
        assert select_fallback_provider("anthropic") == "openai"

    def test_openai_primary_falls_back_to_ollama(self) -> None:
        assert select_fallback_provider("openai") == "ollama"

    def test_last_in_chain_returns_none(self) -> None:
        assert select_fallback_provider("ollama") is None

    def test_unknown_primary_returns_none(self) -> None:
        # Community providers — we don't guess.
        assert select_fallback_provider("openrouter") is None
        assert select_fallback_provider("totally-made-up") is None

    def test_deepl_not_in_fallback_chain(self) -> None:
        # DeepL is a peer for plain-text locales, not a fallback target.
        assert select_fallback_provider("deepl") is None


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    def _make_provider(self) -> AnthropicProvider:
        with patch("app.llm.providers.anthropic.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-6")
        return provider

    @pytest.mark.asyncio
    async def test_translate_cache_system_true_sends_list_with_cache_control(self) -> None:
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = "Bonjour"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 12
        mock_usage.output_tokens = 7
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = mock_usage

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.translate("Hello", "Translate to French", cache_system=True)

        assert text == "Bonjour"
        assert usage == {"input_tokens": 12, "output_tokens": 7}
        call_kwargs = provider._client.messages.create.call_args.kwargs
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, list)
        assert system_arg[0]["type"] == "text"
        assert system_arg[0]["text"] == "Translate to French"
        assert system_arg[0]["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_translate_cache_system_false_sends_plain_string(self) -> None:
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = "Bonjour"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 5
        mock_usage.output_tokens = 3
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = mock_usage

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.translate("Hello", "Translate to French", cache_system=False)

        assert text == "Bonjour"
        assert usage == {"input_tokens": 5, "output_tokens": 3}
        call_kwargs = provider._client.messages.create.call_args.kwargs
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, str)
        assert system_arg == "Translate to French"

    @pytest.mark.asyncio
    async def test_translate_missing_usage_returns_zero_tokens(self) -> None:
        """Defensive: if the SDK shape changes and ``usage`` is missing, the
        call still succeeds with under-counted (zero) tokens rather than
        raising."""
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = "Bonjour"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = None

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.translate("Hello", "sys")
        assert text == "Bonjour"
        assert usage == {"input_tokens": 0, "output_tokens": 0}

    @pytest.mark.asyncio
    async def test_evaluate_returns_text_and_usage(self) -> None:
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = '{"naturalness": 5}'
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.usage = mock_usage

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.evaluate("Score this translation")
        assert text == '{"naturalness": 5}'
        assert usage == {"input_tokens": 100, "output_tokens": 50}

    @pytest.mark.asyncio
    async def test_embed_raises_not_implemented(self) -> None:
        provider = self._make_provider()
        with pytest.raises(NotImplementedError, match="Anthropic does not support embeddings"):
            await provider.embed("some text")


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    def _make_provider(self) -> OpenAIProvider:
        with patch("app.llm.providers.openai.openai.AsyncOpenAI"):
            provider = OpenAIProvider(api_key="test-key")
        return provider

    @pytest.mark.asyncio
    async def test_embed_returns_list_of_floats(self) -> None:
        provider = self._make_provider()

        fake_embedding = [0.1, 0.2, 0.3]
        mock_data_item = MagicMock()
        mock_data_item.embedding = fake_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        provider._client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await provider.embed("translation memory query")

        assert result == fake_embedding
        assert isinstance(result, list)
        provider._client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="translation memory query",
        )

    @pytest.mark.asyncio
    async def test_translate_returns_text_and_usage(self) -> None:
        """OpenAI maps ``prompt_tokens`` → ``input_tokens`` and
        ``completion_tokens`` → ``output_tokens``."""
        provider = self._make_provider()

        mock_message = MagicMock()
        mock_message.content = "Bonjour"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 42
        mock_usage.completion_tokens = 9
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.translate("Hello", "Translate to French")
        assert text == "Bonjour"
        assert usage == {"input_tokens": 42, "output_tokens": 9}

    @pytest.mark.asyncio
    async def test_evaluate_returns_text_and_usage(self) -> None:
        provider = self._make_provider()

        mock_message = MagicMock()
        mock_message.content = '{"naturalness": 4}'
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 15
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.evaluate("Score this")
        assert text == '{"naturalness": 4}'
        assert usage == {"input_tokens": 200, "output_tokens": 15}

    @pytest.mark.asyncio
    async def test_translate_missing_usage_returns_zero_tokens(self) -> None:
        provider = self._make_provider()

        mock_message = MagicMock()
        mock_message.content = "Bonjour"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        text, usage = await provider.translate("Hello", "sys")
        assert text == "Bonjour"
        assert usage == {"input_tokens": 0, "output_tokens": 0}


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_translate_raises_connection_error_on_connect_error(self) -> None:
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        with patch("app.llm.providers.ollama.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

            with pytest.raises(ConnectionError, match="Ollama not running at"):
                await provider.translate("Hello", "Translate to French")

    @pytest.mark.asyncio
    async def test_translate_extracts_tokens_from_prompt_eval_and_eval_count(self) -> None:
        """Ollama's ``/api/chat`` returns ``prompt_eval_count`` (input tokens) and
        ``eval_count`` (output tokens) at the top level of the response."""
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={
                "message": {"content": "Bonjour"},
                "prompt_eval_count": 30,
                "eval_count": 4,
            }
        )

        with patch("app.llm.providers.ollama.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            text, usage = await provider.translate("Hello", "Translate to French")

        assert text == "Bonjour"
        assert usage == {"input_tokens": 30, "output_tokens": 4}

    @pytest.mark.asyncio
    async def test_translate_missing_eval_counts_returns_zero_tokens(self) -> None:
        """Some local model runners omit eval counts — we default to zeros so
        the call still succeeds with an under-counted (free) cost."""
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"message": {"content": "Bonjour"}})

        with patch("app.llm.providers.ollama.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            text, usage = await provider.translate("Hello", "sys")

        assert text == "Bonjour"
        assert usage == {"input_tokens": 0, "output_tokens": 0}


# ---------------------------------------------------------------------------
# DeepLProvider
# ---------------------------------------------------------------------------


class TestDeepLProvider:
    @pytest.mark.asyncio
    async def test_translate_returns_zero_usage(self) -> None:
        """DeepL bills per character; per-token usage is not exposed.

        The provider must still satisfy the ``(text, usage)`` Protocol shape
        introduced by D2 — zero counts here mean ``mt_runs.cost_usd`` will
        be 0.0 for DeepL paths, consistent with "cost unknown" semantics.
        """
        from app.llm.providers.deepl import DeepLProvider

        provider = DeepLProvider(api_key="dl-test")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"translations": [{"text": "Bonjour le monde"}]})

        with patch("app.llm.providers.deepl.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            text, usage = await provider.translate('{"hello": "Hello, world"}', "fr-FR")

        # Parsed translation roundtrips as JSON.
        import json as _json

        assert _json.loads(text) == {"hello": "Bonjour le monde"}
        assert usage == {"input_tokens": 0, "output_tokens": 0}


# ---------------------------------------------------------------------------
# LLMRegistry
# ---------------------------------------------------------------------------


class TestLLMRegistry:
    def test_get_raises_key_error_for_unknown_provider(self) -> None:
        reg = LLMRegistry()
        with pytest.raises(KeyError, match="unknown-provider"):
            reg.get("unknown-provider")

    def test_register_and_get_roundtrip(self) -> None:
        reg = LLMRegistry()
        mock_provider = MagicMock()
        reg.register("mock", mock_provider)
        assert reg.get("mock") is mock_provider


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class TestOpenRouterProvider:
    def test_provider_name(self) -> None:
        from app.llm.providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider(api_key="or-test")
        assert p.provider_name == "openrouter"

    def test_default_model_uses_openrouter_namespace(self) -> None:
        from app.llm.providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider(api_key="or-test")
        assert p.model_id == "anthropic/claude-sonnet-4-6"

    def test_custom_model(self) -> None:
        from app.llm.providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider(api_key="or-test", model="openai/gpt-4o")
        assert p.model_id == "openai/gpt-4o"

    def test_client_base_url_is_openrouter(self) -> None:
        from app.llm.providers.openrouter import _BASE_URL, OpenRouterProvider

        p = OpenRouterProvider(api_key="or-test")
        assert str(p._client.base_url).rstrip("/") == _BASE_URL.rstrip("/")
