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
