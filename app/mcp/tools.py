"""MCP tool implementations.

Each tool is a thin wrapper around one or a small handful of REST
calls. The contract: tools return JSON-serializable, structured,
agent-sized payloads — not paginated walls. When the underlying
API supports pagination, the tool exposes `limit` and `offset`
arguments and includes `total` in the response so the agent can
decide whether to page.

One tool from the original eight-tool spec (`tm_search`) is still
deferred — the REST surface has no similarity-search endpoint yet.
See `docs/13-agent-integration.md` for the gap and timeline.
"""

from __future__ import annotations

from typing import Any

from app.mcp.client import ClaritiClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _caller_org_id(client: ClaritiClient) -> str:
    """Look up the organization the calling API key belongs to.

    Regular keys can only see their own org, so `GET /organizations`
    returns exactly one entry. Org-admin keys can see all orgs; in
    that case we take the first as a sensible default and let the
    agent override with an explicit `org_id` argument when it cares.
    """
    payload = await client.get("/organizations")
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        raise RuntimeError("Calling API key has no associated organization")
    return str(items[0]["id"])


def _trim_project(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "slug": p.get("slug"),
        "source_locale": p.get("source_locale"),
        "target_locales": p.get("target_locales"),
    }


def _trim_repository(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "platform": r.get("platform"),
        "project_id": r.get("project_id"),
    }


