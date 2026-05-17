from __future__ import annotations

import openai

from app.llm.protocol import LLMProviderBase


class OpenAIProvider(LLMProviderBase):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    async def evaluate(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

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
