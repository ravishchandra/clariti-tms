"""F6: publication endpoint maps classified GitHub errors to HTTP responses.

These tests exercise the FastAPI endpoint directly via `httpx.ASGITransport`
and override the dependencies (`ScopedRepository`, `DB`) so no Postgres is
required — every dependency is faked in-process. The objective is to lock
down the response shape:

  * `GitHubRetryableError` from `get_installation_token` → 503 + `Retry-After`
  * `GitHubPermanentError` (404)                         → 422 + actionable detail
  * `GitHubPermanentError` (401)                         → 422 + actionable detail
  * `GitHubNetworkError`                                 → 503 (no header)
  * `GitHubRetryableError` from `publish_repository`     → 503 + `Retry-After`
  * `GitHubPermanentError` from `publish_repository`     → 422 + actionable detail
  * `RuntimeError` from `get_installation_token`         → 503 (existing behaviour)

Tests are alphabetically organized by failure mode for easy navigation.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import scoped_repository
from app.api.v1.endpoints import publication as publication_endpoint
from app.api.v1.endpoints.publication import router as publication_router
from app.core.database import get_db
from app.integrations.github.errors import (
    GitHubNetworkError,
    GitHubPermanentError,
    GitHubRetryableError,
)

# Capture the real symbols once at import time so the autouse fixture can
# restore them regardless of any prior monkeypatching.
_REAL_GET_INSTALLATION_TOKEN = publication_endpoint.get_installation_token
_REAL_PUBLISH_REPOSITORY = publication_endpoint.publish_repository


# ---------------------------------------------------------------------------
# Fake dependencies
# ---------------------------------------------------------------------------


class _FakeRepository:
    """Just enough of Repository for the publication endpoint to work."""

    def __init__(
        self,
        *,
        github_repo: str | None = "acme/example",
        github_installation_id: int | None = 12345,
    ) -> None:
        self.id = uuid.uuid4()
        self.github_repo = github_repo
        self.github_installation_id = github_installation_id


def _build_app(
    repo: _FakeRepository,
    *,
    install_token_side_effect: Any = "ghs_dummy",
    publish_side_effect: Any = "https://github.com/acme/example/pull/1",
) -> FastAPI:
    """Build a FastAPI app with publication router and the GitHub helpers stubbed.

    `install_token_side_effect` and `publish_side_effect` are either return
    values or callables. If a callable, called with the same args as the
    real function and its result is returned/raised. To raise, return an
    Exception instance from the callable, or simply set it to an Exception
    instance — the helper raises it.
    """

    async def _override_scoped_repository() -> _FakeRepository:
        return repo

    async def _override_get_db() -> AsyncIterator[None]:
        yield None

    async def _fake_get_installation_token(installation_id: int, **kwargs: Any) -> str:
        if isinstance(install_token_side_effect, Exception):
            raise install_token_side_effect
        if callable(install_token_side_effect):
            result = install_token_side_effect(installation_id)
            if isinstance(result, Exception):
                raise result
            return result
        return install_token_side_effect

    async def _fake_publish_repository(db: Any, repository: Any, github_token: str) -> str | None:
        if isinstance(publish_side_effect, Exception):
            raise publish_side_effect
        if callable(publish_side_effect):
            result = publish_side_effect(repository, github_token)
            if isinstance(result, Exception):
                raise result
            return result
        return publish_side_effect

    app = FastAPI()
    app.include_router(publication_router, prefix="/api/v1")
    app.dependency_overrides[scoped_repository] = _override_scoped_repository
    app.dependency_overrides[get_db] = _override_get_db
    # The publication module imports `get_installation_token` and
    # `publish_repository` at module load; monkeypatch the symbols it sees.
    publication_endpoint.get_installation_token = _fake_get_installation_token  # type: ignore[assignment]
    publication_endpoint.publish_repository = _fake_publish_repository  # type: ignore[assignment]
    return app


@pytest.fixture(autouse=True)
def _restore_publication_globals():
    """Restore the module's real symbols after each test."""
    yield
    publication_endpoint.get_installation_token = _REAL_GET_INSTALLATION_TOKEN  # type: ignore[assignment]
    publication_endpoint.publish_repository = _REAL_PUBLISH_REPOSITORY  # type: ignore[assignment]


