"""Sparse access to git-annex datasets without full cloning.

Provides utilities for accessing file metadata and content from git-annex
repositories using datalad-fuse's FsspecAdapter or direct git commands.

This module enables:
- Listing files/directories from git tree (no download)
- Extracting file sizes from annex keys (no download)
- Opening remote files via fsspec for partial reads (minimal download)
"""

import fnmatch
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Try to import datalad-fuse, but don't require it
try:
    from datalad_fuse import FsspecAdapter

    DATALAD_FUSE_AVAILABLE = True
except ImportError:
    DATALAD_FUSE_AVAILABLE = False
    FsspecAdapter = None

# Pattern to extract size from git-annex key
# Example: SHA256E-s12345678--abc123.nii.gz -> size=12345678
ANNEX_KEY_SIZE_PATTERN = re.compile(r"-s(\d+)--")


class SparseDataset:
    """Sparse access wrapper for git-annex datasets.

    Provides methods to list files, get sizes, and open files for reading
    without requiring a full clone of the dataset.

    Usage:
        with SparseDataset("/path/to/dataset") as ds:
            subjects = ds.list_dirs("sub-*")
            size = ds.get_file_size("sub-01/anat/sub-01_T1w.nii.gz")
            with ds.open_file("sub-01/anat/sub-01_T1w.nii.gz") as f:
                data = f.read(352)  # Read NIfTI header
    """

    def __init__(self, path: Union[str, Path]):
        """Initialize sparse dataset access.

        Args:
            path: Path to the git-annex repository
        """
        self.path = Path(path)
        self._adapter: Optional[FsspecAdapter] = None
        self._tree_cache: Optional[list[tuple[str, str, str]]] = None

    def __enter__(self) -> "SparseDataset":
        """Enter context manager."""
        if DATALAD_FUSE_AVAILABLE:
            try:
                self._adapter = FsspecAdapter(str(self.path))
            except Exception as e:
                logger.warning(f"Failed to initialize FsspecAdapter: {e}")
                self._adapter = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self._adapter is not None:
            try:
                # FsspecAdapter may have cleanup
                if hasattr(self._adapter, "close"):
                    self._adapter.close()
            except Exception:
                pass
            self._adapter = None
        self._tree_cache = None

    def _get_git_tree(self) -> list[tuple[str, str, str]]:
        """Get the full git tree for the repository.

        Returns:
            List of (mode, type, path) tuples
        """
        if self._tree_cache is not None:
            return self._tree_cache

        try:
            result = subprocess.run(
                ["git", "-C", str(self.path), "ls-tree", "-r", "--full-tree", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            entries = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                # Format: mode type hash\tpath
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                meta, path = parts
                meta_parts = meta.split()
                if len(meta_parts) >= 2:
                    mode, obj_type = meta_parts[0], meta_parts[1]
                    entries.append((mode, obj_type, path))
            self._tree_cache = entries
            return entries
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get git tree: {e}")
            return []

    def list_files(self, pattern: str = "*") -> list[str]:
        """List files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/func/*_bold.nii*")

        Returns:
            List of file paths relative to repository root
        """
        tree = self._get_git_tree()
        files = [path for mode, obj_type, path in tree if obj_type == "blob"]

        # Filter by pattern
        if pattern != "*":
            # Handle ** pattern for recursive matching
            if "**" in pattern:
                # Convert glob to regex
                regex_pattern = pattern.replace(".", r"\.")
                regex_pattern = regex_pattern.replace("**", ".*")
                regex_pattern = regex_pattern.replace("*", "[^/]*")
                regex_pattern = f"^{regex_pattern}$"
                regex = re.compile(regex_pattern)
                files = [f for f in files if regex.match(f)]
            else:
                files = [f for f in files if fnmatch.fnmatch(f, pattern)]

        return sorted(files)

    def list_dirs(self, pattern: str = "*") -> list[str]:
        """List directories matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "sub-*")

        Returns:
            List of directory paths relative to repository root
        """
        tree = self._get_git_tree()

        # Extract unique directory paths from file paths
        dirs = set()
        for mode, obj_type, path in tree:
            # Add all parent directories
            parts = path.split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))

        # Filter by pattern
        if pattern != "*":
            if "/" in pattern:
                # Pattern includes path components
                dirs = [d for d in dirs if fnmatch.fnmatch(d, pattern)]
            else:
                # Pattern is for directory name only
                dirs = [d for d in dirs if fnmatch.fnmatch(d.split("/")[-1], pattern)]

        return sorted(dirs)

    def list_bids_datatypes(self) -> set[str]:
        """List BIDS datatype directories present in the dataset.

        Returns:
            Set of datatype names (e.g., {"anat", "func", "dwi"})
        """
        known_datatypes = {
            "anat",
            "func",
            "dwi",
            "fmap",
            "perf",
            "meg",
            "eeg",
            "ieeg",
            "beh",
            "pet",
            "micr",
            "nirs",
            "motion",
        }

        dirs = self.list_dirs("*")
        datatypes = set()

        for d in dirs:
            name = d.split("/")[-1]
            if name in known_datatypes:
                datatypes.add(name)

        return datatypes

    def get_file_size(self, path: str) -> Optional[int]:
        """Get file size from git-annex key without downloading.

        Args:
            path: File path relative to repository root

        Returns:
            File size in bytes, or None if not available
        """
        # Try to read symlink target (git-annex key)
        full_path = self.path / path
        try:
            if full_path.is_symlink():
                target = os.readlink(full_path)
                # Extract size from annex key
                match = ANNEX_KEY_SIZE_PATTERN.search(target)
                if match:
                    return int(match.group(1))
        except OSError:
            pass

        # Try git cat-file to get symlink content
        try:
            result = subprocess.run(
                ["git", "-C", str(self.path), "cat-file", "-p", f"HEAD:{path}"],
                capture_output=True,
                text=True,
                check=True,
            )
            target = result.stdout.strip()
            match = ANNEX_KEY_SIZE_PATTERN.search(target)
            if match:
                return int(match.group(1))
        except subprocess.CalledProcessError:
            pass

        # If adapter available, try to get file state
        if self._adapter is not None:
            try:
                is_local, annex_key = self._adapter.get_file_state(path)
                if annex_key:
                    match = ANNEX_KEY_SIZE_PATTERN.search(str(annex_key))
                    if match:
                        return int(match.group(1))
            except Exception as e:
                logger.debug(f"Failed to get file state via adapter: {e}")

        return None

    def open_file(self, path: str):
        """Open a file for reading via sparse access.

        Uses fsspec to open the file from its remote URL, enabling
        partial reads without downloading the entire file.

        Args:
            path: File path relative to repository root

        Returns:
            File-like object supporting read() and seek()

        Raises:
            RuntimeError: If sparse access is not available
            FileNotFoundError: If file URL cannot be resolved
        """
        if self._adapter is not None:
            try:
                return self._adapter.open(path)
            except Exception as e:
                logger.warning(f"FsspecAdapter.open failed: {e}")

        # Fall back to direct fsspec with git-annex whereis
        return self._open_via_whereis(path)

    def _open_via_whereis(self, path: str):
        """Open file using git-annex whereis and fsspec.

        Args:
            path: File path relative to repository root

        Returns:
            File-like object from fsspec
        """
        try:
            import fsspec
        except ImportError:
            raise RuntimeError("fsspec not installed. Install with: pip install fsspec aiohttp")

        # Get remote URL from git-annex whereis
        url = self._get_remote_url(path)
        if url is None:
            raise FileNotFoundError(f"No remote URL found for {path}")

        # Open via fsspec
        fs = fsspec.filesystem("http")
        return fs.open(url)

    def _get_remote_url(self, path: str) -> Optional[str]:
        """Get HTTP URL for annexed file via git-annex whereis.

        Args:
            path: File path relative to repository root

        Returns:
            HTTP URL or None if not found
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(self.path), "annex", "whereis", "--json", path],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            # Look for web remote URLs
            for remote in data.get("whereis", []):
                for url in remote.get("urls", []):
                    if url.startswith("http"):
                        return url

            # Check untrusted remotes too
            for remote in data.get("untrusted", []):
                for url in remote.get("urls", []):
                    if url.startswith("http"):
                        return url

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.debug(f"git annex whereis failed: {e}")

        return None


def is_sparse_access_available() -> bool:
    """Check if sparse access is available.

    Returns:
        True if datalad-fuse or fsspec is available
    """
    if DATALAD_FUSE_AVAILABLE:
        return True

    try:
        import fsspec

        return True
    except ImportError:
        return False
