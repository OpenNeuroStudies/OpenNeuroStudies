"""Main CLI entry point for openneuro-studies."""

import logging
import os
from datetime import datetime
from pathlib import Path

import click

from openneuro_studies import __version__
from openneuro_studies.cli.discover import discover as discover_cmd
from openneuro_studies.cli.init import init as init_cmd
from openneuro_studies.cli.migrate import migrate as migrate_cmd
from openneuro_studies.cli.organize import organize as organize_cmd
from openneuro_studies.cli.provision import provision as provision_cmd
from openneuro_studies.cli.publish import publish as publish_cmd
from openneuro_studies.cli.unpublish import unpublish as unpublish_cmd


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
cli.add_command(provision_cmd, name="provision")
cli.add_command(migrate_cmd, name="migrate")
cli.add_command(publish_cmd, name="publish")
cli.add_command(unpublish_cmd, name="unpublish")


@cli.group()
def metadata() -> None:
    """Generate and synchronize metadata files.

    Commands for creating dataset_description.json, studies.tsv, studies+derivatives.tsv,
    and their JSON sidecars.
    """
    pass


@metadata.command(name="generate")
@click.argument("study_ids", nargs=-1, required=False)
@click.option(
    "--dataset-description/--no-dataset-description",
    default=True,
    help="Generate dataset_description.json for each study",
)
@click.option(
    "--studies-tsv/--no-studies-tsv",
    default=True,
    help="Generate studies.tsv and studies.json at root level",
)
@click.option(
    "--derivatives-tsv/--no-derivatives-tsv",
    default=True,
    help="Generate studies+derivatives.tsv and studies+derivatives.json at root level",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite existing files (default: update/merge)",
)
@click.option(
    "--commit/--no-commit",
    default=True,
    help="Commit changes with datalad save (includes descriptive stats)",
)
@click.option(
    "--imaging/--no-imaging",
    default=False,
    help="Extract imaging metrics (voxel counts, durations) - requires nibabel and sparse access",
)
@click.pass_context
def metadata_generate(
    ctx: click.Context,
    study_ids: tuple[str, ...],
    dataset_description: bool,
    studies_tsv: bool,
    derivatives_tsv: bool,
    overwrite: bool,
    commit: bool,
    imaging: bool,
) -> None:
    """Generate metadata for study datasets.

    Creates dataset_description.json, studies.tsv, studies+derivatives.tsv, and JSON sidecars.

    Arguments:
        STUDY_IDS: Optional list of study IDs. If not provided, generates for all studies.

    Example:
        openneuro-studies metadata generate
        openneuro-studies metadata generate study-ds000001
        openneuro-studies metadata generate --no-studies-tsv
        openneuro-studies metadata generate --no-commit
    """
    from openneuro_studies.lib import save_with_stats
    from openneuro_studies.metadata import (
        generate_dataset_description,
        generate_studies_derivatives_json,
        generate_studies_derivatives_tsv,
        generate_studies_json,
        generate_studies_tsv,
    )

    root_path = Path(".")

    # Find study directories
    if study_ids:
        # Normalize study IDs (accept both study-ds000001 and ds000001)
        study_paths = []
        for study_id in study_ids:
            if not study_id.startswith("study-"):
                study_id = f"study-{study_id}"
            study_path = root_path / study_id
            if study_path.is_dir():
                study_paths.append(study_path)
            else:
                click.echo(f"Warning: Study directory not found: {study_id}", err=True)
    else:
        # Find all study directories
        study_paths = sorted(
            [p for p in root_path.iterdir() if p.is_dir() and p.name.startswith("study-")]
        )

    if not study_paths:
        click.echo("No study directories found.", err=True)
        return

    click.echo(f"Generating metadata for {len(study_paths)} studies...")

    # Track statistics for commit message
    stats: dict[str, int | str] = {"studies": len(study_paths)}
    modified_paths: list[Path] = []
    desc_success = 0
    desc_errors = 0

    # Generate dataset_description.json for each study
    if dataset_description:
        click.echo("\nGenerating dataset_description.json files...")
        for study_path in study_paths:
            try:
                generate_dataset_description(study_path, overwrite=overwrite)
                click.echo(f"  ✓ {study_path.name}")
                modified_paths.append(study_path / "dataset_description.json")
                desc_success += 1
            except Exception as e:
                click.echo(f"  ✗ {study_path.name}: {e}", err=True)
                desc_errors += 1
        stats["dataset_descriptions"] = desc_success
        if desc_errors:
            stats["dataset_description_errors"] = desc_errors

    # Generate studies.tsv and studies.json at root level
    if studies_tsv:
        # Determine extraction stage
        stage = "imaging" if imaging else "sizes"
        click.echo(f"\nGenerating studies.tsv (stage={stage})...")
        try:
            generate_studies_tsv(study_paths, root_path / "studies.tsv", stage=stage)
            generate_studies_json(root_path / "studies.json")
            click.echo("  ✓ studies.tsv")
            click.echo("  ✓ studies.json")
            modified_paths.extend([root_path / "studies.tsv", root_path / "studies.json"])
        except Exception as e:
            click.echo(f"  ✗ Failed: {e}", err=True)

    # Generate hierarchical sourcedata TSV files when imaging is enabled
    if imaging:
        from bids_studies.extraction import extract_study_stats

        click.echo("\nGenerating per-source hierarchical statistics...")
        for study_path in study_paths:
            try:
                extract_study_stats(
                    study_path,
                    sourcedata_subdir="sourcedata",
                    include_imaging=True,
                    write_files=True,
                )
                click.echo(f"  ✓ {study_path.name}/sourcedata/*.tsv")
                # Add sourcedata files to modified paths
                sourcedata_path = study_path / "sourcedata"
                if sourcedata_path.exists():
                    for tsv in sourcedata_path.glob("sourcedata+*.tsv"):
                        modified_paths.append(tsv)
                    for json_file in sourcedata_path.glob("sourcedata+*.json"):
                        modified_paths.append(json_file)
            except Exception as e:
                click.echo(f"  ✗ {study_path.name}: {e}", err=True)

    # Generate studies+derivatives.tsv and studies+derivatives.json at root level
    if derivatives_tsv:
        click.echo("\nGenerating studies+derivatives.tsv...")
        try:
            generate_studies_derivatives_tsv(study_paths, root_path / "studies+derivatives.tsv")
            generate_studies_derivatives_json(root_path / "studies+derivatives.json")
            click.echo("  ✓ studies+derivatives.tsv")
            click.echo("  ✓ studies+derivatives.json")
            modified_paths.extend(
                [
                    root_path / "studies+derivatives.tsv",
                    root_path / "studies+derivatives.json",
                ]
            )
        except Exception as e:
            click.echo(f"  ✗ Failed: {e}", err=True)

    click.echo("\nMetadata generation complete.")

    # Commit changes if requested
    if commit and modified_paths:
        click.echo("\nCommitting changes...")
        # First commit changes in study subdatasets
        for study_path in study_paths:
            try:
                import subprocess

                # Check if there are changes to commit
                result = subprocess.run(
                    ["git", "-C", str(study_path), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip():
                    subprocess.run(
                        ["git", "-C", str(study_path), "add", "dataset_description.json"],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(study_path),
                            "commit",
                            "-m",
                            "Update dataset_description.json\n\n"
                            "Generated by openneuro-studies metadata generate",
                        ],
                        check=True,
                        capture_output=True,
                    )
            except subprocess.CalledProcessError:
                pass  # Ignore commit errors in subdatasets

        # Then commit at root level with stats
        success = save_with_stats(
            message="Generate metadata files",
            stats=stats,
            dataset=".",
        )
        if success:
            click.echo("  ✓ Changes committed")
        else:
            click.echo("  ✗ Failed to commit changes", err=True)


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
@click.option(
    "--timeout",
    type=int,
    default=600,
    help="Timeout per study in seconds",
    show_default=True,
)
@click.option(
    "--update-tsv/--no-update-tsv",
    default=True,
    help="Update bids_valid column in studies.tsv",
)
@click.option(
    "--commit/--no-commit",
    default=True,
    help="Commit validation results with datalad save",
)
@click.option(
    "--when",
    type=click.Choice(["always", "new-commits"], case_sensitive=False),
    default="new-commits",
    help="When to run validation: 'always' or 'new-commits' (skip if no changes since last validation)",
    show_default=True,
)
def validate(
    study_ids: tuple[str, ...],
    timeout: int,
    update_tsv: bool,
    commit: bool,
    when: str,
) -> None:
    """Run BIDS validation on study datasets.

    Executes bids-validator and stores results in derivatives/bids-validator/:
    - version.txt: Validator version
    - report.json: Machine-readable results
    - report.txt: Human-readable summary

    Updates bids_valid column in studies.tsv.

    Arguments:
        STUDY_IDS: Optional list of study IDs. If not provided, validates all studies.

    Example:
        openneuro-studies validate
        openneuro-studies validate study-ds000001
        openneuro-studies validate --when=always  # Force revalidation
    """
    from openneuro_studies.validation import (
        ValidationStatus,
        find_validator,
        needs_validation,
        run_validation,
        update_studies_tsv_validation,
    )

    root_path = Path(".")

    # Check for validator first
    validator = find_validator()
    if validator is None:
        click.echo(
            "Error: No BIDS validator found.\n"
            "Install with one of:\n"
            "  pip install bids-validator\n"
            "  Or ensure deno or npx is in PATH",
            err=True,
        )
        return

    validator_cmd, validator_type = validator
    click.echo(f"Using {validator_type} for validation")

    # Find study directories
    if study_ids:
        # Normalize study IDs (accept both study-ds000001 and ds000001)
        study_paths = []
        for study_id in study_ids:
            if not study_id.startswith("study-"):
                study_id = f"study-{study_id}"
            study_path = root_path / study_id
            if study_path.is_dir():
                study_paths.append(study_path)
            else:
                click.echo(f"Warning: Study directory not found: {study_id}", err=True)
    else:
        # Find all study directories
        study_paths = sorted(
            [p for p in root_path.iterdir() if p.is_dir() and p.name.startswith("study-")]
        )

    if not study_paths:
        click.echo("No study directories found.", err=True)
        return

    click.echo(f"\nValidating {len(study_paths)} studies...")

    # Track results
    results_summary = {
        ValidationStatus.VALID: 0,
        ValidationStatus.WARNINGS: 0,
        ValidationStatus.ERRORS: 0,
        ValidationStatus.NOT_AVAILABLE: 0,
    }
    skipped_count = 0

    for study_path in study_paths:
        # Check if validation is needed (--when option)
        if when.lower() == "new-commits" and not needs_validation(study_path):
            click.echo(f"\n  {study_path.name}: skipped (no changes)")
            skipped_count += 1
            continue

        click.echo(f"\n  Validating {study_path.name}...", nl=False)

        result = run_validation(
            study_path,
            validator_cmd=validator_cmd,
            timeout=timeout,
        )

        results_summary[result.status] += 1

        # Display result
        status_icons = {
            ValidationStatus.VALID: "✓",
            ValidationStatus.WARNINGS: "⚠",
            ValidationStatus.ERRORS: "✗",
            ValidationStatus.NOT_AVAILABLE: "?",
        }
        icon = status_icons.get(result.status, "?")

        if result.status == ValidationStatus.VALID:
            click.echo(f" {icon} valid")
        elif result.status == ValidationStatus.WARNINGS:
            click.echo(f" {icon} {result.warning_count} warnings")
        elif result.status == ValidationStatus.ERRORS:
            click.echo(f" {icon} {result.error_count} errors, {result.warning_count} warnings")
        else:
            click.echo(f" {icon} n/a")

        # Update studies.tsv
        if update_tsv:
            studies_tsv = root_path / "studies.tsv"
            if studies_tsv.exists():
                update_studies_tsv_validation(studies_tsv, study_path.name, result.status)

    # Summary
    click.echo("\n" + "=" * 60)
    click.echo("Validation Summary:")
    click.echo(f"  Valid:    {results_summary[ValidationStatus.VALID]}")
    click.echo(f"  Warnings: {results_summary[ValidationStatus.WARNINGS]}")
    click.echo(f"  Errors:   {results_summary[ValidationStatus.ERRORS]}")
    click.echo(f"  N/A:      {results_summary[ValidationStatus.NOT_AVAILABLE]}")
    if skipped_count > 0:
        click.echo(f"  Skipped:  {skipped_count} (no changes since last validation)")
    click.echo("\nResults stored in derivatives/bids-validator/ per study.")

    # Commit changes if requested
    if commit:
        from openneuro_studies.lib import save_with_stats

        click.echo("\nCommitting validation results...")
        # First commit in study subdatasets
        for study_path in study_paths:
            try:
                import subprocess

                git_result = subprocess.run(
                    ["git", "-C", str(study_path), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                )
                if git_result.stdout.strip():
                    subprocess.run(
                        ["git", "-C", str(study_path), "add", "-A"],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(study_path),
                            "commit",
                            "-m",
                            "Add BIDS validation results\n\n"
                            "Generated by openneuro-studies validate",
                        ],
                        check=True,
                        capture_output=True,
                    )
            except subprocess.CalledProcessError:
                pass

        # Then commit at root level with stats
        stats: dict[str, int | str] = {
            "valid": results_summary[ValidationStatus.VALID],
            "warnings": results_summary[ValidationStatus.WARNINGS],
            "errors": results_summary[ValidationStatus.ERRORS],
            "n/a": results_summary[ValidationStatus.NOT_AVAILABLE],
        }
        if skipped_count > 0:
            stats["skipped"] = skipped_count
        success = save_with_stats(
            message="Run BIDS validation",
            stats=stats,
            dataset=".",
        )
        if success:
            click.echo("  ✓ Changes committed")
        else:
            click.echo("  ✗ Failed to commit changes", err=True)


@cli.command()
@click.option(
    "--format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format",
)
def status(format: str) -> None:
    """Show processing status and statistics.

    Displays counts of discovered, organized, metadata-complete, validated, and published studies.

    Example:
        openneuro-studies status
        openneuro-studies status --format json
    """
    from openneuro_studies.publishing import PublicationTracker

    config_dir = Path(".openneuro-studies")

    # Count organized studies
    organized_studies = [
        p for p in Path(".").iterdir() if p.is_dir() and p.name.startswith("study-")
    ]

    # Load publication status
    tracker = PublicationTracker(config_dir)
    published_studies = tracker.get_published_studies()

    if format == "json":
        import json

        data = {
            "organized": len(organized_studies),
            "published": len(published_studies),
            "organization": tracker.status.organization or "not configured",
            "last_updated": (
                tracker.status.last_updated.isoformat() if tracker.status.last_updated else None
            ),
        }
        click.echo(json.dumps(data, indent=2))
    else:
        # Text format
        click.echo("OpenNeuroStudies Status")
        click.echo("=" * 60)
        click.echo(f"Organized studies: {len(organized_studies)}")
        click.echo(f"Published studies: {len(published_studies)}")

        if tracker.status.organization:
            click.echo(f"\nGitHub Organization: {tracker.status.organization}")
            click.echo(f"URL: https://github.com/{tracker.status.organization}")

        if tracker.status.last_updated:
            click.echo(f"\nLast publication update: {tracker.status.last_updated.isoformat()}")

        # Show unpublished studies
        unpublished = [s.name for s in organized_studies if s.name not in published_studies]
        if unpublished:
            click.echo(f"\nUnpublished studies ({len(unpublished)}):")
            for study_id in sorted(unpublished)[:10]:  # Show first 10
                click.echo(f"  - {study_id}")
            if len(unpublished) > 10:
                click.echo(f"  ... and {len(unpublished) - 10} more")

        click.echo("\nNote: Full status implementation pending (Phase 6)")


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
