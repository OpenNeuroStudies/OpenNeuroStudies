"""Subdataset state management utilities.

Provides functions for temporarily initializing git submodules (subdatasets)
for metadata extraction without permanent state changes.

Usage patterns:
    1. Snapshot current state before operations
    2. Initialize needed subdatasets
    3. Perform extraction
    4. Restore original state (uninitialize what we initialized)

This ensures extraction has access to git trees without modifying the
user's working state.
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_subdataset_initialized(subdataset_path: Path) -> bool:
    """Check if subdataset has git tree available with files.

    A subdataset is initialized if:
    - .git exists (file or directory)
    - git rev-parse --show-toplevel returns THIS path (not parent)
    - Working tree has files (not empty)

    This fixes the false positive bug where git commands would find
    the parent repository instead of detecting an uninitialized subdataset.

    Args:
        subdataset_path: Path to subdataset directory

    Returns:
        True if subdataset is initialized with files, False otherwise
    """
    if not subdataset_path.exists():
        return False

    git_path = subdataset_path / ".git"
    if not git_path.exists():
        return False

    # Check if this is its own repository (not parent)
    try:
        result = subprocess.run(
            ["git", "-C", str(subdataset_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=5,
            check=True,
            text=True,
        )

        # The git root MUST be this subdataset path, not a parent
        git_root = Path(result.stdout.strip()).resolve()
        subdataset_resolved = subdataset_path.resolve()

        if git_root != subdataset_resolved:
            logger.debug(f"Not own repo: {subdataset_path} (root={git_root})")
            return False

        # Verify working tree has files (not empty except .git)
        non_hidden_items = [
            item for item in subdataset_path.iterdir()
            if not item.name.startswith(".")
        ]

        if not non_hidden_items:
            logger.debug(f"No files: {subdataset_path}")
            return False

        logger.debug(f"Initialized: {subdataset_path}")
        return True

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_uninitialized_sourcedata(study_path: Path) -> list[Path]:
    """Find sourcedata subdatasets that need initialization.

    Args:
        study_path: Path to study directory (e.g., study-ds000001)

    Returns:
        List of paths to uninitialized sourcedata subdatasets
        (e.g., [study-ds000001/sourcedata/ds000001, ...])
    """
    sourcedata_dir = study_path / "sourcedata"
    if not sourcedata_dir.exists():
        return []

    uninitialized = []
    for subdataset_path in sourcedata_dir.iterdir():
        if subdataset_path.is_dir() and not is_subdataset_initialized(subdataset_path):
            uninitialized.append(subdataset_path)

    return sorted(uninitialized)


def _find_immediate_parent_repo(subdataset_path: Path, repo_root: Path) -> Path | None:
    """Find the immediate parent repository that registers this subdataset.

    Walks up directory tree from subdataset, checking each level's .gitmodules
    for an entry matching this subdataset.

    Args:
        subdataset_path: Absolute path to subdataset
        repo_root: Root of top-level repository

    Returns:
        Path to immediate parent repo, or None if not found
    """
    subdataset_resolved = subdataset_path.resolve()
    repo_root_resolved = repo_root.resolve()
    current = subdataset_resolved.parent

    while current >= repo_root_resolved:
        gitmodules = current / ".gitmodules"
        if not gitmodules.exists():
            current = current.parent
            continue

        # Make subdataset path relative to current directory
        try:
            relative_path = subdataset_resolved.relative_to(current)
        except ValueError:
            # Can't make relative (shouldn't happen in upward walk)
            current = current.parent
            continue

        # Read .gitmodules and look for path = {relative_path}
        try:
            with open(gitmodules) as f:
                content = f.read()
                # Match both "path = relative/path" and "path=relative/path"
                if f"\tpath = {relative_path}" in content or f"path = {relative_path}" in content:
                    logger.debug(f"Found parent repo for {subdataset_path}: {current}")
                    return current
        except (OSError, IOError) as e:
            logger.debug(f"Error reading {gitmodules}: {e}")

        current = current.parent

    logger.debug(f"No parent repo found for {subdataset_path}")
    return None


def _initialize_single_subdataset(subdataset_path: Path, parent_path: Path) -> tuple[Path, bool]:
    """Initialize a single subdataset from its immediate parent repository.

    Args:
        subdataset_path: Path to subdataset to initialize
        parent_path: Path to top-level parent repository

    Returns:
        Tuple of (subdataset_path, success)
    """
    try:
        # Find the immediate parent repository that registers this subdataset
        immediate_parent = _find_immediate_parent_repo(subdataset_path, parent_path)

        if immediate_parent is None:
            logger.warning(
                f"Could not find parent repo for {subdataset_path} "
                f"(not registered in any .gitmodules)"
            )
            return (subdataset_path, False)

        # Make subdataset path relative to its immediate parent
        subdataset_relative = subdataset_path.resolve().relative_to(immediate_parent.resolve())

        # Use git submodule update --init from the immediate parent context
        # This is faster than datalad install as it only sets up git tree
        result = subprocess.run(
            ["git", "-C", str(immediate_parent), "submodule", "update", "--init", str(subdataset_relative)],
            capture_output=True,
            timeout=300,  # 5 minutes max per subdataset
            check=False,
            text=True,
        )

        if result.returncode == 0:
            logger.info(f"Initialized subdataset: {subdataset_path}")
            return (subdataset_path, True)
        else:
            logger.warning(
                f"Failed to initialize {subdataset_path}: "
                f"returncode={result.returncode}, stderr={result.stderr}"
            )
            return (subdataset_path, False)

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout initializing {subdataset_path}")
        return (subdataset_path, False)
    except Exception as e:
        logger.warning(f"Exception initializing {subdataset_path}: {e}")
        return (subdataset_path, False)


def initialize_subdatasets(
    subdataset_paths: list[Path],
    parent_path: Path = Path("."),
    jobs: int = 1,
) -> dict[Path, bool]:
    """Initialize subdatasets using git submodule update.

    Args:
        subdataset_paths: List of subdataset paths to initialize
        parent_path: Path to parent repository (default: current directory)
        jobs: Number of parallel initialization jobs (default: 1)

    Returns:
        Dictionary mapping subdataset path to success status (True/False)
    """
    if not subdataset_paths:
        return {}

    logger.info(f"Initializing {len(subdataset_paths)} subdatasets with {jobs} parallel jobs")

    if jobs == 1:
        # Sequential initialization
        results = {}
        for path in subdataset_paths:
            path_result, success = _initialize_single_subdataset(path, parent_path)
            results[path_result] = success
        return results

    # Parallel initialization
    results = {}
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [
            executor.submit(_initialize_single_subdataset, path, parent_path)
            for path in subdataset_paths
        ]
        for future in futures:
            path_result, success = future.result()
            results[path_result] = success

    return results


def snapshot_initialization_state(study_paths: list[Path]) -> set[Path]:
    """Record which sourcedata subdatasets are currently initialized.

    Args:
        study_paths: List of study directories to snapshot

    Returns:
        Set of initialized sourcedata subdataset paths
    """
    initialized = set()

    for study_path in study_paths:
        sourcedata_dir = study_path / "sourcedata"
        if not sourcedata_dir.exists():
            continue

        for subdataset_path in sourcedata_dir.iterdir():
            if subdataset_path.is_dir() and is_subdataset_initialized(subdataset_path):
                initialized.add(subdataset_path)

    return initialized


def _deinitialize_single_subdataset(subdataset_path: Path, parent_path: Path) -> tuple[Path, bool]:
    """Deinitialize a single subdataset from its immediate parent repository.

    Args:
        subdataset_path: Path to subdataset to deinitialize
        parent_path: Path to top-level parent repository

    Returns:
        Tuple of (subdataset_path, success)
    """
    try:
        # Find the immediate parent repository that registers this subdataset
        immediate_parent = _find_immediate_parent_repo(subdataset_path, parent_path)

        if immediate_parent is None:
            logger.warning(
                f"Could not find parent repo for {subdataset_path} "
                f"(not registered in any .gitmodules)"
            )
            return (subdataset_path, False)

        # Make subdataset path relative to its immediate parent
        subdataset_relative = subdataset_path.resolve().relative_to(immediate_parent.resolve())

        result = subprocess.run(
            ["git", "-C", str(immediate_parent), "submodule", "deinit", "-f", str(subdataset_relative)],
            capture_output=True,
            timeout=30,
            check=False,
            text=True,
        )

        if result.returncode == 0:
            logger.info(f"Deinitialized subdataset: {subdataset_path}")
            return (subdataset_path, True)
        else:
            logger.warning(
                f"Failed to deinitialize {subdataset_path}: "
                f"returncode={result.returncode}, stderr={result.stderr}"
            )
            return (subdataset_path, False)

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout deinitializing {subdataset_path}")
        return (subdataset_path, False)
    except Exception as e:
        logger.warning(f"Exception deinitializing {subdataset_path}: {e}")
        return (subdataset_path, False)


def restore_initialization_state(
    current_state: set[Path],
    desired_state: set[Path],
    parent_path: Path = Path("."),
) -> None:
    """Uninstall subdatasets that weren't in the original state.

    Deinitializes subdatasets that are currently initialized but weren't
    in the desired state (i.e., subdatasets we initialized temporarily).

    Args:
        current_state: Set of currently initialized subdataset paths
        desired_state: Set of subdataset paths that should remain initialized
        parent_path: Path to parent repository (default: current directory)
    """
    to_deinitialize = current_state - desired_state

    if not to_deinitialize:
        logger.debug("No subdatasets to deinitialize (state matches desired)")
        return

    logger.info(f"Deinitializing {len(to_deinitialize)} temporarily initialized subdatasets")

    for subdataset_path in sorted(to_deinitialize):
        _deinitialize_single_subdataset(subdataset_path, parent_path)
