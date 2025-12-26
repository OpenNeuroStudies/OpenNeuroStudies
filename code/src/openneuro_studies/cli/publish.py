"""CLI command for publishing study repositories to GitHub."""

import logging
from pathlib import Path

import click

from openneuro_studies.publishing import (
    GitHubPublisher,
    PublicationTracker,
    PublishError,
    sync_publication_status,
)
from openneuro_studies.publishing.github_publisher import datalad_push_since

logger = logging.getLogger(__name__)


@click.command()
@click.argument("study_ids", nargs=-1, required=False)
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
    "--force",
    is_flag=True,
    help="Force push if remote differs from local",
)
@click.option(
    "--sync",
    is_flag=True,
    help="Sync local tracking with GitHub state (reconcile manual changes)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be published without actually doing it",
)
@click.option(
    "--since",
    type=str,
    default=None,
    help="Use datalad push --since for efficient incremental push. "
    'Use "^" for last pushed state or a git ref (branch/tag/commit).',
)
@click.pass_context
def publish(
    ctx: click.Context,
    study_ids: tuple[str, ...],
    organization: str,
    token: str,
    force: bool,
    sync: bool,
    dry_run: bool,
    since: str | None,
) -> None:
    """Publish study repositories to GitHub.

    Creates remote repositories (if they don't exist) and pushes local study
    repositories to the configured GitHub organization.

    Arguments:
        STUDY_IDS: Optional list of study IDs to publish. If not provided,
                   publishes all organized studies.

    Environment Variables:
        GITHUB_TOKEN: GitHub personal access token (required)
        OPENNEURO_STUDIES_GITHUB_ORG: GitHub organization (default: OpenNeuroStudies)

    Examples:
        # Publish all studies
        openneuro-studies publish --token ghp_xxxxx

        # Publish specific studies
        openneuro-studies publish study-ds000001 study-ds005256

        # Force push to overwrite remote
        openneuro-studies publish --force study-ds000001

        # Sync local tracking with GitHub state
        openneuro-studies publish --sync

        # Dry run (show what would happen)
        openneuro-studies publish --dry-run

        # Efficient incremental push (only push changed studies since last push)
        openneuro-studies publish --since=^

        # Push only studies changed since a specific tag
        openneuro-studies publish --since=v1.0.0
    """
    config_dir = Path(".openneuro-studies")

    # Sync mode: reconcile local tracking with GitHub
    if sync:
        click.echo(f"Synchronizing publication status with {organization}...")
        tracker = PublicationTracker(config_dir)

        # Set organization if not already set
        if not tracker.status.organization:
            tracker.status.organization = organization

        if dry_run:
            click.echo("[DRY RUN] Would sync with GitHub, no changes made")
            return

        try:
            result = sync_publication_status(token, organization, tracker.status)
            click.echo(str(result))

            # Save updated status
            if result.added > 0 or result.removed > 0 or result.updated > 0:
                tracker.save(commit=True)
                click.echo(f"\nUpdated {config_dir}/published-studies.json")
            else:
                click.echo(f"\n{config_dir}/published-studies.json already up-to-date")

        except Exception as e:
            raise click.ClickException(f"Sync failed: {e}") from e

        return

    # Efficient incremental push using datalad push --since
    if since is not None:
        click.echo(f"Using datalad push --since={since} for incremental push...")

        if study_ids:
            click.echo(
                "Warning: --since mode pushes all changed subdatasets, "
                "ignoring specific study IDs",
                err=True,
            )

        try:
            pushed, skipped, pushed_paths = datalad_push_since(
                dataset_path=Path("."),
                since=since,
                to="origin",  # Push to origin remote
                recursive=True,
                dry_run=dry_run,
            )

            if dry_run:
                click.echo(f"[DRY RUN] Would push {pushed} datasets")
            else:
                click.echo(f"\nPushed: {pushed} datasets")
                click.echo(f"Skipped (no changes): {skipped} datasets")
                if pushed_paths:
                    click.echo("\nPushed paths:")
                    for path in pushed_paths[:20]:  # Show first 20
                        click.echo(f"  {path}")
                    if len(pushed_paths) > 20:
                        click.echo(f"  ... and {len(pushed_paths) - 20} more")

        except Exception as e:
            raise click.ClickException(f"datalad push failed: {e}") from e

        return

    # Publishing mode: publish studies to GitHub
    try:
        publisher = GitHubPublisher(token, organization)
    except PublishError as e:
        raise click.ClickException(str(e)) from e

    # Load publication tracker
    tracker = PublicationTracker(config_dir)

    # Set organization if not already set
    if not tracker.status.organization:
        tracker.status.organization = organization

    # Determine which studies to publish
    if study_ids:
        # Publish specified studies
        studies_to_publish = []
        for study_id in study_ids:
            study_path = Path(study_id)
            if not study_path.exists():
                click.echo(f"Warning: {study_id} not found, skipping", err=True)
                continue
            if not study_path.is_dir():
                click.echo(f"Warning: {study_id} is not a directory, skipping", err=True)
                continue
            studies_to_publish.append(study_path)
    else:
        # Find all study-* directories
        studies_to_publish = [
            p for p in Path(".").iterdir() if p.is_dir() and p.name.startswith("study-")
        ]

        if not studies_to_publish:
            click.echo("No study directories found. Run 'openneuro-studies organize' first.")
            return

    if not studies_to_publish:
        click.echo("No studies to publish")
        return

    click.echo(f"Publishing {len(studies_to_publish)} studies to {organization}...")

    if dry_run:
        click.echo("[DRY RUN] Would publish the following studies:")
        for study_path in studies_to_publish:
            status = "exists" if publisher.repository_exists(study_path.name) else "new"
            click.echo(f"  - {study_path.name} ({status})")
        return

    # Publish each study
    published_count = 0
    created_count = 0
    updated_count = 0
    failed_count = 0

    for study_path in studies_to_publish:
        study_id = study_path.name

        try:
            click.echo(f"\nPublishing {study_id}...", nl=False)

            # Check if already up-to-date
            if not force and tracker.is_published(study_id):
                tracked_study = tracker.status.get_study(study_id)
                if tracked_study:
                    remote_sha = publisher.get_remote_head_sha(study_id)
                    if remote_sha == tracked_study.last_push_commit_sha:
                        click.echo(" already up-to-date")
                        continue

            github_url, commit_sha, was_created = publisher.publish_study(study_path, force=force)

            # Update tracking
            tracker.mark_published(study_id, github_url, commit_sha)

            if was_created:
                click.echo(f" created and pushed ({commit_sha[:8]})")
                created_count += 1
            else:
                click.echo(f" pushed ({commit_sha[:8]})")
                updated_count += 1

            published_count += 1

        except PublishError as e:
            click.echo(f" FAILED: {e}", err=True)
            failed_count += 1
            logger.error(f"Failed to publish {study_id}: {e}")

    # Save publication status
    tracker.save(commit=True)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"Published: {published_count} studies")
    if created_count > 0:
        click.echo(f"  Created: {created_count} new repositories")
    if updated_count > 0:
        click.echo(f"  Updated: {updated_count} existing repositories")
    if failed_count > 0:
        click.echo(f"  Failed: {failed_count} studies", err=True)
    click.echo(f"\nTracking file: {config_dir}/published-studies.json")
    click.echo(f"Organization: https://github.com/{organization}")
