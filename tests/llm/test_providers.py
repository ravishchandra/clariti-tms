from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.registry import LLMRegistry, select_provider

# ---------------------------------------------------------------------------
# select_provider routing
# ---------------------------------------------------------------------------

class TestSelectProvider:
    def test_structural_tags_always_use_config_provider(self) -> None:
        result = select_provider(
            batch_has_structural_tags=True,
            batch_has_icu=False,
            locale="fr-FR",
            config_provider="anthropic",
            deepl_locales=["fr-FR"],
        )
        assert result == "anthropic"
        assert result != "deepl"

    def test_icu_always_use_config_provider(self) -> None:
        result = select_provider(
            batch_has_structural_tags=False,
            batch_has_icu=True,
            locale="fr-FR",
            config_provider="anthropic",
            deepl_locales=["fr-FR"],
        )
        assert result == "anthropic"
        assert result != "deepl"

    def test_plain_text_in_deepl_locales_returns_deepl(self) -> None:
        result = select_provider(
            batch_has_structural_tags=False,
            batch_has_icu=False,
            locale="fr-FR",
            config_provider="anthropic",
            deepl_locales=["fr-FR", "de-DE"],
        )
        assert result == "deepl"

    def test_plain_text_not_in_deepl_locales_returns_config_provider(self) -> None:
        result = select_provider(
            batch_has_structural_tags=False,
            batch_has_icu=False,
            locale="ja-JP",
            config_provider="anthropic",
            deepl_locales=["fr-FR", "de-DE"],
        )
        assert result == "anthropic"


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
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.translate("Hello", "Translate to French", cache_system=True)

        assert result == "Bonjour"
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
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.translate("Hello", "Translate to French", cache_system=False)

        assert result == "Bonjour"
        call_kwargs = provider._client.messages.create.call_args.kwargs
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, str)
        assert system_arg == "Translate to French"

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
        from app.llm.providers.openrouter import OpenRouterProvider, _BASE_URL
        p = OpenRouterProvider(api_key="or-test")
        assert str(p._client.base_url).rstrip("/") == _BASE_URL.rstrip("/")
