from __future__ import annotations

from typing import cast

import anthropic
from anthropic.types import TextBlock, TextBlockParam

from app.llm.protocol import DEFAULT_TEMPERATURE, LLMProviderBase, TokenUsage


def _first_text(content: list[object]) -> str:
    """Pull the text out of the first TextBlock in an Anthropic response.

    `response.content` is a list of `ContentBlock` (a union of `TextBlock`,
    `ThinkingBlock`, `ToolUseBlock`, ...). Only `TextBlock` has `.text`. For
    a plain translate/evaluate call we don't request tools or thinking, so
    the first block is always a TextBlock — but mypy still needs the
    isinstance narrowing.
    """
    for block in content:
        if isinstance(block, TextBlock):
            return block.text
    raise RuntimeError("Anthropic response contained no TextBlock")


class AnthropicProvider(LLMProviderBase):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def translate(
        self,
        prompt: str,
        system: str,
        *,
        cache_system: bool = False,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]:
        system_arg: str | list[TextBlockParam]
        if cache_system:
            system_arg = [
                cast(
                    TextBlockParam,
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    },
                )
            ]
        else:
            system_arg = system

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_arg,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return _first_text(list(response.content)), _extract_usage(response)

    async def evaluate(
        self,
        prompt: str,
        *,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system="",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return _first_text(list(response.content)), _extract_usage(response)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Anthropic does not support embeddings — use OpenAIProvider for TM retrieval")

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    # Anthropic Claude Sonnet 4.x pricing (USD per 1K tokens).
    # Source: anthropic.com/pricing — adjust when the configured model changes.
    @property
    def price_per_1k_input(self) -> float:
        return 0.003

    @property
    def price_per_1k_output(self) -> float:
        return 0.015


def _extract_usage(response: object) -> TokenUsage:
    """Pull ``input_tokens`` / ``output_tokens`` off an Anthropic response.

    The Anthropic SDK returns ``response.usage`` with ``input_tokens`` and
    ``output_tokens`` integer attributes (Messages API). We use ``getattr``
    with zero defaults to avoid coupling to a specific SDK minor version —
    if the shape changes, the call still succeeds with under-counted usage
    rather than raising on every translate call.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }
