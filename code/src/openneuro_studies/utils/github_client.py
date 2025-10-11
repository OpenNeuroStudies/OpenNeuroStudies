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
                   If no token provided, will use unauthenticated requests (lower rate limit).
            cache_dir: Directory for cache storage
            cache_expire_after: Cache expiration time in seconds (default: 1 hour)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")

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

        # Set up headers - only add Authorization if token is available
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        self.session.headers.update(headers)

        self.base_url = "https://api.github.com"

    def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, retry: int = 3
    ) -> Any:
        """Make GitHub API request with retry logic.

        Args:
            endpoint: API endpoint (e.g., "/repos/owner/repo")
            params: Query parameters
            retry: Number of retries for transient errors

        Returns:
            JSON response (can be dict, list, or other JSON types)

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

                        # Provide helpful message if no token is set
                        token_hint = ""
                        if not self.token:
                            token_hint = " Set GITHUB_TOKEN environment variable for higher rate limits."

                        if wait_time > 300:  # Don't wait more than 5 minutes
                            raise GitHubAPIError(
                                f"Rate limit exceeded. Reset in {wait_time/60:.1f} minutes.{token_hint}"
                            )
                        time.sleep(wait_time + 1)
                        continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt == retry - 1:  # Last attempt
                    raise GitHubAPIError(f"GitHub API request failed: {e}") from e
                time.sleep(2**attempt)  # Exponential backoff

        raise GitHubAPIError(f"Failed to fetch {url} after {retry} attempts")

    def list_repositories(
        self, organization: str, dataset_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """List repositories in an organization.

        Args:
            organization: GitHub organization name
            dataset_filter: Optional list of dataset IDs to filter (e.g., ["ds000001", "ds005256"])

        Returns:
            List of repository dictionaries

        Raises:
            GitHubAPIError: If request fails
        """
        repos: List[Dict[str, Any]] = []
        page = 1
        per_page = 100

        while True:
            endpoint = f"/orgs/{organization}/repos"
            params = {"page": page, "per_page": per_page, "type": "public"}

            response_data: Any = self._request(endpoint, params)

            if not response_data:
                break

            # Ensure response_data is a list
            if not isinstance(response_data, list):
                break

            # Apply dataset filter if provided
            filtered_repos: List[Dict[str, Any]] = response_data
            if dataset_filter:
                filtered_repos = [repo for repo in response_data if repo["name"] in dataset_filter]

            repos.extend(filtered_repos)

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

        response_data: Any = self._request(endpoint, params)

        if not isinstance(response_data, dict) or "content" not in response_data:
            raise GitHubAPIError(f"File {file_path} has no content field")

        # GitHub returns base64-encoded content
        import base64

        content_encoded: Any = response_data["content"]
        content = base64.b64decode(content_encoded).decode("utf-8")
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
        response_data: Any = self._request(endpoint)

        if not isinstance(response_data, dict):
            raise GitHubAPIError(f"Invalid response for repo {owner}/{repo}")

        default_branch: str = response_data.get("default_branch", "main")

        # Try to get latest commit on default branch
        # Some repos may have empty/broken default branches, so try alternatives
        for branch in [default_branch, "main", "master"]:
            try:
                endpoint = f"/repos/{owner}/{repo}/commits/{branch}"
                commit_data: Any = self._request(endpoint, retry=1)

                if isinstance(commit_data, dict) and "sha" in commit_data:
                    return str(commit_data["sha"])
            except GitHubAPIError:
                # Try next branch
                continue

        # If all branches failed, raise error
        raise GitHubAPIError(
            f"Could not get commit SHA for {owner}/{repo}. "
            f"Tried branches: {default_branch}, main, master"
        )

    def clear_cache(self) -> None:
        """Clear all cached API responses."""
        if hasattr(self.session.cache, "clear"):
            self.session.cache.clear()
