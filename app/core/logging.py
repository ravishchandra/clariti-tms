"""Structured JSON logging for ClaritiTMS.

Per ``CLAUDE.md`` the project emits structured JSON logs and always
includes ``project_id``, ``translation_id``, and ``request_id`` where
they are available.  This module provides a tiny, stdlib-only helper
(no new dependency) that other modules can adopt incrementally.

Public API
----------
``configure_logging(level="INFO")``
    Idempotent root-logger setup that installs a JSON ``StreamHandler``
    on stderr.  Safe to call from process startup; subsequent calls do
    not stack handlers.

``bind(**fields)``
    Context manager that pushes arbitrary fields into a
    :class:`contextvars.ContextVar`.  Every ``logger.info(...)`` (or
    any other level) emitted inside the block automatically attaches
    those fields to the JSON record.  Reentrant; nested ``bind``
    blocks merge their fields with the outer scope and restore on
    exit.  Built on ``contextvars`` so it is safe across ``asyncio``
    tasks.

``get_request_id() -> str``
    Returns the request id from the current context.  If none is
    bound, a fresh ``uuid4().hex`` is generated and returned (but not
    persisted into the context — that is the middleware's job).

``request_id_middleware(app)``
    Adds a FastAPI/Starlette middleware that reads the inbound
    ``X-Request-ID`` header (or mints one), binds it for the duration
    of the request, and echoes it back on the response.

Recommended patterns
--------------------

In a FastAPI endpoint — the middleware has already bound
``request_id``, so just attach the per-call ids on ``extra``::

    @router.post("/translations/{tid}/approve")
    async def approve(tid: UUID, project_id: UUID = ...):
        logger.info(
            "translation.approve",
            extra={"project_id": str(project_id), "translation_id": str(tid)},
        )

In a long-running worker / background job, scope a block of
related work with ``bind``::

    with bind(project_id=str(pid), batch_id=str(bid)):
        logger.info("batch.start")
        ...  # any logs in here carry project_id + batch_id automatically
        logger.info("batch.done")

In service code that already has the ids in scope, pass them as
``extra`` directly — there is no need to ``bind`` for a single line::

    logger.info("mt.run.completed", extra={"translation_id": str(tid)})

Operator hygiene
----------------

This formatter does not filter fields. Anything passed via ``extra=`` or
bound via ``bind(...)`` lands in the JSON output verbatim. Do not pass
API keys, passwords, decrypted secrets, raw user content, or PII as
``extra`` fields — log structured *identifiers* (ids, hashes) and short
event names. Add log-shipping side filters if your platform handles PII
at the sink.

JSON record shape::

    {"ts": "2026-05-17T10:11:12.345678+00:00",
     "level": "INFO",
     "logger": "app.main",
     "msg": "app.startup",
     "project_id": "...",
     "request_id": "..."}
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "configure_logging",
    "bind",
    "get_request_id",
    "request_id_middleware",
    "JsonFormatter",
    "REQUEST_ID_HEADER",
]

REQUEST_ID_HEADER = "X-Request-ID"

# Context variable holding the merged dict of fields bound for the
# current task / request.  Always a plain dict — never None.
_context_fields: ContextVar[dict[str, Any]] = ContextVar("clariti_log_context", default={})

# Standard LogRecord attributes we *don't* want to copy into the JSON
# record's extra fields.  Anything else attached via ``extra=`` (or via
# ``bind``) is included.
_LOG_RECORD_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "asctime",
        "taskName",
        "message",
    }
)


class JsonFormatter(logging.Formatter):
    """Emit a single-line JSON object per log record.

    Always includes ``ts`` (ISO-8601 UTC), ``level``, ``logger``, and
    ``msg``.  Merges in fields from the ``bind()`` context first, then
    any ``extra=`` passed at the call site (call-site wins on
    conflict).  Exception info, if present, is rendered to a ``exc``
    string field.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Bound context first — call-site extras can override.
        for k, v in _context_fields.get().items():
            payload[k] = v

        # Anything set on the record that isn't a standard attribute is
        # treated as user-provided extra.
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_RESERVED or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        try:
            return json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            # Fall back to a safe repr — never raise from a logger.
            safe = {k: repr(v) for k, v in payload.items()}
            return json.dumps(safe, ensure_ascii=False)


# Sentinel attribute we stamp on our handler so ``configure_logging``
# can recognise it across re-imports / repeated calls.
_HANDLER_MARKER = "_clariti_json_handler"


def configure_logging(level: str = "INFO") -> None:
    """Install a JSON handler on the root logger.  Idempotent.

    Safe to call multiple times — subsequent calls only update the
    log level on the existing handler instead of adding a duplicate.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            handler.setLevel(level)
            return

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)


@contextlib.contextmanager
def bind(**fields: Any) -> Iterator[None]:
    """Push ``fields`` into the logging context for the duration of the block.

    Nested calls merge with the outer scope rather than replacing it.
    On exit, the previous mapping is restored exactly (so siblings
    don't leak into each other).
    """
    current = _context_fields.get()
    merged = {**current, **fields}
    token = _context_fields.set(merged)
    try:
        yield
    finally:
        _context_fields.reset(token)


def get_request_id() -> str:
    """Return the bound request id, or a freshly generated uuid4 hex."""
    rid = _context_fields.get().get("request_id")
    if isinstance(rid, str) and rid:
        return rid
    return uuid.uuid4().hex


def request_id_middleware(app: Any) -> None:
    """Register a request-id middleware on a FastAPI/Starlette app.

    Reads ``X-Request-ID`` from the incoming request (or mints a new
    uuid4 hex), binds it to the logging context for the duration of
    the request, and echoes the same value back on the response.
    """

    @app.middleware("http")
    async def _request_id_mw(request: Any, call_next: Any) -> Any:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        rid = incoming if (isinstance(incoming, str) and incoming) else uuid.uuid4().hex
        with bind(request_id=rid):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
