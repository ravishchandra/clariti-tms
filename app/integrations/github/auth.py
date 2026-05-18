"""GitHub App authentication — installation access tokens.

GitHub App-authenticated API calls require a short-lived *installation access
token*, not the App-level webhook secret. The token flow:

1. Build a JSON Web Token (JWT) using the App's private key. The JWT has a
   10-minute lifetime and identifies the App (iss = GITHUB_APP_ID).
2. POST that JWT (as Bearer) to
   ``/app/installations/{installation_id}/access_tokens``.
3. GitHub returns an installation token (~1 hour lifetime) which is used as
   Bearer for all subsequent API calls on behalf of that installation.

The previous codebase mis-used ``settings.GITHUB_WEBHOOK_SECRET`` as a Bearer
token — that secret is for HMAC payload verification only and would never
authenticate a GitHub API call. This module replaces that path.

Caching: installation tokens are cached in-process by installation_id. A token
is refreshed when within ``REFRESH_BUFFER_SECONDS`` of expiry. An asyncio.Lock
serializes refreshes per installation so concurrent callers don't double-mint.

Limitations (intentional, see follow-up):
- The App's PEM private key is read from disk (or env var) in plain text.
  Encrypting it at rest with Fernet is a planned follow-up — out of scope here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

import httpx
import jwt

from app.core.settings import get_settings
from app.integrations.github.errors import (
    classify_http_status_error,
    classify_request_error,
)

logger = logging.getLogger(__name__)


# How early to refresh, in seconds, before the GitHub-reported expiry.
REFRESH_BUFFER_SECONDS = 5 * 60

# JWT lifetime sent to GitHub. GitHub allows up to 10 minutes; we use 9 to leave
# clock-skew headroom on both ends.
_APP_JWT_LIFETIME_SECONDS = 9 * 60

_GITHUB_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# Internal cache
# ---------------------------------------------------------------------------


@dataclass
class _CachedInstallationToken:
    """Cached installation token plus its absolute expiry (unix seconds)."""

    token: str
    expires_at: float


# Per-installation cache and lock. The lock prevents stampedes when multiple
# coroutines need the same installation's token simultaneously.
_token_cache: dict[int, _CachedInstallationToken] = {}
_token_locks: dict[int, asyncio.Lock] = {}


def _lock_for(installation_id: int) -> asyncio.Lock:
    """Return (creating on first use) the per-installation refresh lock."""
    lock = _token_locks.get(installation_id)
    if lock is None:
        lock = asyncio.Lock()
        _token_locks[installation_id] = lock
    return lock


# ---------------------------------------------------------------------------
# Public test/admin helpers
# ---------------------------------------------------------------------------


def _clear_cache_for_tests() -> None:
    """Drop all cached tokens. Intended for tests only."""
    _token_cache.clear()
    _token_locks.clear()


# ---------------------------------------------------------------------------
# Private key loading
# ---------------------------------------------------------------------------


def _load_private_key() -> str:
    """Return the GitHub App's PEM private key as a string.

    Precedence: ``GITHUB_APP_PRIVATE_KEY`` env var wins (used when the PEM is
    injected directly — e.g. via Vault, Kubernetes secret). If that's empty,
    fall back to reading ``GITHUB_APP_PRIVATE_KEY_PATH`` from disk.
    """
    settings = get_settings()
    inline = settings.GITHUB_APP_PRIVATE_KEY
    if inline:
        return inline

    path = Path(settings.GITHUB_APP_PRIVATE_KEY_PATH)
    if not path.is_file():
        raise RuntimeError(
            "GitHub App private key is not configured. Set GITHUB_APP_PRIVATE_KEY "
            "(PEM content) or place the PEM at GITHUB_APP_PRIVATE_KEY_PATH "
            f"(currently {path!s})."
        )
    return path.read_text()


# ---------------------------------------------------------------------------
# JWT generation
# ---------------------------------------------------------------------------


def generate_app_jwt(
    *,
    app_id: str | None = None,
    private_key: str | None = None,
    now: float | None = None,
) -> str:
    """Generate a short-lived RS256 JWT identifying the GitHub App.

    Arguments default to settings; passing them explicitly is useful for tests.

    The ``iat`` claim is set 60s in the past to absorb modest clock skew, per
    GitHub's published guidance for App JWTs.
    """
    settings = get_settings()
    app_id = app_id if app_id is not None else settings.GITHUB_APP_ID
    if not app_id:
        raise RuntimeError("GITHUB_APP_ID is not configured — cannot mint App JWT.")

    pem = private_key if private_key is not None else _load_private_key()

    now_ts = int(now if now is not None else time.time())
    payload = {
        "iat": now_ts - 60,
        "exp": now_ts + _APP_JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    token = jwt.encode(payload, pem, algorithm="RS256")
    # PyJWT 2.x returns str directly; older versions returned bytes. Normalize.
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token


# ---------------------------------------------------------------------------
# Installation token exchange
# ---------------------------------------------------------------------------


async def _exchange_jwt_for_installation_token(
    installation_id: int,
    app_jwt: str,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> _CachedInstallationToken:
    """Call GitHub's access_tokens endpoint with the App JWT.

    Returns the freshly-minted installation token plus its expiry.
    """
    url = f"{_GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient()
    # Wrap GitHub failures into the typed hierarchy from `errors.py` so the
    # publication endpoint (F6) can map them onto stable HTTP responses
    # without re-encoding the classification logic at the call site.
    context = f"minting installation token for installation {installation_id}"
    try:
        try:
            resp = await client.post(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise classify_http_status_error(exc, context=context) from exc
        except httpx.RequestError as exc:
            raise classify_request_error(exc, context=context) from exc
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    token = data["token"]
    # GitHub returns ISO-8601 e.g. "2026-05-17T18:30:00Z".
    expires_at_iso: str = data["expires_at"]
    expires_at_ts = _parse_github_timestamp(expires_at_iso)
    return _CachedInstallationToken(token=token, expires_at=expires_at_ts)


def _parse_github_timestamp(ts: str) -> float:
    """Parse a GitHub-style ISO-8601 UTC timestamp into a unix-seconds float.

    GitHub's `/app/installations/{id}/access_tokens` response returns
    `expires_at` with a `Z` suffix in current docs, but defensively handle:
      - `Z` suffix (rewritten to `+00:00` for older Python parsers)
      - explicit non-UTC offsets like `+02:00` — converted to UTC, not
        relabelled (the prior `.replace(tzinfo=utc)` mis-relabelled them
        and would have produced a time 2h skewed for non-UTC responses)
      - naive timestamps (no tz at all) — treated as UTC by GitHub convention
    """
    from datetime import datetime

    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def get_installation_token(
    installation_id: int,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Return a valid installation access token for ``installation_id``.

    Uses an in-process cache. Refreshes when within ``REFRESH_BUFFER_SECONDS``
    of expiry. Concurrent calls for the same installation_id are serialized
    via an asyncio.Lock so we don't mint two tokens in parallel.

    ``http_client`` is for testing — pass a client backed by an
    ``httpx.MockTransport`` to avoid hitting real GitHub.

    Raises ``ValueError`` if ``installation_id`` is falsy.
    """
    if not installation_id:
        raise ValueError("installation_id is required to mint a GitHub installation token")

    cached = _token_cache.get(installation_id)
    now = time.time()
    if cached is not None and cached.expires_at - now > REFRESH_BUFFER_SECONDS:
        return cached.token

    lock = _lock_for(installation_id)
    async with lock:
        # Re-check under the lock — another coroutine may have refreshed.
        cached = _token_cache.get(installation_id)
        now = time.time()
        if cached is not None and cached.expires_at - now > REFRESH_BUFFER_SECONDS:
            return cached.token

        app_jwt = generate_app_jwt()
        fresh = await _exchange_jwt_for_installation_token(installation_id, app_jwt, http_client=http_client)
        _token_cache[installation_id] = fresh
        logger.info(
            "minted github installation token for installation_id=%s (expires %ds from now)",
            installation_id,
            int(fresh.expires_at - time.time()),
        )
        return fresh.token
