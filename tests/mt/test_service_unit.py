"""Pure-Python unit tests for ``app.mt.service`` helpers.

No DB, no LLM, no network. Lives alongside ``test_pipeline.py`` so the same
``pytest`` invocation picks both up.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from app.mt.errors import TranslationError
from app.mt.service import _RETRYABLE_HTTP_STATUS, _cost_from_usage, _is_retryable


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


class TestCostFromUsage:
    """D2 — cost is real-tokens × provider-price, not word-count estimates."""

    def _provider(self, in_price: float, out_price: float) -> MagicMock:
        p = MagicMock()
        p.price_per_1k_input = in_price
        p.price_per_1k_output = out_price
        return p

    def test_anthropic_shaped_pricing(self) -> None:
        # 1000 input @ $0.003 + 500 output @ $0.015 = $0.003 + $0.0075 = $0.0105
        provider = self._provider(0.003, 0.015)
        cost = _cost_from_usage(
            provider, {"input_tokens": 1000, "output_tokens": 500}
        )
        assert cost == 0.0105

    def test_zero_usage_returns_zero(self) -> None:
        provider = self._provider(0.003, 0.015)
        cost = _cost_from_usage(provider, {"input_tokens": 0, "output_tokens": 0})
        assert cost == 0.0

    def test_zero_pricing_returns_zero(self) -> None:
        # Ollama / DeepL / OpenRouter: price 0.0 → cost 0.0 regardless of
        # tokens. Documents the "unknown / not billed per token" branch.
        provider = self._provider(0.0, 0.0)
        cost = _cost_from_usage(
            provider, {"input_tokens": 5000, "output_tokens": 2000}
        )
        assert cost == 0.0

    def test_rounded_to_six_decimals(self) -> None:
        # 1 token @ $0.003/1K = 0.000003 (already 6-decimal). Verifies no
        # precision drift sneaks in across the multiplication.
        provider = self._provider(0.003, 0.015)
        cost = _cost_from_usage(provider, {"input_tokens": 1, "output_tokens": 0})
        assert cost == 0.000003
