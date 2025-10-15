"""Shared locks for preventing race conditions in parallel operations."""

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

# Global lock for serializing parent repository modifications
# Used to prevent git index.lock conflicts when parallel workers:
# - Link submodules (.gitmodules modifications)
# - Register studies in parent repository
parent_repo_lock = threading.Lock()

# Per-study locks for serializing operations within each study dataset
# Prevents race conditions when multiple workers modify the same study
_study_locks: Dict[str, threading.Lock] = {}
_study_locks_lock = threading.Lock()  # Lock for managing the locks dictionary


@contextmanager
def study_lock(study_path: Path):
    """Context manager for per-study locking.

    Ensures that only one thread at a time can modify a specific study dataset.
    This prevents race conditions when both raw and derivative datasets try to
    organize into the same study simultaneously.

    Args:
        study_path: Path to the study dataset directory

    Example:
        with study_lock(Path("study-ds000001")):
            # Perform operations on study-ds000001
            link_submodule(...)
            git_commit(...)
    """
    study_key = str(study_path.resolve())

    # Get or create lock for this study
    with _study_locks_lock:
        if study_key not in _study_locks:
            _study_locks[study_key] = threading.Lock()
        lock = _study_locks[study_key]

    # Acquire study-specific lock
    with lock:
        yield
