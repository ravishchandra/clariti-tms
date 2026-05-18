from __future__ import annotations

import httpx

from app.llm.protocol import LLMProviderBase, TokenUsage


class OllamaProvider(LLMProviderBase):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        embed_model: str = "nomic-embed-text",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._embed_model = embed_model

    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> tuple[str, TokenUsage]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"], _extract_usage(data)
        except httpx.ConnectError:
            raise ConnectionError(f"Ollama not running at {self._base_url}")

    async def evaluate(self, prompt: str) -> tuple[str, TokenUsage]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"], _extract_usage(data)
        except httpx.ConnectError:
            raise ConnectionError(f"Ollama not running at {self._base_url}")

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={
                        "model": self._embed_model,
                        "prompt": text,
                    },
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
        except httpx.ConnectError:
            raise ConnectionError(f"Ollama not running at {self._base_url}")

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"


def _extract_usage(payload: dict) -> TokenUsage:
    """Pull token counts off an Ollama ``/api/chat`` response body.

    Ollama returns ``prompt_eval_count`` (input tokens) and ``eval_count``
    (output tokens) at the top level of the JSON response when the model
    runner reports them. Some local model setups omit these — we default
    to zero so usage stays consistent with the "unknown" semantics from
    ``TokenUsage`` rather than raising. Cost remains under-counted in
    that case, which matches reality: Ollama is local and unbilled.
    """
    return {
        "input_tokens": int(payload.get("prompt_eval_count", 0) or 0),
        "output_tokens": int(payload.get("eval_count", 0) or 0),
    }
