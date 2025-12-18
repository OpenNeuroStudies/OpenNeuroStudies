"""CLI command for provisioning study datasets with templated content."""

import logging
from pathlib import Path

import click

from openneuro_studies.provision import (
    TEMPLATE_VERSION_FILE,
    needs_provisioning,
    provision_study,
)

logger = logging.getLogger(__name__)


@click.command()
@click.argument("study_ids", nargs=-1, required=False)
@click.option(
    "--force",
    is_flag=True,
    help="Force re-provisioning even if already up-to-date",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be provisioned without making changes",
)
@click.option(
    "--commit/--no-commit",
    default=True,
    help="Commit changes with datalad save",
)
@click.pass_context
def provision(
    ctx: click.Context,
    study_ids: tuple[str, ...],
    force: bool,
    dry_run: bool,
    commit: bool,
) -> None:
    """Provision study datasets with templated content.

    Creates standardized files in each study:
    - code/run-bids-validator: Script for running BIDS validation via datalad run
    - README.md: Study dataset overview
    - .openneuro-studies/template-version: Template version tracking

    Arguments:
        STUDY_IDS: Optional list of study IDs. If not provided, provisions all studies.

    Examples:
        # Provision all studies
        openneuro-studies provision

        # Provision specific studies
        openneuro-studies provision study-ds000001 study-ds005256

        # Force re-provisioning
        openneuro-studies provision --force

        # Preview changes
        openneuro-studies provision --dry-run
    """
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

    click.echo(f"Provisioning {len(study_paths)} studies...")

    if dry_run:
        click.echo("[DRY RUN] Would provision the following:")

    # Track results
    provisioned_count = 0
    skipped_count = 0
    error_count = 0

    for study_path in study_paths:
        result = provision_study(study_path, force=force, dry_run=dry_run)

        if result.error and "Already up-to-date" in result.error:
            click.echo(f"  {result.study_id}: skipped (up-to-date)")
            skipped_count += 1
        elif result.error:
            click.echo(f"  {result.study_id}: ERROR - {result.error}", err=True)
            error_count += 1
        elif result.provisioned:
            if dry_run:
                changes = []
                if result.files_created:
                    changes.append(f"create: {', '.join(result.files_created)}")
                if result.files_updated:
                    changes.append(f"update: {', '.join(result.files_updated)}")
                click.echo(f"  {result.study_id}: {'; '.join(changes)}")
            else:
                changes = []
                if result.files_created:
                    changes.append(f"+{len(result.files_created)}")
                if result.files_updated:
                    changes.append(f"~{len(result.files_updated)}")
                click.echo(f"  {result.study_id}: provisioned ({', '.join(changes)} files)")
            provisioned_count += 1

    # Summary
    click.echo("")
    click.echo("=" * 60)
    if dry_run:
        click.echo(f"Would provision: {provisioned_count} studies")
    else:
        click.echo(f"Provisioned: {provisioned_count} studies")
    click.echo(f"Skipped: {skipped_count} (already up-to-date)")
    if error_count > 0:
        click.echo(f"Errors: {error_count}", err=True)

    # Commit changes if requested
    if commit and provisioned_count > 0 and not dry_run:
        from openneuro_studies.lib import save_with_stats

        click.echo("\nCommitting changes...")

        # First commit in study subdatasets
        for study_path in study_paths:
            if not needs_provisioning(study_path, force=False):
                # Already provisioned, commit changes
                try:
                    import subprocess

                    result = subprocess.run(
                        ["git", "-C", str(study_path), "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                    )
                    if result.stdout.strip():
                        subprocess.run(
                            ["git", "-C", str(study_path), "add", "-A"],
                            check=True,
                            capture_output=True,
                        )
                        subprocess.run(
                            [
                                "git", "-C", str(study_path), "commit", "-m",
                                "Provision study with templated content\n\n"
                                "Generated by openneuro-studies provision",
                            ],
                            check=True,
                            capture_output=True,
                        )
                except subprocess.CalledProcessError:
                    pass

        # Then commit at root level with stats
        stats: dict[str, int | str] = {
            "provisioned": provisioned_count,
            "skipped": skipped_count,
        }
        if error_count > 0:
            stats["errors"] = error_count

        success = save_with_stats(
            message="Provision study datasets",
            stats=stats,
            dataset=".",
        )
        if success:
            click.echo("  Changes committed")
        else:
            click.echo("  Failed to commit changes", err=True)
