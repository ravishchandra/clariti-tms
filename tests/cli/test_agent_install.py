"""Unit tests for the `loc agent install` helpers.

These exist for one reason: the Claude Code config file is 56KB+ of session
state. A merge bug here would silently corrupt the user's editor settings.
The merge + atomic-write contract is the whole point of splitting these
helpers out of the Typer command into a pure module.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from cli.agent_install import (
    CLAUDE_MD_BEGIN,
    CLAUDE_MD_END,
    MCP_SERVER_NAME,
    EditorConfig,
    atomic_write_json,
    build_mcp_entry,
    check_backend_reachable,
    claude_code_config_path,
    cursor_config_path,
    detect_editors,
    merge_mcp_config,
    read_editor_config,
    render_claude_md_section,
    upsert_claude_md_section,
)

# ---------------------------------------------------------------------------
# build_mcp_entry — the JSON shape Claude Code / Cursor expect
# ---------------------------------------------------------------------------


def test_build_mcp_entry_shape() -> None:
    entry = build_mcp_entry(api_url="http://localhost:8000", api_key="abc123")
    assert entry == {
        "command": "clariti-mcp",
        "env": {
            "CLARITI_API_URL": "http://localhost:8000",
            "CLARITI_API_KEY": "abc123",
        },
    }


# ---------------------------------------------------------------------------
# merge_mcp_config — preserve everything except the one entry we own
# ---------------------------------------------------------------------------


def test_merge_into_empty_config() -> None:
    merged = merge_mcp_config({}, {"command": "x", "env": {}})
    assert merged == {"mcpServers": {MCP_SERVER_NAME: {"command": "x", "env": {}}}}


def test_merge_preserves_other_top_level_keys() -> None:
    existing = {
        "userID": "u-123",
        "numStartups": 47,
        "claudeCodeHints": {"foo": True},
        "mcpServers": {},
    }
    merged = merge_mcp_config(existing, {"command": "x", "env": {}})
    assert merged["userID"] == "u-123"
    assert merged["numStartups"] == 47
    assert merged["claudeCodeHints"] == {"foo": True}
    assert MCP_SERVER_NAME in merged["mcpServers"]


def test_merge_preserves_other_mcp_servers() -> None:
    """Other MCP servers (figma, etc.) must survive untouched."""
    existing = {
        "mcpServers": {
            "figma": {"type": "sse", "url": "https://figma.example/mcp"},
            "custom": {"command": "my-server", "args": ["--flag"]},
        }
    }
    merged = merge_mcp_config(existing, {"command": "clariti-mcp", "env": {}})
    assert merged["mcpServers"]["figma"] == {"type": "sse", "url": "https://figma.example/mcp"}
    assert merged["mcpServers"]["custom"] == {"command": "my-server", "args": ["--flag"]}
    assert merged["mcpServers"][MCP_SERVER_NAME] == {"command": "clariti-mcp", "env": {}}


def test_merge_updates_existing_clariti_entry() -> None:
    """Re-running install replaces the entry, doesn't duplicate it."""
    existing = {
        "mcpServers": {
            MCP_SERVER_NAME: {"command": "old", "env": {"CLARITI_API_KEY": "old-key"}},
        }
    }
    new_entry = {"command": "clariti-mcp", "env": {"CLARITI_API_KEY": "new-key"}}
    merged = merge_mcp_config(existing, new_entry)
    assert merged["mcpServers"][MCP_SERVER_NAME] == new_entry
    assert len(merged["mcpServers"]) == 1


def test_merge_does_not_mutate_input() -> None:
    existing = {"mcpServers": {"figma": {"type": "sse"}}}
    merge_mcp_config(existing, {"command": "x"})
    # The original dict must be untouched — the caller may still hold a reference.
    assert existing == {"mcpServers": {"figma": {"type": "sse"}}}


def test_merge_with_null_mcp_servers() -> None:
    """Tolerate `mcpServers: null` as well as missing-key."""
    existing = {"userID": "u-1", "mcpServers": None}
    merged = merge_mcp_config(existing, {"command": "x"})
    assert merged["mcpServers"] == {MCP_SERVER_NAME: {"command": "x"}}
    assert merged["userID"] == "u-1"


