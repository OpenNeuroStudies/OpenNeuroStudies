"""Sparse access to git-annex BIDS datasets.

Provides utilities for accessing file metadata and content from git-annex
repositories without requiring full clones.
"""

from bids_studies.sparse.access import SparseDataset, is_sparse_access_available

__all__ = ["SparseDataset", "is_sparse_access_available"]
