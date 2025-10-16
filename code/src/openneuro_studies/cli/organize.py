"""Organize CLI command implementation."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional, Union

import click
from tqdm import tqdm  # type: ignore[import-untyped]

from openneuro_studies.config import ConfigLoadError, load_config
from openneuro_studies.models import (
    DerivativeDataset,
    SourceDataset,
    UnorganizedDataset,
    UnorganizedReason,
)
from openneuro_studies.organization import OrganizationError, organize_study
from openneuro_studies.organization.unorganized_tracker import (
    add_unorganized_dataset,
    get_unorganized_summary,
)


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
@click.option(
    "--workers",
    type=int,
    default=1,
    help="Number of parallel workers for organizing datasets (default: 1 for serial processing)",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress bar display",
)
@click.pass_context
def organize(
    ctx: click.Context,
    targets: tuple[str, ...],
    github_org: Optional[str],
    dry_run: bool,
    no_publish: bool,
    force: bool,
    workers: int,
    no_progress: bool,
) -> None:
    """Organize datasets into BIDS study structures.

    Create study-{id} folders as DataLad datasets, link source and derivative
    datasets as git submodules, and prepare for metadata generation.

    Arguments accept:
    - Study IDs: study-ds000001, study-ds005256 (supports shell globs: study-ds0000*)
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
        openneuro-studies organize study-ds000001 study-ds005256

        # Use shell globs to select studies
        openneuro-studies organize study-ds0000*

        # Add/update specific derivative from URL
        openneuro-studies organize https://github.com/OpenNeuroDerivatives/ds001761-fmriprep

        # Organize with parallel workers
        openneuro-studies organize --workers 10

        # Dry run to see what would be created
        openneuro-studies organize --dry-run study-ds000001
    """
    try:
        # Load configuration (no GitHub token needed for organize)
        config_path = ctx.obj.get("config", ".openneuro-studies/config.yaml")
        cfg = load_config(config_path, require_tokens=False)

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

        # Build lookup dictionary for source resolution (dataset_id -> dataset)
        # This allows multi-source derivatives to look up URL/commit info for sources
        # Note: mypy has issues with Union assignment, so we build from combined list
        all_datasets_for_lookup: list[Union[SourceDataset, DerivativeDataset]] = [
            *raw_datasets,
            *derivative_datasets,
        ]
        discovered_lookup: Dict[str, Union[SourceDataset, DerivativeDataset]] = {
            ds.dataset_id: ds for ds in all_datasets_for_lookup
        }

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
        config_dir = Path(".openneuro-studies")
        logger = logging.getLogger(__name__)

        # Combine all datasets for processing
        all_datasets = list(raw_datasets) + list(derivative_datasets)

        def organize_single_dataset(
            dataset: Union[SourceDataset, DerivativeDataset],
        ) -> tuple[str, str, Optional[Path], Optional[Exception]]:
            """Organize a single dataset (raw or derivative)."""
            try:
                study_path = organize_study(dataset, cfg, discovered_datasets=discovered_lookup)
                logger.info(f"Organized {dataset.dataset_id} -> {study_path}")
                return ("success", dataset.dataset_id, study_path, None)
            except OrganizationError as e:
                logger.error(f"Failed to organize {dataset.dataset_id}: {e}")
                return ("error", dataset.dataset_id, None, e)

        # Process datasets with parallelization
        if workers == 1:
            # Serial processing (no threading overhead)
            results = []
            iterator = tqdm(all_datasets, desc="Organizing", unit="dataset", disable=no_progress)
            for dataset in iterator:
                result = organize_single_dataset(dataset)
                results.append(result)
                # Update progress description
                status, ds_id, path, error = result
                if status == "success":
                    iterator.set_postfix_str(f"✓ {ds_id}")
                else:
                    iterator.set_postfix_str(f"✗ {ds_id}")
        else:
            # Parallel processing with ThreadPoolExecutor
            results = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(organize_single_dataset, dataset): dataset
                    for dataset in all_datasets
                }

                with tqdm(
                    total=len(all_datasets),
                    desc="Organizing",
                    unit="dataset",
                    disable=no_progress,
                ) as pbar:
                    for future in as_completed(futures):
                        result = future.result()
                        results.append(result)
                        status, ds_id, path, error = result
                        pbar.update(1)
                        if status == "success":
                            pbar.set_postfix_str(f"✓ {ds_id}")
                        else:
                            pbar.set_postfix_str(f"✗ {ds_id}")

        # Process results and collect successful studies
        successful_studies = []
        for status, ds_id, path, error in results:
            if status == "success":
                click.echo(f"✓ Organized {ds_id} -> {path}")
                success_count += 1
                successful_studies.append(path)
            else:
                click.echo(f"✗ Failed to organize {ds_id}: {error}", err=True)
                error_count += 1

                # Track unorganized derivative (only for derivatives, not raw datasets)
                # Find the original dataset object to check if it's a derivative
                dataset = next((d for d in derivative_datasets if d.dataset_id == ds_id), None)
                if dataset:
                    unorganized = UnorganizedDataset.from_derivative_dataset(
                        dataset,
                        reason=UnorganizedReason.ORGANIZATION_ERROR,
                        notes=str(error),
                    )
                    add_unorganized_dataset(unorganized, config_dir)

        # Commit all organized studies to parent repository in a single batch operation
        # This avoids git index.lock conflicts from parallel workers
        if successful_studies:
            click.echo(
                f"\nCommitting {len(successful_studies)} organized studies to parent repository..."
            )
            try:
                import datalad.api as dl

                from openneuro_studies import __version__

                # Use dataset="^" to save from top dataset
                dl.save(
                    dataset="^",
                    message=f"Organize {len(successful_studies)} study datasets\n\n"
                    f"Added/updated {len(successful_studies)} study submodules\n"
                    f"Updated by openneuro-studies {__version__} organize command",
                )
                click.echo("✓ Committed all studies to parent repository")
            except Exception as e:
                click.echo(f"✗ Failed to commit studies to parent: {e}", err=True)
                logger.error(f"Failed to commit parent repository: {e}")
                # Don't exit with error - studies were organized successfully

        # Display summary
        click.echo("\nSummary:")
        click.echo(f"  ✓ Organized: {success_count}")
        if error_count > 0:
            click.echo(f"  ✗ Failed: {error_count}")

            # Show unorganized summary
            unorg_summary = get_unorganized_summary(config_dir)
            if unorg_summary:
                click.echo("\nUnorganized datasets by reason:")
                for reason, count in unorg_summary.items():
                    click.echo(f"  - {reason}: {count}")
                click.echo(f"\nSee {config_dir}/unorganized-datasets.json for details")

        # Announce log file location
        log_file = ctx.obj.get("log_file")
        if log_file:
            click.echo(f"\nDetailed logs: {log_file}")

        if error_count > 0:
            ctx.exit(1)

    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)
