from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> str: ...

    async def evaluate(self, prompt: str) -> str: ...

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
    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> str: ...

    @abstractmethod
    async def evaluate(self, prompt: str) -> str: ...

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
