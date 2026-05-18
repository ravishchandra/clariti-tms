"""Custom exceptions raised by the MT pipeline.

Defined separately so providers and the service layer can both import from a
neutral module without circular imports.
"""

from __future__ import annotations


class TranslationError(Exception):
    """Provider-level transient failure.

    Raised (or matched against) when an LLM call fails in a way that is worth
    retrying or falling back from — e.g. malformed output, transient API
    errors, timeouts. The MT service retries once and then falls back to the
    next provider in the configured chain (see ``app.llm.registry``).

    Note: ``httpx.HTTPStatusError`` (with a retryable status) and
    ``httpx.RequestError`` (network errors) are also treated as retryable in
    ``app/mt/service.py``; this exception exists so provider implementations
    can wrap their own failure modes (e.g. JSON parse errors that should
    trigger a retry) without forcing httpx semantics on every provider.
    """