def _trim_key(k: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": k.get("id"),
        "key": k.get("key"),
        "source_text": k.get("source_text"),
        "component": k.get("component"),
        "string_type": k.get("string_type"),
        "repository_id": k.get("repository_id"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def list_projects(
    client: ClaritiClient,
    org_id: str | None = None,
) -> dict[str, Any]:
    """List projects in the caller's organization (or in `org_id` if given)."""
    target_org = org_id or await _caller_org_id(client)
    payload = await client.get(f"/organizations/{target_org}/projects")
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {
        "org_id": target_org,
        "projects": [_trim_project(p) for p in items],
        "total": len(items),
    }


async def list_repositories(
    client: ClaritiClient,
    project_id: str,
) -> dict[str, Any]:
    """List repositories in a project."""
    payload = await client.get(f"/projects/{project_id}/repositories")
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {
        "project_id": project_id,
        "repositories": [_trim_repository(r) for r in items],
        "total": len(items),
    }


async def get_review_queue(
    client: ClaritiClient,
    project_id: str,
    locale: str,
    status: str = "draft",
    repository_id: str | None = None,
    component: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Keys awaiting review for one (project, locale).

    `status` is a translation-row status — typically `draft` (MT
    output not yet reviewed). The page is bounded; if `total` is
    larger than `limit`, the agent should re-call with `offset`.
    """
    page = max(1, (offset // limit) + 1)
    params: dict[str, Any] = {
        "project_id": project_id,
        "locale": locale,
        "status": status,
        "page": page,
        "page_size": limit,
    }
    if repository_id is not None:
        params["repository_id"] = repository_id
    if component is not None:
        params["component"] = component
    payload = await client.get("/keys", params=params)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    total = payload.get("total", len(items)) if isinstance(payload, dict) else len(items)
    return {
        "project_id": project_id,
        "locale": locale,
        "status": status,
        "keys": [_trim_key(k) for k in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


async def translate_batch(
    client: ClaritiClient,
    batch_id: str,
) -> dict[str, Any]:
    """Trigger MT for a batch. Returns the batch's queued state.

    The batch is the unit of translation in ClaritiTMS (a screen's
    worth of strings translated together). Create batches through the
    ingestion or CLI path; this tool only triggers MT for one that
    already exists.
    """
    payload = await client.post(f"/batches/{batch_id}/trigger-mt")
    return {"batch_id": batch_id, "triggered": True, "result": payload}


async def approve_batch(
    client: ClaritiClient,
    batch_id: str,
) -> dict[str, Any]:
    """Approve every translation in a batch (bulk reviewer action)."""
    payload = await client.post(f"/batches/{batch_id}/approve")
    return {"batch_id": batch_id, "approved": True, "result": payload}


async def publish_repository(
    client: ClaritiClient,
    repository_id: str,
) -> dict[str, Any]:
    """Push approved translations for a repository to its source-code remote.

    Concretely: writes target-locale files in the configured format
    (iOS .strings, Android XML, i18next JSON, etc.) and opens or
    updates the PR. The backend handles the git plumbing.
    """
    payload = await client.post(f"/publications/repositories/{repository_id}/publish")
    return {"repository_id": repository_id, "published": True, "result": payload}


async def ingest_strings(
    client: ClaritiClient,
    repository_id: str,
    format: str,
    path: str,
    content: str,
    on_conflict: str = "update_source",
    auto_translate: bool = True,
) -> dict[str, Any]:
    """Ingest a source file into a repository.

    The agent typically already has the file open — it sends the raw
    contents and the platform format ("i18next", "ios-strings", etc.)
    and the backend runs the same parser the GitHub/Contentful webhook
    uses. Runs in partial mode: keys absent from this upload are NOT
    deactivated. See docs/13-agent-integration.md.
    """
    payload = await client.post(
        f"/repositories/{repository_id}/ingest",
        json={
            "format": format,
            "path": path,
            "content": content,
            "on_conflict": on_conflict,
            "auto_translate": auto_translate,
        },
    )
    # The endpoint already returns a trimmed envelope; pass it through.
    return payload if isinstance(payload, dict) else {"result": payload}


async def explain_translation(
    client: ClaritiClient,
    translation_id: str,
) -> dict[str, Any]:
    """Return the translation's current state plus its history.

    Useful for an agent answering "why does this string look like
    that?" — the history includes who changed it, when, and (for MT
    rows) the model + prompt version. History is bounded server-side.
    """
    current = await client.get(f"/translations/{translation_id}")
    history = await client.get(f"/translations/{translation_id}/history")
    history_items = history.get("items", []) if isinstance(history, dict) else []
    return {
        "translation_id": translation_id,
        "current": {
            "locale": current.get("locale"),
            "status": current.get("status"),
            "value": current.get("value"),
            "mt_value": current.get("mt_value"),
            "reviewer_action": current.get("reviewer_action"),
            "model": current.get("model"),
            "prompt_version": current.get("prompt_version"),
        },
        "history": history_items,
    }


# Registry consumed by `server.py` to register tools with the MCP runtime.
# Each entry: (name, description, schema, handler).
TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_projects",
        "description": "List projects in the caller's organization.",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Override the org. Defaults to the caller's org.",
                },
            },
        },
        "handler": list_projects,
    },
    {
        "name": "list_repositories",
        "description": "List repositories in a project.",
        "input_schema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
        "handler": list_repositories,
    },
    {
        "name": "get_review_queue",
        "description": (
            "List keys awaiting reviewer action for one (project, locale). "
            "Returns a bounded page with `total` for pagination."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "locale": {"type": "string", "description": "BCP-47, e.g. 'fr-FR'."},
                "status": {
                    "type": "string",
                    "description": "Translation status. Defaults to 'draft'.",
                    "default": "draft",
                },
                "repository_id": {"type": "string"},
                "component": {"type": "string"},
                "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["project_id", "locale"],
        },
        "handler": get_review_queue,
    },
    {
        "name": "ingest_strings",
        "description": (
            "Ingest a source-strings file into a repository. The backend parses with "
            "the same parser the GitHub/Contentful webhook uses, so the agent doesn't "
            "need per-format logic. Runs in partial mode — keys absent from this "
            "upload are not deactivated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repository_id": {"type": "string"},
                "format": {
                    "type": "string",
                    "enum": [
                        "ios-strings",
                        "ios-xcstrings",
                        "ios-stringsdict",
                        "android-xml",
                        "i18next",
                        "icu",
                        "flat-json",
                    ],
                },
                "path": {
                    "type": "string",
                    "description": "Original file path, used for component inference.",
                },
                "content": {"type": "string", "description": "Raw file contents."},
                "on_conflict": {
                    "type": "string",
                    "enum": ["update_source"],
                    "default": "update_source",
                },
                "auto_translate": {"type": "boolean", "default": True},
            },
            "required": ["repository_id", "format", "path", "content"],
        },
        "handler": ingest_strings,
    },
    {
        "name": "translate_batch",
        "description": "Trigger machine translation for a translation batch.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}},
            "required": ["batch_id"],
        },
        "handler": translate_batch,
    },
    {
        "name": "approve_batch",
        "description": "Bulk-approve every translation in a batch.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}},
            "required": ["batch_id"],
        },
        "handler": approve_batch,
    },
    {
        "name": "publish_repository",
        "description": "Publish approved translations for a repository back to its source-code remote.",
        "input_schema": {
            "type": "object",
            "properties": {"repository_id": {"type": "string"}},
            "required": ["repository_id"],
        },
        "handler": publish_repository,
    },
    {
        "name": "explain_translation",
        "description": "Return a translation's current state and edit history.",
        "input_schema": {
            "type": "object",
            "properties": {"translation_id": {"type": "string"}},
            "required": ["translation_id"],
        },
        "handler": explain_translation,
    },
]
