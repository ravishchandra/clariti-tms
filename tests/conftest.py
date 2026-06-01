"""Test-suite-wide setup.

Most test modules import `app.*` which constructs `Settings()` at import time.
Since C4 made `Settings` strict (DEBUG defaults to False, SECRET_KEY required
in production), the suite needs a safe default at collection time. Using
`os.environ.setdefault` so any developer who explicitly sets `DEBUG=false`
in their shell to exercise the production path still wins.

`tests/core/test_settings.py` clears these env vars per-test via monkeypatch
and constructs `Settings(_env_file=None, ...)` directly, so it's unaffected.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

os.environ.setdefault("DEBUG", "true")
# Keep the in-process MT worker off during tests — otherwise every TestClient
# that triggers the lifespan would spawn a polling loop that hits the real DB
# and clobbers test fixtures.
os.environ.setdefault("MT_WORKER_ENABLED", "false")

# Default the DB-touching suites to a dedicated *test* database. Several of them
# TRUNCATE every table for a clean slate, so they must never default to the
# app's `tms` database. conftest is imported before any test module, so this
# wins over the per-module `setdefault(..., ".../tms")` calls.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tms:tms@localhost:5432/tms_test",
)


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def pytest_configure(config):  # noqa: ARG001 — pytest hook signature
    """Fail closed if DATABASE_URL points at a non-test database.

    The integration suites (`tests/ingestion`, `tests/mt`, `tests/integration`,
    and several `tests/api`) TRUNCATE every table to start from a clean slate.
    If DATABASE_URL points at a real database, abort the entire run *before any
    fixture can touch it* — a populated instance was wiped exactly this way once.

    Allowed targets: a database whose name ends in ``_test`` (or is ``test``).
    Escape hatch for disposable CI databases: ``CLARITI_ALLOW_NONTEST_DB=1``.
    """
    if os.environ.get("CLARITI_ALLOW_NONTEST_DB") == "1":
        return
    name = _database_name(os.environ.get("DATABASE_URL", ""))
    if name.endswith("_test") or name == "test":
        return
    raise pytest.UsageError(
        f"Refusing to run the test suite against database {name!r}: these suites "
        f"TRUNCATE every table and would destroy its data. Point DATABASE_URL at a "
        f"dedicated test database (e.g. tms_test), or set CLARITI_ALLOW_NONTEST_DB=1 "
        f"if this is a disposable CI database."
    )
