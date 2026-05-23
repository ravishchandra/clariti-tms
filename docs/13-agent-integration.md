# 13. Agent integration

ClaritiTMS ships a first-party **Model Context Protocol (MCP) server** so
AI coding agents — Claude Code, Cursor, Cline — can drive the platform
directly. The intent is one-move adoption: an engineer asks the agent
to "translate this screen", and the agent calls the MCP tools without
opening a tab or copying a UUID by hand.

This document covers what the server exposes today, how to wire it into
an agent, and the deliberate gaps still on the roadmap.

## What it is

A stdio-mode MCP server that translates tool calls into REST calls against
the existing `/api/v1/` surface. It is a **separate process**, not an
in-process integration — keeping the trust boundary explicit (the agent
talks to the MCP server; the MCP server talks to the backend with a
scoped API key).

- **Source:** `app/mcp/` in this repo.
- **Console scripts:** `clariti-mcp` (standalone) and `loc mcp serve`
  (bundled with the regular CLI).
- **Distribution:** Python wheel (`clariti-tms` on PyPI, includes the
  server) and Docker image (`app/mcp/Dockerfile`).
- **Transport:** stdio. HTTP/SSE is deferred (see "Not yet" below).
- **Auth:** the server reads `CLARITI_API_URL` and `CLARITI_API_KEY` from
  its environment. The API key is a regular ClaritiTMS key — create one
  through `loc api-key` or the REST API, scope it to the org you want
  the agent to operate on.

## Available tools

| Tool | Purpose | Underlying REST call |
|------|---------|----------------------|
| `list_projects` | Projects in the caller's organization. | `GET /organizations/{org}/projects` |
| `list_repositories` | Repositories under a project. | `GET /projects/{id}/repositories` |
| `get_review_queue` | Keys awaiting reviewer action for one (project, locale). Bounded page with `total`. | `GET /keys?project_id=…&locale=…&status=…` |
| `ingest_strings` | Ingest a source-strings file into a repository. Partial-sync; auto-translates by default. | `POST /repositories/{id}/ingest` |
| `translate_batch` | Trigger MT for a batch. | `POST /batches/{id}/trigger-mt` |
| `approve_batch` | Bulk-approve a batch. | `POST /batches/{id}/approve` |
| `publish_repository` | Push approved translations back to source-code remote. | `POST /publications/repositories/{id}/publish` |
| `explain_translation` | Current value + edit history of a translation. | `GET /translations/{id}` + `/history` |

Each tool returns a trimmed payload — id + name + a few human-readable
fields, never the raw SQLAlchemy row. Pagination is exposed where it
exists upstream (`limit` / `offset` on `get_review_queue`).

## Quick start — `loc agent install`

One-shot setup. Detects which editors are installed, mints an API key,
and writes the MCP server entry into each editor's config file —
preserving every other entry already there:

```bash
loc agent install
```

What it does:

1. Detects Claude Code (`~/.claude.json` exists) and Cursor (`~/.cursor/`
   exists), or use `--editor claude` / `--editor cursor` to pick one.
2. Mints an API key for the first organization in the DB (or pass
   `--org <slug>`) and labels it `claude-code` by default
   (`--name <label>` to override). Skip minting entirely with
   `--api-key <existing>`.
3. Merges a `clariti-tms` entry into the editor's `mcpServers` object
   without touching any other key in the file — the merge is atomic
   (tmp file + rename), so a crash mid-write cannot truncate the editor
   config.
4. Writes (or updates) a marker-bounded `## ClaritiTMS` block in
   `CLAUDE.md` in the current directory so agents working in this
   checkout know the platform is available. Skip with `--no-claude-md`.

Preview the changes before they happen:

```bash
loc agent install --dry-run
```

After running, restart your editor and try:

> "List my ClaritiTMS projects."

The agent should call the `clariti-tms.list_projects` tool.

## Manual setup

If you prefer to hand-edit the config (or are scripting an install
where `loc` is not available), add a `clariti-tms` entry under
`mcpServers` in `~/.claude.json`:

```json
{
  "mcpServers": {
    "clariti-tms": {
      "command": "clariti-mcp",
      "env": {
        "CLARITI_API_URL": "https://tms.example.com",
        "CLARITI_API_KEY": "ctms_live_..."
      }
    }
  }
}
```

Or with Docker, for environments where you don't want a Python toolchain
on the agent host:

```json
{
  "mcpServers": {
    "clariti-tms": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "CLARITI_API_URL",
        "-e", "CLARITI_API_KEY",
        "clariti/mcp:latest"
      ],
      "env": {
        "CLARITI_API_URL": "https://tms.example.com",
        "CLARITI_API_KEY": "ctms_live_..."
      }
    }
  }
}
```

Cursor uses the same schema at `~/.cursor/mcp.json`. Cline reads its
own per-workspace settings; see its docs for the exact path.

