"""Unit tests for publishing functionality."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from github import GithubException, UnknownObjectException

from openneuro_studies.models import PublicationStatus, PublishedStudy
from openneuro_studies.publishing import (
    GitHubPublisher,
    PublicationTracker,
    PublishError,
    load_publication_status,
    save_publication_status,
)
from openneuro_studies.publishing.sync import SyncResult, sync_publication_status


class TestPublishedStudy:
    """Test PublishedStudy model."""

    @pytest.mark.ai_generated
    def test_valid_study(self):
        """Test creating a valid published study."""
        study = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/OpenNeuroStudies/study-ds000001",
            published_at=datetime(2025, 1, 1, 12, 0, 0),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime(2025, 1, 2, 12, 0, 0),
        )
        assert study.study_id == "study-ds000001"
        assert str(study.github_url) == "https://github.com/OpenNeuroStudies/study-ds000001"

    @pytest.mark.ai_generated
    def test_invalid_study_id(self):
        """Test that invalid study ID patterns are rejected."""
        with pytest.raises(Exception):  # Pydantic validation error
            PublishedStudy(
                study_id="invalid-id",
                github_url="https://github.com/test/repo",
                published_at=datetime.utcnow(),
                last_push_commit_sha="a" * 40,
                last_push_at=datetime.utcnow(),
            )

    @pytest.mark.ai_generated
    def test_invalid_commit_sha(self):
        """Test that invalid commit SHA is rejected."""
        with pytest.raises(Exception):  # Pydantic validation error
            PublishedStudy(
                study_id="study-ds000001",
                github_url="https://github.com/test/repo",
                published_at=datetime.utcnow(),
                last_push_commit_sha="short",  # Too short
                last_push_at=datetime.utcnow(),
            )


class TestPublicationStatus:
    """Test PublicationStatus model."""

    @pytest.mark.ai_generated
    def test_empty_status(self):
        """Test creating empty publication status."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        assert len(status.studies) == 0
        assert status.organization == "TestOrg"

    @pytest.mark.ai_generated
    def test_add_study(self):
        """Test adding a study to status."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        study = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime.utcnow(),
        )
        status.add_study(study)
        assert len(status.studies) == 1
        assert status.studies[0].study_id == "study-ds000001"

    @pytest.mark.ai_generated
    def test_add_duplicate_study_replaces(self):
        """Test that adding duplicate study replaces existing entry."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        study1 = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime.utcnow(),
        )
        study2 = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="b" * 40,
            last_push_at=datetime.utcnow(),
        )
        status.add_study(study1)
        status.add_study(study2)
        assert len(status.studies) == 1
        assert status.studies[0].last_push_commit_sha == "b" * 40

    @pytest.mark.ai_generated
    def test_remove_study(self):
        """Test removing a study from status."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        study = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime.utcnow(),
        )
        status.add_study(study)
        assert status.remove_study("study-ds000001") is True
        assert len(status.studies) == 0

    @pytest.mark.ai_generated
    def test_remove_nonexistent_study(self):
        """Test removing a study that doesn't exist."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        assert status.remove_study("study-ds999999") is False

    @pytest.mark.ai_generated
    def test_is_published(self):
        """Test checking if a study is published."""
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        study = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime.utcnow(),
        )
        status.add_study(study)
        assert status.is_published("study-ds000001") is True
        assert status.is_published("study-ds999999") is False


