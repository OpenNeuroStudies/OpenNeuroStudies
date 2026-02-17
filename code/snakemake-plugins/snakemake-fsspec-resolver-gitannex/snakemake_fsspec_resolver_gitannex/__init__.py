"""git-annex URL resolver for snakemake-storage-plugin-fsspec.

This resolver translates local file paths to remote URLs by querying
git-annex whereis. It enables transparent streaming access to annexed
files without downloading them first.

Usage:
    from snakemake_storage_plugin_fsspec import register_resolver
    from snakemake_fsspec_resolver_gitannex import GitAnnexResolver

    # Register with default settings
    register_resolver(GitAnnexResolver())

    # Or with custom settings
    register_resolver(GitAnnexResolver(
        prefer_https=True,
        cache_size=1000,
        repo_path="/path/to/repo",
    ))
"""

from snakemake_fsspec_resolver_gitannex.resolver import GitAnnexResolver

__all__ = ["GitAnnexResolver"]

__version__ = "0.1.0"
