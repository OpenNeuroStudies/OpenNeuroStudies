"""GitHub API client with caching."""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests_cache import CachedSession

logger = logging.getLogger(__name__)

# TODO: requests_cache logs "Unable to deserialize response" at ERROR level without
# URL/dataset context when cached entries are corrupted (e.g., after library upgrades).
# Per constitution V (Error Visibility), errors must include contextual identifiers.
# Options to fix:
# 1. Add a logging filter on 'requests_cache.backends.base' that captures the URL
#    from the thread-local request context
# 2. Suppress requests_cache ERROR logging and handle cache misses in _request()
#    with our own contextual warning
# 3. Use requests_cache's serializer parameter to use a more robust format (JSON
#    instead of pickle) that degrades gracefully across versions
# For now, deleting the cache file resolves the issue after upgrades.

# Global lock for rate limit coordination across threads
_rate_limit_lock = threading.Lock()


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
        max_connections: int = 50,
    ):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If None, reads from GITHUB_TOKEN env var.
                   If no token provided, will use unauthenticated requests (lower rate limit).
            cache_dir: Directory for cache storage
            cache_expire_after: Cache expiration time in seconds (default: 1 hour)
            max_connections: Maximum number of connections in pool (default: 50)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create cached session with larger connection pool
        cache_path = self.cache_dir / "github_api_cache"
        self.session = CachedSession(
            str(cache_path),
            expire_after=cache_expire_after,
            allowable_methods=["GET"],
            stale_if_error=True,  # Use stale cache if API fails
        )

        # Configure connection pool size for parallel workers
        # HTTPAdapter settings: pool_connections controls number of connection pools
        # pool_maxsize controls max connections per pool
        from requests.adapters import HTTPAdapter

        adapter = HTTPAdapter(
            pool_connections=max_connections,
            pool_maxsize=max_connections,
            max_retries=0,  # We handle retries in _request()
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

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
                response = self._do_request(url, params)
                return self._parse_response(response, url)

            except GitHubAPIError:
                raise  # Propagate our own errors without re-wrapping
            except requests.exceptions.RequestException as e:
                if attempt == retry - 1:
                    raise GitHubAPIError(
                        f"GitHub API request failed for {url}: {e}"
                    ) from e
                time.sleep(2**attempt)
            except Exception as e:
                # Cache backend errors (e.g., sqlite3.OperationalError) or other
                # unexpected failures — wrap with context for troubleshooting
                cache_file = self.cache_dir / "github_api_cache.sqlite"
                raise GitHubAPIError(
                    f"{type(e).__name__} while requesting {url}: {e} "
                    f"(cache: {cache_file})"
                ) from e

        raise GitHubAPIError(f"Failed to fetch {url} after {retry} attempts")

    def _do_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a single HTTP request, handling rate limits.

        Returns the response object. Raises on HTTP errors or rate limit exhaustion.
        """
        response = self.session.get(url, params=params, timeout=30)

        # Handle rate limiting
        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            if reset_time:
                token_hint = ""
                if not self.token:
                    token_hint = (
                        " Set GITHUB_TOKEN environment variable for higher rate limits."
                    )

                # Use lock to coordinate waiting across threads
                with _rate_limit_lock:
                    current_wait = max(0, reset_time - time.time())
                    if current_wait > 0:
                        logger.warning(
                            "Rate limit exceeded. Waiting %.1f seconds until reset...%s",
                            current_wait,
                            token_hint,
                        )
                        time.sleep(current_wait + 1)

                # Retry after waiting
                response = self.session.get(url, params=params, timeout=30)

        response.raise_for_status()

        # Handle empty/None response content (can happen with cache corruption)
        if response.content is None:
            logger.warning(
                "Empty response from %s (possibly corrupted cache entry). Retrying.",
                url,
            )
            response = self.session.get(
                url, params=params, timeout=30,
                headers={"Cache-Control": "no-cache"},
            )
            response.raise_for_status()

        return response

    def _parse_response(self, response: Any, url: str) -> Any:
        """Parse JSON from response, raising GitHubAPIError on failure."""
        try:
            return response.json()
        except (ValueError, TypeError) as e:
            raise GitHubAPIError(
                f"Invalid JSON response from {url}: {e} "
                f"(content_type={response.headers.get('content-type')}, "
                f"length={response.headers.get('content-length')})"
            ) from e

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
        # Use dict.fromkeys() instead of set() to preserve order (default_branch first)
        branches = list(dict.fromkeys([default_branch, "main", "master"]))

        for branch in branches:
            try:
                endpoint = f"/repos/{owner}/{repo}/commits/{branch}"
                # Use retry=3 to allow for rate limit wait + retry
                commit_data: Any = self._request(endpoint, retry=3)

                if isinstance(commit_data, dict) and "sha" in commit_data:
                    return str(commit_data["sha"])
            except GitHubAPIError:
                # Try next branch
                continue

        # If all branches failed, raise error
        raise GitHubAPIError(
            f"Could not get commit SHA for {owner}/{repo}. "
            f"Tried branches: {', '.join(branches)}"
        )

    def clear_cache(self) -> None:
        """Clear all cached API responses."""
        if hasattr(self.session.cache, "clear"):
            self.session.cache.clear()
