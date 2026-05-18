"""Typed exception hierarchy for GitHub integration failures.

The publication endpoint (`app/api/v1/endpoints/publication.py`) needs to
classify GitHub failures into three buckets and map them onto HTTP responses
that are useful to the operator:

* **Retryable** (GitHub 5xx, 429) — a transient outage on GitHub's side.
  Surface as 503 with a ``Retry-After`` header.
* **Permanent** (401 with a revoked App, 404 for a stale installation id) —
  operator must fix configuration. Surface as 422 with a detail message that
  names which configuration is bad (e.g. "GitHub App installation 12345 not
  found — verify github_installation_id").
* **Network** (DNS / TCP / TLS failures) — surface as 503.

Per docs/11 F6 we deliberately *do not* retry in-process; publication is
operator-triggered and the operator's UI shows the result. The retry-loop
shape mirrors docs/05:52 but the failure mode here is surfaced to the
caller, not absorbed.

The hierarchy is intentionally small and flat:

    GitHubError                     (base)
    ├── GitHubRetryableError        (5xx, 429)
    ├── GitHubPermanentError        (401, 404, and other 4xx config errors)
    └── GitHubNetworkError          (no HTTP response at all)

`classify_http_status_error` is the single place that decides which subclass
a given `httpx.HTTPStatusError` maps to — keeping the rule out of every call
site.
"""

from __future__ import annotations

from typing import Final

import httpx

# Retry-After hint surfaced when GitHub returns a 429/5xx without giving us
# an explicit value. Mirrors the docs/05 retry chain default.
DEFAULT_RETRY_AFTER_SECONDS: Final[int] = 30


class GitHubError(Exception):
    """Base class for all classified GitHub integration failures."""


class GitHubRetryableError(GitHubError):
    """GitHub returned 5xx or 429 — transient, safe to retry later.

    ``retry_after_seconds`` is taken from the response's ``Retry-After``
    header when present, else falls back to ``DEFAULT_RETRY_AFTER_SECONDS``.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class GitHubPermanentError(GitHubError):
    """GitHub returned a 4xx that indicates a misconfiguration on our side.

    Retrying will not help — the operator needs to update the repository row
    or re-install the App. ``detail`` is the operator-facing message that
    will be echoed in the HTTP response body. ``status_code`` is preserved
    for logging.
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubNetworkError(GitHubError):
    """A network-level failure occurred — no HTTP response was received.

    Causes include DNS resolution failure, TCP RST, TLS handshake errors, or
    a connection / read timeout. Treated as retryable from the caller's
    perspective (operator can retry in a moment).
    """


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


_RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


def _parse_retry_after(response: httpx.Response) -> int:
    """Return a non-negative ``Retry-After`` value in seconds.

    Accepts the integer-seconds form GitHub uses for rate-limit responses.
    Falls back to ``DEFAULT_RETRY_AFTER_SECONDS`` on anything we can't parse
    cleanly (including the HTTP-date form, which GitHub does not currently
    emit for these codes).
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        value = int(raw.strip())
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS
    return max(value, 0)


def classify_http_status_error(exc: httpx.HTTPStatusError, *, context: str) -> GitHubError:
    """Map an ``httpx.HTTPStatusError`` to a classified ``GitHubError``.

    ``context`` is a short operator-facing description of the operation that
    failed (e.g. ``"minting installation token for installation 12345"``).
    It is embedded in the resulting exception message so logs and 422
    responses are actionable without the operator having to cross-reference
    a request id.
    """
    status_code = exc.response.status_code

    if status_code in _RETRYABLE_STATUS_CODES:
        return GitHubRetryableError(
            f"GitHub returned {status_code} while {context}; retry later.",
            status_code=status_code,
            retry_after_seconds=_parse_retry_after(exc.response),
        )

    # Everything else — 401 (revoked App), 404 (bad installation / repo), 403
    # (lacking permission), 422 (validation), etc. — is a configuration
    # problem on our side. Bundle status code into the message so the
    # operator doesn't have to dig through logs to find it.
    return GitHubPermanentError(
        f"GitHub returned {status_code} while {context}.",
        status_code=status_code,
    )


def classify_request_error(exc: httpx.RequestError, *, context: str) -> GitHubNetworkError:
    """Map an ``httpx.RequestError`` (no response received) to a network error."""
    # httpx.RequestError covers TimeoutException, ConnectError, ReadError,
    # WriteError, ProtocolError, ProxyError, etc. The exception class name
    # carries the most useful operator hint.
    return GitHubNetworkError(f"network failure while {context}: {type(exc).__name__}: {exc}")


__all__ = [
    "DEFAULT_RETRY_AFTER_SECONDS",
    "GitHubError",
    "GitHubNetworkError",
    "GitHubPermanentError",
    "GitHubRetryableError",
    "classify_http_status_error",
    "classify_request_error",
]
