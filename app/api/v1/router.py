from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.api_keys import router as api_keys_router
from app.api.v1.endpoints.component_contexts import router as component_contexts_router
from app.api.v1.endpoints.glossary import router as glossary_router
from app.api.v1.endpoints.locale_configs import router as locale_configs_router
from app.api.v1.endpoints.orgs import router as orgs_router
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.repositories import router as repositories_router

router = APIRouter()

router.include_router(api_keys_router, prefix="/api-keys", tags=["API Keys"])
router.include_router(orgs_router, prefix="/organizations", tags=["Organizations"])
# Projects, repositories, locale-configs, and glossary are nested under their parents,
# so they mount at their parent prefix and carry sub-paths within the router.
router.include_router(projects_router, prefix="/organizations", tags=["Projects"])
router.include_router(repositories_router, prefix="/projects", tags=["Repositories"])
router.include_router(locale_configs_router, prefix="/projects", tags=["Locale Configs"])
router.include_router(component_contexts_router, prefix="/repositories", tags=["Component Contexts"])
router.include_router(glossary_router, prefix="/projects", tags=["Glossary"])

# Parallel agent routers — optional imports so the app starts without them.
try:
    from app.api.v1.endpoints.keys import router as keys_router  # type: ignore[import]

    router.include_router(keys_router, prefix="/keys", tags=["Keys"])
except ImportError:
    pass

try:
    from app.api.v1.endpoints.translations import router as translations_router  # type: ignore[import]

    router.include_router(translations_router, prefix="/translations", tags=["Translations"])
except ImportError:
    pass

try:
    from app.api.v1.endpoints.batches import router as batches_router  # type: ignore[import]

    router.include_router(batches_router, prefix="/batches", tags=["Batches"])
except ImportError:
    pass

# C3: the legacy `webhooks.py` stub (Phase 3 placeholder) shadowed the real
# /webhooks/github and /webhooks/contentful endpoints because FastAPI uses
# first-match route resolution. Stub removed; real routers mount directly.
try:
    from app.api.v1.endpoints.github_webhook import router as github_webhook_router
    from app.api.v1.endpoints.publication import router as publication_router

    router.include_router(github_webhook_router, prefix="/webhooks/github", tags=["GitHub"])
    router.include_router(publication_router, tags=["Publication"])
except ImportError:
    pass

try:
    from app.api.v1.endpoints.contentful_webhook import router as contentful_webhook_router

    router.include_router(contentful_webhook_router, prefix="/webhooks/contentful", tags=["Contentful"])
except ImportError:
    pass

# Phase 5 — Excel round-trip. Export and import shipped as parallel halves;
# both use try/except so partial merges (or future module renames) don't
# break app boot.
try:
    from app.api.v1.endpoints.exports import router as exports_router

    router.include_router(exports_router, prefix="/exports", tags=["Exports"])
except ImportError:
    pass

try:
    from app.api.v1.endpoints.imports import router as imports_router

    router.include_router(imports_router, prefix="/imports", tags=["Imports"])
except ImportError:
    pass

# Phase 7 — OTA locale delivery for mobile. Public read-only endpoint;
# no X-API-Key. Guarded with try/except to match the rest of this file's
# partial-merge tolerance, even though the OTA module has no optional deps.
try:
    from app.api.v1.endpoints.ota import router as ota_router

    router.include_router(ota_router, prefix="/ota", tags=["OTA"])
except ImportError:
    pass
