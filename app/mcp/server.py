"""MCP server runtime for ClaritiTMS.

Registers the tools defined in `tools.py` with the MCP Python SDK
and serves them over stdio. Wired to the CLI via `loc mcp serve`.

Only stdio is supported in this first cut. HTTP/SSE is deferred —
remote agent transport adds an auth-and-discovery surface that
needs its own design pass.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.mcp.client import ClaritiClient, ClaritiClientError
from app.mcp.tools import TOOLS

logger = logging.getLogger("clariti.mcp")


def _build_server() -> tuple[Server, dict[str, Any]]:
    server: Server = Server("clariti-tms")
    state: dict[str, Any] = {"client": None}

    async def _client() -> ClaritiClient:
        if state["client"] is None:
            state["client"] = ClaritiClient()
        return state["client"]

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["input_schema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if spec is None:
            return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        handler = spec["handler"]
        try:
            client = await _client()
            result = await handler(client, **(arguments or {}))
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except ClaritiClientError as exc:
            payload = {"error": exc.message, "status_code": exc.status_code}
            return [TextContent(type="text", text=json.dumps(payload))]
        except TypeError as exc:
            return [TextContent(type="text", text=json.dumps({"error": f"bad arguments: {exc}"}))]
        except Exception as exc:
            logger.exception("MCP tool '%s' failed", name)
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    return server, state


async def serve_stdio() -> None:
    server, state = _build_server()
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        client = state.get("client")
        if client is not None:
            await client.aclose()


def main() -> None:
    """Console entry-point. Used by `loc mcp serve` and `clariti-mcp`."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
