"""CLI command for unpublishing (deleting) study repositories from GitHub."""

import logging

import click

from openneuro_studies.publishing import (
    GitHubPublisher,
    PublicationTracker,
    PublishError,
)

logger = logging.getLogger(__name__)


@click.command()
@click.argument("study_ids", nargs=-1, required=True)
@click.option(
    "--organization",
    type=str,
    envvar="OPENNEURO_STUDIES_GITHUB_ORG",
    default="OpenNeuroStudies",
    help="GitHub organization name",
    show_default=True,
)
@click.option(
    "--token",
    type=str,
    envvar="GITHUB_TOKEN",
    required=True,
    help="GitHub personal access token (or set GITHUB_TOKEN env var)",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip confirmation prompt (dangerous!)",
)
@click.pass_context
def unpublish(
    ctx: click.Context,
    study_ids: tuple[str, ...],
    organization: str,
    token: str,
    yes: bool,
) -> None:
    """Unpublish (delete) study repositories from GitHub.

    WARNING: This permanently deletes repositories from GitHub! Local copies
    are not affected.

    Arguments:
        STUDY_IDS: One or more study IDs to unpublish (required).

    Environment Variables:
        GITHUB_TOKEN: GitHub personal access token (required)
        OPENNEURO_STUDIES_GITHUB_ORG: GitHub organization (default: OpenNeuroStudies)

    Examples:
        # Unpublish a single study (with confirmation)
        openneuro-studies unpublish study-ds000001

        # Unpublish multiple studies
        openneuro-studies unpublish study-ds000001 study-ds005256

        # Skip confirmation (dangerous!)
        openneuro-studies unpublish study-ds000001 --yes

    Safety Features:
        - Requires explicit study IDs (no "all" option)
        - Interactive confirmation prompt (unless --yes)
        - Lists what will be deleted before proceeding
        - Only removes from tracking after successful GitHub deletion
    """
    from pathlib import Path

    config_dir = Path(".openneuro-studies")

    # Initialize publisher and tracker
    try:
        publisher = GitHubPublisher(token, organization)
    except PublishError as e:
        raise click.ClickException(str(e)) from e

    tracker = PublicationTracker(config_dir)

    # Validate study IDs and check existence
    studies_to_delete = []
    for study_id in study_ids:
        # Check if repository exists on GitHub
        if not publisher.repository_exists(study_id):
            click.echo(f"Warning: {study_id} not found on GitHub, skipping", err=True)
            continue

        studies_to_delete.append(study_id)

    if not studies_to_delete:
        click.echo("No repositories to unpublish")
        return

    # Show what will be deleted
    click.echo("The following repositories will be PERMANENTLY DELETED from GitHub:")
    click.echo(f"Organization: {organization}")
    click.echo()
    for study_id in studies_to_delete:
        tracked = tracker.is_published(study_id)
        status = " (tracked locally)" if tracked else " (not tracked locally)"
        click.echo(f"  - {study_id}{status}")
    click.echo()
    click.echo(f"Total: {len(studies_to_delete)} repositories")

    # Confirmation prompt
    if not yes:
        click.echo()
        click.echo("WARNING: This action CANNOT be undone!")
        click.echo("Local study directories will NOT be affected.")
        confirm = click.confirm(
            "Are you sure you want to DELETE these repositories from GitHub?",
            default=False,
        )
        if not confirm:
            click.echo("Aborted - no repositories deleted")
            return

    # Delete repositories
    click.echo()
    deleted_count = 0
    failed_count = 0

    for study_id in studies_to_delete:
        try:
            click.echo(f"Deleting {study_id}...", nl=False)
            publisher.delete_repository(study_id)

            # Remove from tracking
            tracker.mark_unpublished(study_id)

            click.echo(" deleted")
            deleted_count += 1

        except PublishError as e:
            click.echo(f" FAILED: {e}", err=True)
            failed_count += 1
            logger.error(f"Failed to delete {study_id}: {e}")

    # Save updated tracking
    if deleted_count > 0:
        tracker.save(commit=True)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"Deleted: {deleted_count} repositories")
    if failed_count > 0:
        click.echo(f"Failed: {failed_count} repositories", err=True)
    click.echo(f"\nUpdated tracking file: {config_dir}/published-studies.json")