class TestPublicationTracker:
    """Test PublicationTracker class."""

    @pytest.mark.ai_generated
    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from nonexistent file creates empty status."""
        config_dir = tmp_path / "config"
        tracker = PublicationTracker(config_dir)
        assert len(tracker.status.studies) == 0

    @pytest.mark.ai_generated
    def test_mark_published(self, tmp_path):
        """Test marking a study as published."""
        config_dir = tmp_path / "config"
        tracker = PublicationTracker(config_dir)
        tracker.mark_published(
            "study-ds000001",
            "https://github.com/TestOrg/study-ds000001",
            "a" * 40,
        )
        assert tracker.is_published("study-ds000001") is True

    @pytest.mark.ai_generated
    def test_mark_unpublished(self, tmp_path):
        """Test marking a study as unpublished."""
        config_dir = tmp_path / "config"
        tracker = PublicationTracker(config_dir)
        tracker.mark_published(
            "study-ds000001",
            "https://github.com/TestOrg/study-ds000001",
            "a" * 40,
        )
        assert tracker.mark_unpublished("study-ds000001") is True
        assert tracker.is_published("study-ds000001") is False

    @pytest.mark.ai_generated
    def test_get_published_studies(self, tmp_path):
        """Test getting list of published study IDs."""
        config_dir = tmp_path / "config"
        tracker = PublicationTracker(config_dir)
        tracker.mark_published(
            "study-ds000001",
            "https://github.com/TestOrg/study-ds000001",
            "a" * 40,
        )
        tracker.mark_published(
            "study-ds000002",
            "https://github.com/TestOrg/study-ds000002",
            "b" * 40,
        )
        studies = tracker.get_published_studies()
        assert len(studies) == 2
        assert "study-ds000001" in studies
        assert "study-ds000002" in studies


class TestLoadSavePublicationStatus:
    """Test load/save publication status functions."""

    @pytest.mark.ai_generated
    def test_save_and_load(self, tmp_path):
        """Test saving and loading publication status."""
        config_dir = tmp_path / "config"
        status = PublicationStatus(
            studies=[], organization="TestOrg", last_updated=datetime.utcnow()
        )
        study = PublishedStudy(
            study_id="study-ds000001",
            github_url="https://github.com/TestOrg/study-ds000001",
            published_at=datetime.utcnow(),
            last_push_commit_sha="a" * 40,
            last_push_at=datetime.utcnow(),
        )
        status.add_study(study)

        # Save (without git commit)
        save_publication_status(status, config_dir, commit=False)

        # Load
        loaded_status = load_publication_status(config_dir)
        assert len(loaded_status.studies) == 1
        assert loaded_status.studies[0].study_id == "study-ds000001"
        assert loaded_status.organization == "TestOrg"


class TestGitHubPublisher:
    """Test GitHubPublisher class."""

    @pytest.mark.ai_generated
    def test_init_invalid_organization(self):
        """Test initialization with invalid organization."""
        with patch("openneuro_studies.publishing.github_publisher.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_github_instance.get_organization.side_effect = UnknownObjectException(
                status=404, data={"message": "Not Found"}, headers={}
            )

            with pytest.raises(PublishError, match="not found"):
                GitHubPublisher("fake-token", "NonexistentOrg")

    @pytest.mark.ai_generated
    def test_repository_exists(self):
        """Test checking if repository exists."""
        with patch("openneuro_studies.publishing.github_publisher.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_org = Mock()
            mock_github_instance.get_organization.return_value = mock_org

            # Repository exists
            mock_org.get_repo.return_value = Mock()
            publisher = GitHubPublisher("fake-token", "TestOrg")
            assert publisher.repository_exists("study-ds000001") is True

            # Repository doesn't exist
            mock_org.get_repo.side_effect = UnknownObjectException(
                status=404, data={"message": "Not Found"}, headers={}
            )
            assert publisher.repository_exists("study-ds999999") is False

    @pytest.mark.ai_generated
    def test_get_remote_head_sha(self):
        """Test getting remote HEAD commit SHA."""
        with patch("openneuro_studies.publishing.github_publisher.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_org = Mock()
            mock_github_instance.get_organization.return_value = mock_org

            mock_repo = Mock()
            mock_repo.default_branch = "main"
            mock_branch = Mock()
            mock_commit = Mock()
            mock_commit.sha = "a" * 40
            mock_branch.commit = mock_commit
            mock_repo.get_branch.return_value = mock_branch
            mock_org.get_repo.return_value = mock_repo

            publisher = GitHubPublisher("fake-token", "TestOrg")
            sha = publisher.get_remote_head_sha("study-ds000001")
            assert sha == "a" * 40


class TestSyncPublicationStatus:
    """Test sync_publication_status function."""

    @pytest.mark.ai_generated
    def test_sync_add_new_study(self):
        """Test syncing when GitHub has new study not in local tracking."""
        with patch("openneuro_studies.publishing.sync.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_org = Mock()
            mock_github_instance.get_organization.return_value = mock_org

            # Mock GitHub repos
            mock_repo = Mock()
            mock_repo.name = "study-ds000001"
            mock_repo.html_url = "https://github.com/TestOrg/study-ds000001"
            mock_repo.default_branch = "main"
            mock_branch = Mock()
            mock_commit = Mock()
            mock_commit.sha = "a" * 40
            mock_branch.commit = mock_commit
            mock_repo.get_branch.return_value = mock_branch
            mock_org.get_repos.return_value = [mock_repo]

            # Empty local status
            status = PublicationStatus(
                studies=[], organization="TestOrg", last_updated=datetime.utcnow()
            )

            result = sync_publication_status("fake-token", "TestOrg", status)
            assert result.added == 1
            assert "study-ds000001" in result.added_studies
            assert len(status.studies) == 1

    @pytest.mark.ai_generated
    def test_sync_remove_deleted_study(self):
        """Test syncing when local tracking has study deleted from GitHub."""
        with patch("openneuro_studies.publishing.sync.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_org = Mock()
            mock_github_instance.get_organization.return_value = mock_org

            # Empty GitHub repos
            mock_org.get_repos.return_value = []

            # Local status has a study
            status = PublicationStatus(
                studies=[], organization="TestOrg", last_updated=datetime.utcnow()
            )
            study = PublishedStudy(
                study_id="study-ds000001",
                github_url="https://github.com/TestOrg/study-ds000001",
                published_at=datetime.utcnow(),
                last_push_commit_sha="a" * 40,
                last_push_at=datetime.utcnow(),
            )
            status.add_study(study)

            result = sync_publication_status("fake-token", "TestOrg", status)
            assert result.removed == 1
            assert "study-ds000001" in result.removed_studies
            assert len(status.studies) == 0

    @pytest.mark.ai_generated
    def test_sync_update_commit_sha(self):
        """Test syncing when commit SHA differs between local and GitHub."""
        with patch("openneuro_studies.publishing.sync.Github") as mock_github:
            mock_github_instance = Mock()
            mock_github.return_value = mock_github_instance
            mock_org = Mock()
            mock_github_instance.get_organization.return_value = mock_org

            # Mock GitHub repos with new SHA
            mock_repo = Mock()
            mock_repo.name = "study-ds000001"
            mock_repo.html_url = "https://github.com/TestOrg/study-ds000001"
            mock_repo.default_branch = "main"
            mock_branch = Mock()
            mock_commit = Mock()
            mock_commit.sha = "b" * 40  # New SHA
            mock_branch.commit = mock_commit
            mock_repo.get_branch.return_value = mock_branch
            mock_org.get_repos.return_value = [mock_repo]

            # Local status has old SHA
            status = PublicationStatus(
                studies=[], organization="TestOrg", last_updated=datetime.utcnow()
            )
            study = PublishedStudy(
                study_id="study-ds000001",
                github_url="https://github.com/TestOrg/study-ds000001",
                published_at=datetime.utcnow(),
                last_push_commit_sha="a" * 40,  # Old SHA
                last_push_at=datetime.utcnow(),
            )
            status.add_study(study)

            result = sync_publication_status("fake-token", "TestOrg", status)
            assert result.updated == 1
            assert len(result.updated_studies) == 1
            assert result.updated_studies[0][0] == "study-ds000001"
            assert result.updated_studies[0][1] == "a" * 40  # Old
            assert result.updated_studies[0][2] == "b" * 40  # New
            assert status.studies[0].last_push_commit_sha == "b" * 40


class TestSyncResult:
    """Test SyncResult class."""

    @pytest.mark.ai_generated
    def test_str_no_changes(self):
        """Test string representation with no changes."""
        result = SyncResult()
        assert "No changes" in str(result)

    @pytest.mark.ai_generated
    def test_str_with_changes(self):
        """Test string representation with changes."""
        result = SyncResult()
        result.added = 1
        result.added_studies = ["study-ds000001"]
        result.removed = 1
        result.removed_studies = ["study-ds000002"]
        result.updated = 1
        result.updated_studies = [("study-ds000003", "a" * 40, "b" * 40)]

        output = str(result)
        assert "Added 1" in output
        assert "Removed 1" in output
        assert "Updated 1" in output
        assert "study-ds000001" in output
        assert "study-ds000002" in output
        assert "study-ds000003" in output
