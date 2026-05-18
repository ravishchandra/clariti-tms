from __future__ import annotations

from app.llm.providers.openai import OpenAIProvider

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    """Single-key access to any model via OpenRouter's OpenAI-compatible API.

    Model strings use OpenRouter's namespace:
        anthropic/claude-sonnet-4-6
        openai/gpt-4o
        google/gemini-2.0-flash
        meta-llama/llama-3.3-70b-instruct

    Embeddings default to openai/text-embedding-3-small which OpenRouter
    proxies to the real OpenAI endpoint.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-sonnet-4-6",
        embedding_model: str = "openai/text-embedding-3-small",
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            embedding_model=embedding_model,
            base_url=_BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "openrouter"

    # OpenRouter's prices vary per underlying model — we can't safely return
    # the OpenAI defaults inherited from the parent. Return 0.0 so callers
    # know the cost is unknown for this provider; an operator who needs
    # accurate cost tracking should subclass and override per model.
    @property
    def price_per_1k_input(self) -> float:
        return 0.0

    @property
    def price_per_1k_output(self) -> float:
        return 0.0