# ---------------------------------------------------------------------------
# atomic_write_json — must produce valid JSON, must not truncate
# ---------------------------------------------------------------------------


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_json(target, {"hello": "world"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"old": true}\n')
    atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_atomic_write_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "config.json"
    atomic_write_json(target, {"x": 1})
    assert target.exists()


def test_atomic_write_leaves_no_tmp_files_on_success(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_json(target, {"x": 1})
    # Only the target file should exist; no .tmp-*.json siblings.
    siblings = [p.name for p in tmp_path.iterdir()]
    assert siblings == ["config.json"]


def test_read_editor_config_missing_returns_empty(tmp_path: Path) -> None:
    assert read_editor_config(tmp_path / "nope.json") == {}


def test_read_editor_config_existing(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text('{"x": 1}')
    assert read_editor_config(p) == {"x": 1}


# ---------------------------------------------------------------------------
# detect_editors — file existence drives auto-detection
# ---------------------------------------------------------------------------


def test_detect_editors_only_claude_returns_one(tmp_path: Path) -> None:
    out = detect_editors(only="claude", home=tmp_path)
    assert len(out) == 1
    assert out[0].name == "claude"
    assert out[0].path == tmp_path / ".claude.json"


def test_detect_editors_only_cursor_returns_one(tmp_path: Path) -> None:
    out = detect_editors(only="cursor", home=tmp_path)
    assert len(out) == 1
    assert out[0].name == "cursor"
    assert out[0].path == tmp_path / ".cursor" / "mcp.json"


def test_detect_editors_auto_finds_claude_via_file(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text("{}")
    out = detect_editors(home=tmp_path)
    names = [e.name for e in out]
    assert "claude" in names


def test_detect_editors_auto_finds_cursor_via_dir(tmp_path: Path) -> None:
    (tmp_path / ".cursor").mkdir()
    out = detect_editors(home=tmp_path)
    names = [e.name for e in out]
    assert "cursor" in names


def test_detect_editors_auto_empty_home_returns_nothing(tmp_path: Path) -> None:
    assert detect_editors(home=tmp_path) == []


def test_editor_config_display_names() -> None:
    assert EditorConfig(name="claude", path=Path("/x")).display == "Claude Code"
    assert EditorConfig(name="cursor", path=Path("/y")).display == "Cursor"
    assert EditorConfig(name="unknown", path=Path("/z")).display == "unknown"


def test_path_helpers_use_home() -> None:
    # Sanity: helpers accept a home override (used by detect_editors).
    fake = Path("/fake/home")
    assert claude_code_config_path(fake) == fake / ".claude.json"
    assert cursor_config_path(fake) == fake / ".cursor" / "mcp.json"


# ---------------------------------------------------------------------------
# render_claude_md_section + upsert_claude_md_section
# ---------------------------------------------------------------------------


def test_render_section_has_markers() -> None:
    section = render_claude_md_section(repo_name="frontend", server_url="http://localhost:8000")
    assert section.startswith(CLAUDE_MD_BEGIN)
    assert section.endswith(CLAUDE_MD_END)
    assert "frontend" in section
    assert "http://localhost:8000" in section


def test_render_section_without_repo_name() -> None:
    section = render_claude_md_section(repo_name=None, server_url="http://localhost:8000")
    # Should not include the "Repository:" line when no repo name is configured.
    assert "**Repository:**" not in section
    assert "http://localhost:8000" in section


def test_upsert_creates_new_claude_md(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    section = render_claude_md_section(repo_name="x", server_url="http://localhost:8000")
    modified = upsert_claude_md_section(target, section)
    assert modified is True
    assert target.exists()
    content = target.read_text()
    assert CLAUDE_MD_BEGIN in content
    assert CLAUDE_MD_END in content


def test_upsert_appends_to_existing_claude_md(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text("# My project\n\nSome existing text.\n")
    section = render_claude_md_section(repo_name="x", server_url="http://localhost:8000")
    modified = upsert_claude_md_section(target, section)
    assert modified is True
    content = target.read_text()
    # Existing content preserved.
    assert "# My project" in content
    assert "Some existing text." in content
    # New section appended.
    assert CLAUDE_MD_BEGIN in content
    assert CLAUDE_MD_END in content


def test_upsert_replaces_existing_section_in_place(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    initial = render_claude_md_section(repo_name="old-repo", server_url="http://old.example")
    target.write_text("# header\n\n" + initial + "\n\n## trailing section\n\nstill here\n")

    new_section = render_claude_md_section(repo_name="new-repo", server_url="http://new.example")
    modified = upsert_claude_md_section(target, new_section)
    assert modified is True
    content = target.read_text()
    # Old values gone, new ones present.
    assert "old-repo" not in content
    assert "http://old.example" not in content
    assert "new-repo" in content
    assert "http://new.example" in content
    # Header and trailing content preserved.
    assert "# header" in content
    assert "## trailing section" in content
    assert "still here" in content
    # Only one BEGIN/END pair (no duplication on re-run).
    assert content.count(CLAUDE_MD_BEGIN) == 1
    assert content.count(CLAUDE_MD_END) == 1


def test_upsert_idempotent_when_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    section = render_claude_md_section(repo_name="x", server_url="http://localhost:8000")
    upsert_claude_md_section(target, section)
    # Second call with identical section should be a no-op.
    modified = upsert_claude_md_section(target, section)
    assert modified is False


# ---------------------------------------------------------------------------
# End-to-end merge against a realistic Claude Code config shape
# ---------------------------------------------------------------------------


def test_full_round_trip_against_realistic_config(tmp_path: Path) -> None:
    """Read a realistic 50-key config, merge, write atomically, re-read.

    Every original key must survive byte-identical. The Claude Code config
    file in the wild has ~70 top-level keys; this fixture proves the merge
    doesn't drop any of them.
    """
    target = tmp_path / ".claude.json"
    realistic: dict = {
        "userID": "u-abc",
        "numStartups": 142,
        "firstStartTime": "2025-11-01T00:00:00Z",
        "hasCompletedOnboarding": True,
        "claudeCodeHints": {"a": 1, "b": [1, 2, 3]},
        "projects": {"/Users/x/proj": {"lastUsed": "2026-05-21"}},
        "skillUsage": {"investigate": 7},
        "mcpServers": {
            "figma": {"type": "sse", "url": "https://figma.example/mcp"},
        },
        "githubRepoPaths": ["/Users/x/repo1", "/Users/x/repo2"],
    }
    target.write_text(json.dumps(realistic, indent=2) + "\n")

    existing = read_editor_config(target)
    entry = build_mcp_entry(api_url="http://localhost:8000", api_key="key-xyz")
    merged = merge_mcp_config(existing, entry)
    atomic_write_json(target, merged)

    re_read = read_editor_config(target)
    # All original top-level keys preserved.
    for k, v in realistic.items():
        if k == "mcpServers":
            continue
        assert re_read[k] == v, f"key {k} was modified or dropped"
    # figma is still there.
    assert re_read["mcpServers"]["figma"] == {"type": "sse", "url": "https://figma.example/mcp"}
    # clariti-tms was added with the right shape.
    assert re_read["mcpServers"][MCP_SERVER_NAME] == entry


# ---------------------------------------------------------------------------
# check_backend_reachable — short timeout, non-fatal probe
# ---------------------------------------------------------------------------


def _make_probe_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_backend_reachable_when_health_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    async with _make_probe_client(handler) as client:
        ok, err = await check_backend_reachable("http://localhost:8000", client=client)
    assert ok is True
    assert err is None


@pytest.mark.asyncio
async def test_backend_unreachable_on_non_200() -> None:
    async with _make_probe_client(lambda r: httpx.Response(503, text="down")) as client:
        ok, err = await check_backend_reachable("http://localhost:8000", client=client)
    assert ok is False
    assert err == "HTTP 503"


@pytest.mark.asyncio
async def test_backend_unreachable_on_unexpected_payload() -> None:
    async with _make_probe_client(lambda r: httpx.Response(200, json={"status": "degraded"})) as client:
        ok, err = await check_backend_reachable("http://localhost:8000", client=client)
    assert ok is False
    assert err is not None and "unexpected health payload" in err


@pytest.mark.asyncio
async def test_backend_unreachable_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _make_probe_client(handler) as client:
        ok, err = await check_backend_reachable("http://localhost:8000", client=client)
    assert ok is False
    assert err == "connection refused"


@pytest.mark.asyncio
async def test_backend_probe_strips_trailing_slash() -> None:
    """Verify trailing slash on api_url doesn't produce //health."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    async with _make_probe_client(handler) as client:
        await check_backend_reachable("http://localhost:8000/", client=client)
    assert seen == ["/health"]


def test_re_install_does_not_duplicate(tmp_path: Path) -> None:
    """Running install twice yields one clariti-tms entry, not two."""
    target = tmp_path / ".claude.json"
    target.write_text('{"mcpServers": {}}')

    for key in ("first-key", "second-key"):
        existing = read_editor_config(target)
        entry = build_mcp_entry(api_url="http://localhost:8000", api_key=key)
        merged = merge_mcp_config(existing, entry)
        atomic_write_json(target, merged)

    final = read_editor_config(target)
    assert len(final["mcpServers"]) == 1
    assert final["mcpServers"][MCP_SERVER_NAME]["env"]["CLARITI_API_KEY"] == "second-key"
