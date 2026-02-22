"""Subdataset management utilities for BIDS study datasets.

This module provides tools for managing git subdatasets during metadata extraction,
including temporary installation/uninstallation with state preservation.
"""

import logging
import time
from pathlib import Path
from typing import Iterator

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import IncompleteResultsError

logger = logging.getLogger(__name__)


# ============================================================================
# Low-level utilities
# ============================================================================

def iter_sourcedata_subdatasets(study_path: Path) -> Iterator[Path]:
    """Iterate over sourcedata subdataset paths in a study.

    Yields absolute paths to all subdatasets under study_path/sourcedata/,
    regardless of whether they are installed.

    Args:
        study_path: Path to study directory

    Yields:
        Absolute paths to sourcedata subdatasets
    """
    parent_ds = Dataset(str(study_path))
    if not parent_ds.is_installed():
        return

    try:
        subdatasets = list(parent_ds.subdatasets(result_renderer='disabled'))
        for sd in subdatasets:
            sd_path = Path(sd['path'])
            # Filter for sourcedata subdatasets
            if 'sourcedata' in sd_path.parts:
                yield sd_path
    except Exception as e:
        logger.warning(f"Failed to list subdatasets of {study_path}: {e}")


def get_subdataset_states(study_path: Path) -> dict[Path, str]:
    """Get installation state of all sourcedata subdatasets.

    Args:
        study_path: Path to study directory

    Returns:
        Dict mapping subdataset path to state ('absent' or 'present')
    """
    states = {}
    for sd_path in iter_sourcedata_subdatasets(study_path):
        ds = Dataset(str(sd_path))
        states[sd_path] = 'present' if ds.is_installed() else 'absent'
    return states


def ensure_subdatasets_installed(
    study_path: Path,
    get_data: bool = False,
    max_retries: int = 3
) -> tuple[set[Path], set[Path]]:
    """Install sourcedata subdatasets if not already installed.

    Args:
        study_path: Path to study directory
        get_data: If True, also get file content (not just git tree)
        max_retries: Maximum retry attempts for transient errors

    Returns:
        Tuple of (newly_installed, already_installed) path sets

    Raises:
        RuntimeError: If installation fails after retries or on non-transient errors
    """
    newly_installed = set()
    already_installed = set()

    parent_ds = Dataset(str(study_path))

    for sd_path in iter_sourcedata_subdatasets(study_path):
        ds = Dataset(str(sd_path))

        if ds.is_installed():
            already_installed.add(sd_path)
        else:
            # Install using parent dataset's get method with retries
            # DataLad accepts absolute paths directly - no need for relative_to()
            last_error = None
            for attempt in range(max_retries):
                try:
                    parent_ds.get(str(sd_path), get_data=get_data,
                                 result_renderer='disabled')
                    newly_installed.add(sd_path)
                    logger.info(f"Installed subdataset: {sd_path}")
                    break
                except (IncompleteResultsError, OSError, IOError) as e:
                    # Transient errors: network issues, file locks, etc.
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(
                            f"Transient error installing {sd_path} "
                            f"(attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to install {sd_path} after {max_retries} attempts"
                        )
                        raise RuntimeError(
                            f"Installation failed after {max_retries} retries: {e}"
                        ) from e
                except Exception as e:
                    # Non-transient error: fail immediately
                    logger.error(f"Fatal error installing {sd_path}: {e}")
                    raise RuntimeError(
                        f"Installation of {sd_path} failed with unexpected error: {e}"
                    ) from e

    return newly_installed, already_installed


