from __future__ import annotations

import openai

from app.llm.protocol import LLMProviderBase, TokenUsage


class OpenAIProvider(LLMProviderBase):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        # `**{conditional-dict}` confuses mypy on the multi-overload AsyncOpenAI
        # constructor — pass base_url explicitly instead.
        if base_url:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = openai.AsyncOpenAI(api_key=api_key)

    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> tuple[str, TokenUsage]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        # OpenAI types `.message.content` as `Optional[str]` (the SDK allows
        # `None` when content was filtered or refused). For our translate path
        # we treat that as a provider failure rather than silently returning "".
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("OpenAI returned no content (filtered or refused)")
        return content, _extract_usage(response)

    async def evaluate(self, prompt: str) -> tuple[str, TokenUsage]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("OpenAI returned no content (filtered or refused)")
        return content, _extract_usage(response)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return response.data[0].embedding

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    # OpenAI GPT-4o pricing (USD per 1K tokens). openai.com/pricing.
    @property
    def price_per_1k_input(self) -> float:
        return 0.0025

    @property
    def price_per_1k_output(self) -> float:
        return 0.01


def _extract_usage(response: object) -> TokenUsage:
    """Pull ``prompt_tokens`` / ``completion_tokens`` off an OpenAI response.

    The OpenAI Python SDK (v1.x) Chat Completions response exposes
    ``response.usage.prompt_tokens`` and ``completion_tokens``. OpenRouter
    proxies the same field names so this helper covers both providers (the
    OpenRouter subclass reuses ``translate`` / ``evaluate`` unchanged).

    Zero defaults handle the case where the upstream provider omits the
    usage block — under-counted cost is preferable to a crashed translate
    call.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }
