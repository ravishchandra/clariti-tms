"""F6: classification of GitHub failures via `app.integrations.github.errors`.

These tests cover the wrapper layer that turns raw ``httpx`` exceptions
into the typed `GitHubRetryableError` / `GitHubPermanentError` /
`GitHubNetworkError` hierarchy that the publication endpoint consumes.

The tests deliberately don't spin up FastAPI — they prove the
classification logic in isolation (against `errors.classify_*` directly and
against `auth.get_installation_token` + `client.GitHubClient` wired to
``httpx.MockTransport``). End-to-end coverage of the publication endpoint's
HTTP response mapping is in `tests/api/test_publication_errors.py`.
"""

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.settings import get_settings
from app.integrations.github import auth as gh_auth
from app.integrations.github import errors as gh_errors
from app.integrations.github.client import GitHubClient


# ---------------------------------------------------------------------------
# classify_http_status_error
# ---------------------------------------------------------------------------


def _build_status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with a given status / headers."""
    request = httpx.Request("GET", "https://api.github.com/whatever")
    response = httpx.Response(status_code, request=request, headers=headers or {})
    return httpx.HTTPStatusError(
        f"{status_code} test", request=request, response=response
    )


class TestClassifyHttpStatusError:
    @pytest.mark.parametrize("status_code", [500, 502, 503, 504, 429])
    def test_retryable_codes_classified_as_retryable(self, status_code: int) -> None:
        exc = _build_status_error(status_code)
        result = gh_errors.classify_http_status_error(exc, context="doing X")
        assert isinstance(result, gh_errors.GitHubRetryableError)
        assert result.status_code == status_code
        # No header → fallback to the default.
        assert result.retry_after_seconds == gh_errors.DEFAULT_RETRY_AFTER_SECONDS

    def test_retry_after_header_is_honoured(self) -> None:
        exc = _build_status_error(503, headers={"Retry-After": "120"})
        result = gh_errors.classify_http_status_error(exc, context="doing X")
        assert isinstance(result, gh_errors.GitHubRetryableError)
        assert result.retry_after_seconds == 120

    def test_retry_after_header_invalid_falls_back_to_default(self) -> None:
        # GitHub *can* emit HTTP-date format for Retry-After in theory; we
        # don't parse those (the default is fine), so test that we don't
        # raise and instead fall back to the default.
        exc = _build_status_error(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        result = gh_errors.classify_http_status_error(exc, context="doing X")
        assert isinstance(result, gh_errors.GitHubRetryableError)
        assert result.retry_after_seconds == gh_errors.DEFAULT_RETRY_AFTER_SECONDS

    def test_retry_after_header_negative_clamped_to_zero(self) -> None:
        exc = _build_status_error(503, headers={"Retry-After": "-1"})
        result = gh_errors.classify_http_status_error(exc, context="doing X")
        assert isinstance(result, gh_errors.GitHubRetryableError)
        assert result.retry_after_seconds == 0

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_4xx_codes_classified_as_permanent(self, status_code: int) -> None:
        exc = _build_status_error(status_code)
        result = gh_errors.classify_http_status_error(exc, context="doing X")
        assert isinstance(result, gh_errors.GitHubPermanentError)
        assert result.status_code == status_code

    def test_context_is_embedded_in_message(self) -> None:
        exc = _build_status_error(404)
        result = gh_errors.classify_http_status_error(
            exc, context="minting installation token for installation 99"
        )
        assert "minting installation token for installation 99" in str(result)


# ---------------------------------------------------------------------------
# classify_request_error
# ---------------------------------------------------------------------------


class TestClassifyRequestError:
    def test_timeout_classified_as_network_error(self) -> None:
        request = httpx.Request("GET", "https://api.github.com/whatever")
        exc = httpx.ConnectTimeout("connect timeout", request=request)
        result = gh_errors.classify_request_error(exc, context="reaching github")
        assert isinstance(result, gh_errors.GitHubNetworkError)
        assert "reaching github" in str(result)
        assert "ConnectTimeout" in str(result)

    def test_connect_error_classified_as_network_error(self) -> None:
        request = httpx.Request("GET", "https://api.github.com/whatever")
        exc = httpx.ConnectError("DNS fail", request=request)
        result = gh_errors.classify_request_error(exc, context="reaching github")
        assert isinstance(result, gh_errors.GitHubNetworkError)
        assert "ConnectError" in str(result)


# ---------------------------------------------------------------------------
# Integration: get_installation_token wraps GitHub errors.
# Mirrors / extends the existing test_github_5xx_raises_retryable check.
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _clear_token_cache():
    gh_auth._clear_cache_for_tests()
    yield
    gh_auth._clear_cache_for_tests()


@pytest.fixture
def configured_settings(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, str]):
    private_pem, _ = rsa_keypair
    settings = get_settings()
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "12345")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", private_pem)
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", "")
    return settings


class TestGetInstallationTokenErrorClassification:
    @pytest.mark.asyncio
    async def test_404_raises_permanent_error(self, configured_settings) -> None:
        """404 means the installation id is bad (revoked / never installed).
        Surfaces as GitHubPermanentError → 422 at the endpoint.
        """
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(gh_errors.GitHubPermanentError) as exc_info:
                await gh_auth.get_installation_token(12345, http_client=client)
        assert exc_info.value.status_code == 404
        assert "installation 12345" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_401_raises_permanent_error(self, configured_settings) -> None:
        """401 means the App credentials were rejected (App revoked / key rotated)."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(gh_errors.GitHubPermanentError) as exc_info:
                await gh_auth.get_installation_token(99, http_client=client)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_502_raises_retryable_error(self, configured_settings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, headers={"Retry-After": "45"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(gh_errors.GitHubRetryableError) as exc_info:
                await gh_auth.get_installation_token(77, http_client=client)
        assert exc_info.value.status_code == 502
        assert exc_info.value.retry_after_seconds == 45

    @pytest.mark.asyncio
    async def test_429_raises_retryable_error(self, configured_settings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "60"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(gh_errors.GitHubRetryableError) as exc_info:
                await gh_auth.get_installation_token(77, http_client=client)
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after_seconds == 60

    @pytest.mark.asyncio
    async def test_network_failure_raises_network_error(self, configured_settings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns fail")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(gh_errors.GitHubNetworkError) as exc_info:
                await gh_auth.get_installation_token(88, http_client=client)
        assert "ConnectError" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Integration: GitHubClient wraps GitHub errors via _classify.
# ---------------------------------------------------------------------------


class TestGitHubClientErrorClassification:
    """Sanity: each GitHubClient method routes errors through `_classify`.

    `app.publication.service.publish_repository` instantiates `GitHubClient`
    directly and never sees the raw httpx exceptions — so any new typed
    error from GitHubClient must propagate the same hierarchy.

    These tests monkeypatch `httpx.AsyncClient` because GitHubClient builds
    its own `async with httpx.AsyncClient()` block (no DI hook).
    """

    @pytest.mark.asyncio
    async def test_get_branch_sha_500_maps_to_retryable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        transport = httpx.MockTransport(handler)
        # Patch the constructor so GitHubClient's `async with httpx.AsyncClient()`
        # picks up our mock transport.
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        client = GitHubClient(token="ghs_test")
        with pytest.raises(gh_errors.GitHubRetryableError) as exc_info:
            await client.get_branch_sha("acme/repo", "main")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_create_pull_request_404_maps_to_permanent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        client = GitHubClient(token="ghs_test")
        with pytest.raises(gh_errors.GitHubPermanentError) as exc_info:
            await client.create_pull_request(
                repo="acme/repo",
                title="x",
                body="y",
                head="feature",
                base="main",
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_branch_network_failure_maps_to_network_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timeout")

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        client = GitHubClient(token="ghs_test")
        with pytest.raises(gh_errors.GitHubNetworkError) as exc_info:
            await client.create_branch("acme/repo", "feature", "abc123")
        assert "ReadTimeout" in str(exc_info.value)
