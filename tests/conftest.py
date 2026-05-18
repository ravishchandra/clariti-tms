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

os.environ.setdefault("DEBUG", "true")
