"""Pure-Python unit tests for ``app.mt.service`` helpers.

No DB, no LLM, no network. Lives alongside ``test_pipeline.py`` so the same
``pytest`` invocation picks both up.
"""

from __future__ import annotations

import httpx

from app.mt.errors import TranslationError
from app.mt.service import _RETRYABLE_HTTP_STATUS, _is_retryable


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "http://example/x")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


class TestIsRetryable:
    def test_translation_error_is_retryable(self) -> None:
        assert _is_retryable(TranslationError("boom")) is True

    def test_request_error_is_retryable(self) -> None:
        # ConnectError is a subclass of RequestError — represents network errors.
        assert _is_retryable(httpx.ConnectError("refused")) is True

    def test_retryable_http_status_codes(self) -> None:
        for status in _RETRYABLE_HTTP_STATUS:
            assert _is_retryable(_http_status_error(status)) is True, status

    def test_4xx_client_errors_not_retryable(self) -> None:
        assert _is_retryable(_http_status_error(400)) is False
        assert _is_retryable(_http_status_error(401)) is False
        assert _is_retryable(_http_status_error(403)) is False
        assert _is_retryable(_http_status_error(404)) is False

    def test_unexpected_exceptions_not_retryable(self) -> None:
        assert _is_retryable(ValueError("nope")) is False
        assert _is_retryable(RuntimeError("nope")) is False
        # NotImplementedError covers e.g. DeepL.evaluate() being invoked by
        # accident — we don't want infinite retries on that.
        assert _is_retryable(NotImplementedError("nope")) is False
