"""Per-subject statistics extraction from BIDS datasets.

Extracts file counts, sizes, and optionally imaging metrics for each
subject (and session if multi-session) in a BIDS dataset.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from bids_studies.sparse import SparseDataset, is_sparse_access_available

logger = logging.getLogger(__name__)

# Known BIDS datatype directories
BIDS_DATATYPES = {
    "anat",
    "func",
    "dwi",
    "fmap",
    "perf",
    "meg",
    "eeg",
    "ieeg",
    "beh",
    "pet",
    "micr",
    "nirs",
    "motion",
}


def extract_subject_stats(
    ds: SparseDataset,
    source_id: str,
    subject: str,
    session: Optional[str] = None,
    include_imaging: bool = False,
) -> dict[str, Any]:
    """Extract stats for a single subject (or subject+session).

    Args:
        ds: SparseDataset instance for the source
        source_id: Source dataset ID (e.g., "ds000001")
        subject: Subject ID (e.g., "sub-01")
        session: Session ID if multi-session (e.g., "ses-01"), else None
        include_imaging: Whether to extract voxel/duration metrics

    Returns:
        Dictionary with per-subject statistics
    """
    # Build path prefix for this subject/session
    if session:
        prefix = f"{subject}/{session}/"
        session_id = session
    else:
        prefix = f"{subject}/"
        session_id = "n/a"

    result = {
        "source_id": source_id,
        "subject_id": subject,
        "session_id": session_id,
        "bold_num": 0,
        "t1w_num": 0,
        "t2w_num": 0,
        "bold_size": 0,
        "t1w_size": 0,
        "bold_duration_total": None,
        "bold_duration_mean": None,
        "bold_voxels_total": None,
        "bold_voxels_mean": None,
        "datatypes": set(),
    }

    # Get files for this subject/session
    all_files = ds.list_files("*")
    subject_files = [f for f in all_files if f.startswith(prefix)]

    # Count files by modality
    bold_files = [f for f in subject_files if "_bold.nii" in f]
    t1w_files = [f for f in subject_files if "_T1w.nii" in f]
    t2w_files = [f for f in subject_files if "_T2w.nii" in f]

    result["bold_num"] = len(bold_files)
    result["t1w_num"] = len(t1w_files)
    result["t2w_num"] = len(t2w_files)

    # Get file sizes
    bold_sizes = []
    for f in bold_files:
        size = ds.get_file_size(f)
        if size is not None:
            bold_sizes.append(size)

    t1w_sizes = []
    for f in t1w_files:
        size = ds.get_file_size(f)
        if size is not None:
            t1w_sizes.append(size)

    if bold_sizes:
        result["bold_size"] = sum(bold_sizes)
    if t1w_sizes:
        result["t1w_size"] = sum(t1w_sizes)

    # Extract datatypes
    for f in subject_files:
        parts = f.split("/")
        for part in parts:
            if part in BIDS_DATATYPES:
                result["datatypes"].add(part)
                break

    # Extract imaging metrics if requested
    if include_imaging and bold_files and is_sparse_access_available():
        _extract_imaging_metrics(ds, bold_files, result)

    # Convert datatypes set to sorted comma-separated string
    result["datatypes"] = (
        ",".join(sorted(result["datatypes"])) if result["datatypes"] else "n/a"
    )

    return result


def _extract_imaging_metrics(
    ds: SparseDataset,
    bold_files: list[str],
    result: dict[str, Any],
) -> None:
    """Extract imaging metrics from BOLD files.

    Args:
        ds: SparseDataset instance
        bold_files: List of BOLD file paths
        result: Result dict to update in place
    """
    try:
        import nibabel as nib
        import numpy as np
    except ImportError:
        logger.debug("nibabel not available for imaging extraction")
        return

    durations = []
    voxel_counts = []

    for bold_file in bold_files:
        try:
            with ds.open_file(bold_file) as f:
                img = nib.Nifti1Image.from_stream(f)
                shape = img.shape
                zooms = img.header.get_zooms()
                tr = zooms[3] if len(zooms) > 3 else None

                # Calculate voxels (X * Y * Z)
                voxels = int(np.prod(shape[:3]))
                voxel_counts.append(voxels)

                # Calculate duration if TR available
                if tr and tr > 0 and len(shape) > 3:
                    n_volumes = shape[3]
                    duration = float(tr) * n_volumes
                    durations.append(duration)

        except Exception as e:
            logger.debug(f"Failed to read BOLD header from {bold_file}: {e}")
            continue

    if voxel_counts:
        result["bold_voxels_total"] = sum(voxel_counts)
        result["bold_voxels_mean"] = sum(voxel_counts) / len(voxel_counts)

    if durations:
        result["bold_duration_total"] = sum(durations)
        result["bold_duration_mean"] = sum(durations) / len(durations)


def extract_subjects_stats(
    source_path: Path,
    source_id: str,
    include_imaging: bool = False,
) -> list[dict[str, Any]]:
    """Extract stats for all subjects in a source dataset.

    Args:
        source_path: Path to source dataset
        source_id: Source dataset ID
        include_imaging: Whether to extract voxel/duration metrics

    Returns:
        List of per-subject statistics dictionaries
    """
    results = []

    try:
        with SparseDataset(source_path) as ds:
            # Find all subjects
            subjects = ds.list_dirs("sub-*")
            if not subjects:
                return results

            for subject in subjects:
                subject_name = subject.split("/")[-1]

                # Check for sessions
                sessions = ds.list_dirs(f"{subject_name}/ses-*")

                if sessions:
                    # Multi-session: one row per subject+session
                    for session in sessions:
                        session_name = session.split("/")[-1]
                        stats = extract_subject_stats(
                            ds, source_id, subject_name, session_name, include_imaging
                        )
                        results.append(stats)
                else:
                    # Single-session: one row per subject
                    stats = extract_subject_stats(
                        ds, source_id, subject_name, None, include_imaging
                    )
                    results.append(stats)

    except Exception as e:
        logger.warning(f"Failed to extract subjects from {source_path}: {e}")

    return results