## Talking to a local dev backend

```bash
export CLARITI_API_URL=http://localhost:8000
loc api-key --name mcp-dev   # prints a key; export it as CLARITI_API_KEY
export CLARITI_API_KEY=...   # paste the key from the previous command
clariti-mcp                  # serves on stdio; drive with the MCP inspector or a client
```

## Design choices worth knowing

- **Why REST, not in-process.** The MCP server runs out-of-process so the
  same code works in three environments: the agent on the developer's
  laptop talking to a hosted ClaritiTMS, an agent inside CI talking to a
  self-hosted instance, and a `docker run` in production. An in-process
  integration would have coupled the agent host to ClaritiTMS's Python
  runtime and Postgres connection.
- **Why payload trimming.** Agents pay tokens for tool outputs. Returning
  a full Pydantic model with 25 fields per row makes every list call
  expensive. We trim aggressively in `app/mcp/tools.py`. Add a field only
  if a real agent flow needs it.
- **Why stdio first.** Every MCP client supports stdio; remote
  HTTP/SSE adds an auth surface (the existing X-API-Key is good for the
  backend, not for transport-level identity of the agent).

## `ingest_strings` — examples

The agent sends the raw file. The backend parses with the same parsers
the GitHub/Contentful webhook ingest uses, so iOS, Android, and React
all work without per-format agent logic.

**i18next (React/TS):**

```json
{
  "format": "i18next",
  "path": "src/locales/en-US/checkout.json",
  "content": "{\"checkout\":{\"button\":{\"pay\":\"Pay {{amount}}\"},\"error\":{\"card_declined\":\"Your card was declined.\"}}}",
  "auto_translate": true
}
```

**iOS .strings:**

```json
{
  "format": "ios-strings",
  "path": "App/en.lproj/Checkout.strings",
  "content": "\"checkout.button.pay\" = \"Pay %@\";\n\"checkout.error.card_declined\" = \"Your card was declined.\";\n"
}
```

**Response (HTTP 200):**

```json
{
  "repository_id": "8b3...e1",
  "format": "i18next",
  "path": "src/locales/en-US/checkout.json",
  "parsed": 2,
  "created": 2,
  "updated": 0,
  "unchanged": 0,
  "keys": [
    {"id": "k_a", "key": "checkout.button.pay"},
    {"id": "k_b", "key": "checkout.error.card_declined"}
  ],
  "batches": [
    {"id": "b_1", "locale": "fr-FR", "component": "checkout", "status": "pending"}
  ]
}
```

**Important contract notes:**

- **Partial sync.** Keys present in the repository but absent from this
  upload are NOT deactivated. The webhook ingest path is full-sync; agent
  ingest is partial-sync because agents typically send one component at
  a time. If you need to deactivate keys, use the CLI's `loc ingest` or
  the GitHub webhook path.
- **`on_conflict`.** Only `update_source` is supported today. When a key
  exists with a different `source_text`, the row updates and approved /
  published translations demote to `needs_review`. `reject` was
  considered and held — it creates a dead-end agent flow with no clean
  recovery. Reopen if a real use case appears.
- **`auto_translate`.** When `true` (default), the endpoint calls
  `assemble_batches` and the new batches land in `status=pending`, ready
  for the scheduler. Set `false` if the agent wants to drive
  translation manually via `translate_batch`.

## Not yet (deferred from the original eight-tool spec)

- **`tm_search`.** The translation memory is consulted internally during
  MT prompt construction. There is no public REST endpoint for
  similarity search yet. Will land alongside the broader retrieval
  surface in a later phase.
- **HTTP/SSE transport.** Remote agents (hosted Claude, web-based IDEs)
  need this. Holds on a clean story for transport-level auth.
- **GitHub App OAuth in `loc agent install`.** The current install
  command writes editor config and CLAUDE.md but does not wire the
  GitHub App connection. Pending a real second user to validate the
  flow before automating it.
- **First-translation run in `loc agent install`.** The full IDEAS.md
  spec includes running an initial translation as proof-of-life.
  Deferred — the existing `loc demo` covers this for a mock provider;
  doing it for real keys without per-user judgment is risky.

See `IDEAS.md` (entry: "Agent-native integration surface") for the rest
of the roadmap.

## Operational notes

- **Errors.** Tools always return JSON. Backend errors arrive as
  `{"error": "...", "status_code": 401}` rather than raising — keeps the
  agent's view structured.
- **Concurrency.** A single `httpx.AsyncClient` is shared across tool
  calls in one server process. Each agent gets its own server process,
  so cross-tenant contamination isn't possible at the transport layer.
- **Logging.** Set `LOG_LEVEL=DEBUG` to see request/response bodies in
  the server's stderr. stdout is reserved for the MCP protocol.
