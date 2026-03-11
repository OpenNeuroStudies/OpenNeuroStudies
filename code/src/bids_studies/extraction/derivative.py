"""Per-subject statistics extraction from derivative datasets.

Extracts file counts and sizes for derivative outputs, including breakdowns
by file type (NIfTI, HTML reports, etc.).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from bids_studies.sparse import SparseDataset

# Import NetworkError if available (bids_studies can be used standalone)
try:
    from openneuro_studies.lib.exceptions import NetworkError
    NETWORK_ERROR_AVAILABLE = True
except ImportError:
    NetworkError = Exception  # type: ignore[misc, assignment]
    NETWORK_ERROR_AVAILABLE = False

logger = logging.getLogger(__name__)

# Known BIDS datatype directories (derivatives may follow similar structure)
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


def extract_derivative_subject_stats(
    ds: SparseDataset,
    source_id: str,
    derivative_id: str,
    subject: str,
    session: Optional[str] = None,
) -> dict[str, Any]:
    """Extract stats for a single subject's derivative outputs.

    Args:
        ds: SparseDataset instance for the derivative
        source_id: Source dataset ID (e.g., "ds000001")
        derivative_id: Derivative ID (e.g., "mriqc-25.0.0")
        subject: Subject ID (e.g., "sub-01")
        session: Session ID if multi-session (e.g., "ses-01"), else None

    Returns:
        Dictionary with per-subject derivative statistics
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
        "derivative_id": derivative_id,
        "subject_id": subject,
        "session_id": session_id,
        "output_num": 0,
        "output_size": 0,
        "nifti_num": 0,
        "nifti_size": 0,
        "html_num": 0,
    }

    # Get files for this subject/session
    all_files = ds.list_files("*")
    subject_files = [f for f in all_files if f.startswith(prefix)]

    # Count all output files
    result["output_num"] = len(subject_files)

    # Categorize by file type
    nifti_files = [f for f in subject_files if f.endswith((".nii", ".nii.gz"))]
    html_files = [f for f in subject_files if f.endswith(".html")]

    result["nifti_num"] = len(nifti_files)
    result["html_num"] = len(html_files)

    # Get file sizes
    total_size = 0
    nifti_size = 0

    for f in subject_files:
        size = ds.get_file_size(f)
        if size is not None:
            total_size += size
            if f in nifti_files:
                nifti_size += size

    result["output_size"] = total_size
    result["nifti_size"] = nifti_size

    return result


def extract_derivative_subjects_stats(
    derivative_path: Path,
    source_id: str,
    derivative_id: str,
) -> list[dict[str, Any]]:
    """Extract stats for all subjects in a derivative dataset.

    Args:
        derivative_path: Path to derivative dataset
        source_id: Source dataset ID
        derivative_id: Derivative ID

    Returns:
        List of per-subject statistics dictionaries
    """
    results: list[dict[str, Any]] = []

    try:
        with SparseDataset(derivative_path) as ds:
            # Find all subjects
            subjects = ds.list_dirs("sub-*")
            if not subjects:
                return results

            for subject in subjects:
                subject_name = subject.split("/")[-1]

                # Check for sessions
                sessions = ds.list_dirs(f"{subject_name}/ses-*")

                # Filter out non-session directories (like datatypes)
                # Valid sessions must start with "ses-" and not be a BIDS datatype
                valid_sessions = []
                for session in sessions:
                    session_name = session.split("/")[-1]
                    # Only include if it starts with "ses-" and is not a datatype
                    if session_name.startswith("ses-") and session_name not in BIDS_DATATYPES:
                        valid_sessions.append(session)

                if valid_sessions:
                    # Multi-session: one row per subject+session
                    for session in valid_sessions:
                        session_name = session.split("/")[-1]
                        stats = extract_derivative_subject_stats(
                            ds, source_id, derivative_id, subject_name, session_name
                        )
                        results.append(stats)
                else:
                    # Single-session: one row per subject
                    stats = extract_derivative_subject_stats(
                        ds, source_id, derivative_id, subject_name, None
                    )
                    results.append(stats)

    except Exception as e:
        logger.warning(f"Failed to extract derivative subjects from {derivative_path}: {e}")

    return results


def aggregate_derivative_to_dataset(
    subjects_stats: list[dict[str, Any]],
    source_id: str,
    derivative_id: str,
) -> dict[str, Any]:
    """Aggregate subject-level derivative stats to dataset level.

    Args:
        subjects_stats: List of per-subject derivative statistics
        source_id: Source dataset ID
        derivative_id: Derivative ID

    Returns:
        Dataset-level aggregated derivative statistics
    """
    if not subjects_stats:
        return {
            "source_id": source_id,
            "derivative_id": derivative_id,
            "subjects_num": 0,
            "sessions_num": "n/a",
            "output_num": 0,
            "output_size": 0,
            "nifti_num": 0,
            "nifti_size": 0,
            "html_num": 0,
        }

    # Count unique subjects
    unique_subjects = {s["subject_id"] for s in subjects_stats}

    # Count sessions per subject (only valid ses-* sessions)
    session_counts: dict[str, int] = {}
    for s in subjects_stats:
        subj = s["subject_id"]
        sess = s["session_id"]
        # Only count valid sessions (not n/a and starts with ses-)
        if sess != "n/a" and sess.startswith("ses-"):
            session_counts[subj] = session_counts.get(subj, 0) + 1

    # Sum numeric fields
    total_output_num = sum(s["output_num"] for s in subjects_stats)
    total_output_size = sum(s["output_size"] for s in subjects_stats if isinstance(s["output_size"], int))
    total_nifti_num = sum(s["nifti_num"] for s in subjects_stats)
    total_nifti_size = sum(s["nifti_size"] for s in subjects_stats if isinstance(s["nifti_size"], int))
    total_html_num = sum(s["html_num"] for s in subjects_stats)

    result = {
        "source_id": source_id,
        "derivative_id": derivative_id,
        "subjects_num": len(unique_subjects),
        "sessions_num": sum(session_counts.values()) if session_counts else "n/a",
        "output_num": total_output_num,
        "output_size": total_output_size,
        "nifti_num": total_nifti_num,
        "nifti_size": total_nifti_size,
        "html_num": total_html_num,
    }

    return result
