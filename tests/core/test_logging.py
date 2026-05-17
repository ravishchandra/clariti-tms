"""Tests for ``app.core.logging``."""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import logging as clariti_logging
from app.core.logging import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    bind,
    configure_logging,
    get_request_id,
    request_id_middleware,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capture_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    """Return a logger wired to a fresh StringIO with the JSON formatter.

    Bypasses the root logger so tests don't fight with handlers
    installed by ``configure_logging`` elsewhere in the test suite.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger(name)
    # Reset on each call so we don't accumulate handlers.
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, buf


def _last_record(buf: io.StringIO) -> dict:
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert lines, "expected at least one log line, got none"
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_idempotent_does_not_stack_handlers(self) -> None:
        root = logging.getLogger()
        # Snapshot pre-existing handler count so we don't depend on
        # other test files' state.
        before = len(root.handlers)
        configure_logging("INFO")
        after_first = len(root.handlers)
        configure_logging("INFO")
        configure_logging("DEBUG")
        after_third = len(root.handlers)

        # First call may add 0 (already configured) or 1 handler.
        assert after_first - before in (0, 1)
        # Subsequent calls must not add more handlers.
        assert after_third == after_first

    def test_updates_level_on_repeat_call(self) -> None:
        configure_logging("INFO")
        configure_logging("WARNING")
        root = logging.getLogger()
        # The clariti handler should be at WARNING after the second call.
        clariti_handlers = [
            h for h in root.handlers if getattr(h, "_clariti_json_handler", False)
        ]
        assert clariti_handlers, "expected at least one clariti json handler"
        assert clariti_handlers[-1].level == logging.WARNING


# ---------------------------------------------------------------------------
# JSON formatter output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_record_has_required_keys(self) -> None:
        logger, buf = _make_capture_logger("test.json.required")
        logger.info("hello world")
        record = _last_record(buf)
        for key in ("ts", "level", "logger", "msg"):
            assert key in record, f"missing {key!r} in {record!r}"
        assert record["level"] == "INFO"
        assert record["logger"] == "test.json.required"
        assert record["msg"] == "hello world"

    def test_ts_is_iso_utc(self) -> None:
        logger, buf = _make_capture_logger("test.json.ts")
        logger.info("tick")
        record = _last_record(buf)
        # ISO-8601 with offset.  Stdlib will accept it back.
        parsed = datetime.fromisoformat(record["ts"])
        offset = parsed.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0

    def test_extra_fields_included(self) -> None:
        logger, buf = _make_capture_logger("test.json.extra")
        logger.info("with extras", extra={"project_id": "abc", "n": 7})
        record = _last_record(buf)
        assert record["project_id"] == "abc"
        assert record["n"] == 7

    def test_unserialisable_extra_does_not_crash(self) -> None:
        class Weird:
            def __repr__(self) -> str:
                return "<Weird>"

        logger, buf = _make_capture_logger("test.json.weird")
        logger.info("oddball", extra={"obj": Weird()})
        record = _last_record(buf)
        assert "obj" in record


# ---------------------------------------------------------------------------
# bind() context manager
# ---------------------------------------------------------------------------


class TestBind:
    def test_fields_present_inside_block_absent_outside(self) -> None:
        logger, buf = _make_capture_logger("test.bind.basic")

        logger.info("before")
        with bind(project_id="p1"):
            logger.info("inside")
        logger.info("after")

        lines = [
            json.loads(line) for line in buf.getvalue().splitlines() if line.strip()
        ]
        assert len(lines) == 3
        assert "project_id" not in lines[0]
        assert lines[1]["project_id"] == "p1"
        assert "project_id" not in lines[2]

    def test_nested_binds_merge(self) -> None:
        logger, buf = _make_capture_logger("test.bind.nested")
        with bind(project_id="p1"):
            with bind(translation_id="t1"):
                logger.info("inner")
            logger.info("outer")

        lines = [
            json.loads(line) for line in buf.getvalue().splitlines() if line.strip()
        ]
        inner, outer = lines[0], lines[1]
        assert inner["project_id"] == "p1"
        assert inner["translation_id"] == "t1"
        assert outer["project_id"] == "p1"
        assert "translation_id" not in outer

    def test_inner_overrides_outer(self) -> None:
        logger, buf = _make_capture_logger("test.bind.override")
        with bind(project_id="outer"):
            with bind(project_id="inner"):
                logger.info("inner")
            logger.info("outer")

        lines = [
            json.loads(line) for line in buf.getvalue().splitlines() if line.strip()
        ]
        assert lines[0]["project_id"] == "inner"
        assert lines[1]["project_id"] == "outer"

    def test_extra_overrides_bound(self) -> None:
        logger, buf = _make_capture_logger("test.bind.extraoverride")
        with bind(project_id="bound"):
            logger.info("msg", extra={"project_id": "explicit"})
        record = _last_record(buf)
        assert record["project_id"] == "explicit"

    def test_exception_in_block_still_restores_context(self) -> None:
        logger, buf = _make_capture_logger("test.bind.exc")

        with pytest.raises(RuntimeError):
            with bind(project_id="p1"):
                raise RuntimeError("boom")

        logger.info("after")
        record = _last_record(buf)
        assert "project_id" not in record


# ---------------------------------------------------------------------------
# get_request_id
# ---------------------------------------------------------------------------


class TestGetRequestId:
    def test_returns_bound_id(self) -> None:
        with bind(request_id="abc123"):
            assert get_request_id() == "abc123"

    def test_generates_when_absent(self) -> None:
        rid = get_request_id()
        # Should be a valid uuid hex (32 chars).
        assert isinstance(rid, str)
        assert len(rid) == 32
        # Re-parsable as a UUID.
        uuid.UUID(hex=rid)

    def test_generated_ids_are_unique(self) -> None:
        a = get_request_id()
        b = get_request_id()
        assert a != b


# ---------------------------------------------------------------------------
# request_id_middleware
# ---------------------------------------------------------------------------


class TestRequestIdMiddleware:
    def _app(self) -> FastAPI:
        app = FastAPI()
        request_id_middleware(app)

        @app.get("/ping")
        async def ping() -> dict:
            return {"request_id": get_request_id()}

        return app

    def test_round_trips_incoming_header(self) -> None:
        client = TestClient(self._app())
        rid = "deadbeefcafefeed"
        resp = client.get("/ping", headers={REQUEST_ID_HEADER: rid})
        assert resp.status_code == 200
        assert resp.headers[REQUEST_ID_HEADER] == rid
        assert resp.json()["request_id"] == rid

    def test_generates_when_missing(self) -> None:
        client = TestClient(self._app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        rid = resp.headers[REQUEST_ID_HEADER]
        assert isinstance(rid, str) and len(rid) == 32
        # Body matches the response header (middleware bound it for the call).
        assert resp.json()["request_id"] == rid

    def test_different_requests_get_different_ids(self) -> None:
        client = TestClient(self._app())
        a = client.get("/ping").headers[REQUEST_ID_HEADER]
        b = client.get("/ping").headers[REQUEST_ID_HEADER]
        assert a != b


# ---------------------------------------------------------------------------
# Smoke test: configure_logging + bind work end-to-end on the root logger.
# ---------------------------------------------------------------------------


def test_configure_logging_emits_bound_fields() -> None:
    # Build an in-memory mirror of the root JSON handler so we can read
    # back whatever it would have written.  ``configure_logging`` is
    # idempotent so we still exercise it; the capture handler is a
    # second instance of the same ``JsonFormatter`` attached for the
    # duration of the test.
    configure_logging("INFO")

    buf = io.StringIO()
    capture = logging.StreamHandler(stream=buf)
    capture.setFormatter(JsonFormatter())
    capture.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(capture)
    try:
        logger = logging.getLogger("test.smoke")
        with bind(project_id="proj-xyz", request_id="req-7"):
            logger.info("smoke.event", extra={"translation_id": "t-1"})
    finally:
        root.removeHandler(capture)

    matches = [
        line
        for line in buf.getvalue().splitlines()
        if line.strip() and "smoke.event" in line
    ]
    assert matches, f"no JSON line captured: {buf.getvalue()!r}"
    record = json.loads(matches[-1])
    assert record["project_id"] == "proj-xyz"
    assert record["request_id"] == "req-7"
    assert record["translation_id"] == "t-1"
    assert record["msg"] == "smoke.event"
    assert record["level"] == "INFO"


# Ensure the module exposes the documented surface.
def test_module_exports() -> None:
    assert hasattr(clariti_logging, "configure_logging")
    assert hasattr(clariti_logging, "bind")
    assert hasattr(clariti_logging, "get_request_id")
    assert hasattr(clariti_logging, "request_id_middleware")
