"""Sparse access to git-annex datasets without full cloning.

This module re-exports from bids_studies.sparse for backwards compatibility.
"""

# Re-export from bids_studies
from bids_studies.sparse import SparseDataset, is_sparse_access_available

__all__ = ["SparseDataset", "is_sparse_access_available"]
