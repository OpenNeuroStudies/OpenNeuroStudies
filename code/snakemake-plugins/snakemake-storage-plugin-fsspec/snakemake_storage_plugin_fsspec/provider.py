"""Snakemake storage provider implementation using fsspec.

This module implements the Snakemake storage plugin interface,
enabling transparent remote file access via fsspec.

The provider:
1. Resolves local paths to remote URLs (via pluggable resolvers)
2. Opens files using fsspec with block caching
3. Reports file existence and modification based on remote state
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
import logging

import fsspec

from snakemake_interface_storage_plugins.settings import StorageProviderSettingsBase
from snakemake_interface_storage_plugins.storage_provider import (
    StorageProviderBase,
    StorageQueryValidationResult,
    ExampleQuery,
    QueryType,
)
from snakemake_interface_storage_plugins.storage_object import (
    StorageObjectRead,
    StorageObjectWrite,
    StorageObjectGlob,
)
from snakemake_interface_storage_plugins.io import IOCacheStorageInterface

from snakemake_storage_plugin_fsspec.resolver import (
    URLResolverRegistry,
    get_global_registry,
)

logger = logging.getLogger(__name__)


@dataclass
class StorageProviderSettings(StorageProviderSettingsBase):
    """Settings for the fsspec storage provider."""

    # fsspec cache type: "blockcache", "readahead", "none", etc.
    cache_type: str = field(
        default="blockcache",
        metadata={
            "help": "fsspec cache type for remote files",
            "choices": ["blockcache", "readahead", "none", "all"],
        },
    )

    # Block size for block cache (bytes)
    block_size: int = field(
        default=8 * 1024 * 1024,  # 8 MB
        metadata={
            "help": "Block size for fsspec block cache in bytes",
        },
    )

    # Whether to prefer HTTPS URLs
    prefer_https: bool = field(
        default=True,
        metadata={
            "help": "Prefer HTTPS URLs over HTTP when available",
        },
    )


class StorageProvider(StorageProviderBase):
    """Storage provider using fsspec for remote file access."""

    # Required class attributes
    supports_read = True
    supports_write = False  # Read-only for now
    supports_glob = False  # Glob not yet implemented

    def __init__(
        self,
        local_prefix: Path,
        settings: Optional[StorageProviderSettings] = None,
        keep_local: bool = False,
        is_default: bool = False,
    ):
        """Initialize the storage provider.

        Args:
            local_prefix: Local path prefix for file mapping
            settings: Provider settings
            keep_local: Whether to keep local copies after use
            is_default: Whether this is the default storage provider
        """
        super().__init__(
            local_prefix=local_prefix,
            settings=settings or StorageProviderSettings(),
            keep_local=keep_local,
            is_default=is_default,
        )
        self._registry = get_global_registry()
        self._url_cache: dict[str, Optional[str]] = {}

    @classmethod
    def example_queries(cls) -> Iterable[ExampleQuery]:
        """Provide example queries for documentation."""
        return [
            ExampleQuery(
                query="sub-01/func/sub-01_bold.nii.gz",
                query_type=QueryType.ANY,
                description="Local path resolved via registered URL resolver",
            ),
            ExampleQuery(
                query="https://s3.amazonaws.com/bucket/file.nii.gz",
                query_type=QueryType.ANY,
                description="Direct URL access",
            ),
        ]

    def rate_limiter_key(self, query: str, operation: str) -> Any:
        """Return rate limiter key for the query."""
        # Use hostname for rate limiting
        url = self._resolve_url(query)
        if url:
            from urllib.parse import urlparse
            return urlparse(url).hostname
        return "local"

    @classmethod
    def is_valid_query(cls, query: str) -> StorageQueryValidationResult:
        """Validate a storage query."""
        # Accept any path or URL
        return StorageQueryValidationResult(valid=True, query=query)

    def _resolve_url(self, query: str) -> Optional[str]:
        """Resolve a query to a URL.

        Args:
            query: Local path or URL

        Returns:
            URL string or None
        """
        # Check cache
        if query in self._url_cache:
            return self._url_cache[query]

        # If already a URL, return as-is
        if query.startswith(("http://", "https://", "s3://", "gs://")):
            self._url_cache[query] = query
            return query

        # Try resolvers
        url = self._registry.resolve(Path(query))
        self._url_cache[query] = url
        return url

    def object_factory(self, query: str) -> "StorageObject":
        """Create a storage object for the query."""
        return StorageObject(
            query=query,
            keep_local=self.keep_local,
            retrieve=True,
            provider=self,
        )


class StorageObject(StorageObjectRead):
    """Storage object for fsspec-based file access."""

    def __init__(
        self,
        query: str,
        keep_local: bool,
        retrieve: bool,
        provider: StorageProvider,
    ):
        """Initialize storage object.

        Args:
            query: Storage query (path or URL)
            keep_local: Whether to keep local copy
            retrieve: Whether to retrieve the file
            provider: Parent storage provider
        """
        super().__init__(
            query=query,
            keep_local=keep_local,
            retrieve=retrieve,
            provider=provider,
        )
        self._provider = provider
        self._url: Optional[str] = None
        self._fs: Optional[fsspec.AbstractFileSystem] = None

    def _get_url(self) -> Optional[str]:
        """Get URL for this object."""
        if self._url is None:
            self._url = self._provider._resolve_url(self.query)
        return self._url

    def _get_fs(self) -> fsspec.AbstractFileSystem:
        """Get fsspec filesystem for this object."""
        if self._fs is None:
            url = self._get_url()
            if url is None:
                raise FileNotFoundError(f"Cannot resolve URL for {self.query}")

            # Determine protocol from URL
            if url.startswith("s3://"):
                self._fs = fsspec.filesystem("s3", anon=True)
            elif url.startswith("gs://"):
                self._fs = fsspec.filesystem("gcs", anon=True)
            elif url.startswith(("http://", "https://")):
                self._fs = fsspec.filesystem(
                    "http",
                    cache_type=self._provider.settings.cache_type,
                    block_size=self._provider.settings.block_size,
                )
            else:
                self._fs = fsspec.filesystem("file")

        return self._fs

    def local_path(self) -> Path:
        """Return local path for this object."""
        return self._provider.local_prefix / self.query

    def exists(self) -> bool:
        """Check if the remote file exists."""
        url = self._get_url()
        if url is None:
            return False

        try:
            fs = self._get_fs()
            # Strip protocol for fsspec
            if url.startswith(("http://", "https://")):
                return fs.exists(url)
            else:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                path = parsed.netloc + parsed.path
                return fs.exists(path)
        except Exception as e:
            logger.debug(f"Error checking existence of {url}: {e}")
            return False

    def mtime(self) -> float:
        """Return modification time of remote file.

        Note: For content-addressed storage (git-annex), this returns
        a hash-based timestamp since actual mtime is not meaningful.
        """
        url = self._get_url()
        if url is None:
            return 0.0

        try:
            fs = self._get_fs()
            info = fs.info(url)
            # Try various mtime fields
            for key in ("mtime", "LastModified", "updated", "created"):
                if key in info:
                    mtime = info[key]
                    if isinstance(mtime, (int, float)):
                        return float(mtime)
                    # Handle datetime objects
                    if hasattr(mtime, "timestamp"):
                        return mtime.timestamp()
            return 0.0
        except Exception as e:
            logger.debug(f"Error getting mtime for {url}: {e}")
            return 0.0

    def size(self) -> int:
        """Return size of remote file in bytes."""
        url = self._get_url()
        if url is None:
            return 0

        try:
            fs = self._get_fs()
            info = fs.info(url)
            return info.get("size", 0)
        except Exception as e:
            logger.debug(f"Error getting size for {url}: {e}")
            return 0

    def retrieve_object(self) -> None:
        """Retrieve the remote file to local storage.

        For fsspec, this is a no-op since we access files on-demand.
        The file handle is created when the file is opened.
        """
        # No-op: fsspec provides on-demand access
        pass

    def open(self, mode: str = "rb"):
        """Open the file for reading.

        Returns an fsspec file handle that streams from remote.

        Args:
            mode: File mode (only 'rb' supported)

        Returns:
            File-like object
        """
        if "w" in mode:
            raise NotImplementedError("Write mode not supported")

        url = self._get_url()
        if url is None:
            raise FileNotFoundError(f"Cannot resolve URL for {self.query}")

        fs = self._get_fs()

        # Open with block caching for efficient partial reads
        return fs.open(
            url,
            mode=mode,
            cache_type=self._provider.settings.cache_type,
            block_size=self._provider.settings.block_size,
        )
