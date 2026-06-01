"""Screenshot capture endpoints (Phase 7, docs/09:187).

Surfaces:

  * ``POST   /api/v1/keys/{key_id}/screenshots``  — multipart upload.
  * ``GET    /api/v1/keys/{key_id}/screenshots``  — list for a key.
  * ``GET    /api/v1/screenshots/{sid}/image``    — raw bytes (image/png|jpeg).
  * ``DELETE /api/v1/screenshots/{sid}``          — remove row + file.

**Storage**: the v1 backend writes images to ``infra/screenshots/{key_id}/{uuid}.{ext}``
on local disk. Cloud-object adapters (S3 / R2 / GCS) are intentionally a future
contribution — the boring filesystem choice means no new runtime dependency
for the OSS path. The chosen storage path is recorded in
``screenshots.storage_url`` as a relative URL (``/api/v1/screenshots/<id>/image``)
so the response shape is identical regardless of backend.

**Auth**: every route requires ``X-API-Key`` and scopes through ``scoped_key`` /
the screenshot's owning key so cross-org access returns 404, matching the
isolation contract verified by ``tests/api/test_tenant_isolation.py``.

**Module boundary** (CLAUDE.md): this module owns the ``screenshots`` table.
``keys`` is read indirectly through the existing ``scoped_key`` dep / a one-shot
SELECT join — never UPDATEd from here.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentKey, ScopedKey
from app.api.v1.schemas.screenshots import ScreenshotRead
from app.models import Key, Project, Repository, Screenshot

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config — kept local to this module so storage swaps don't ripple.
# --------------------------------------------------------------------------- #

# 10 MB hard cap on uploads. Mobile PNG screenshots at 3x scale rarely exceed
# 3-4 MB; 10 MB gives headroom for full-page captures without inviting OOM.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# PNG: 89 50 4E 47 0D 0A 1A 0A
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# JPEG: any JPEG starts with FF D8 FF and ends with FF D9 (we only check head).
_JPEG_MAGIC = b"\xff\xd8\xff"

# Storage root. Resolved lazily so tests can monkeypatch.
_STORAGE_ROOT = Path("infra/screenshots")


def _detect_image_kind(data: bytes) -> tuple[str, str] | None:
    """Return (extension, content_type) by sniffing magic bytes, else None.

    We don't trust the multipart Content-Type header — a hostile client can
    label `evil.exe` as `image/png`. Magic-byte detection is the canonical
    check for "is this really a PNG or JPEG".
    """
    if data.startswith(_PNG_MAGIC):
        return "png", "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "jpg", "image/jpeg"
    return None


def _content_type_for_path(path: Path) -> str:
    """Map a stored file's extension back to its Content-Type."""
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    # Defensive: we only ever write png/jpg, so this branch is unreachable
    # in normal operation. Fall back to a safe binary type rather than raising.
    return "application/octet-stream"


# --------------------------------------------------------------------------- #
# Routers — split into two so the prefix mounts in `router.py` line up with
# the existing convention (`/keys/...` vs `/screenshots/...`).
# --------------------------------------------------------------------------- #

router = APIRouter()  # mounted at /keys
screenshots_router = APIRouter()  # mounted at /screenshots


# --------------------------------------------------------------------------- #
# /keys/{key_id}/screenshots — upload + list
# --------------------------------------------------------------------------- #


@router.post(
    "/{key_id}/screenshots",
    status_code=status.HTTP_201_CREATED,
    response_model=ScreenshotRead,
)
async def upload_screenshot(
    db: DB,
    key: ScopedKey,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
) -> ScreenshotRead:
    """Accept a PNG / JPEG attached to a key.

    Validation runs in this order so the cheapest checks fail first:

      1. Size: ``file.size`` is the multipart-declared length (fast, but
         spoofable). After reading we double-check the real length so a
         lying client gets 413, not silent acceptance.
      2. Magic bytes: must start with the PNG or JPEG header. Spoofed
         Content-Types are rejected here as 422.
      3. Write to disk, then INSERT. If the INSERT fails we delete the
         orphan file in a ``try/except`` rather than leaving it.
    """
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds {_MAX_UPLOAD_BYTES} bytes.",
        )
    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Empty upload.",
        )

    detected = _detect_image_kind(raw)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File is not a PNG or JPEG (magic bytes did not match).",
        )
    ext, _content_type = detected

    # Disk layout: infra/screenshots/{key_id}/{uuid}.{ext}.
    # Per-key subdir means `ls` enumeration on the host stays readable and
    # `rm -rf infra/screenshots/{key_id}` cleanly drops everything when a
    # key is deleted (cascade is on the DB side; the file rm is best-effort).
    screenshot_id = uuid.uuid4()
    storage_dir = _STORAGE_ROOT / str(key.id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{screenshot_id}.{ext}"
    storage_path.write_bytes(raw)

    # The wire-level URL the UI hits to render the thumbnail. The Phase 6
    # key-detail page uses this directly as `<img src=...>` (see
    # `web/src/app/(app)/keys/[keyId]/page.tsx:649`).
    storage_url = f"/api/v1/screenshots/{screenshot_id}/image"

    screenshot = Screenshot(
        id=screenshot_id,
        key_id=key.id,
        storage_url=storage_url,
        caption=caption,
    )
    db.add(screenshot)
    try:
        await db.flush()
    except Exception:
        # If the INSERT loses the race, don't leak the on-disk file.
        # Catch broad — any DB failure should result in a clean rollback.
        try:
            storage_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "screenshot.cleanup_failed",
                extra={"event": "screenshot.cleanup_failed", "path": str(storage_path)},
            )
        raise

    await db.refresh(screenshot)
    logger.info(
        "screenshot.uploaded",
        extra={
            "event": "screenshot.uploaded",
            "key_id": str(key.id),
            "screenshot_id": str(screenshot.id),
            "bytes": len(raw),
            "ext": ext,
        },
    )
    return ScreenshotRead.model_validate(screenshot)


