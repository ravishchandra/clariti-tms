"""Tests for app.integrations.github.auth — JWT minting + installation tokens.

These tests do NOT hit real GitHub. They use ``httpx.MockTransport`` to intercept
requests, and they generate a throwaway RSA keypair so tests are hermetic.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.settings import get_settings
from app.integrations.github import auth as gh_auth


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_keypair() -> tuple[str, str]:
    """Generate a throwaway RSA-2048 keypair (PEM strings) for the test."""
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
    """Reset the per-installation token cache between tests."""
    gh_auth._clear_cache_for_tests()
    yield
    gh_auth._clear_cache_for_tests()


@pytest.fixture
def configured_settings(monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, str]):
    """Inject a working App ID + private key into Settings."""
    private_pem, _public_pem = rsa_keypair
    settings = get_settings()
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "123456")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", private_pem)
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", "")
    return settings


def _expires_at_iso(seconds_from_now: int) -> str:
    """ISO-8601 UTC timestamp ``seconds_from_now`` in the future."""
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)
    # GitHub returns "...Z" without microseconds; mimic that.
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# JWT generation
# ---------------------------------------------------------------------------


class TestGenerateAppJwt:
    def test_produces_valid_rs256_jwt_with_expected_claims(
        self, rsa_keypair: tuple[str, str]
    ) -> None:
        private_pem, public_pem = rsa_keypair
        now = 1_700_000_000

        token = gh_auth.generate_app_jwt(
            app_id="987654", private_key=private_pem, now=now
        )

        # Header advertises RS256.
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"

        # Signature verifies with the public half; claims match what we sent.
        # `verify_exp=False` because we deliberately froze `now` to a past
        # instant (`1_700_000_000`) to make claim values deterministic — the
        # wall-clock exp check is irrelevant here.
        decoded = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        assert decoded["iss"] == "987654"
        assert decoded["iat"] == now - 60  # 60s clock-skew buffer
        assert decoded["exp"] == now + 9 * 60  # 9-minute lifetime

    def test_missing_app_id_raises(self, rsa_keypair: tuple[str, str]) -> None:
        private_pem, _ = rsa_keypair
        with pytest.raises(RuntimeError, match="GITHUB_APP_ID"):
            gh_auth.generate_app_jwt(app_id="", private_key=private_pem)


# ---------------------------------------------------------------------------
# Private key loading precedence
# ---------------------------------------------------------------------------


class TestLoadPrivateKey:
    def test_env_var_wins_over_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        rsa_keypair: tuple[str, str],
        tmp_path,
    ) -> None:
        private_pem, _ = rsa_keypair
        # Path points at a non-existent file — should be ignored.
        bad_path = tmp_path / "nope.pem"
        settings = get_settings()
        monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", private_pem)
        monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", str(bad_path))

        assert gh_auth._load_private_key() == private_pem

    def test_falls_back_to_path_when_env_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        rsa_keypair: tuple[str, str],
        tmp_path,
    ) -> None:
        private_pem, _ = rsa_keypair
        pem_file = tmp_path / "app.pem"
        pem_file.write_text(private_pem)

        settings = get_settings()
        monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
        monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", str(pem_file))

        assert gh_auth._load_private_key() == private_pem

    def test_missing_both_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
        monkeypatch.setattr(
            settings, "GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem")
        )
        with pytest.raises(RuntimeError, match="GitHub App private key is not configured"):
            gh_auth._load_private_key()


# ---------------------------------------------------------------------------
# get_installation_token — caching, refresh, JWT-as-bearer, failure paths
# ---------------------------------------------------------------------------


class TestGetInstallationToken:
    @pytest.mark.asyncio
    async def test_sends_jwt_as_bearer_and_returns_token(
        self, configured_settings, rsa_keypair: tuple[str, str]
    ) -> None:
        _private_pem, public_pem = rsa_keypair
        seen_auth: list[str] = []
        seen_url: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_url.append(str(request.url))
            seen_auth.append(request.headers["Authorization"])
            return httpx.Response(
                201,
                json={"token": "ghs_installtoken_abc", "expires_at": _expires_at_iso(3600)},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            token = await gh_auth.get_installation_token(7777, http_client=client)

        assert token == "ghs_installtoken_abc"
        assert seen_url == [
            "https://api.github.com/app/installations/7777/access_tokens"
        ]
        assert len(seen_auth) == 1
        assert seen_auth[0].startswith("Bearer ")

        # The Bearer value should be a valid RS256 App JWT we can verify.
        sent_jwt = seen_auth[0].removeprefix("Bearer ")
        decoded = jwt.decode(sent_jwt, public_pem, algorithms=["RS256"])
        assert decoded["iss"] == "123456"

    @pytest.mark.asyncio
    async def test_caches_token_across_calls(self, configured_settings) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                201,
                json={
                    "token": f"ghs_token_{call_count}",
                    "expires_at": _expires_at_iso(3600),
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            t1 = await gh_auth.get_installation_token(42, http_client=client)
            t2 = await gh_auth.get_installation_token(42, http_client=client)
            t3 = await gh_auth.get_installation_token(42, http_client=client)

        assert t1 == t2 == t3 == "ghs_token_1"
        assert call_count == 1  # One mint, two cache hits.

    @pytest.mark.asyncio
    async def test_refreshes_when_within_buffer(self, configured_settings) -> None:
        """Tokens within REFRESH_BUFFER_SECONDS of expiry must be refreshed."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # First call: token expires in 60s (well inside the 5-minute buffer).
            # Second call: token expires in 1 hour.
            ttl = 60 if call_count == 1 else 3600
            return httpx.Response(
                201,
                json={
                    "token": f"ghs_token_{call_count}",
                    "expires_at": _expires_at_iso(ttl),
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            t1 = await gh_auth.get_installation_token(99, http_client=client)
            t2 = await gh_auth.get_installation_token(99, http_client=client)

        assert t1 == "ghs_token_1"
        assert t2 == "ghs_token_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_installations_get_separate_tokens(
        self, configured_settings
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Extract installation id from URL path: /app/installations/{id}/...
            install_id = request.url.path.split("/")[3]
            return httpx.Response(
                201,
                json={
                    "token": f"ghs_install_{install_id}",
                    "expires_at": _expires_at_iso(3600),
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            ta = await gh_auth.get_installation_token(111, http_client=client)
            tb = await gh_auth.get_installation_token(222, http_client=client)

        assert ta == "ghs_install_111"
        assert tb == "ghs_install_222"

    @pytest.mark.asyncio
    async def test_missing_installation_id_raises(self, configured_settings) -> None:
        with pytest.raises(ValueError, match="installation_id is required"):
            await gh_auth.get_installation_token(0)
        with pytest.raises(ValueError, match="installation_id is required"):
            await gh_auth.get_installation_token(None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_github_5xx_raises(self, configured_settings) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await gh_auth.get_installation_token(55, http_client=client)


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


class TestParseGithubTimestamp:
    def test_handles_z_suffix(self) -> None:
        ts = "2026-05-17T18:30:00Z"
        parsed = gh_auth._parse_github_timestamp(ts)
        # 2026-05-17T18:30:00Z in unix seconds.
        expected = datetime(2026, 5, 17, 18, 30, 0, tzinfo=timezone.utc).timestamp()
        assert parsed == pytest.approx(expected, abs=1.0)

    def test_handles_offset_suffix(self) -> None:
        ts = "2026-05-17T18:30:00+00:00"
        parsed = gh_auth._parse_github_timestamp(ts)
        expected = datetime(2026, 5, 17, 18, 30, 0, tzinfo=timezone.utc).timestamp()
        assert parsed == pytest.approx(expected, abs=1.0)
