"""Synchronize publication status with GitHub state."""

import logging
from datetime import datetime

from github import Github, GithubException, UnknownObjectException

from openneuro_studies.models import PublicationStatus, PublishedStudy

logger = logging.getLogger(__name__)


class SyncResult:
    """Result of a sync operation.

    Attributes:
        added: Number of studies added to tracking
        removed: Number of studies removed from tracking
        updated: Number of studies with updated commit SHAs
        added_studies: List of added study IDs
        removed_studies: List of removed study IDs
        updated_studies: List of updated study IDs with old/new SHAs
    """

    def __init__(self):
        self.added = 0
        self.removed = 0
        self.updated = 0
        self.added_studies: list[str] = []
        self.removed_studies: list[str] = []
        self.updated_studies: list[tuple[str, str, str]] = []  # (study_id, old_sha, new_sha)

    def __str__(self) -> str:
        """Human-readable summary."""
        lines = ["Sync completed:"]
        if self.added > 0:
            lines.append(f"  Added {self.added} studies: {', '.join(self.added_studies)}")
        if self.removed > 0:
            lines.append(f"  Removed {self.removed} studies: {', '.join(self.removed_studies)}")
        if self.updated > 0:
            update_details = [
                f"{sid} ({old[:8]} → {new[:8]})" for sid, old, new in self.updated_studies
            ]
            lines.append(f"  Updated {self.updated} studies: {', '.join(update_details)}")
        if self.added == 0 and self.removed == 0 and self.updated == 0:
            lines.append("  No changes - local tracking matches GitHub state")
        return "\n".join(lines)


def sync_publication_status(
    github_token: str,
    organization_name: str,
    status: PublicationStatus,
) -> SyncResult:
    """Synchronize publication status with GitHub state.

    Reconciles local published-studies.json with actual repositories on GitHub:
    1. Queries GitHub API for all repos matching study-* pattern
    2. Adds entries for repos on GitHub but not in tracking (manual additions)
    3. Removes entries in tracking but not on GitHub (manual deletions)
    4. Updates commit SHAs for all tracked studies by querying remote HEAD

    Args:
        github_token: GitHub personal access token
        organization_name: GitHub organization name
        status: Current PublicationStatus to sync

    Returns:
        SyncResult with summary of changes

    Raises:
        GithubException: If GitHub API queries fail
    """
    result = SyncResult()
    github = Github(github_token)

    try:
        organization = github.get_organization(organization_name)
    except UnknownObjectException as e:
        raise GithubException(
            status=404,
            data={"message": f"Organization '{organization_name}' not found"},
            headers={},
        ) from e

    # Get all study-* repositories from GitHub
    try:
        repos = organization.get_repos()
        github_studies = {}  # study_id -> (repo_url, commit_sha)

        for repo in repos:
            repo_name = repo.name
            if not repo_name.startswith("study-"):
                continue

            # Get HEAD commit SHA if available
            try:
                branch = repo.get_branch(repo.default_branch)
                commit_sha = branch.commit.sha
            except GithubException:
                # Repository exists but has no commits yet
                logger.warning(f"Repository {repo_name} has no commits, skipping")
                continue

            github_studies[repo_name] = (repo.html_url, commit_sha)

    except GithubException as e:
        logger.error(f"Failed to list repositories: {e}")
        raise

    # Get current tracked studies
    tracked_studies = {s.study_id: s for s in status.studies}

    # Find studies on GitHub but not tracked locally (manual additions)
    for study_id, (github_url, commit_sha) in github_studies.items():
        if study_id not in tracked_studies:
            # Add new entry
            now = datetime.utcnow()
            new_study = PublishedStudy(
                study_id=study_id,
                github_url=github_url,
                published_at=now,  # We don't know original publish time
                last_push_commit_sha=commit_sha,
                last_push_at=now,
            )
            status.add_study(new_study)
            result.added += 1
            result.added_studies.append(study_id)
            logger.info(f"Added {study_id} to tracking (found on GitHub)")

    # Find studies tracked locally but not on GitHub (manual deletions)
    for study_id in list(tracked_studies.keys()):
        if study_id not in github_studies:
            status.remove_study(study_id)
            result.removed += 1
            result.removed_studies.append(study_id)
            logger.info(f"Removed {study_id} from tracking (deleted from GitHub)")

    # Update commit SHAs for studies that exist in both places
    for study_id, (_github_url, github_sha) in github_studies.items():
        tracked_study = status.get_study(study_id)
        if tracked_study and tracked_study.last_push_commit_sha != github_sha:
            # Update with new SHA
            old_sha = tracked_study.last_push_commit_sha
            updated_study = PublishedStudy(
                study_id=study_id,
                github_url=tracked_study.github_url,
                published_at=tracked_study.published_at,
                last_push_commit_sha=github_sha,
                last_push_at=datetime.utcnow(),
            )
            status.add_study(updated_study)
            result.updated += 1
            result.updated_studies.append((study_id, old_sha, github_sha))
            logger.info(f"Updated {study_id} commit SHA: {old_sha[:8]} → {github_sha[:8]}")

    return result
