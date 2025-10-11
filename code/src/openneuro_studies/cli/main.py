"""Main CLI entry point for openneuro-studies."""

import click

from openneuro_studies import __version__
from openneuro_studies.cli.discover import discover as discover_cmd
from openneuro_studies.cli.init import init as init_cmd
from openneuro_studies.cli.organize import organize as organize_cmd


@click.group()
@click.version_option(version=__version__, prog_name="openneuro-studies")
@click.option(
    "--config",
    type=click.Path(dir_okay=False, readable=True),
    default=".openneuro-studies/config.yaml",
    help="Configuration file path",
    show_default=True,
)
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """OpenNeuroStudies: Infrastructure for organizing OpenNeuro datasets.

    Discover, organize, and maintain OpenNeuro datasets as BIDS study structures
    with automated metadata generation.

    For detailed documentation, see: https://github.com/OpenNeuroStudies/OpenNeuroStudies
    """
    # Ensure context object exists for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


# Register commands
cli.add_command(init_cmd, name="init")
cli.add_command(discover_cmd, name="discover")
cli.add_command(organize_cmd, name="organize")


@cli.group()
def metadata() -> None:
    """Generate and synchronize metadata files.

    Commands for creating dataset_description.json, studies.tsv, studies_derivatives.tsv,
    and their JSON sidecars.
    """
    pass


@metadata.command(name="generate")
@click.argument("study_ids", nargs=-1, required=False)
@click.pass_context
def metadata_generate(ctx: click.Context, study_ids: tuple[str, ...]) -> None:
    """Generate metadata for study datasets.

    Creates dataset_description.json, studies.tsv, studies_derivatives.tsv, and JSON sidecars.

    Arguments:
        STUDY_IDS: Optional list of study IDs. If not provided, generates for all studies.

    Example:
        openneuro-studies metadata generate
        openneuro-studies metadata generate study-ds000001
    """
    if study_ids:
        click.echo(f"[Placeholder] Would generate metadata for: {', '.join(study_ids)}")
    else:
        click.echo("[Placeholder] Would generate metadata for all studies")
    click.echo("Phase 4 implementation pending...")


@metadata.command(name="sync")
@click.argument("study_ids", nargs=-1, required=True)
def metadata_sync(study_ids: tuple[str, ...]) -> None:
    """Synchronize metadata for specific studies (incremental update).

    Updates only the specified studies' metadata without regenerating everything.

    Arguments:
        STUDY_IDS: One or more study IDs to synchronize.

    Example:
        openneuro-studies metadata sync study-ds000001 study-ds000010
    """
    click.echo(f"[Placeholder] Would sync metadata for: {', '.join(study_ids)}")
    click.echo("Phase 4 implementation pending...")


@cli.command()
@click.argument("study_ids", nargs=-1, required=False)
def validate(study_ids: tuple[str, ...]) -> None:
    """Run BIDS validation on study datasets.

    Executes bids-validator-deno and stores results in derivatives/bids-validator.{json,txt}.
    Updates bids_valid column in studies.tsv.

    Arguments:
        STUDY_IDS: Optional list of study IDs. If not provided, validates all studies.

    Example:
        openneuro-studies validate
        openneuro-studies validate study-ds000001
    """
    if study_ids:
        click.echo(f"[Placeholder] Would validate studies: {', '.join(study_ids)}")
    else:
        click.echo("[Placeholder] Would validate all studies")
    click.echo("Phase 5 implementation pending...")


@cli.command()
@click.option(
    "--format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format",
)
def status(format: str) -> None:
    """Show processing status and statistics.

    Displays counts of discovered, organized, metadata-complete, and validated studies.

    Example:
        openneuro-studies status
        openneuro-studies status --format json
    """
    click.echo(f"[Placeholder] Would show status in {format} format")
    click.echo("Phase 6 implementation pending...")


@cli.command()
@click.option("--cache", is_flag=True, help="Clear API cache")
@click.option("--temp", is_flag=True, help="Clear temporary files")
@click.option("--all", "all_files", is_flag=True, help="Clear all cached and temporary files")
def clean(cache: bool, temp: bool, all_files: bool) -> None:
    """Clean cached data and temporary files.

    Example:
        openneuro-studies clean --cache
        openneuro-studies clean --all
    """
    if all_files:
        click.echo("[Placeholder] Would clean all cached and temporary files")
    elif cache:
        click.echo("[Placeholder] Would clean API cache")
    elif temp:
        click.echo("[Placeholder] Would clean temporary files")
    else:
        click.echo("No cleanup options specified. Use --cache, --temp, or --all")
    click.echo("Phase 6 implementation pending...")


if __name__ == "__main__":
    cli()
