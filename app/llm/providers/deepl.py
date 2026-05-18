from __future__ import annotations

import json

import httpx

from app.llm.protocol import LLMProviderBase, TokenUsage, zero_usage


class DeepLProvider(LLMProviderBase):
    def __init__(self, api_key: str, pro: bool = False) -> None:
        self._api_key = api_key
        self._base_url = "https://api.deepl.com/v2" if pro else "https://api-free.deepl.com/v2"
        self._headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}

    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> tuple[str, TokenUsage]:
        # prompt is a JSON string of {key: source_text, ...}; system is the target locale
        texts: dict[str, str] = json.loads(prompt)
        # DeepL uses language codes without region subtag (fr-FR → FR)
        target_lang = system.split("-")[0].upper() if "-" in system else system.upper()

        translated: dict[str, str] = {}
        async with httpx.AsyncClient() as client:
            for key, value in texts.items():
                resp = await client.post(
                    f"{self._base_url}/translate",
                    headers=self._headers,
                    json={
                        "text": [value],
                        "source_lang": "EN",
                        "target_lang": target_lang,
                    },
                )
                resp.raise_for_status()
                translated[key] = resp.json()["translations"][0]["text"]

        # DeepL bills per character, not per token; the API doesn't expose a
        # per-call usage block. Returning zeros documents "unknown" cleanly
        # (see ``TokenUsage`` docstring); accurate cost tracking would
        # require summing characters and applying the DeepL char rate, which
        # is out of scope for D2.
        return json.dumps(translated, ensure_ascii=False), zero_usage()

    async def evaluate(self, prompt: str) -> tuple[str, TokenUsage]:
        raise NotImplementedError("DeepL does not support evaluation")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("DeepL does not support embeddings")

    @property
    def model_id(self) -> str:
        return "deepl"

    @property
    def provider_name(self) -> str:
        return "deepl"
