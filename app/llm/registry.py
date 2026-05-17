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


# Ordered fallback chain — primary providers that can run the full structured
# translate-then-evaluate flow. Intentionally excludes "deepl": DeepL is a peer
# selection (plain-text-only locales) rather than a fallback target because it
# cannot run QA evaluation or structural-tag preservation.
# See docs/05-llm-translation-pipeline.md:52.
_FALLBACK_CHAIN: tuple[str, ...] = ("anthropic", "openai", "ollama")


def select_fallback_provider(primary_name: str) -> str | None:
    """Return the next provider in the configured fallback chain.

    Skips ``primary_name`` and any provider before it in the chain, then
    returns the first remaining one. Returns ``None`` when the primary is the
    last entry (no further fallback) or when the primary is not in the chain
    at all (e.g. a community provider — we conservatively refuse to guess).
    """
    if primary_name not in _FALLBACK_CHAIN:
        return None
    idx = _FALLBACK_CHAIN.index(primary_name)
    if idx + 1 >= len(_FALLBACK_CHAIN):
        return None
    return _FALLBACK_CHAIN[idx + 1]
