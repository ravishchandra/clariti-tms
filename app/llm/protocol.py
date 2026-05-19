from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, TypedDict, runtime_checkable


class TokenUsage(TypedDict):
    """Per-call token counts reported by an LLM provider's SDK response.

    D2 (docs/11-audit-followups.md): ``mt_runs.input_tokens`` /
    ``mt_runs.output_tokens`` need real counts, not word-count estimates,
    so every ``translate()`` / ``evaluate()`` call returns its usage
    alongside the generated text.

    * Anthropic — ``response.usage.input_tokens`` / ``output_tokens``.
    * OpenAI / OpenRouter — ``response.usage.prompt_tokens`` /
      ``completion_tokens``.
    * Ollama — ``prompt_eval_count`` / ``eval_count`` from ``/api/chat``
      (best-effort; fields are absent on some local model setups). Zeros
      when missing.
    * DeepL — no per-token billing (per-character). Zeros.

    Zeros mean "unknown / not billed per token" — the consumer should treat
    that as "cost is a known under-estimate" rather than "the call used
    zero tokens".
    """

    input_tokens: int
    output_tokens: int


def zero_usage() -> TokenUsage:
    """Default usage dict for providers that don't expose token counts."""
    return {"input_tokens": 0, "output_tokens": 0}


# Sampling temperature for translate / evaluate. 0.0 = deterministic (the
# canonical setting for production translation pipelines — see docs/05
# "Determinism & reproducibility"). Higher values produce more variation
# but break:
#
#  * eval-harness reproducibility (same prompt → different score)
#  * regression debugging ("re-run this and tell me what happened")
#  * back-translation similarity scoring (cosine drift across runs)
#  * translation-memory cleanliness (same source → multiple approved targets)
#
# Providers that don't sample (DeepL: deterministic neural MT) accept and
# ignore this kwarg to keep the Protocol uniform.
DEFAULT_TEMPERATURE: float = 0.0


@runtime_checkable
class LLMProvider(Protocol):
    async def translate(
        self,
        prompt: str,
        system: str,
        *,
        cache_system: bool = False,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]: ...

    async def evaluate(
        self,
        prompt: str,
        *,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]: ...

    async def embed(self, text: str) -> list[float]: ...

    @property
    def model_id(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    # M5 — per-provider USD pricing per 1K tokens, used by the MT service to
    # populate `mt_runs.cost_usd`. Providers that don't bill per token
    # (Ollama: local; DeepL: per-character) return 0.0 and the cost field
    # is then a known under-estimate for that provider — surface it through
    # a separate sink if it matters.
    @property
    def price_per_1k_input(self) -> float: ...

    @property
    def price_per_1k_output(self) -> float: ...


class LLMProviderBase(ABC):
    @abstractmethod
    async def translate(
        self,
        prompt: str,
        system: str,
        *,
        cache_system: bool = False,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]: ...

    @abstractmethod
    async def evaluate(
        self,
        prompt: str,
        *,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, TokenUsage]: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    def price_per_1k_input(self) -> float:
        return 0.0

    @property
    def price_per_1k_output(self) -> float:
        return 0.0
