"""Snakemake storage plugin using fsspec for transparent remote file access.

This plugin enables Snakemake workflows to access remote files via fsspec
without downloading the entire file. It supports:

- HTTP/HTTPS URLs with range requests (partial downloads)
- S3, GCS, and other fsspec-supported backends
- Pluggable URL resolvers (e.g., git-annex, datalad)
- Block caching for efficient repeated access

Usage in Snakefile:
    from snakemake.storage import storage

    # Direct URL access
    rule process:
        input:
            storage.fsspec("https://example.com/data.nii.gz")
        ...

    # With registered resolver (e.g., git-annex)
    from snakemake_fsspec_resolver_gitannex import GitAnnexResolver
    storage.fsspec.register_resolver(GitAnnexResolver())

    rule process:
        input:
            storage.fsspec("sub-01/func/sub-01_bold.nii.gz")  # resolved via git-annex
        ...
"""

from snakemake_storage_plugin_fsspec.provider import StorageProvider
from snakemake_storage_plugin_fsspec.resolver import URLResolver, URLResolverRegistry

__all__ = [
    "StorageProvider",
    "URLResolver",
    "URLResolverRegistry",
]

__version__ = "0.1.0"
