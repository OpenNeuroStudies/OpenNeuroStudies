"""Unit tests for GitHub API client."""

import base64
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from openneuro_studies.utils import GitHubAPIError, GitHubClient


@pytest.mark.unit
@pytest.mark.ai_generated
class TestGitHubClient:
    """Tests for GitHubClient class."""

    def test_init_with_token(self) -> None:
        """Test initialization with explicit token."""
        client = GitHubClient(token="test_token")
        assert client.token == "test_token"
        assert client.base_url == "https://api.github.com"

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization from GITHUB_TOKEN environment variable."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient()
        assert client.token == "env_token"

    def test_init_no_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when no token is provided."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(GitHubAPIError, match="GitHub token required"):
            GitHubClient()

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_list_repositories(self, mock_session_class: Mock) -> None:
        """Test listing repositories from an organization."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "ds000001", "url": "https://api.github.com/repos/org/ds000001"},
            {"name": "ds000002", "url": "https://api.github.com/repos/org/ds000002"},
        ]
        mock_session.get.return_value = mock_response

        client = GitHubClient(token="test_token")
        repos = client.list_repositories("TestOrg")

        assert len(repos) == 2
        assert repos[0]["name"] == "ds000001"
        assert repos[1]["name"] == "ds000002"

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_list_repositories_with_filter(self, mock_session_class: Mock) -> None:
        """Test filtering repositories by dataset ID."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "ds000001", "url": "https://api.github.com/repos/org/ds000001"},
            {"name": "ds000002", "url": "https://api.github.com/repos/org/ds000002"},
            {"name": "ds000003", "url": "https://api.github.com/repos/org/ds000003"},
        ]
        mock_session.get.return_value = mock_response

        client = GitHubClient(token="test_token")
        repos = client.list_repositories("TestOrg", dataset_filter=["ds000001", "ds000003"])

        assert len(repos) == 2
        assert repos[0]["name"] == "ds000001"
        assert repos[1]["name"] == "ds000003"

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_get_file_content(self, mock_session_class: Mock) -> None:
        """Test getting file content from repository."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        test_content = "test file content"
        encoded_content = base64.b64encode(test_content.encode()).decode()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": encoded_content}
        mock_session.get.return_value = mock_response

        client = GitHubClient(token="test_token")
        content = client.get_file_content("owner", "repo", "path/to/file.txt")

        assert content == test_content

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_get_file_content_missing_field(self, mock_session_class: Mock) -> None:
        """Test error when content field is missing."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"not_content": "data"}
        mock_session.get.return_value = mock_response

        client = GitHubClient(token="test_token")

        with pytest.raises(GitHubAPIError, match="no content field"):
            client.get_file_content("owner", "repo", "path/to/file.txt")

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_get_default_branch_sha(self, mock_session_class: Mock) -> None:
        """Test getting commit SHA of default branch."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock repository info
        repo_response = Mock()
        repo_response.status_code = 200
        repo_response.json.return_value = {"default_branch": "main"}

        # Mock commit info
        commit_response = Mock()
        commit_response.status_code = 200
        commit_response.json.return_value = {"sha": "a" * 40}

        mock_session.get.side_effect = [repo_response, commit_response]

        client = GitHubClient(token="test_token")
        sha = client.get_default_branch_sha("owner", "repo")

        assert sha == "a" * 40
        assert mock_session.get.call_count == 2

    @patch("openneuro_studies.utils.github_client.CachedSession")
    def test_rate_limit_handling(self, mock_session_class: Mock) -> None:
        """Test rate limit detection."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "API rate limit exceeded"
        mock_response.headers = {"X-RateLimit-Reset": "9999999999"}
        mock_session.get.return_value = mock_response

        client = GitHubClient(token="test_token")

        with pytest.raises(GitHubAPIError, match="Rate limit exceeded"):
            client._request("/test/endpoint")

    @patch("openneuro_studies.utils.github_client.CachedSession")
    @patch("time.sleep")  # Mock sleep to speed up test
    def test_retry_on_failure(self, mock_sleep: Mock, mock_session_class: Mock) -> None:
        """Test retry logic on transient failures."""
        # Setup mock
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # First call raises exception, second succeeds
        import requests

        def side_effect_func(*args: Any, **kwargs: Any) -> Mock:
            if mock_session.get.call_count == 1:
                raise requests.exceptions.RequestException("Server error")
            success_response = Mock()
            success_response.status_code = 200
            success_response.json.return_value = {"data": "success"}
            success_response.raise_for_status.return_value = None
            return success_response

        mock_session.get.side_effect = side_effect_func

        client = GitHubClient(token="test_token")
        result = client._request("/test/endpoint", retry=2)

        assert result == {"data": "success"}
        assert mock_session.get.call_count == 2
        assert mock_sleep.called  # Verify exponential backoff was used
