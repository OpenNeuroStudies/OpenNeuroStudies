"""Pydantic models for publication tracking."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, HttpUrl


class PublishedStudy(BaseModel):
    """Model for a published study repository.

    Tracks publication status of a study dataset on GitHub.

    Attributes:
        study_id: Study identifier (e.g., "study-ds000001")
        github_url: Full URL to the GitHub repository
        published_at: Timestamp when first published
        last_push_commit_sha: Commit SHA of last push to GitHub
        last_push_at: Timestamp of last push
    """

    study_id: str = Field(..., pattern=r"^study-ds\d+$")
    github_url: HttpUrl
    published_at: datetime
    last_push_commit_sha: str = Field(..., min_length=40, max_length=40)
    last_push_at: datetime


class PublicationStatus(BaseModel):
    """Model for the publication tracking file.

    Stored in .openneuro-studies/published-studies.json

    Attributes:
        studies: List of published studies
        organization: GitHub organization name
        last_updated: Timestamp of last update to this file
    """

    studies: List[PublishedStudy] = Field(default_factory=list)
    organization: str
    last_updated: datetime

    def get_study(self, study_id: str) -> PublishedStudy | None:
        """Get a published study by ID.

        Args:
            study_id: Study identifier to look up

        Returns:
            PublishedStudy if found, None otherwise
        """
        for study in self.studies:
            if study.study_id == study_id:
                return study
        return None

    def add_study(self, study: PublishedStudy) -> None:
        """Add a published study, replacing if already exists.

        Args:
            study: PublishedStudy to add
        """
        # Remove existing entry if present
        self.studies = [s for s in self.studies if s.study_id != study.study_id]
        # Add new entry
        self.studies.append(study)
        # Keep sorted by study_id
        self.studies.sort(key=lambda s: s.study_id)
        # Update timestamp
        self.last_updated = datetime.utcnow()

    def remove_study(self, study_id: str) -> bool:
        """Remove a published study.

        Args:
            study_id: Study identifier to remove

        Returns:
            True if study was removed, False if not found
        """
        original_count = len(self.studies)
        self.studies = [s for s in self.studies if s.study_id != study_id]
        if len(self.studies) < original_count:
            self.last_updated = datetime.utcnow()
            return True
        return False

    def is_published(self, study_id: str) -> bool:
        """Check if a study is published.

        Args:
            study_id: Study identifier to check

        Returns:
            True if published, False otherwise
        """
        return self.get_study(study_id) is not None
