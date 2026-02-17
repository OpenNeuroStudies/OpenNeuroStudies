"""git-annex URL resolver implementation.

Resolves local file paths to remote URLs by querying git-annex whereis.
Supports batch queries for efficiency and caching to reduce subprocess calls.
"""

import json
import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional

from snakemake_storage_plugin_fsspec.resolver import BaseResolver

logger = logging.getLogger(__name__)


class GitAnnexResolver(BaseResolver):
    """Resolve file paths to URLs via git-annex whereis.

    This resolver queries git-annex to find remote URLs for annexed files,
    enabling streaming access without downloading the entire file.

    Attributes:
        prefer_https: If True, prefer HTTPS URLs over other protocols
        repo_path: Path to git-annex repository (default: current directory)
        cache_size: Maximum number of cached URL lookups
    """

    _name = "git-annex"
    _priority = 10  # Primary resolver

    def __init__(
        self,
        prefer_https: bool = True,
        repo_path: Optional[Path] = None,
        cache_size: int = 1000,
        priority: Optional[int] = None,
    ):
        """Initialize the git-annex resolver.

        Args:
            prefer_https: Prefer HTTPS URLs when available
            repo_path: Path to git-annex repository
            cache_size: Maximum cached lookups
            priority: Override default priority
        """
        super().__init__(priority=priority)
        self.prefer_https = prefer_https
        self.repo_path = repo_path
        self._cache: dict[str, Optional[str]] = {}
        self._cache_size = cache_size

    def resolve(self, path: Path, cwd: Optional[Path] = None) -> Optional[str]:
        """Resolve a local path to a remote URL via git-annex.

        Args:
            path: Local file path to resolve
            cwd: Working directory (overrides repo_path if set)

        Returns:
            Remote URL string, or None if not found
        """
        # Determine repository path
        repo = cwd or self.repo_path or Path.cwd()
        cache_key = f"{repo}:{path}"

        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Query git-annex whereis
        url = self._query_whereis(path, repo)

        # Cache result (with size limit)
        if len(self._cache) >= self._cache_size:
            # Simple eviction: clear half the cache
            keys = list(self._cache.keys())
            for key in keys[: len(keys) // 2]:
                del self._cache[key]

        self._cache[cache_key] = url
        return url

    def _query_whereis(self, path: Path, repo: Path) -> Optional[str]:
        """Query git-annex whereis for a file's URLs.

        Args:
            path: File path relative to repository
            repo: Repository path

        Returns:
            Best URL or None
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "annex", "whereis", "--json", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.debug(f"git annex whereis failed for {path}: {result.stderr}")
                return None

            data = json.loads(result.stdout)
            return self._extract_best_url(data)

        except subprocess.TimeoutExpired:
            logger.warning(f"git annex whereis timed out for {path}")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse git annex whereis output: {e}")
            return None
        except FileNotFoundError:
            logger.warning("git-annex not found in PATH")
            return None

    def _extract_best_url(self, whereis_data: dict) -> Optional[str]:
        """Extract the best URL from git-annex whereis output.

        Prefers HTTPS URLs, then S3, then any available URL.

        Args:
            whereis_data: Parsed JSON from git annex whereis

        Returns:
            Best URL or None
        """
        all_urls: list[str] = []

        # Collect URLs from all remotes
        for remote in whereis_data.get("whereis", []):
            all_urls.extend(remote.get("urls", []))

        # Also check untrusted remotes
        for remote in whereis_data.get("untrusted", []):
            all_urls.extend(remote.get("urls", []))

        if not all_urls:
            return None

        # Categorize URLs by protocol
        https_urls = [u for u in all_urls if u.startswith("https://")]
        http_urls = [u for u in all_urls if u.startswith("http://") and not u.startswith("https://")]
        s3_urls = [u for u in all_urls if u.startswith("s3://")]

        # Select best URL based on preferences
        if self.prefer_https and https_urls:
            return https_urls[0]

        if https_urls:
            return https_urls[0]

        if http_urls:
            return http_urls[0]

        if s3_urls:
            return s3_urls[0]

        # Return any URL as fallback
        return all_urls[0]

    def clear_cache(self) -> None:
        """Clear the URL cache."""
        self._cache.clear()

    def batch_resolve(
        self, paths: list[Path], cwd: Optional[Path] = None
    ) -> dict[Path, Optional[str]]:
        """Resolve multiple paths efficiently using batch mode.

        Uses git-annex whereis --batch for better performance with
        many files.

        Args:
            paths: List of paths to resolve
            cwd: Working directory

        Returns:
            Dictionary mapping paths to URLs (None if not found)
        """
        repo = cwd or self.repo_path or Path.cwd()
        results: dict[Path, Optional[str]] = {}

        # Check cache first
        uncached_paths = []
        for path in paths:
            cache_key = f"{repo}:{path}"
            if cache_key in self._cache:
                results[path] = self._cache[cache_key]
            else:
                uncached_paths.append(path)

        if not uncached_paths:
            return results

        # Use batch mode for uncached paths
        try:
            proc = subprocess.Popen(
                ["git", "-C", str(repo), "annex", "whereis", "--batch", "--json"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Send all paths
            input_data = "\n".join(str(p) for p in uncached_paths) + "\n"
            stdout, stderr = proc.communicate(input=input_data, timeout=60)

            # Parse results
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    file_path = Path(data.get("file", ""))
                    url = self._extract_best_url(data)

                    results[file_path] = url

                    # Cache result
                    cache_key = f"{repo}:{file_path}"
                    self._cache[cache_key] = url

                except json.JSONDecodeError:
                    continue

        except subprocess.TimeoutExpired:
            logger.warning("git annex whereis --batch timed out")
            proc.kill()
        except Exception as e:
            logger.warning(f"Batch whereis failed: {e}")

        # Fill in None for any paths not in results
        for path in uncached_paths:
            if path not in results:
                results[path] = None
                cache_key = f"{repo}:{path}"
                self._cache[cache_key] = None

        return results

    def get_content_hash(self, path: Path, cwd: Optional[Path] = None) -> Optional[str]:
        """Get the git-annex key (content hash) for a file.

        This can be used for content-based dependency tracking.

        Args:
            path: File path
            cwd: Working directory

        Returns:
            git-annex key or None
        """
        repo = cwd or self.repo_path or Path.cwd()

        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "annex", "lookupkey", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return None

        except Exception:
            return None
