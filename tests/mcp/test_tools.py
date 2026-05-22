"""Tool-payload contract tests.

The MCP server's value depends on returning small, predictable
payloads. These tests stub the REST layer with `httpx.MockTransport`
and assert that each tool trims the upstream response to the
agreed shape (id, name, locale, etc.) — no full SQLAlchemy row
dumps, no nested 50-field objects.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.mcp import tools
from app.mcp.client import ClaritiClient, ClaritiClientError


def _make_client(handler: callable) -> ClaritiClient:
    """Build a ClaritiClient whose httpx layer is replaced with a mock transport."""
    transport = httpx.MockTransport(handler)
    client = ClaritiClient.__new__(ClaritiClient)
    client._base = "http://test"
    client._client = httpx.AsyncClient(
        base_url="http://test/api/v1",
        headers={"X-API-Key": "test", "Accept": "application/json"},
        transport=transport,
    )
    return client


def _ok(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


@pytest.mark.asyncio
async def test_list_projects_trims_payload() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/organizations"):
            return _ok({"items": [{"id": "org-1", "name": "Acme"}]})
        if req.url.path.endswith("/organizations/org-1/projects"):
            return _ok(
                {
                    "items": [
                        {
                            "id": "proj-1",
                            "name": "Mobile",
                            "slug": "mobile",
                            "source_locale": "en-US",
                            "target_locales": ["fr-FR", "de-DE"],
                            "_internal_blob": "should be dropped",
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = _make_client(handler)
    result = await tools.list_projects(client)

    assert result["org_id"] == "org-1"
    assert result["total"] == 1
    assert result["projects"][0] == {
        "id": "proj-1",
        "name": "Mobile",
        "slug": "mobile",
        "source_locale": "en-US",
        "target_locales": ["fr-FR", "de-DE"],
    }
    # Trimming contract: internal fields must not leak.
    assert "_internal_blob" not in result["projects"][0]
    await client.aclose()


@pytest.mark.asyncio
async def test_get_review_queue_passes_filters() -> None:
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/keys")
        seen.update(dict(req.url.params))
        return _ok({"items": [{"id": "k1", "key": "hello", "source_text": "Hello"}], "total": 1})

    client = _make_client(handler)
    out = await tools.get_review_queue(
        client,
        project_id="proj-1",
        locale="fr-FR",
        repository_id="repo-1",
        component="checkout",
        limit=25,
        offset=50,
    )

    assert seen["project_id"] == "proj-1"
    assert seen["locale"] == "fr-FR"
    assert seen["status"] == "draft"
    assert seen["repository_id"] == "repo-1"
    assert seen["component"] == "checkout"
    assert seen["page_size"] == "25"
    assert seen["page"] == "3"  # offset=50, limit=25 -> page 3
    assert out["keys"][0]["id"] == "k1"
    await client.aclose()


@pytest.mark.asyncio
async def test_client_raises_on_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or revoked API key"})

    client = _make_client(handler)
    with pytest.raises(ClaritiClientError) as info:
        await client.get("/organizations")
    assert info.value.status_code == 401
    assert "revoked" in info.value.message
    await client.aclose()


@pytest.mark.asyncio
async def test_explain_translation_merges_two_calls() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/translations/t-1"):
            return _ok(
                {
                    "id": "t-1",
                    "locale": "fr-FR",
                    "status": "draft",
                    "value": "Bonjour",
                    "mt_value": "Bonjour",
                    "reviewer_action": None,
                    "model": "claude-3-5-sonnet",
                    "prompt_version": "translate_v2",
                }
            )
        if req.url.path.endswith("/translations/t-1/history"):
            return _ok({"items": [{"at": "2026-01-01", "change_source": "mt"}]})
        raise AssertionError(req.url.path)

    client = _make_client(handler)
    out = await tools.explain_translation(client, translation_id="t-1")
    assert out["translation_id"] == "t-1"
    assert out["current"]["model"] == "claude-3-5-sonnet"
    assert out["history"][0]["change_source"] == "mt"
    await client.aclose()


@pytest.mark.asyncio
async def test_ingest_strings_posts_body_and_returns_envelope() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path.endswith("/repositories/r-1/ingest")
        captured["body"] = json.loads(req.content.decode())
        return _ok(
            {
                "repository_id": "r-1",
                "format": "i18next",
                "path": "src/locales/en-US/checkout.json",
                "parsed": 3,
                "created": 2,
                "updated": 1,
                "unchanged": 0,
                "keys": [
                    {"id": "k_a", "key": "checkout.button.pay"},
                    {"id": "k_b", "key": "checkout.error.card_declined"},
                    {"id": "k_c", "key": "checkout.label.shipping"},
                ],
                "batches": [
                    {"id": "b_1", "locale": "fr-FR", "component": "checkout", "status": "pending"}
                ],
            },
            status=201,
        )

    client = _make_client(handler)
    result = await tools.ingest_strings(
        client,
        repository_id="r-1",
        format="i18next",
        path="src/locales/en-US/checkout.json",
        content='{"checkout": {"button": {"pay": "Pay {{amount}}"}}}',
    )

    # Body shape contract: backend gets exactly these fields with the agreed defaults.
    assert captured["body"] == {
        "format": "i18next",
        "path": "src/locales/en-US/checkout.json",
        "content": '{"checkout": {"button": {"pay": "Pay {{amount}}"}}}',
        "on_conflict": "update_source",
        "auto_translate": True,
    }
    assert result["created"] == 2
    assert result["updated"] == 1
    assert len(result["keys"]) == 3
    assert result["batches"][0]["locale"] == "fr-FR"
    await client.aclose()


@pytest.mark.asyncio
async def test_tool_registry_has_required_shape() -> None:
    """Every entry in TOOLS must be MCP-ready."""
    seen_names = set()
    for spec in tools.TOOLS:
        for key in ("name", "description", "input_schema", "handler"):
            assert key in spec, f"missing {key} in {spec.get('name')}"
        assert callable(spec["handler"])
        assert spec["name"] not in seen_names
        seen_names.add(spec["name"])
        # JSON-schema validity check — must be serializable.
        json.dumps(spec["input_schema"])
