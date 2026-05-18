"""loc — Clariti TMS command-line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

app = typer.Typer(
    name="loc",
    help="Clariti TMS — translation management CLI",
    no_args_is_help=True,
)
console = Console()
err = Console(stderr=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TMS_YML_NAME = "tms.yml"

PLATFORM_FORMATS = {
    "ios": ["ios-strings", "ios-xcstrings"],
    "android": ["android-xml"],
    "web": ["i18next", "icu", "flat-json"],
    "backend": ["i18next", "flat-json"],
}

FILE_FORMAT_EXTENSIONS = {
    ".strings": "ios-strings",
    ".xcstrings": "ios-xcstrings",
    ".stringsdict": "ios-stringsdict",
    ".xml": "android-xml",
    ".json": "i18next",
}


def _detect_format(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    return FILE_FORMAT_EXTENSIONS.get(ext)


def _load_tms_yml(cwd: Path) -> dict:
    p = cwd / TMS_YML_NAME
    if not p.exists():
        err.print(f"[red]No {TMS_YML_NAME} found in {cwd}.[/red]\nRun [bold]loc init[/bold] to set up this repository.")
        raise typer.Exit(1)
    import yaml  # lazy — only needed when tms.yml exists

    return yaml.safe_load(p.read_text()) or {}


# ---------------------------------------------------------------------------
# loc init
# ---------------------------------------------------------------------------


@app.command()
def init(
    cwd: Path = typer.Option(Path("."), "--dir", "-d", help="Repository root"),
) -> None:
    """Scaffold tms.yml for this repository."""
    cwd = cwd.resolve()
    out = cwd / TMS_YML_NAME

    if out.exists():
        overwrite = typer.confirm(f"{TMS_YML_NAME} already exists. Overwrite?", default=False)
        if not overwrite:
            raise typer.Exit(0)

    console.print("\n[bold]Clariti TMS — repository setup[/bold]\n")

    # Repo name
    repo_name = typer.prompt("Repository name (e.g. ios, android, frontend)", default=cwd.name)

    # Platform
    platform_choices = ["ios", "android", "web", "backend", "other"]
    console.print(f"Platform: {', '.join(platform_choices)}")
    platform = typer.prompt("Platform", default="web")
    while platform not in platform_choices:
        err.print(f"[red]Choose one of: {', '.join(platform_choices)}[/red]")
        platform = typer.prompt("Platform", default="web")

    # File format
    formats = PLATFORM_FORMATS.get(platform, ["i18next"])
    if len(formats) == 1:
        file_format = formats[0]
        console.print(f"File format: [dim]{file_format}[/dim] (auto-detected)")
    else:
        console.print(f"File format: {', '.join(formats)}")
        file_format = typer.prompt("File format", default=formats[0])

    # Source file
    source_file = typer.prompt(
        "Source strings file (relative path)",
        default={
            "ios": "Localizable.strings",
            "android": "app/src/main/res/values/strings.xml",
            "web": "src/locales/en/common.json",
            "backend": "locales/en.json",
            "other": "locales/en.json",
        }.get(platform, "locales/en.json"),
    )

    # Target locales
    locales_raw = typer.prompt("Target locales (comma-separated)", default="fr-FR,de-DE,es-ES")
    target_locales = [loc.strip() for loc in locales_raw.split(",") if loc.strip()]

    # TMS server
    server_url = typer.prompt("TMS server URL", default="http://localhost:8000")

    # Domain description (goes into every LLM prompt)
    domain = typer.prompt(
        "Describe this app in one sentence (used in translation prompts)",
        default="A professional mobile and web application.",
    )

    config = {
        "repo": repo_name,
        "platform": platform,
        "file_format": file_format,
        "source_file": source_file,
        "target_locales": target_locales,
        "server": server_url,
        "domain_description": domain,
        "llm": {
            "provider": "anthropic",
            "fallback_provider": "openai",
        },
    }

    # Write YAML manually (avoid PyYAML dependency at init time)
    lines = [
        "# Clariti TMS — repository configuration",
        f"repo: {config['repo']}",
        f"platform: {config['platform']}",
        f"file_format: {config['file_format']}",
        f"source_file: {config['source_file']}",
        "target_locales:",
        *[f"  - {loc}" for loc in config["target_locales"]],
        f"server: {config['server']}",
        f'domain_description: "{config["domain_description"]}"',
        "llm:",
        f"  provider: {config['llm']['provider']}",
        f"  fallback_provider: {config['llm']['fallback_provider']}",
    ]
    out.write_text("\n".join(lines) + "\n")

    console.print(f"\n[green]✓[/green] Created [bold]{out}[/bold]")
    console.print("\nNext step:")
    console.print(f"  [bold]loc ingest-file {source_file} --repo {repo_name}[/bold]")


# ---------------------------------------------------------------------------
# loc ingest-file
# ---------------------------------------------------------------------------


@app.command(name="ingest-file")
def ingest_file(
    path: str = typer.Argument(..., help="Path to source strings file"),
    repo: str = typer.Option(None, "--repo", help="Repository name (overrides tms.yml)"),
    file_format: str = typer.Option(None, "--format", help="File format override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse only, do not write to DB"),
    server: str = typer.Option(None, "--server", help="TMS server URL override"),
) -> None:
    """Parse a source strings file and upsert keys into the TMS."""
    asyncio.run(_ingest_file(path, repo, file_format, dry_run, server))


async def _ingest_file(
    path: str,
    repo_name: str | None,
    file_format: str | None,
    dry_run: bool,
    server_override: str | None,
) -> None:
    from app.ingestion.parsers import parse_file

    file_path = Path(path).resolve()
    if not file_path.exists():
        err.print(f"[red]File not found:[/red] {path}")
        raise typer.Exit(1)

    # Detect format
    fmt = file_format or _detect_format(file_path.name)
    if fmt is None:
        err.print(
            f"[red]Cannot detect file format for {file_path.name}.[/red]\n"
            "Use [bold]--format[/bold] to specify: ios-strings, ios-xcstrings, "
            "android-xml, i18next, icu, flat-json"
        )
        raise typer.Exit(1)

    # Parse
    content = file_path.read_text(encoding="utf-8")
    try:
        result = parse_file(content, file_path.name, fmt)
    except Exception as exc:
        err.print(f"[red]Parse error:[/red] {exc}")
        raise typer.Exit(1)

    key_count = len(result.keys)

    if dry_run:
        # Show a preview table
        console.print(f"\n[bold]Dry run:[/bold] {file_path.name} ({fmt}, {key_count} keys)\n")
        table = Table("Key", "Component", "Risk", "Structural", "ICU", show_header=True)
        for k in result.keys[:20]:
            table.add_row(
                k.key,
                k.component or "—",
                k.risk_class,
                "✓" if k.has_structural_tags else "",
                k.icu_shape if k.icu_shape != "plain" else "",
            )
        console.print(table)
        if key_count > 20:
            console.print(f"  [dim]… and {key_count - 20} more[/dim]")
        return

    # Check if server is running; if so, use API. Otherwise write directly to DB.
    # For Phase 1 (before Phase 3 REST API), write directly via SQLAlchemy.
    tms_config_path = Path(".") / TMS_YML_NAME
    if not tms_config_path.exists():
        err.print(
            "[yellow]No tms.yml found — writing directly to local DB.[/yellow]\n"
            "Run [bold]loc init[/bold] to configure repository settings."
        )

    await _ingest_direct(result, repo_name or file_path.stem, key_count)


async def _ingest_direct(result, repo_name: str, key_count: int) -> None:
    """Write directly to the DB (Phase 1 path — before REST API exists)."""
    from app.core.database import AsyncSessionLocal
    from app.ingestion.service import assemble_batches, upsert_keys
    from app.models import Organization, Project, Repository

    async with AsyncSessionLocal() as db:
        # Find or create a dev organization/project/repository
        org = await db.scalar(select(Organization).where(Organization.slug == "dev"))
        if org is None:
            org = Organization(name="Dev Organization", slug="dev")
            db.add(org)
            await db.flush()

        project = await db.scalar(select(Project).where(Project.slug == "dev-project"))
        if project is None:
            project = Project(
                organization_id=org.id,
                name="Dev Project",
                slug="dev-project",
                target_locales=["fr-FR", "de-DE"],
            )
            db.add(project)
            await db.flush()

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
                platform=result.platform,
                file_format=result.file_format,
            )
            db.add(repo)
            await db.flush()

        await db.commit()

        # Upsert keys
        summary = await upsert_keys(
            db=db,
            result=result,
            repository_id=str(repo.id),
            project_id=str(project.id),
            target_locales=project.target_locales,
        )

        # Assemble screen batches
        batch_count = await assemble_batches(
            db=db,
            repository_id=str(repo.id),
            project_id=str(project.id),
        )

    # Print summary
    console.print(f"\n[green]✓[/green] Ingested [bold]{result.source_file}[/bold]")
    console.print(
        f"  {summary['inserted']} inserted · "
        f"{summary['updated']} updated · "
        f"{summary['unchanged']} unchanged · "
        f"{summary['deactivated']} deactivated"
    )
    console.print(f"  {batch_count} translation batch(es) queued for MT")


# ---------------------------------------------------------------------------
# loc translate (stub)
# ---------------------------------------------------------------------------


@app.command()
def translate(
    project: str = typer.Option(..., "--project", help="Project slug"),
    locale: str = typer.Option(None, "--locale", help="Target locale (e.g. fr-FR); omit to run all locales"),
    provider: str = typer.Option("anthropic", "--provider", help="LLM provider"),
    max_batches: int = typer.Option(None, "--max-batches", help="Stop after N batches"),
) -> None:
    """Run MT on all pending batches for a project (optionally filtered to one locale)."""
    asyncio.run(_translate(project, locale, provider, max_batches))


async def _translate(project_slug: str, locale: str | None, provider_name: str, max_batches: int | None) -> None:
    from app.core.database import AsyncSessionLocal
    from app.core.settings import get_settings
    from app.llm.providers.anthropic import AnthropicProvider
    from app.llm.providers.openai import OpenAIProvider
    from app.llm.providers.openrouter import OpenRouterProvider
    from app.models import BatchStatus, Project, TranslationBatch
    from app.mt.worker import run_worker

    settings = get_settings()

    providers: dict = {}
    if settings.ANTHROPIC_API_KEY:
        providers["anthropic"] = AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
    if settings.OPENAI_API_KEY:
        providers["openai"] = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
    if settings.OPENROUTER_API_KEY:
        providers["openrouter"] = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)

    if not providers:
        err.print("[red]No API keys configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.[/red]")
        raise typer.Exit(1)

    if provider_name not in providers:
        err.print(f"[red]Provider '{provider_name}' not available — missing API key.[/red]")
        raise typer.Exit(1)

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)
        q = select(TranslationBatch).where(
            TranslationBatch.project_id == project.id,
            TranslationBatch.status == BatchStatus.pending,
        )
        if locale:
            q = q.where(TranslationBatch.locale == locale)
        batch_list = list(await db.scalars(q))

    if not batch_list:
        label = f"{project_slug} / {locale}" if locale else project_slug
        console.print(f"[dim]No pending batches for {label}.[/dim]")
        return

    locales_label = locale or "all locales"
    console.print(f"\nRunning MT on [bold]{len(batch_list)}[/bold] batch(es) — {project_slug} / {locales_label}\n")

    await run_worker(
        providers=providers,
        max_batches=max_batches or len(batch_list),
        config_provider=provider_name,
        embed_provider="openai" if "openai" in providers else provider_name,
        project_id=str(project.id),
        locale=locale,
    )
    console.print(f"\n[green]✓[/green] MT complete for {locales_label}")


# ---------------------------------------------------------------------------
# loc api-key
# ---------------------------------------------------------------------------


@app.command(name="api-key")
def api_key(
    name: str = typer.Option("default", "--name", help="Human label for this key"),
    org: str = typer.Option(None, "--org", help="Organization slug (defaults to first org)"),
) -> None:
    """Generate an API key and print it. Store it — it is shown only once."""
    asyncio.run(_api_key(name, org))


async def _api_key(name: str, org_slug: str | None) -> None:
    import hashlib
    import secrets

    from sqlalchemy import func as sa_func

    from app.core.database import AsyncSessionLocal
    from app.models import ApiKey, Organization

    async with AsyncSessionLocal() as db:
        if org_slug:
            organization = await db.scalar(select(Organization).where(Organization.slug == org_slug))
            if organization is None:
                err.print(f"[red]Organization '{org_slug}' not found.[/red]")
                raise typer.Exit(1)
        else:
            organization = await db.scalar(select(Organization))
            if organization is None:
                err.print("[red]No organizations found. Run `loc init` first.[/red]")
                raise typer.Exit(1)

        # The first key in an empty database is an org-admin (allowed to create
        # and delete organizations via the API). Subsequent CLI-minted keys are
        # ordinary tenant keys.
        existing_count = await db.scalar(select(sa_func.count()).select_from(ApiKey))
        is_admin = (existing_count or 0) == 0

        raw_key = secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key_obj = ApiKey(
            key_hash=key_hash,
            name=name,
            organization_id=organization.id,
            is_org_admin=is_admin,
        )
        db.add(api_key_obj)
        await db.commit()

    role = "org-admin" if is_admin else "tenant"
    console.print(f"\n[bold green]API key created[/bold green] ({name} / {organization.slug}) [{role}]")
    console.print(f"\n  [bold]{raw_key}[/bold]\n")
    console.print("[dim]This is shown once. Add it to your .env as API_KEY= or pass via X-API-Key header.[/dim]\n")


# ---------------------------------------------------------------------------
# loc status
# ---------------------------------------------------------------------------


@app.command()
def status(
    project: str = typer.Option(..., "--project", help="Project slug"),
    locale: str = typer.Option(None, "--locale", help="Filter to a single locale"),
) -> None:
    """Show translation coverage for a project."""
    asyncio.run(_status(project, locale))


async def _status(project_slug: str, locale_filter: str | None) -> None:
    from sqlalchemy import func as sa_func

    from app.core.database import AsyncSessionLocal
    from app.models import Key, Project, Translation, TranslationStatus

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)

        total_keys = await db.scalar(
            select(sa_func.count(Key.id)).where(
                Key.project_id == project.id,
                Key.is_active.is_(True),
            )
        )

        q = (
            select(
                Translation.locale,
                Translation.status,
                sa_func.count(Translation.id).label("cnt"),
            )
            .join(Key, Translation.key_id == Key.id)
            .where(
                Key.project_id == project.id,
                Key.is_active.is_(True),
            )
            .group_by(Translation.locale, Translation.status)
            .order_by(Translation.locale)
        )
        if locale_filter:
            q = q.where(Translation.locale == locale_filter)

        rows = (await db.execute(q)).all()

    # Aggregate by locale
    from collections import defaultdict

    locale_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row_locale, row_status, cnt in rows:
        locale_stats[row_locale][row_status] = cnt

    console.print(f"\nProject: [bold]{project_slug}[/bold]\n")
    table = Table("Locale", "Total", "Needs Revw", "Approved", "Coverage", show_header=True)
    for loc in sorted(locale_stats):
        stats = locale_stats[loc]
        total = total_keys or 0
        needs_review = stats.get(TranslationStatus.needs_review, 0)
        approved = stats.get(TranslationStatus.approved, 0) + stats.get(TranslationStatus.published, 0)
        coverage = f"{int(approved / total * 100)}%" if total else "—"
        table.add_row(loc, str(total), str(needs_review), str(approved), coverage)
    console.print(table)


# ---------------------------------------------------------------------------
# loc add
# ---------------------------------------------------------------------------


@app.command(name="add")
def add_key(
    project: str = typer.Option(..., "--project", help="Project slug"),
    key: str = typer.Option(..., "--key", help="Translation key identifier"),
    text: str = typer.Option(..., "--text", help="Source text (English)"),
    context: str = typer.Option(None, "--context", help="Optional translator context note"),
    repo: str = typer.Option(None, "--repo", help="Repository name (defaults to first repo in project)"),
) -> None:
    """Add a new translation key and queue it for MT."""
    asyncio.run(_add_key(project, key, text, context, repo))


async def _add_key(
    project_slug: str,
    key_name: str,
    source_text: str,
    context: str | None,
    repo_name: str | None,
) -> None:
    import hashlib

    from app.core.database import AsyncSessionLocal
    from app.ingestion.parsers.common import detect_structural_tags, infer_risk_class, infer_string_type
    from app.ingestion.service import assemble_batches
    from app.models import Key, Project, Repository, Translation, TranslationStatus

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)

        if repo_name:
            repository = await db.scalar(
                select(Repository).where(
                    Repository.project_id == project.id,
                    Repository.name == repo_name,
                )
            )
            if repository is None:
                err.print(f"[red]Repository '{repo_name}' not found in project '{project_slug}'.[/red]")
                raise typer.Exit(1)
        else:
            repository = await db.scalar(select(Repository).where(Repository.project_id == project.id))
            if repository is None:
                err.print(f"[red]No repositories found for project '{project_slug}'.[/red]")
                raise typer.Exit(1)

        existing = await db.scalar(
            select(Key).where(
                Key.repository_id == repository.id,
                Key.key == key_name,
            )
        )
        if existing is not None:
            err.print(f"[red]Key '{key_name}' already exists in repository '{repository.name}'.[/red]")
            raise typer.Exit(1)

        file_format = repository.file_format
        has_structural = detect_structural_tags(source_text, file_format)
        string_type = infer_string_type(key_name, source_text, has_structural_tags=has_structural)
        risk_class = infer_risk_class(key_name, source_text, string_type)
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()

        new_key = Key(
            repository_id=repository.id,
            project_id=project.id,
            key=key_name,
            source_text=source_text,
            source_hash=source_hash,
            string_type=string_type,
            risk_class=risk_class,
            has_structural_tags=has_structural,
            description=context,
            source="cli",
        )
        db.add(new_key)
        await db.flush()

        for locale in project.target_locales:
            db.add(Translation(key_id=new_key.id, locale=locale, status=TranslationStatus.draft))

        await db.commit()

        batch_count = await assemble_batches(
            db=db,
            repository_id=str(repository.id),
            project_id=str(project.id),
        )

    console.print(f"\n[green]✓[/green] Added key [bold]{key_name}[/bold]")
    console.print(f"  string_type={string_type} · risk_class={risk_class} · structural_tags={has_structural}")
    console.print(f"  {len(project.target_locales)} draft translation(s) created · {batch_count} batch(es) queued")


# ---------------------------------------------------------------------------
# loc pull
# ---------------------------------------------------------------------------


@app.command()
def pull(
    project: str = typer.Option(..., "--project", help="Project slug"),
    locale: str = typer.Option(None, "--locale", help="Filter to a single locale"),
    output_dir: str = typer.Option(".", "--output-dir", help="Directory to write locale files into"),
) -> None:
    """Fetch approved translations and write them to local locale files."""
    asyncio.run(_pull(project, locale, output_dir))


async def _pull(project_slug: str, locale_filter: str | None, output_dir: str) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models import Key, Project, Repository, Translation, TranslationStatus

    try:
        from app.publication.helpers import locale_file_path, serialize_locale_file
    except ImportError:
        err.print(
            "[red]app.publication.helpers not found.[/red] "
            "This module is provided by a parallel agent — ensure it exists before running loc pull."
        )
        raise typer.Exit(1)

    out_root = Path(output_dir).resolve()
    files_written: list[Path] = []

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)

        repos = list(await db.scalars(select(Repository).where(Repository.project_id == project.id)))
        if not repos:
            console.print(f"[dim]No repositories found for project '{project_slug}'.[/dim]")
            return

        for repository in repos:
            q = (
                select(Key.key, Translation.locale, Translation.value)
                .join(Translation, Translation.key_id == Key.id)
                .where(
                    Key.repository_id == repository.id,
                    Key.is_active.is_(True),
                    Translation.status.in_([TranslationStatus.approved, TranslationStatus.published]),
                    Translation.value.isnot(None),
                )
                .order_by(Translation.locale, Key.key)
            )
            if locale_filter:
                q = q.where(Translation.locale == locale_filter)

            rows = (await db.execute(q)).all()
            if not rows:
                continue

            # Group by locale
            from collections import defaultdict

            by_locale: dict[str, dict[str, str]] = defaultdict(dict)
            for key_name, loc, value in rows:
                by_locale[loc][key_name] = value

            for loc, translations in by_locale.items():
                content = serialize_locale_file(translations, repository, loc)
                rel_path = locale_file_path(repository, loc)
                dest = out_root / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
                files_written.append(dest)

    if not files_written:
        console.print("[dim]No approved translations found — nothing written.[/dim]")
        return

    console.print(f"\n[green]✓[/green] Wrote {len(files_written)} locale file(s) to {out_root}")
    for f in files_written:
        console.print(f"  {f.relative_to(out_root)}")


# ---------------------------------------------------------------------------
# loc export / import (stubs)
# ---------------------------------------------------------------------------


@app.command()
def export(
    project: str = typer.Option(..., "--project"),
    locales: str = typer.Option(..., "--locales"),
    output: str = typer.Option("./export.xlsx", "--output"),
) -> None:
    """Export translations to Excel. (Phase 5)"""
    console.print("[dim]loc export — Phase 5[/dim]")


@app.command(name="import")
def import_file(
    file: str = typer.Option(..., "--file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    commit: bool = typer.Option(False, "--commit"),
    rollback: str = typer.Option(None, "--rollback"),
) -> None:
    """Import translations from Excel. (Phase 5)"""
    console.print("[dim]loc import — Phase 5[/dim]")


# ---------------------------------------------------------------------------
# loc eval
# ---------------------------------------------------------------------------


@app.command()
def eval(
    reference: str = typer.Option(..., "--reference", help="Path to reference JSON"),
    prompt: str = typer.Option("translate_v1", "--prompt", help="Prompt version label"),
    provider: str = typer.Option("anthropic", "--provider"),
    output: str = typer.Option(None, "--output", help="Save results to JSON file"),
) -> None:
    """Run eval harness against a reference translation set."""
    asyncio.run(_eval(reference, prompt, provider, output))


async def _eval(reference: str, prompt_version: str, provider_name: str, output: str | None) -> None:
    from app.core.settings import get_settings
    from app.llm.providers.anthropic import AnthropicProvider
    from app.llm.providers.openai import OpenAIProvider
    from app.llm.providers.openrouter import OpenRouterProvider
    from app.mt.eval import run_eval

    settings = get_settings()
    providers: dict = {}
    if settings.ANTHROPIC_API_KEY:
        providers["anthropic"] = AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
    if settings.OPENAI_API_KEY:
        providers["openai"] = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
    if settings.OPENROUTER_API_KEY:
        providers["openrouter"] = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)

    if provider_name not in providers:
        err.print(f"[red]Provider '{provider_name}' not available.[/red]")
        raise typer.Exit(1)

    prov = providers[provider_name]
    embed_prov = providers.get("openai", prov)

    ref_path = Path(reference).resolve()
    if not ref_path.exists():
        err.print(f"[red]Reference file not found: {reference}[/red]")
        raise typer.Exit(1)

    console.print(f"\nRunning eval: [bold]{prompt_version}[/bold] vs {ref_path.name}\n")
    results = await run_eval(ref_path, prompt_version, prov.translate, embed_prov.embed)

    console.print(f"  Strings:    {results['string_count']}")
    console.print(f"  Avg BLEU:   {results['avg_bleu']:.4f}")
    console.print(f"  Avg SemSim: {results['avg_semantic_similarity']:.4f}")

    if output:
        import json as _json

        Path(output).write_text(_json.dumps(results, indent=2, ensure_ascii=False))
        console.print(f"\n[green]✓[/green] Results saved to {output}")


# ---------------------------------------------------------------------------
# loc export-tm / loc import-tm
# ---------------------------------------------------------------------------


@app.command(name="export-tm")
def export_tm(
    project: str = typer.Option(..., "--project"),
    locale: str = typer.Option(..., "--locale"),
    output: str = typer.Option(None, "--output", help="Output .tmx file (default: <project>-<locale>.tmx)"),
) -> None:
    """Export translation memory to TMX."""
    asyncio.run(_export_tm(project, locale, output))


async def _export_tm(project_slug: str, locale: str, output: str | None) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models import Project
    from app.mt.tmx import export_tmx

    out_path = Path(output) if output else Path(f"{project_slug}-{locale}.tmx")
    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)
        count = await export_tmx(db, str(project.id), locale, out_path)
    console.print(f"[green]✓[/green] Exported {count} TM entries to {out_path}")


@app.command(name="import-tm")
def import_tm(
    file: str = typer.Argument(..., help="Path to .tmx file"),
    project: str = typer.Option(..., "--project"),
    platform: str = typer.Option("web", "--platform"),
) -> None:
    """Import translation memory from TMX."""
    asyncio.run(_import_tm(file, project, platform))


async def _import_tm(tmx_path: str, project_slug: str, platform: str) -> None:
    from app.core.database import AsyncSessionLocal
    from app.models import Project
    from app.mt.tmx import import_tmx

    path = Path(tmx_path).resolve()
    if not path.exists():
        err.print(f"[red]File not found: {tmx_path}[/red]")
        raise typer.Exit(1)

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)
        summary = await import_tmx(db, str(project.id), path, platform)
    console.print(f"[green]✓[/green] Imported {summary['imported']} TM entries ({summary['skipped']} skipped)")


# ---------------------------------------------------------------------------
# loc demo — end-to-end walkthrough without any API keys
# ---------------------------------------------------------------------------


@app.command()
def demo(
    locale: str = typer.Option("fr-FR", "--locale", help="Target locale for the demo"),
) -> None:
    """Run an end-to-end demo with a mock LLM provider (no API keys required).

    Walks through the canonical flow: seed → ingest → translate → status.
    Useful for evaluating Clariti TMS before configuring real providers.

    Each invocation creates a fresh, timestamped demo project so previous
    runs are preserved (and the DB doesn't need a destructive reset).

    Requires:
    - Postgres running (`docker compose up -d postgres`)
    - Migrations applied (`cd infra && alembic upgrade head`)
    """
    asyncio.run(_demo(locale))


async def _demo(target_locale: str) -> None:
    import json
    import tempfile
    from datetime import UTC, datetime

    from rich.panel import Panel

    from app.core.database import AsyncSessionLocal
    from app.ingestion.parsers import parse_file
    from app.ingestion.service import assemble_batches, upsert_keys
    from app.llm.protocol import LLMProviderBase, TokenUsage
    from app.llm.registry import registry
    from app.models import (
        Key,
        LocaleConfig,
        Organization,
        Project,
        Repository,
        Translation,
        TranslationBatch,
    )
    from app.mt.service import translate_batch

    # ----- Mock LLM provider --------------------------------------------------

    class DemoProvider(LLMProviderBase):
        """In-process mock provider for the demo.

        ``translate()`` parses the last JSON object out of the user prompt
        (the prompt template ends with ``{{ strings | tojson }}``), then
        returns each value prefixed with a locale tag so the round-trip is
        visible. ``evaluate()`` returns canned QA scores. ``embed()``
        returns a deterministic 1536-d zero-vector — enough for TM storage
        without similarity to anything else.
        """

        @staticmethod
        def _extract_strings_block(prompt: str) -> dict[str, str]:
            """Return the JSON dict at the end of the rendered prompt.

            Source values can contain literal ``{{name}}`` i18next
            placeholders — those are *inside double-quoted strings* in the
            JSON, not nested objects. A naive `{...}` regex matches the
            inner ``{{name}}`` and breaks parsing. Instead, walk forward
            from the strings-block opening brace (the prompt template
            renders ``{{ strings | tojson(indent=2) }}`` so the opening
            ``{`` sits at column 0 of its own line), tracking depth and
            respecting quoted strings.
            """
            start = prompt.rfind("\n{")
            if start == -1:
                return {}
            start += 1
            depth = 0
            in_string = False
            escape = False
            end = -1
            for i in range(start, len(prompt)):
                ch = prompt[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end == -1:
                return {}
            return json.loads(prompt[start:end])

        async def translate(self, prompt: str, system: str, *, cache_system: bool = False) -> tuple[str, TokenUsage]:
            strings = self._extract_strings_block(prompt)
            tag = f"[{target_locale}]"
            out = {k: f"{tag} {v}" for k, v in strings.items()}
            return json.dumps(out, ensure_ascii=False), {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(json.dumps(out)) // 4,
            }

        async def evaluate(self, prompt: str) -> tuple[str, TokenUsage]:
            # Mid-range scores so review-policy routing doesn't force review
            # solely on QA grounds. Validation can still force review on
            # placeholder mismatch, etc.
            return (
                json.dumps({"naturalness": 4, "consistency": 4, "accuracy": 4, "issue": None}),
                {"input_tokens": 50, "output_tokens": 30},
            )

        async def embed(self, text: str) -> list[float]:
            return [0.0] * 1536

        @property
        def model_id(self) -> str:
            return "demo-mock-v1"

        @property
        def provider_name(self) -> str:
            return "demo"

        @property
        def price_per_1k_input(self) -> float:
            return 0.0

        @property
        def price_per_1k_output(self) -> float:
            return 0.0

    # ----- Demo flow ----------------------------------------------------------

    console.print(
        Panel.fit(
            "[bold cyan]Clariti TMS demo[/bold cyan]\n"
            f"Target locale: [bold]{target_locale}[/bold]\n"
            "Provider: [bold]demo[/bold] (mock, no API key required)\n\n"
            "[dim]Walks: seed → ingest → translate → status[/dim]",
            border_style="cyan",
        )
    )

    async with AsyncSessionLocal() as db:
        # Step 1 — seed a fresh demo project + repo + locale config -----------
        # Each run is timestamped so prior runs are preserved and we never
        # have to delete data (which trips FK NOT NULL constraints if the
        # CASCADE chain isn't perfect).
        run_id = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        console.print(f"\n[bold][1/4][/bold] Seeding demo project ([dim]run {run_id}[/dim]) ...")

        org = await db.scalar(select(Organization).where(Organization.slug == "demo"))
        if org is None:
            org = Organization(name="Demo Org", slug="demo")
            db.add(org)
            await db.flush()

        project_slug = f"demo-{run_id}"
        project = Project(
            organization_id=org.id,
            name=f"Demo Project ({run_id})",
            slug=project_slug,
            source_locale="en-US",
            target_locales=[target_locale],
            style_guide="A friendly consumer-facing mobile app.",
        )
        db.add(project)
        await db.flush()

        repo = Repository(
            project_id=project.id,
            name="demo-web",
            platform="web",
            file_format="i18next",
        )
        db.add(repo)
        await db.flush()

        # Locale config — mark bootstrapped so the review policy doesn't force
        # every batch into needs_review for the demo.
        lc = await db.scalar(
            select(LocaleConfig).where(
                LocaleConfig.project_id == project.id,
                LocaleConfig.locale == target_locale,
            )
        )
        if lc is None:
            db.add(
                LocaleConfig(
                    project_id=project.id,
                    locale=target_locale,
                    is_bootstrapped=True,
                )
            )

        await db.commit()
        console.print(
            f"  [green]✓[/green] project [bold]{project_slug}[/bold]  "
            f"repo [bold]demo-web[/bold]  locale [bold]{target_locale}[/bold]"
        )

        # Step 2 — write a sample source file and ingest it -------------------
        console.print("\n[bold][2/4][/bold] Ingesting sample source file ...")
        demo_source = {
            "settings.title": "Settings",
            "settings.account.label": "Account",
            "checkout.button.pay": "Pay {{amount}}",
            "errors.network": "Could not reach the server. Try again.",
            "onboarding.welcome": "Welcome to Clariti.",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(demo_source, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        content = Path(tmp_path).read_text(encoding="utf-8")
        result = parse_file(content, "demo.json", repo.file_format)
        summary = await upsert_keys(
            db,
            result,
            str(repo.id),
            str(project.id),
            project.target_locales,
        )
        batch_count = await assemble_batches(db, str(repo.id), str(project.id))
        console.print(
            f"  [green]✓[/green] inserted [bold]{summary['inserted']}[/bold] keys  "
            f"→  [bold]{batch_count}[/bold] batches"
        )

        # Step 3 — register mock provider and translate -----------------------
        console.print("\n[bold][3/4][/bold] Translating with [bold]demo[/bold] provider (mock) ...")
        demo_provider = DemoProvider()
        registry.register("demo", demo_provider)
        # Annotate the wider Protocol type so translate_batch's
        # `dict[str, LLMProvider]` parameter accepts our DemoProvider entry.
        from app.llm.protocol import LLMProvider

        providers: dict[str, LLMProvider] = {"demo": demo_provider}

        batches = list(
            (
                await db.scalars(
                    select(TranslationBatch).where(
                        TranslationBatch.project_id == project.id,
                        TranslationBatch.repository_id == repo.id,
                    )
                )
            ).all()
        )

        totals = {"translated": 0, "needs_review": 0, "cost_usd": 0.0}
        for batch in batches:
            res = await translate_batch(
                db,
                batch,
                providers,
                deepl_locales=[],
                config_provider="demo",
                embed_provider="demo",
            )
            for k, v in res.items():
                if k == "cost_usd":
                    totals[k] += float(v)
                elif k in totals:
                    totals[k] += int(v)
        console.print(
            f"  [green]✓[/green] translated [bold]{totals['translated']}[/bold] strings  "
            f"({totals['needs_review']} needs review, cost ${totals['cost_usd']:.4f})"
        )

        # Step 4 — render a results table -------------------------------------
        console.print("\n[bold][4/4][/bold] Resulting translations:\n")
        rows = (
            await db.execute(
                select(Key, Translation)
                .join(Translation, Translation.key_id == Key.id)
                .where(
                    Key.repository_id == repo.id,
                    Translation.locale == target_locale,
                )
                .order_by(Key.key)
            )
        ).all()

        t = Table(show_header=True, header_style="bold", border_style="dim")
        from rich.markup import escape as rich_escape

        t.add_column("key", style="cyan", no_wrap=True)
        t.add_column("source", overflow="fold")
        t.add_column(target_locale, overflow="fold")
        t.add_column("status", style="magenta")
        for key, translation in rows:
            # `escape` keeps `[fr-FR]` / `{{amount}}` visible — Rich would
            # otherwise interpret the brackets as style tags and eat them.
            t.add_row(
                rich_escape(key.key),
                rich_escape(key.source_text),
                rich_escape(translation.value) if translation.value else "[dim](none)[/dim]",
                str(translation.status.value if hasattr(translation.status, "value") else translation.status),
            )
        console.print(t)

    console.print(
        Panel.fit(
            "[bold green]Demo complete.[/bold green]\n\n"
            "What just happened:\n"
            f"  • [bold]{project_slug}[/bold] was created under org [bold]demo[/bold]\n"
            "  • Five sample strings were ingested as a i18next-shaped repo\n"
            "  • A batch was translated by the mock provider (no API calls)\n"
            "  • Translations were written through the canonical state-machine\n"
            "    path [dim]draft → mt_proposed → {needs_review, approved}[/dim]\n\n"
            "Next steps:\n"
            "  • Run again with [bold]--locale de-DE[/bold] to translate a different locale\n"
            "  • Drop in a real provider by setting [bold]ANTHROPIC_API_KEY[/bold] and\n"
            f"    running [bold]loc translate --project {project_slug} --locale {target_locale}[/bold]\n"
            "  • See [bold]GETTING_STARTED.md[/bold] for the full walkthrough\n"
            f"  • [dim]Demo timestamp: {datetime.now(tz=UTC).isoformat(timespec='seconds')}[/dim]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    app()