async def _client_for(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# install-token classification → HTTP response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_token_retryable_returns_503_with_retry_after() -> None:
    repo = _FakeRepository()
    app = _build_app(
        repo,
        install_token_side_effect=GitHubRetryableError(
            "GitHub returned 502 while minting installation token",
            status_code=502,
            retry_after_seconds=45,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503, resp.text
    assert resp.headers.get("Retry-After") == "45"
    assert "502" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_install_token_404_returns_422_with_installation_id() -> None:
    repo = _FakeRepository(github_installation_id=12345)
    app = _build_app(
        repo,
        install_token_side_effect=GitHubPermanentError(
            "GitHub returned 404 while minting installation token",
            status_code=404,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # Operator-actionable message: name the installation id and the column.
    assert "12345" in detail
    assert "github_installation_id" in detail


@pytest.mark.asyncio
async def test_install_token_401_returns_422_with_app_credentials_hint() -> None:
    repo = _FakeRepository(github_installation_id=42)
    app = _build_app(
        repo,
        install_token_side_effect=GitHubPermanentError(
            "GitHub returned 401 while minting installation token",
            status_code=401,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "GITHUB_APP_ID" in detail or "GITHUB_APP_PRIVATE_KEY" in detail
    assert "42" in detail


@pytest.mark.asyncio
async def test_install_token_network_error_returns_503_without_retry_after() -> None:
    repo = _FakeRepository()
    app = _build_app(
        repo,
        install_token_side_effect=GitHubNetworkError(
            "network failure while minting installation token: ConnectError: dns fail"
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503, resp.text
    assert "Retry-After" not in resp.headers
    assert "network failure" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_install_token_runtime_error_returns_503_unchanged() -> None:
    """Pre-existing behaviour: RuntimeError from misconfigured App still maps to 503."""
    repo = _FakeRepository()
    app = _build_app(
        repo,
        install_token_side_effect=RuntimeError("GITHUB_APP_ID is not configured"),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503, resp.text
    assert "GITHUB_APP_ID" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# publish_repository classification → HTTP response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_retryable_returns_503_with_retry_after() -> None:
    repo = _FakeRepository()
    app = _build_app(
        repo,
        publish_side_effect=GitHubRetryableError(
            "GitHub returned 503 while opening pull request",
            status_code=503,
            retry_after_seconds=15,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503, resp.text
    assert resp.headers.get("Retry-After") == "15"


@pytest.mark.asyncio
async def test_publish_403_returns_422_with_permissions_hint() -> None:
    repo = _FakeRepository(github_installation_id=12345)
    app = _build_app(
        repo,
        publish_side_effect=GitHubPermanentError(
            "GitHub returned 403 while opening pull request",
            status_code=403,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # Surface enough hint for the operator to fix the App permissions.
    assert "contents:write" in detail or "pull-requests:write" in detail
    assert "12345" in detail


@pytest.mark.asyncio
async def test_publish_404_returns_422_with_repo_or_app_hint() -> None:
    repo = _FakeRepository(github_installation_id=12345)
    app = _build_app(
        repo,
        publish_side_effect=GitHubPermanentError(
            "GitHub returned 404 while opening pull request",
            status_code=404,
        ),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "github_repo" in detail or "installed" in detail
    assert "12345" in detail


@pytest.mark.asyncio
async def test_publish_network_error_returns_503() -> None:
    repo = _FakeRepository()
    app = _build_app(
        repo,
        publish_side_effect=GitHubNetworkError("network failure while opening pull request: ConnectError: dns fail"),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503, resp.text
    assert "Retry-After" not in resp.headers


# ---------------------------------------------------------------------------
# Happy path: success still works.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_pr_url() -> None:
    repo = _FakeRepository()
    app = _build_app(
        repo,
        install_token_side_effect="ghs_dummy",
        publish_side_effect="https://github.com/acme/example/pull/42",
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "status": "ok",
        "pr_url": "https://github.com/acme/example/pull/42",
    }


@pytest.mark.asyncio
async def test_no_op_when_publish_returns_none() -> None:
    repo = _FakeRepository()
    app = _build_app(repo, publish_side_effect=None)
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "no_op"
    assert payload["pr_url"] is None


# ---------------------------------------------------------------------------
# Pre-condition checks unrelated to GitHub still take effect.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_github_repo_returns_422_before_calling_github() -> None:
    repo = _FakeRepository(github_repo=None)
    # If we ever called the token mint, this exception would surface — assert
    # we never get there.
    app = _build_app(
        repo,
        install_token_side_effect=RuntimeError("should not have been called"),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 422
    assert "GitHub integration" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_missing_installation_id_returns_503_before_calling_github() -> None:
    repo = _FakeRepository(github_installation_id=None)
    app = _build_app(
        repo,
        install_token_side_effect=RuntimeError("should not have been called"),
    )
    async with await _client_for(app) as client:
        resp = await client.post(f"/api/v1/repositories/{repo.id}/publish")

    assert resp.status_code == 503
    assert "github_installation_id" in resp.json()["detail"]
