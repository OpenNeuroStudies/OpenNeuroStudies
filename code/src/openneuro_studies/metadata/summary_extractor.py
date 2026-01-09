"""Extract summary metadata from study datasets.

Implements extraction of:
- Phase 1: Raw dataset metadata (author_lead_raw, author_senior_raw, raw_version)
- Phase 2: Directory-based counts (subjects_num, sessions_*, datatypes)
- Phase 3: File counts (bold_num, t1w_num, t2w_num)
- Phase 4: File sizes from annex keys (bold_size, t1w_size, bold_size_max)
- Phase 5: Voxel counts (bold_voxels) - requires nibabel

All extraction uses sparse access via git commands and datalad-fuse,
avoiding full clones of source datasets.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from bids_studies.sparse import SparseDataset, is_sparse_access_available

logger = logging.getLogger(__name__)


# ============================================================================
# Phase 1: Raw Dataset Metadata
# ============================================================================


def extract_raw_metadata(study_path: Path) -> dict[str, Any]:
    """Extract metadata from raw source datasets.

    Gets author_lead_raw, author_senior_raw from source dataset's
    dataset_description.json, and raw_version from git tags.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with author_lead_raw, author_senior_raw, raw_version
    """
    result = {
        "author_lead_raw": "n/a",
        "author_senior_raw": "n/a",
        "raw_version": "n/a",
    }

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    # Collect authors from all sources
    all_lead_authors = []
    all_senior_authors = []
    all_versions = []

    for source_dir in source_dirs:
        # Try to read dataset_description.json
        desc_path = source_dir / "dataset_description.json"
        if desc_path.exists():
            try:
                with open(desc_path) as f:
                    desc = json.load(f)
                authors = desc.get("Authors", [])
                if authors:
                    all_lead_authors.append(authors[0])
                    all_senior_authors.append(authors[-1])
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read {desc_path}: {e}")

        # Try to get version from git tags
        version = _get_git_version(source_dir)
        if version:
            all_versions.append(version)

    # Determine final values
    if len(source_dirs) == 1:
        # Single source - use its values
        if all_lead_authors:
            result["author_lead_raw"] = all_lead_authors[0]
        if all_senior_authors:
            result["author_senior_raw"] = all_senior_authors[0]
        if all_versions:
            result["raw_version"] = all_versions[0]
    else:
        # Multiple sources - check for consistency
        if all_lead_authors and len(set(all_lead_authors)) == 1:
            result["author_lead_raw"] = all_lead_authors[0]
        if all_senior_authors and len(set(all_senior_authors)) == 1:
            result["author_senior_raw"] = all_senior_authors[0]
        # raw_version stays n/a for multi-source

    return result


def _get_git_version(repo_path: Path) -> Optional[str]:
    """Get latest git tag version from repository.

    Args:
        repo_path: Path to git repository

    Returns:
        Version string or None
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        pass

    # Try git tag --list as fallback
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "tag", "--list", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = result.stdout.strip().split("\n")
        if tags and tags[0]:
            return tags[0]
    except subprocess.CalledProcessError:
        pass

    return None


# ============================================================================
# Phase 2: Directory-Based Counts
# ============================================================================


def extract_directory_summary(study_path: Path) -> dict[str, Any]:
    """Extract summary from directory structure via sparse access.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with subjects_num, sessions_num, sessions_min,
        sessions_max, datatypes
    """
    result: dict[str, Any] = {
        "subjects_num": "n/a",
        "sessions_num": "n/a",
        "sessions_min": "n/a",
        "sessions_max": "n/a",
        "datatypes": "n/a",
    }

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    # Aggregate across all sources
    total_subjects = 0
    all_session_counts = []
    all_datatypes = set()

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                # Count subjects
                subjects = ds.list_dirs("sub-*")
                total_subjects += len(subjects)

                # Count sessions per subject
                for sub in subjects:
                    sub_name = sub.split("/")[-1]
                    sessions = ds.list_dirs(f"{sub_name}/ses-*")
                    if sessions:
                        all_session_counts.append(len(sessions))

                # Get datatypes
                datatypes = ds.list_bids_datatypes()
                all_datatypes.update(datatypes)

        except Exception as e:
            logger.warning(f"Failed to extract directory summary from {source_dir}: {e}")
            continue

    # Compile results
    if total_subjects > 0:
        result["subjects_num"] = total_subjects

    if all_session_counts:
        result["sessions_num"] = sum(all_session_counts)
        result["sessions_min"] = min(all_session_counts)
        result["sessions_max"] = max(all_session_counts)

    if all_datatypes:
        result["datatypes"] = ",".join(sorted(all_datatypes))

    return result


# ============================================================================
# Phase 3: File Counts
# ============================================================================


