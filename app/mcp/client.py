"""HTTP client wrapper for the ClaritiTMS REST API.

Reads `CLARITI_API_URL` and `CLARITI_API_KEY` from the environment.
Each MCP tool call is a single REST call (or a small fixed batch);
the client is constructed once per server process and reused.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class ClaritiClientError(RuntimeError):
    """Raised when the REST API returns an error response.

    The MCP server catches this and surfaces `message` as the tool's
    error text — keeping the agent's view structured and short.
    """

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class ClaritiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        url = base_url or os.environ.get("CLARITI_API_URL", "http://localhost:8000")
        key = api_key or os.environ.get("CLARITI_API_KEY")
        if not key:
            raise RuntimeError(
                "CLARITI_API_KEY is required. Set it in the MCP server's "
                "environment (see docs/13-agent-integration.md)."
            )
        self._base = url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base}/api/v1",
            headers={"X-API-Key": key, "Accept": "application/json"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        resp = await self._client.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                message = body.get("detail", resp.text) if isinstance(body, dict) else resp.text
            except ValueError:
                body = resp.text
                message = resp.text
            raise ClaritiClientError(resp.status_code, message, body)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json=json)
