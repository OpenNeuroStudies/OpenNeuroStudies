"""Discovery CLI command implementation."""

from typing import Optional

import click

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
@click.pass_context
def discover(
    ctx: click.Context, config: Optional[str], output: str, test_filter: tuple[str, ...]
) -> None:
    """Discover datasets from configured sources.

    Queries GitHub/Forgejo APIs to identify available raw and derivative datasets
    without cloning. Results are cached to the specified output file.

    Example:
        openneuro-studies discover
        openneuro-studies discover --test-filter ds000001 --test-filter ds000010
    """
    try:
        # Load configuration
        config_path = config or ctx.obj.get("config", ".openneuro-studies/config.yaml")
        cfg = load_config(config_path)

        # Create dataset finder
        test_dataset_filter = list(test_filter) if test_filter else None
        finder = DatasetFinder(cfg, test_dataset_filter=test_dataset_filter)

        # Discover datasets
        click.echo("Discovering datasets from configured sources...")
        if test_dataset_filter:
            click.echo(f"Using test filter: {', '.join(test_dataset_filter)}")

        discovered = finder.discover_all()

        # Report results
        raw_count = len(discovered["raw"])
        deriv_count = len(discovered["derivative"])
        click.echo(f"✓ Found {raw_count} raw datasets")
        click.echo(f"✓ Found {deriv_count} derivative datasets")

        # Save results
        finder.save_discovered(discovered, output)
        click.echo(f"✓ Saved to {output}")

    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except DatasetDiscoveryError as e:
        click.echo(f"Discovery error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)
