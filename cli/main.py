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
        err.print(
            f"[red]No {TMS_YML_NAME} found in {cwd}.[/red]\n"
            "Run [bold]loc init[/bold] to set up this repository."
        )
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
        f"domain_description: \"{config['domain_description']}\"",
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
        console.print(
            f"\n[bold]Dry run:[/bold] {file_path.name} "
            f"({fmt}, {key_count} keys)\n"
        )
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

        project = await db.scalar(
            select(Project).where(Project.slug == "dev-project")
        )
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
    locale: str = typer.Option(..., "--locale", help="Target locale (e.g. fr-FR)"),
    provider: str = typer.Option("anthropic", "--provider", help="LLM provider"),
    max_batches: int = typer.Option(None, "--max-batches", help="Stop after N batches"),
) -> None:
    """Run MT on all pending batches for a project/locale."""
    asyncio.run(_translate(project, locale, provider, max_batches))


async def _translate(project_slug: str, locale: str, provider_name: str, max_batches: int | None) -> None:
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

    # Count pending batches
    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.slug == project_slug))
        if project is None:
            err.print(f"[red]Project '{project_slug}' not found.[/red]")
            raise typer.Exit(1)
        batches = await db.scalars(
            select(TranslationBatch).where(
                TranslationBatch.project_id == project.id,
                TranslationBatch.locale == locale,
                TranslationBatch.status == BatchStatus.pending,
            )
        )
        batch_list = list(batches)

    if not batch_list:
        console.print(f"[dim]No pending batches for {project_slug} / {locale}.[/dim]")
        return

    console.print(f"\nRunning MT on [bold]{len(batch_list)}[/bold] batch(es) — {project_slug} / {locale}\n")

    await run_worker(
        providers=providers,
        max_batches=max_batches or len(batch_list),
        config_provider=provider_name,
        embed_provider="openai" if "openai" in providers else provider_name,
    )
    console.print(f"\n[green]✓[/green] MT complete for {locale}")


# ---------------------------------------------------------------------------
# loc status (stub)
# ---------------------------------------------------------------------------


@app.command()
def status(locale: str = typer.Argument(None)) -> None:
    """Show translation coverage report. (Phase 3)"""
    console.print("[dim]loc status — Phase 3[/dim]")


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


if __name__ == "__main__":
    app()
