from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable

import httpx

from app.integrations.github.errors import (
    classify_http_status_error,
    classify_request_error,
)


async def _classify[T](context: str, op: Callable[[], Awaitable[T]]) -> T:
    """Run ``op`` and re-raise any httpx error as a typed ``GitHubError``.

    Single point where the raw ``httpx`` exceptions are turned into the
    `errors.GitHubRetryableError` / `GitHubPermanentError` / `GitHubNetworkError`
    types the publication endpoint understands. ``context`` is an
    operator-facing short description embedded in the resulting message.
    """
    try:
        return await op()
    except httpx.HTTPStatusError as exc:
        raise classify_http_status_error(exc, context=context) from exc
    except httpx.RequestError as exc:
        raise classify_request_error(exc, context=context) from exc


class GitHubClient:
    _BASE = "https://api.github.com"

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_file_content(self, repo: str, path: str, ref: str = "main") -> str:
        url = f"{self._BASE}/repos/{repo}/contents/{path}"

        async def _do() -> str:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers, params={"ref": ref})
                resp.raise_for_status()
                data = resp.json()
                return base64.b64decode(data["content"]).decode("utf-8")

        return await _classify(f"fetching {path} from {repo}@{ref}", _do)

    async def get_branch_sha(self, repo: str, branch: str) -> str:
        url = f"{self._BASE}/repos/{repo}/git/ref/heads/{branch}"

        async def _do() -> str:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                return resp.json()["object"]["sha"]

        return await _classify(f"resolving branch {branch} on {repo}", _do)

    async def create_branch(self, repo: str, branch: str, base_sha: str) -> None:
        url = f"{self._BASE}/repos/{repo}/git/refs"

        async def _do() -> None:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._headers,
                    json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                )
                resp.raise_for_status()

        await _classify(f"creating branch {branch} on {repo}", _do)

    async def upsert_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> None:
        url = f"{self._BASE}/repos/{repo}/contents/{path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        body: dict = {"message": message, "content": encoded, "branch": branch}

        async def _do() -> None:
            # Fetch current SHA if file exists (required for updates).
            async with httpx.AsyncClient() as client:
                check = await client.get(url, headers=self._headers, params={"ref": branch})
                if check.status_code == 200:
                    body["sha"] = check.json()["sha"]
                resp = await client.put(url, headers=self._headers, json=body)
                resp.raise_for_status()

        await _classify(f"upserting {path} on {repo}@{branch}", _do)

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> str:
        url = f"{self._BASE}/repos/{repo}/pulls"

        async def _do() -> str:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._headers,
                    json={"title": title, "body": body, "head": head, "base": base},
                )
                resp.raise_for_status()
                return resp.json()["html_url"]

        return await _classify(f"opening pull request {head}->{base} on {repo}", _do)
