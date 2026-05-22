"""ClaritiTMS MCP server.

Exposes ClaritiTMS operations as MCP tools so AI coding agents
(Claude Code, Cursor, Cline) can drive the platform without a
human-in-the-loop. Talks to the existing FastAPI backend over
`/api/v1/`; not in-process.

See `docs/13-agent-integration.md` for the user-facing reference.
"""