def extract_file_counts(study_path: Path) -> dict[str, Any]:
    """Count imaging files by modality via sparse access.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with bold_num, t1w_num, t2w_num
    """
    result: dict[str, Any] = {
        "bold_num": "n/a",
        "t1w_num": "n/a",
        "t2w_num": "n/a",
    }

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    # Aggregate across all sources
    total_bold = 0
    total_t1w = 0
    total_t2w = 0

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                # Count BOLD files
                bold_files = ds.list_files("*_bold.nii*")
                total_bold += len(bold_files)

                # Count T1w files
                t1w_files = ds.list_files("*_T1w.nii*")
                total_t1w += len(t1w_files)

                # Count T2w files
                t2w_files = ds.list_files("*_T2w.nii*")
                total_t2w += len(t2w_files)

        except Exception as e:
            logger.warning(f"Failed to extract file counts from {source_dir}: {e}")
            continue

    result["bold_num"] = total_bold
    result["t1w_num"] = total_t1w
    result["t2w_num"] = total_t2w

    return result


# ============================================================================
# Phase 4: File Sizes from Annex Keys
# ============================================================================


def extract_file_sizes(study_path: Path) -> dict[str, Any]:
    """Extract file sizes from annex keys without downloading.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with bold_size, t1w_size, bold_size_max
    """
    result: dict[str, Any] = {
        "bold_size": "n/a",
        "t1w_size": "n/a",
        "bold_size_max": "n/a",
    }

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    # Aggregate across all sources
    all_bold_sizes = []
    all_t1w_sizes = []

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                # Get BOLD file sizes
                bold_files = ds.list_files("*_bold.nii*")
                for f in bold_files:
                    size = ds.get_file_size(f)
                    if size is not None:
                        all_bold_sizes.append(size)

                # Get T1w file sizes
                t1w_files = ds.list_files("*_T1w.nii*")
                for f in t1w_files:
                    size = ds.get_file_size(f)
                    if size is not None:
                        all_t1w_sizes.append(size)

        except Exception as e:
            logger.warning(f"Failed to extract file sizes from {source_dir}: {e}")
            continue

    if all_bold_sizes:
        result["bold_size"] = sum(all_bold_sizes)
        result["bold_size_max"] = max(all_bold_sizes)

    if all_t1w_sizes:
        result["t1w_size"] = sum(all_t1w_sizes)

    return result


# ============================================================================
# Phase 5: Voxel Counts (requires nibabel)
# ============================================================================


def extract_voxel_counts(study_path: Path) -> dict[str, Any]:
    """Extract total voxel counts via sparse access and nibabel.

    This function requires nibabel and sparse access (datalad-fuse or fsspec).
    If not available, returns n/a.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with bold_voxels
    """
    result: dict[str, Any] = {"bold_voxels": "n/a"}

    # Check if sparse access and nibabel are available
    if not is_sparse_access_available():
        logger.info("Sparse access not available, skipping voxel extraction")
        return result

    try:
        import nibabel as nib
        import numpy as np
    except ImportError:
        logger.info("nibabel not installed, skipping voxel extraction")
        return result

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    total_voxels = 0
    files_processed = 0

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                bold_files = ds.list_files("*_bold.nii*")

                for bold_file in bold_files:
                    try:
                        with ds.open_file(bold_file) as f:
                            # Read NIfTI header
                            img = nib.Nifti1Image.from_stream(f)
                            shape = img.shape

                            # Calculate voxels (X * Y * Z * time if 4D)
                            voxels = int(np.prod(shape[:3]))
                            if len(shape) > 3:
                                voxels *= shape[3]

                            total_voxels += voxels
                            files_processed += 1

                    except Exception as e:
                        logger.debug(f"Failed to read NIfTI header from {bold_file}: {e}")
                        continue

        except Exception as e:
            logger.warning(f"Failed to extract voxel counts from {source_dir}: {e}")
            continue

    if files_processed > 0:
        result["bold_voxels"] = total_voxels

    return result


# ============================================================================
# Combined Extraction
# ============================================================================


def extract_all_summaries(
    study_path: Path,
    stage: str = "basic",
) -> dict[str, Any]:
    """Extract all summary metadata for a study.

    Args:
        study_path: Path to study directory
        stage: Extraction stage
            - "basic": Only cached metadata (author, version)
            - "counts": + directory/file counts via git tree
            - "sizes": + file sizes from annex keys
            - "imaging": + voxel counts via nibabel (requires sparse access)

    Returns:
        Dictionary with all extracted metadata
    """
    result = {}

    # Phase 1: Raw metadata (always)
    result.update(extract_raw_metadata(study_path))

    if stage in ("counts", "sizes", "imaging"):
        # Phase 2: Directory counts
        result.update(extract_directory_summary(study_path))

        # Phase 3: File counts
        result.update(extract_file_counts(study_path))

    if stage in ("sizes", "imaging"):
        # Phase 4: File sizes
        result.update(extract_file_sizes(study_path))

    if stage == "imaging":
        # Phase 5: Voxel counts
        result.update(extract_voxel_counts(study_path))

    return result
