"""Shared locks for preventing race conditions in parallel operations."""

import threading

# Global lock for serializing parent repository modifications
# Used to prevent git index.lock conflicts when parallel workers:
# - Create study datasets (DataLad create/save operations)
# - Link submodules (.gitmodules modifications)
# - Register studies in parent repository
parent_repo_lock = threading.Lock()
