"""Discovery CLI command implementation."""

from typing import Optional

import click
import datalad.api as dl

from openneuro_studies import __version__
from openneuro_studies.config import ConfigLoadError, load_config
from openneuro_studies.discovery import DatasetDiscoveryError, DatasetFinder


@click.command()
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Configuration file path (overrides global --config)",
)
@click.option(
    "--output",
    default=".openneuro-studies/discovered-datasets.json",
    help="Output file for discovered datasets",
    show_default=True,
)
@click.option(
    "--test-filter",
    multiple=True,
    help="Filter to specific dataset IDs for testing (e.g., ds000001)",
)
@click.option(
    "--include-derivatives",
    is_flag=True,
    help="When using --test-filter, also include derivatives of filtered datasets "
    "(recursively includes derivatives of derivatives)",
)
@click.option(
    "--workers",
    type=int,
    default=10,
    help="Number of parallel workers for dataset processing",
    show_default=True,
)
@click.option(
    "--progress/--no-progress",
    default=True,
    help="Show progress bar",
    show_default=True,
)
@click.option(
    "--mode",
    type=click.Choice(["update", "overwrite"], case_sensitive=False),
    default="update",
    help="Discovery mode: 'update' merges with existing results, 'overwrite' replaces all",
    show_default=True,
)
@click.pass_context
def discover(
    ctx: click.Context,
    config: Optional[str],
    output: str,
    test_filter: tuple[str, ...],
    include_derivatives: bool,
    workers: int,
    progress: bool,
    mode: str,
) -> None:
    """Discover datasets from configured sources.

    Queries GitHub/Forgejo APIs to identify available raw and derivative datasets
    without cloning. Results are cached to the specified output file.

    By default, newly discovered datasets are merged with existing results (update mode).
    Use --mode overwrite to replace all previous results.

    Datasets are processed in parallel using multiple workers for faster discovery.

    \b
    Examples:
        openneuro-studies discover
        openneuro-studies discover --test-filter ds000001 --test-filter ds005256
        openneuro-studies discover --test-filter ds000001 --include-derivatives
        openneuro-studies discover --workers 20 --no-progress
        openneuro-studies discover --mode overwrite  # Replace all existing results
    """
    try:
        # Load configuration (don't require tokens - will work without until rate limits)
        config_path = config or ctx.obj.get("config", ".openneuro-studies/config.yaml")
        cfg = load_config(config_path, require_tokens=False)

        # Create dataset finder with specified workers
        test_dataset_filter = list(test_filter) if test_filter else None
        finder = DatasetFinder(
            cfg,
            test_dataset_filter=test_dataset_filter,
            include_derivatives=include_derivatives,
            max_workers=workers,
        )

        # Discover datasets
        click.echo("Discovering datasets from configured sources...")
        if test_dataset_filter:
            click.echo(f"Using test filter: {', '.join(test_dataset_filter)}")
            if include_derivatives:
                click.echo("  (including derivatives of filtered datasets)")
        click.echo(f"Using {workers} parallel workers")

        # Set up expansion progress callback for --include-derivatives
        expansion_progress_callback = None
        if include_derivatives and test_dataset_filter:

            def expansion_cb(phase: str, message: str) -> None:
                click.echo(message)

            expansion_progress_callback = expansion_cb

        # Set up progress callback if progress bar is enabled
        progress_callback = None
        pbar = None
        if progress:
            # Skip repo counting if include_derivatives is set - we'll show progress differently
            # because the filter gets expanded after scanning
            if not include_derivatives:
                # Use click.progressbar for progress tracking
                # We'll need to count repos first to know the total
                total_repos = 0
                for source_spec in cfg.sources:
                    org_path = source_spec.organization_url.path
                    org_name = str(org_path).strip("/")
                    repos = finder.github_client.list_repositories(
                        org_name, dataset_filter=test_dataset_filter
                    )
                    # Apply same filtering as discover_all
                    from openneuro_studies.discovery.dataset_finder import DatasetFinder as _DF

                    filtered = _DF._filter_repos(finder, repos, source_spec.inclusion_patterns)
                    if source_spec.exclusion_patterns:
                        import re

                        filtered = [
                            r
                            for r in filtered
                            if not any(re.match(p, r["name"]) for p in source_spec.exclusion_patterns)
                        ]
                    total_repos += len(filtered)

                pbar = click.progressbar(length=total_repos, label="Processing datasets")
                pbar.__enter__()

                def progress_cb(dataset_id: str) -> None:
                    pbar.update(1)

                progress_callback = progress_cb

        try:
            discovered = finder.discover_all(
                progress_callback=progress_callback,
                expansion_progress_callback=expansion_progress_callback,
            )
        finally:
            if pbar:
                pbar.__exit__(None, None, None)

        # Report results
        raw_count = len(discovered["raw"])
        deriv_count = len(discovered["derivative"])
        click.echo(f"\n✓ Found {raw_count} raw datasets")
        click.echo(f"✓ Found {deriv_count} derivative datasets")

        # Save results with specified mode (update or overwrite)
        finder.save_discovered(discovered, output, mode=mode)
        if mode == "update":
            click.echo(f"✓ Updated {output} (merged with existing datasets)")
        else:
            click.echo(f"✓ Saved to {output} (overwrote existing)")

        # Commit the discovered datasets (FR-020a)
        # Use datalad save from top dataset - it will figure out which subdataset changed
        click.echo("Committing discovered datasets...")
        from pathlib import Path

        output_path = Path(output).resolve()

        dl.save(
            dataset="^",  # save all the way from the top dataset
            path=str(output_path),
            message=f"Update discovered datasets: {raw_count} raw and {deriv_count} derivative datasets\n\n"
            f"Updated by openneuro-studies {__version__} discover command",
        )
        click.echo("✓ Committed to .openneuro-studies subdataset")

    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except DatasetDiscoveryError as e:
        click.echo(f"Discovery error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)
