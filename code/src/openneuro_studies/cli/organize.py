"""Organize CLI command implementation."""

import json
from pathlib import Path
from typing import Optional

import click

from openneuro_studies.config import ConfigLoadError, load_config
from openneuro_studies.models import DerivativeDataset, SourceDataset
from openneuro_studies.organization import OrganizationError, organize_study


@click.command()
@click.argument("targets", nargs=-1, type=str)
@click.option(
    "--github-org",
    type=str,
    help="Override GitHub organization from config file for publishing study repositories",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing any changes",
)
@click.option(
    "--no-publish",
    is_flag=True,
    help="Create study datasets locally without publishing to GitHub",
)
@click.option(
    "--force",
    is_flag=True,
    help="Recreate existing studies (DESTRUCTIVE - use with caution)",
)
@click.pass_context
def organize(
    ctx: click.Context,
    targets: tuple[str, ...],
    github_org: Optional[str],
    dry_run: bool,
    no_publish: bool,
    force: bool,
) -> None:
    """Organize datasets into BIDS study structures.

    Create study-{id} folders as DataLad datasets, link source and derivative
    datasets as git submodules, and prepare for metadata generation.

    Arguments accept:
    - Study IDs: study-ds000001, study-ds000010 (supports shell globs: study-ds0000*)
    - Dataset URLs: https://github.com/OpenNeuroDerivatives/ds001761-fmriprep
    - Local paths: /path/to/local/dataset

    When URLs/paths are provided, the system:
    - Detects type (raw vs derivative) from dataset_description.json
    - Adds to appropriate study or creates new study
    - Links as git submodule in correct location

    \b
    Examples:
        # Organize all discovered datasets
        openneuro-studies organize

        # Organize specific studies (incremental)
        openneuro-studies organize study-ds000001 study-ds000010

        # Use shell globs to select studies
        openneuro-studies organize study-ds0000*

        # Add/update specific derivative from URL
        openneuro-studies organize https://github.com/OpenNeuroDerivatives/ds001761-fmriprep

        # Dry run to see what would be created
        openneuro-studies organize --dry-run study-ds000001
    """
    try:
        # Load configuration
        config_path = ctx.obj.get("config", ".openneuro-studies/config.yaml")
        cfg = load_config(config_path)

        # Override github_org if provided
        if github_org:
            cfg.github_org = github_org

        # Load discovered datasets
        discovered_file = Path(".openneuro-studies/discovered-datasets.json")
        if not discovered_file.exists():
            click.echo(
                f"Error: {discovered_file} not found. Run 'openneuro-studies discover' first.",
                err=True,
            )
            ctx.exit(1)

        with open(discovered_file) as f:
            discovered = json.load(f)

        # Parse datasets from discovered JSON
        raw_datasets = [SourceDataset(**d) for d in discovered.get("raw", [])]
        derivative_datasets = [DerivativeDataset(**d) for d in discovered.get("derivative", [])]

        # Filter targets if provided
        if targets:
            # For now, filter by dataset_id matching targets
            # TODO: Support URLs and paths
            target_set = set(targets)
            raw_datasets = [d for d in raw_datasets if d.dataset_id in target_set]
            derivative_datasets = [d for d in derivative_datasets if d.dataset_id in target_set]

        # Display plan
        total_datasets = len(raw_datasets) + len(derivative_datasets)
        if total_datasets == 0:
            click.echo("No datasets to organize.")
            return

        click.echo(f"Organizing {total_datasets} datasets:")
        click.echo(f"  - {len(raw_datasets)} raw datasets")
        click.echo(f"  - {len(derivative_datasets)} derivative datasets")

        if dry_run:
            click.echo("\n[DRY RUN] Would organize:")
            for raw_ds in raw_datasets:
                click.echo(f"  study-{raw_ds.dataset_id}")
            for deriv_ds in derivative_datasets:
                click.echo(f"  {deriv_ds.dataset_id} (derivative)")
            return

        # Organize datasets
        success_count = 0
        error_count = 0

        # Organize raw datasets first
        for raw_dataset in raw_datasets:
            try:
                study_path = organize_study(raw_dataset, cfg)
                click.echo(f"✓ Organized {raw_dataset.dataset_id} -> {study_path}")
                success_count += 1
            except OrganizationError as e:
                click.echo(f"✗ Failed to organize {raw_dataset.dataset_id}: {e}", err=True)
                error_count += 1

        # Then organize derivatives
        for deriv_dataset in derivative_datasets:
            try:
                study_path = organize_study(deriv_dataset, cfg)
                click.echo(f"✓ Organized {deriv_dataset.dataset_id} -> {study_path}")
                success_count += 1
            except OrganizationError as e:
                click.echo(f"✗ Failed to organize {deriv_dataset.dataset_id}: {e}", err=True)
                error_count += 1

        # Display summary
        click.echo("\nSummary:")
        click.echo(f"  ✓ Success: {success_count}")
        if error_count > 0:
            click.echo(f"  ✗ Errors: {error_count}")
            ctx.exit(1)

    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)
