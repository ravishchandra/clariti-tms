"""Generate (or verify) the committed OpenAPI spec in-process.

The spec is the authoritative API contract that the SDKs (``make sdks``) and the
hand-maintained web client are meant to track. It used to be produced by
``curl``-ing a *running* server (``make spec``), which meant nobody ran it and
the committed ``sdk-gen/openapi.json`` rotted to an empty stub — letting the
web client silently drift (developer-packet §19/§20).

This generates the spec straight from ``app.main:app`` (no server, no DB), with
sorted keys so the output is byte-stable and diffable.

Usage::

    python scripts/dump_openapi.py            # write sdk-gen/openapi.json
    python scripts/dump_openapi.py --check    # exit 1 if it would change (CI)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SPEC_PATH = ROOT / "sdk-gen" / "openapi.json"

# Constructing ``Settings`` requires these in non-DEBUG; the spec doesn't touch
# a DB or real secrets, so default safe values for a clean generation.
os.environ.setdefault("DEBUG", "true")


def render_spec() -> str:
    """Return the app's OpenAPI spec as stable, sorted JSON (trailing newline)."""
    from app.main import app

    spec = app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv[1:]
    rendered = render_spec()

    if check:
        current = SPEC_PATH.read_text() if SPEC_PATH.exists() else ""
        if current != rendered:
            print(
                "sdk-gen/openapi.json is stale. Regenerate with:\n"
                "  python scripts/dump_openapi.py\n"
                "and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("OpenAPI spec is up to date.")
        return 0

    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(rendered)
    paths = json.loads(rendered).get("paths", {})
    print(f"Wrote {SPEC_PATH.relative_to(ROOT)} ({len(paths)} paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
