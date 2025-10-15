"""Main CLI entry point for openneuro-studies."""

import logging
import os
from datetime import datetime
from pathlib import Path

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
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level",
    show_default=True,
)
@click.pass_context
def cli(ctx: click.Context, config: str, log_level: str) -> None:
    """OpenNeuroStudies: Infrastructure for organizing OpenNeuro datasets.

    Discover, organize, and maintain OpenNeuro datasets as BIDS study structures
    with automated metadata generation.

    For detailed documentation, see: https://github.com/OpenNeuroStudies/OpenNeuroStudies
    """
    # Configure dual logging (console WARNING, file user-specified level)
    # Logs go in .openneuro-studies subdataset for versioned tracking
    log_dir = Path(".openneuro-studies/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file with timestamp and PID
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    log_file = log_dir / f"{timestamp}-{pid}.log"

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything

    # Console handler - WARNING only (for user-facing messages)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler - user-specified level
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Suppress datalad console output (keep in file)
    datalad_logger = logging.getLogger("datalad")
    datalad_logger.setLevel(logging.WARNING)  # Only show warnings/errors on console
    # Add file handler that captures everything
    datalad_file_handler = logging.FileHandler(log_file)
    datalad_file_handler.setLevel(logging.DEBUG)
    datalad_file_handler.setFormatter(file_formatter)
    datalad_logger.addHandler(datalad_file_handler)
    datalad_logger.propagate = False  # Don't propagate to root logger

    # Store log file path in context for later reference
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["log_file"] = str(log_file)


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
        openneuro-studies metadata sync study-ds000001 study-ds005256
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
