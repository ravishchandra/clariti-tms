from __future__ import annotations

from app.llm.protocol import LLMProvider


class LLMRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider:
        if name not in self._providers:
            raise KeyError(f"LLM provider '{name}' not registered")
        return self._providers[name]


registry = LLMRegistry()


def select_provider(
    batch_has_structural_tags: bool,
    batch_has_icu: bool,
    locale: str,
    config_provider: str,
    deepl_locales: list[str],
) -> str:
    # Structural tags or ICU placeholders require LLM understanding — never delegate to DeepL
    if batch_has_structural_tags or batch_has_icu:
        return config_provider

    if locale in deepl_locales:
        return "deepl"

    return config_provider
