import typer

app = typer.Typer(
    name="loc",
    help="Clariti TMS — translation management CLI",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Scaffold tms.yml for a new project repo."""
    typer.echo("loc init — not yet implemented (Phase 1)")


@app.command()
def ingest_file(
    path: str = typer.Argument(..., help="Path to source strings file"),
    repo: str = typer.Option(..., "--repo", help="Repository name"),
) -> None:
    """Parse and upsert keys from a source strings file."""
    typer.echo(f"loc ingest-file {path} --repo {repo} — not yet implemented (Phase 1)")


@app.command()
def translate(
    project: str = typer.Option(..., "--project"),
    locale: str = typer.Option(..., "--locale"),
) -> None:
    """Trigger MT on all draft strings for a project/locale."""
    typer.echo("loc translate — not yet implemented (Phase 2)")


@app.command()
def status(locale: str = typer.Argument(None)) -> None:
    """Show translation coverage report."""
    typer.echo("loc status — not yet implemented (Phase 3)")


@app.command()
def export(
    project: str = typer.Option(..., "--project"),
    locales: str = typer.Option(..., "--locales"),
    output: str = typer.Option("./export.xlsx", "--output"),
) -> None:
    """Export translations to Excel."""
    typer.echo("loc export — not yet implemented (Phase 5)")


@app.command()
def import_file(
    file: str = typer.Option(..., "--file"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    commit: bool = typer.Option(False, "--commit"),
    rollback: str = typer.Option(None, "--rollback"),
) -> None:
    """Import translations from Excel."""
    typer.echo("loc import — not yet implemented (Phase 5)")


if __name__ == "__main__":
    app()
