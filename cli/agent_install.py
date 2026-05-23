"""Helpers for `loc agent install` — pure functions split out for unit testing.

The Typer command itself lives in `cli/main.py`. This module owns the
mechanical parts that are worth testing in isolation: editor-config-file
locations, the JSON merge that must preserve every unrelated key in a
56KB+ harness config, atomic write semantics, and the marker-bounded
CLAUDE.md section.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

MCP_SERVER_NAME = "clariti-tms"
CLAUDE_MD_BEGIN = "<!-- BEGIN clariti-tms -->"
CLAUDE_MD_END = "<!-- END clariti-tms -->"
BACKEND_PROBE_TIMEOUT_SECS = 2.0

_DISPLAY_NAMES = {"claude": "Claude Code", "cursor": "Cursor"}


@dataclass(frozen=True)
class EditorConfig:
    name: str
    path: Path

    @property
    def display(self) -> str:
        return _DISPLAY_NAMES.get(self.name, self.name)


def claude_code_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude.json"


def cursor_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".cursor" / "mcp.json"


def detect_editors(only: str | None = None, *, home: Path | None = None) -> list[EditorConfig]:
    """Return the editor configs to write to.

    `only` of "claude" or "cursor" forces just that one — the config file is
    created if missing. `only` of None or "all" auto-detects from
    install-marker paths:

    - Claude Code: ``~/.claude.json`` exists (Claude Code writes this on first run).
    - Cursor: ``~/.cursor/`` directory exists.

    The home directory itself is not a valid install marker (it always exists),
    so we check the install-specific marker per editor.
    """
    claude = EditorConfig(name="claude", path=claude_code_config_path(home))
    cursor = EditorConfig(name="cursor", path=cursor_config_path(home))

    if only == "claude":
        return [claude]
    if only == "cursor":
        return [cursor]

    out: list[EditorConfig] = []
    if claude.path.exists():
        out.append(claude)
    if cursor.path.parent.exists():
        out.append(cursor)
    return out


def build_mcp_entry(*, api_url: str, api_key: str) -> dict:
    """The JSON block we insert into mcpServers[MCP_SERVER_NAME]."""
    return {
        "command": "clariti-mcp",
        "env": {
            "CLARITI_API_URL": api_url,
            "CLARITI_API_KEY": api_key,
        },
    }


def merge_mcp_config(existing: dict, entry: dict, *, name: str = MCP_SERVER_NAME) -> dict:
    """Return a new config with `mcpServers[name] = entry`.

    Every other top-level key in `existing` is preserved exactly; other entries
    under `mcpServers` are preserved exactly. `existing` is not mutated.
    """
    merged = dict(existing)
    servers = dict(merged.get("mcpServers") or {})
    servers[name] = entry
    merged["mcpServers"] = servers
    return merged


def read_editor_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via tmp-file + os.replace in the same directory.

    Same-directory matters — os.replace is only atomic on the same filesystem.
    The Claude Code config is 56KB+ of session state; a torn write would be
    catastrophic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def render_claude_md_section(*, repo_name: str | None, server_url: str) -> str:
    """The marker-bounded CLAUDE.md block. Markers make re-install idempotent."""
    lines = [
        CLAUDE_MD_BEGIN,
        "",
        "## ClaritiTMS",
        "",
        "This repository uses ClaritiTMS for translation management. AI coding",
        "agents can drive the platform via the `clariti-tms` MCP server.",
        "",
    ]
    if repo_name:
        lines.append(f"- **Repository:** `{repo_name}`")
    lines.append(f"- **Server:** {server_url}")
    lines.append("")
    lines.append("**MCP tools available:** `list_projects`, `list_repositories`,")
    lines.append("`ingest_strings`, `list_keys`, `get_translation`, `list_pending_review`,")
    lines.append("`approve_translation`, `request_retranslation`.")
    lines.append("")
    lines.append("**When to use:** to ingest source strings from this repo, check")
    lines.append("translation status, or approve pending review items without leaving")
    lines.append("the agent. See `docs/13-agent-integration.md` for tool schemas.")
    lines.append("")
    lines.append(CLAUDE_MD_END)
    return "\n".join(lines)


_CLAUDE_MD_SECTION_RE = re.compile(
    re.escape(CLAUDE_MD_BEGIN) + r".*?" + re.escape(CLAUDE_MD_END),
    re.DOTALL,
)


async def check_backend_reachable(
    api_url: str,
    *,
    timeout: float = BACKEND_PROBE_TIMEOUT_SECS,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str | None]:
    """Probe ``{api_url}/health``. Returns ``(reachable, error_message)``.

    Reachable means HTTP 200 with ``{"status": "ok"}`` in the body — matches
    ``app/main.py:health()``. Anything else (non-200, connection refused,
    DNS failure, timeout) reports unreachable with a short error string.

    Non-fatal at the install-command level: a developer can run
    ``loc agent install`` before starting the backend; the editor config
    just won't function until the backend is up. ``client`` is injectable
    for tests; if omitted, a fresh ``AsyncClient`` is built per call.
    """
    url = api_url.rstrip("/") + "/health"
    owns_client = client is None
    active = client if client is not None else httpx.AsyncClient(timeout=timeout)
    try:
        response = await active.get(url)
    except httpx.HTTPError as exc:
        msg = str(exc).strip() or type(exc).__name__
        return False, msg
    finally:
        if owns_client:
            await active.aclose()

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        return False, "non-JSON response"
    if body.get("status") != "ok":
        return False, f"unexpected health payload: {body!r}"
    return True, None


def upsert_claude_md_section(path: Path, section: str) -> bool:
    """Insert or replace the marker-bounded section in CLAUDE.md.

    Returns True if the file was created or modified, False if the section was
    already byte-identical.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    if _CLAUDE_MD_SECTION_RE.search(existing):
        new = _CLAUDE_MD_SECTION_RE.sub(section, existing)
    else:
        prefix = existing.rstrip() + "\n\n" if existing.strip() else ""
        new = prefix + section + "\n"

    if new == existing:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return True
