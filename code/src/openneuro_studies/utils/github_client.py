"""GitHub API client with caching."""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests_cache import CachedSession


class GitHubAPIError(Exception):
    """Raised when GitHub API request fails."""

    pass


class GitHubClient:
    """GitHub API client with caching and rate limit handling.

    Attributes:
        session: Cached requests session
        token: GitHub personal access token
        cache_dir: Directory for API cache
    """

    def __init__(
        self,
        token: Optional[str] = None,
        cache_dir: str = ".openneuro-studies/cache",
        cache_expire_after: int = 3600,
    ):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If None, reads from GITHUB_TOKEN env var.
            cache_dir: Directory for cache storage
            cache_expire_after: Cache expiration time in seconds (default: 1 hour)

        Raises:
            GitHubAPIError: If no token provided and GITHUB_TOKEN not set
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise GitHubAPIError(
                "GitHub token required. Set GITHUB_TOKEN environment variable or "
                "pass token parameter."
            )

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create cached session
        cache_path = self.cache_dir / "github_api_cache"
        self.session = CachedSession(
            str(cache_path),
            expire_after=cache_expire_after,
            allowable_methods=["GET"],
            stale_if_error=True,  # Use stale cache if API fails
        )

        self.session.headers.update(
            {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )

        self.base_url = "https://api.github.com"

    def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, retry: int = 3
    ) -> Dict[str, Any]:
        """Make GitHub API request with retry logic.

        Args:
            endpoint: API endpoint (e.g., "/repos/owner/repo")
            params: Query parameters
            retry: Number of retries for transient errors

        Returns:
            JSON response as dictionary

        Raises:
            GitHubAPIError: If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retry):
            try:
                response = self.session.get(url, params=params, timeout=30)

                # Handle rate limiting
                if response.status_code == 403 and "rate limit" in response.text.lower():
                    reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                    if reset_time:
                        wait_time = max(0, reset_time - time.time())
                        if wait_time > 300:  # Don't wait more than 5 minutes
                            raise GitHubAPIError(
                                f"Rate limit exceeded. Reset in {wait_time/60:.1f} minutes."
                            )
                        time.sleep(wait_time + 1)
                        continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt == retry - 1:  # Last attempt
                    raise GitHubAPIError(f"GitHub API request failed: {e}")
                time.sleep(2**attempt)  # Exponential backoff

        raise GitHubAPIError(f"Failed to fetch {url} after {retry} attempts")

    def list_repositories(
        self, organization: str, dataset_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """List repositories in an organization.

        Args:
            organization: GitHub organization name
            dataset_filter: Optional list of dataset IDs to filter (e.g., ["ds000001", "ds000010"])

        Returns:
            List of repository dictionaries

        Raises:
            GitHubAPIError: If request fails
        """
        repos = []
        page = 1
        per_page = 100

        while True:
            endpoint = f"/orgs/{organization}/repos"
            params = {"page": page, "per_page": per_page, "type": "public"}

            response_data = self._request(endpoint, params)

            if not response_data:
                break

            # Apply dataset filter if provided
            if dataset_filter:
                response_data = [
                    repo for repo in response_data if repo["name"] in dataset_filter
                ]

            repos.extend(response_data)

            # Check if we've found all filtered datasets or reached end of pagination
            if dataset_filter and len(repos) >= len(dataset_filter):
                break

            if len(response_data) < per_page:
                break

            page += 1

        return repos

    def get_file_content(self, owner: str, repo: str, file_path: str, ref: str = "HEAD") -> str:
        """Get content of a file from repository.

        Args:
            owner: Repository owner
            repo: Repository name
            file_path: Path to file in repository
            ref: Git ref (branch, tag, or commit SHA)

        Returns:
            File content as string

        Raises:
            GitHubAPIError: If file not found or request fails
        """
        endpoint = f"/repos/{owner}/{repo}/contents/{file_path}"
        params = {"ref": ref}

        response_data = self._request(endpoint, params)

        if "content" not in response_data:
            raise GitHubAPIError(f"File {file_path} has no content field")

        # GitHub returns base64-encoded content
        import base64

        content = base64.b64decode(response_data["content"]).decode("utf-8")
        return content

    def get_default_branch_sha(self, owner: str, repo: str) -> str:
        """Get current commit SHA of default branch.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Commit SHA (40-character hex string)

        Raises:
            GitHubAPIError: If request fails
        """
        endpoint = f"/repos/{owner}/{repo}"
        response_data = self._request(endpoint)

        default_branch = response_data.get("default_branch", "main")

        # Get latest commit on default branch
        endpoint = f"/repos/{owner}/{repo}/commits/{default_branch}"
        commit_data = self._request(endpoint)

        return commit_data["sha"]

    def clear_cache(self) -> None:
        """Clear all cached API responses."""
        if hasattr(self.session.cache, "clear"):
            self.session.cache.clear()
