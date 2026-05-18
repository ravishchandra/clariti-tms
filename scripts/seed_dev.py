"""Seed dev database with one org, two repos, sample glossary terms."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib
import secrets

from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import ApiKey, GlossaryTerm, LocaleConfig, Organization, Project, Repository


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        # Org
        org = await db.scalar(select(Organization).where(Organization.slug == "dev"))
        if org is None:
            org = Organization(name="Dev Organization", slug="dev")
            db.add(org)
            await db.flush()
            print(f"  created org: {org.slug}")
        else:
            print(f"  org exists: {org.slug}")

        # Project
        project = await db.scalar(select(Project).where(Project.slug == "dev-project"))
        if project is None:
            project = Project(
                organization_id=org.id,
                name="Dev Project",
                slug="dev-project",
                source_locale="en-US",
                target_locales=["fr-FR", "de-DE", "es-ES"],
                style_guide="A professional mobile and web application.",
            )
            db.add(project)
            await db.flush()
            print(f"  created project: {project.slug}")
        else:
            print(f"  project exists: {project.slug}")

        # Repos
        for repo_name, platform, file_format in [
            ("ios", "ios", "ios-strings"),
            ("web", "web", "i18next"),
        ]:
            repo = await db.scalar(
                select(Repository).where(
                    Repository.project_id == project.id,
                    Repository.name == repo_name,
                )
            )
            if repo is None:
                repo = Repository(
                    project_id=project.id,
                    name=repo_name,
                    platform=platform,
                    file_format=file_format,
                )
                db.add(repo)
                print(f"  created repo: {repo_name}")
            else:
                print(f"  repo exists: {repo_name}")

        # Locale configs (bootstrap flags)
        for locale in ["fr-FR", "de-DE", "es-ES"]:
            lc = await db.scalar(
                select(LocaleConfig).where(
                    LocaleConfig.project_id == project.id,
                    LocaleConfig.locale == locale,
                )
            )
            if lc is None:
                db.add(
                    LocaleConfig(
                        project_id=project.id,
                        locale=locale,
                        is_bootstrapped=True,
                    )
                )
                print(f"  created locale config: {locale}")

        # Sample glossary
        terms = [
            ("Settings", "Paramètres", "fr-FR", "UI navigation term"),
            ("Settings", "Einstellungen", "de-DE", "UI navigation term"),
            ("Settings", "Configuración", "es-ES", "UI navigation term"),
            ("Cancel", "Annuler", "fr-FR", None),
            ("Cancel", "Abbrechen", "de-DE", None),
            ("Cancel", "Cancelar", "es-ES", None),
        ]
        for source_term, target_term, locale, notes in terms:
            existing = await db.scalar(
                select(GlossaryTerm).where(
                    GlossaryTerm.project_id == project.id,
                    GlossaryTerm.locale == locale,
                    GlossaryTerm.source_term == source_term,
                )
            )
            if existing is None:
                db.add(
                    GlossaryTerm(
                        project_id=project.id,
                        locale=locale,
                        source_term=source_term,
                        target_term=target_term,
                        notes=notes,
                    )
                )
                print(f"  glossary: {source_term} → {target_term} ({locale})")

        # Bootstrap an org-admin API key on a fresh database. We only mint a
        # key here when no keys exist — re-running the seed should not silently
        # create extra credentials, and the printed key is shown once.
        existing_keys = await db.scalar(select(sa_func.count()).select_from(ApiKey))
        if (existing_keys or 0) == 0:
            raw_key = secrets.token_hex(32)
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            db.add(
                ApiKey(
                    key_hash=key_hash,
                    name="seed-admin",
                    organization_id=org.id,
                    is_org_admin=True,
                )
            )
            print(f"\n  created org-admin API key (shown once): {raw_key}")
        else:
            print(f"\n  api keys exist ({existing_keys}); skipping admin-key bootstrap")

        await db.commit()
        print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
