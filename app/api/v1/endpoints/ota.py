"""OTA (Over-The-Air) locale delivery endpoint — Phase 7.

Mobile apps fetch their locale strings at runtime from a CDN-fronted HTTP
endpoint, so operators can fix typos without an App Store / Play Store
release. The endpoint is **public** by design — locale files end up shipped
in published apps anyway, so they aren't secrets — and is shaped for
aggressive CDN caching:

* ``Cache-Control: public, max-age=300, stale-while-revalidate=86400``
  Five minutes "fresh", twenty-four hours "stale but usable while we
  revalidate in the background". Five minutes is the slot operators
  expect for typo fixes to propagate; the long SWR keeps the CDN
  serving traffic when origin is briefly down.
* ``ETag: "W/<sha256-prefix>"`` (weak ETag, 16 hex chars).  Clients
  send it back as ``If-None-Match`` on the next poll. On match we
  return 304 with no body, saving the CDN-to-client bytes (which is
  most of the cost for app-startup traffic).
* ``Vary: Accept-Encoding`` so the CDN keeps gzip / brotli variants
  separate per UA.

See ``docs/12-ota.md`` for the operator contract and the iOS/Android
SDK sketches.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import DB
from app.models import Key, Repository, Translation
from app.mt.api import (
    list_published_translations_by_project_slug,
    project_exists_by_slug,
)
from app.publication.writers.ios import serialize_strings

# Keep the type alias narrow but reusable across helpers.
_Row = tuple[Translation, Key, Repository]

router = APIRouter()


# 5 min fresh, 24 h stale-while-revalidate. Tuned for the "typo fix" SLA:
# operators want a corrected string in users' hands within 5-10 minutes,
# while the long SWR window keeps the CDN serving (slightly stale) bytes
# even if the origin TMS is offline for a maintenance window.
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=86400"

# Length of the SHA-256 hex prefix used as the ETag body. 16 hex chars
# == 64 bits of entropy, which is way past the collision bar for the
# tiny working set (one ETag per project*locale*shape).
_ETAG_PREFIX_LEN = 16


def _weak_etag(payload: bytes) -> str:
    """Return a weak ETag header value for a payload.

    Weak (``W/`` prefix) because two byte-different payloads that
    semantically represent the same locale set (e.g. dict order under
    a future serializer change) should still be considered equivalent
    by intermediate caches. We stick with weak even though our current
    serializer is deterministic — it keeps the door open for cosmetic
    formatting changes without invalidating client caches.
    """
    digest = hashlib.sha256(payload).hexdigest()[:_ETAG_PREFIX_LEN]
    return f'W/"{digest}"'


def _flatten(rows: list[_Row]) -> dict[str, str]:
    """Collapse (translation, key, repository) triples to ``{key: value}``.

    If the same key appears in multiple repositories within a project
    (a project with both an iOS repo and an Android repo, say), the
    last write wins — same as a publication flow that flattens at
    the project level. Cross-platform key-name collisions are already
    a smell at the source-code level; we don't try to disambiguate
    them here.

    The ``Repository`` field is unused at the flatten step — it's kept
    in the row tuple because future per-row platform-specific
    serialization may need it (e.g. emitting xcstrings only for rows
    whose repo is ``ios-xcstrings``).
    """
    out: dict[str, str] = {}
    for translation, key, _repo in rows:
        if translation.value is not None:
            out[key.key] = translation.value
    return out


@router.get(
    "/{project_slug}/{locale}.json",
    responses={
        200: {"description": "Locale payload returned (or 304 with no body if ETag matches)."},
        304: {"description": "Client's ETag is still current; body intentionally empty."},
        404: {"description": "Project slug unknown or no published translations in that locale."},
    },
)
async def get_locale(
    project_slug: str,
    locale: str,
    request: Request,
    db: DB,
    platform: Literal["ios"] | None = None,
) -> Response:
    """Return the latest **published** translations for a project + locale.

    Public read — **no ``X-API-Key`` required**. Locale strings ship in
    published mobile apps, so treating them as confidential at the API
    boundary would be theatre. (Operators who genuinely need locked-down
    delivery should put a CDN edge auth layer in front of this endpoint
    and accept the cache-busting cost.)

    Response shape:

    * Default — flat JSON ``{ "<key>": "<value>", ... }``.
    * ``?platform=ios`` — Apple ``.strings`` plain-text format. Other
      platforms (Android XML, i18next nested JSON) are intentionally
      *not* exposed: their existing source-code build pipelines already
      consume the bundled file and OTA is a JSON-merge layer over that.

    Cache semantics:

    * ``Cache-Control: public, max-age=300, stale-while-revalidate=86400``
      — five minutes fresh, twenty-four hours stale-while-revalidate. The
      CDN can keep serving a slightly stale body for a day while it
      revalidates in the background. Picked to balance typo-fix
      propagation speed against origin load.
    * ``ETag: "W/<sha256-prefix>"`` — weak ETag (16-hex prefix of the
      SHA-256 of the serialized body). Clients pass it back via
      ``If-None-Match``; matches return 304 with no body, saving the
      CDN→client bytes which is most of the cost for cold-start traffic.
    * ``Vary: Accept-Encoding`` — gzip / brotli variants stay distinct
      in the CDN cache.

    404 vs empty:

    * Unknown ``project_slug`` → 404 (slug not in DB).
    * Known slug but no rows for ``locale`` in ``published`` → 404
      (clients can distinguish "no locale shipped yet" from "shipped
      but empty", which a 200 ``{}`` would not let them do).
    """
    rows = await list_published_translations_by_project_slug(db, project_slug, locale)

    if not rows:
        # Disambiguate "no such project" from "project exists but nothing
        # published for this locale yet". Both return 404, but the body
        # detail helps operators diagnose from CDN logs.
        slug_exists = await project_exists_by_slug(db, project_slug)
        if slug_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No published translations for project '{project_slug}' "
                    f"in locale '{locale}'. The project exists but nothing "
                    f"has been published to this locale yet."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_slug}' not found.",
        )

    flat = _flatten(rows)

    # Serialize to the requested shape. The JSON path is canonical;
    # ?platform=ios is a convenience for native bundle merge tooling.
    body: bytes
    content_type: str
    if platform == "ios":
        # serialize_strings is platform-agnostic over the flat dict — no
        # per-repository plural rules apply at this layer. (Plural rules
        # for ICU live in the writers' own helpers and aren't reached here.)
        text = serialize_strings(flat)
        body = text.encode("utf-8")
        # text/plain with utf-8 — Apple .strings has no registered MIME
        # type; mobile clients parse it as UTF-8 text.
        content_type = "text/plain; charset=utf-8"
    else:
        # Sort keys so the byte payload is stable across calls — required
        # for the ETag to be stable when the underlying set is unchanged.
        # ensure_ascii=False so unicode strings stay readable in DevTools;
        # the byte size is the same after gzip.
        text = json.dumps(flat, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        body = text.encode("utf-8")
        content_type = "application/json; charset=utf-8"

    etag = _weak_etag(body)

    # If-None-Match handling. RFC 7232: weak-vs-strong comparison is
    # weak for If-None-Match, so a substring match on the quoted hex
    # is the right test. We compare against the *whole* header value,
    # not a parsed list — clients we ship send a single tag.
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None and if_none_match.strip() == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "ETag": etag,
                "Cache-Control": _CACHE_CONTROL,
                "Vary": "Accept-Encoding",
            },
        )

    return Response(
        content=body,
        media_type=content_type,
        headers={
            "ETag": etag,
            "Cache-Control": _CACHE_CONTROL,
            "Vary": "Accept-Encoding",
        },
    )
