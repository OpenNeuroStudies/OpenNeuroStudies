"""Publication status tracking for study repositories."""

import json
import logging
from datetime import datetime
from pathlib import Path

import datalad.api as dl

from openneuro_studies.models import PublicationStatus, PublishedStudy

logger = logging.getLogger(__name__)


def load_publication_status(config_dir: Path = Path(".openneuro-studies")) -> PublicationStatus:
    """Load publication status from JSON file.

    Args:
        config_dir: Configuration directory containing published-studies.json

    Returns:
        PublicationStatus instance (empty if file doesn't exist)
    """
    status_file = config_dir / "published-studies.json"
    if not status_file.exists():
        # Return empty status - will need organization set later
        return PublicationStatus(studies=[], organization="", last_updated=datetime.utcnow())

    with open(status_file) as f:
        data = json.load(f)

    return PublicationStatus(**data)


def save_publication_status(
    status: PublicationStatus,
    config_dir: Path = Path(".openneuro-studies"),
    commit: bool = True,
) -> None:
    """Save publication status to JSON file.

    Studies are sorted by study_id for deterministic output.

    Args:
        status: PublicationStatus to save
        config_dir: Configuration directory for output file
        commit: Whether to commit changes to .openneuro-studies subdataset (default: True)
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    status_file = config_dir / "published-studies.json"

    # Update last_updated timestamp
    status.last_updated = datetime.utcnow()

    # Convert to serializable format
    data = status.model_dump(mode="json")

    with open(status_file, "w") as f:
        json.dump(data, f, indent=2)

    # Commit to .openneuro-studies subdataset
    if commit:
        try:
            status_file_abs = status_file.resolve()
            dl.save(
                dataset="^",
                path=str(status_file_abs),
                message=f"Update publication status\n\n"
                f"Tracked {len(status.studies)} published studies\n"
                f"Updated by openneuro-studies publish command",
            )
            logger.info("Committed published-studies.json to .openneuro-studies subdataset")
        except Exception as e:
            logger.warning(f"Failed to commit published-studies.json: {e}")


class PublicationTracker:
    """Helper class for tracking publication status.

    Provides convenience methods for common publication tracking operations.

    Attributes:
        status: Current publication status
        config_dir: Configuration directory path
    """

    def __init__(self, config_dir: Path = Path(".openneuro-studies")):
        """Initialize publication tracker.

        Args:
            config_dir: Configuration directory
        """
        self.config_dir = config_dir
        self.status = load_publication_status(config_dir)

    def mark_published(
        self,
        study_id: str,
        github_url: str,
        commit_sha: str,
        published_at: datetime | None = None,
    ) -> None:
        """Mark a study as published.

        Args:
            study_id: Study identifier
            github_url: Full GitHub repository URL
            commit_sha: Commit SHA that was pushed
            published_at: Publication timestamp (defaults to now)
        """
        if published_at is None:
            published_at = datetime.utcnow()

        study = PublishedStudy(
            study_id=study_id,
            github_url=github_url,
            published_at=published_at,
            last_push_commit_sha=commit_sha,
            last_push_at=datetime.utcnow(),
        )
        self.status.add_study(study)

    def mark_unpublished(self, study_id: str) -> bool:
        """Mark a study as unpublished (remove from tracking).

        Args:
            study_id: Study identifier

        Returns:
            True if study was removed, False if not found
        """
        return self.status.remove_study(study_id)

    def is_published(self, study_id: str) -> bool:
        """Check if a study is published.

        Args:
            study_id: Study identifier

        Returns:
            True if published, False otherwise
        """
        return self.status.is_published(study_id)

    def get_published_studies(self) -> list[str]:
        """Get list of all published study IDs.

        Returns:
            List of study identifiers
        """
        return [s.study_id for s in self.status.studies]

    def save(self, commit: bool = True) -> None:
        """Save current status to file.

        Args:
            commit: Whether to commit to git (default: True)
        """
        save_publication_status(self.status, self.config_dir, commit=commit)