@router.get("/{key_id}/screenshots")
async def list_screenshots(
    db: DB,
    key: ScopedKey,
) -> dict[str, list[ScreenshotRead]]:
    """List every screenshot row tied to a key (oldest first)."""
    result = await db.execute(select(Screenshot).where(Screenshot.key_id == key.id).order_by(Screenshot.uploaded_at))
    rows = result.scalars().all()
    return {"items": [ScreenshotRead.model_validate(s) for s in rows]}


# --------------------------------------------------------------------------- #
# /screenshots/{sid}/image and /screenshots/{sid} — fetch raw bytes + delete.
# --------------------------------------------------------------------------- #


async def _scoped_screenshot(
    screenshot_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Screenshot:
    """Fetch a screenshot iff its key's owning project is in the caller's org.

    Walks Screenshot → Key → Repository → Project — same defense-in-depth
    pattern as ``scoped_translation`` (avoids trusting the denormalized
    ``Key.project_id``).
    """
    result = await db.execute(
        select(Screenshot)
        .join(Key, Screenshot.key_id == Key.id)
        .join(Repository, Key.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .where(
            Screenshot.id == screenshot_id,
            Project.organization_id == current_key.organization_id,
        )
    )
    screenshot = result.scalar_one_or_none()
    if screenshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return screenshot


@screenshots_router.get("/{screenshot_id}/image")
async def get_screenshot_image(
    screenshot_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Response:
    """Serve the raw image bytes with a correct Content-Type.

    ``Cache-Control: private, max-age=86400`` — screenshots are tenant-scoped
    so we want browser caching but never shared-cache caching. 24h is short
    enough to absorb a re-upload-with-same-id flow if it ever happens.
    """
    screenshot = await _scoped_screenshot(screenshot_id, db, current_key)

    # The wire URL is the public identifier; the on-disk path is derived
    # from the screenshot id + the key it belongs to. We don't trust the
    # storage_url string itself (it could in principle be edited via a
    # future migration); rebuild the path deterministically.
    storage_dir = _STORAGE_ROOT / str(screenshot.key_id)
    # We don't know the extension from the row — probe both. Files are
    # always PNG or JPEG (validated at upload time).
    for ext in ("png", "jpg", "jpeg"):
        candidate = storage_dir / f"{screenshot.id}.{ext}"
        if candidate.exists():
            return FileResponse(
                candidate,
                media_type=_content_type_for_path(candidate),
                headers={"Cache-Control": "private, max-age=86400"},
            )

    # Row exists but the file vanished — disk and DB drifted. Surface as
    # 404 with a structured log so an operator can investigate.
    logger.error(
        "screenshot.file_missing",
        extra={
            "event": "screenshot.file_missing",
            "screenshot_id": str(screenshot.id),
            "key_id": str(screenshot.key_id),
            "expected_dir": str(storage_dir),
        },
    )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot file not found")


@screenshots_router.delete("/{screenshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screenshot(
    screenshot_id: uuid.UUID,
    db: DB,
    current_key: CurrentKey,
) -> Response:
    """Remove the DB row and the on-disk file.

    File deletion is best-effort: if the row was already orphaned (file
    missing) we still drop the row. If the file delete fails for a real
    reason (permissions, etc.) we log and continue — the alternative is
    leaving a dangling row that points at unreachable bytes.
    """
    screenshot = await _scoped_screenshot(screenshot_id, db, current_key)
    key_id = screenshot.key_id

    await db.delete(screenshot)
    await db.flush()

    storage_dir = _STORAGE_ROOT / str(key_id)
    for ext in ("png", "jpg", "jpeg"):
        candidate = storage_dir / f"{screenshot_id}.{ext}"
        try:
            if candidate.exists():
                candidate.unlink()
        except OSError:
            logger.warning(
                "screenshot.file_unlink_failed",
                extra={
                    "event": "screenshot.file_unlink_failed",
                    "screenshot_id": str(screenshot_id),
                    "path": str(candidate),
                },
            )

    # If the per-key directory is now empty, prune it. Cheap and keeps the
    # filesystem tidy.
    try:
        if storage_dir.exists() and not any(storage_dir.iterdir()):
            storage_dir.rmdir()
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Exposed for tests so they can redirect storage to a tmp dir.
def _set_storage_root_for_tests(path: Path) -> None:
    """Test-only escape hatch. Production code never calls this."""
    global _STORAGE_ROOT
    _STORAGE_ROOT = path


def _reset_storage_root_for_tests() -> None:
    """Restore the package-level default after a test."""
    global _STORAGE_ROOT
    _STORAGE_ROOT = Path("infra/screenshots")
