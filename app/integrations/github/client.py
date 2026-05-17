from __future__ import annotations

import base64

import httpx


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
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, params={"ref": ref})
            resp.raise_for_status()
            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8")

    async def get_branch_sha(self, repo: str, branch: str) -> str:
        url = f"{self._BASE}/repos/{repo}/git/ref/heads/{branch}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            return resp.json()["object"]["sha"]

    async def create_branch(self, repo: str, branch: str, base_sha: str) -> None:
        url = f"{self._BASE}/repos/{repo}/git/refs"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers=self._headers,
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
            resp.raise_for_status()

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

        # Fetch current SHA if file exists (required for updates).
        async with httpx.AsyncClient() as client:
            check = await client.get(url, headers=self._headers, params={"ref": branch})
            if check.status_code == 200:
                body["sha"] = check.json()["sha"]
            resp = await client.put(url, headers=self._headers, json=body)
            resp.raise_for_status()

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> str:
        url = f"{self._BASE}/repos/{repo}/pulls"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers=self._headers,
                json={"title": title, "body": body, "head": head, "base": base},
            )
            resp.raise_for_status()
            return resp.json()["html_url"]