def drop_subdatasets(
    subdataset_paths: set[Path],
    study_path: Path,
    reckless: bool = False,
    max_retries: int = 3
) -> set[Path]:
    """Drop (uninstall) subdatasets.

    Args:
        subdataset_paths: Set of subdataset paths to drop
        study_path: Parent study path
        reckless: Skip safety checks for faster operation (default: False)
                 TODO: Consider enabling after verifying correct operation.
                 Using reckless='kill' skips DataLad's availability checks,
                 which is appropriate for local-only datasets but bypasses
                 safety mechanisms during development.
        max_retries: Maximum retry attempts for transient errors

    Returns:
        Set of successfully dropped paths

    Raises:
        RuntimeError: If drop fails after retries or on non-transient errors
    """
    dropped = set()
    parent_ds = Dataset(str(study_path))

    for sd_path in subdataset_paths:
        # DataLad accepts absolute paths directly - no need for relative_to()
        last_error = None
        for attempt in range(max_retries):
            try:
                # Use safe mode by default; reckless='kill' can be enabled later
                # for performance after verifying correctness
                parent_ds.drop(str(sd_path),
                              what='datasets',
                              reckless='kill' if reckless else None,
                              result_renderer='disabled')
                dropped.add(sd_path)
                logger.info(f"Dropped subdataset: {sd_path}")
                break
            except (IncompleteResultsError, OSError, IOError) as e:
                # Transient errors: file locks, network issues, etc.
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Transient error dropping {sd_path} "
                        f"(attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to drop {sd_path} after {max_retries} attempts"
                    )
                    raise RuntimeError(
                        f"Drop failed after {max_retries} retries: {e}"
                    ) from e
            except Exception as e:
                # Non-transient error: fail immediately
                logger.error(f"Fatal error dropping {sd_path}: {e}")
                raise RuntimeError(
                    f"Drop of {sd_path} failed with unexpected error: {e}"
                ) from e

    return dropped


class TemporarySubdatasetInstall:
    """Context manager for temporary subdataset installation.

    Installs sourcedata subdatasets on entry, drops newly-installed ones on exit.
    Preserves the installation state of subdatasets that were already installed.

    Example:
        with TemporarySubdatasetInstall(study_path) as (newly, existing):
            # All sourcedata subdatasets are now installed
            # Extract metadata here
            pass
        # Newly installed subdatasets are dropped, existing ones preserved
    """

    def __init__(self, study_path: Path, get_data: bool = False,
                 reckless_drop: bool = False):
        self.study_path = study_path
        self.get_data = get_data
        self.reckless_drop = reckless_drop
        self.newly_installed = set()
        self.already_installed = set()

    def __enter__(self):
        self.newly_installed, self.already_installed = \
            ensure_subdatasets_installed(self.study_path, self.get_data)
        return self.newly_installed, self.already_installed

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Only drop subdatasets we installed
        if self.newly_installed:
            drop_subdatasets(self.newly_installed, self.study_path,
                           reckless=self.reckless_drop)
        return False  # Don't suppress exceptions


# ============================================================================
# High-level interface for extraction with managed subdatasets
# ============================================================================

def extract_study_with_subdatasets(
    study_path: Path,
    stage: str = "basic",
    get_data: bool = False,
    reckless_drop: bool = False
) -> dict:
    """Extract study metadata with automatic subdataset management.

    High-level function that:
    1. Installs sourcedata subdatasets if needed
    2. Extracts metadata at specified stage
    3. Drops newly-installed subdatasets (preserves existing ones)

    This is the main entry point for both CLI and Snakemake workflows.

    Args:
        study_path: Path to study directory
        stage: Extraction stage ("basic", "counts", "sizes", "imaging")
        get_data: If True, also get file content (not just git tree)
        reckless_drop: Skip safety checks when dropping subdatasets

    Returns:
        Dictionary with extracted metadata (all studies.tsv columns)

    Raises:
        Exception: If subdataset installation/drop or extraction fails

    Example:
        # Use from CLI or Snakemake
        from bids_studies.subdatasets import extract_study_with_subdatasets

        result = extract_study_with_subdatasets(
            Path('study-ds000001'),
            stage='imaging'
        )
        # result contains: study_id, subjects_num, bold_num, etc.
    """
    # Import here to avoid circular dependencies
    from openneuro_studies.metadata.studies_tsv import collect_study_metadata

    with TemporarySubdatasetInstall(study_path, get_data, reckless_drop) as (newly, existing):
        if newly:
            logger.info(f"Installed {len(newly)} sourcedata subdatasets for {study_path.name}")
        if existing:
            logger.info(f"Using {len(existing)} already-installed subdatasets")

        # Extract metadata with subdatasets now available
        result = collect_study_metadata(study_path, stage=stage)
        logger.info(f"Extracted metadata for {study_path.name}")

    # Subdatasets automatically dropped on context exit
    return result


__all__ = [
    'iter_sourcedata_subdatasets',
    'get_subdataset_states',
    'ensure_subdatasets_installed',
    'drop_subdatasets',
    'TemporarySubdatasetInstall',
    'extract_study_with_subdatasets',
]
