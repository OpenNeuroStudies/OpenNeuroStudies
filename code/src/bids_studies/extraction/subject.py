"""Per-subject statistics extraction from BIDS datasets.

Extracts file counts, sizes, and optionally imaging metrics for each
subject (and session if multi-session) in a BIDS dataset.
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
) -> tuple[dict[str, Any], list[str]]:
    """Extract stats for a single subject (or subject+session).

    Args:
        ds: SparseDataset instance for the source
        source_id: Source dataset ID (e.g., "ds000001")
        subject: Subject ID (e.g., "sub-01")
        session: Session ID if multi-session (e.g., "ses-01"), else None
        include_imaging: Whether to extract voxel/duration metrics

    Returns:
        Tuple of (statistics dict, list of error messages)
    """
    # Build path prefix for this subject/session
    if session:
        prefix = f"{subject}/{session}/"
        session_id = session
    else:
        prefix = f"{subject}/"
        session_id = "n/a"

    # Track errors during extraction
    errors: list[str] = []

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
        "datatypes": "",  # Will be set at the end
    }

    # Track datatypes separately for type safety
    datatypes: set[str] = set()

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
                datatypes.add(part)
                break

    # Extract imaging metrics if requested
    if include_imaging and bold_files:
        _extract_imaging_metrics(ds, bold_files, result, errors)

    # Convert datatypes set to sorted comma-separated string
    result["datatypes"] = ",".join(sorted(datatypes)) if datatypes else "n/a"

    return result, errors


def _extract_nifti_header_from_gzip_stream(f: Any) -> Optional[tuple[tuple[int, ...], float]]:
    """Extract NIfTI header info from a gzipped HTTP stream.

    For gzipped NIfTI files over HTTP, we need to read enough data
    to decompress the header (first 352 bytes). This function reads
    ~1MB which is typically sufficient to decompress the header.

    Args:
        f: File-like object (HTTP stream)

    Returns:
        Tuple of (shape, tr) or None if extraction fails
    """
    import struct
    import zlib

    # Read enough gzip data to decompress header (~1MB should suffice)
    chunk_size = 1024 * 1024  # 1MB
    try:
        gzip_data = f.read(chunk_size)
    except Exception as e:
        logger.debug(f"Failed to read from stream: {e}")
        return None

    if len(gzip_data) < 100:
        logger.debug(f"Not enough data read: {len(gzip_data)} bytes")
        return None

    # Check for gzip magic number
    if gzip_data[:2] != b"\x1f\x8b":
        logger.debug("Not a gzip file")
        return None

    # Decompress using zlib (gzip is zlib with extra header)
    try:
        decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16)  # 16 for gzip
        decompressed = decompressor.decompress(gzip_data)
    except zlib.error as e:
        logger.debug(f"Decompression failed: {e}")
        return None

    if len(decompressed) < 352:
        logger.debug(f"Not enough decompressed data: {len(decompressed)} bytes")
        return None

    # Parse NIfTI header
    # sizeof_hdr at offset 0 (int32)
    sizeof_hdr = struct.unpack("<i", decompressed[:4])[0]
    if sizeof_hdr != 348:
        logger.debug(f"Invalid sizeof_hdr: {sizeof_hdr}")
        return None

    # Dimensions at offset 40: dim[0..7] as int16
    dims = struct.unpack("<8h", decompressed[40:56])
    n_dims = dims[0]
    if n_dims < 3 or n_dims > 7:
        logger.debug(f"Invalid n_dims: {n_dims}")
        return None

    # Extract shape
    shape = tuple(dims[1 : n_dims + 1])

    # Pixel dimensions at offset 76: pixdim[0..7] as float32
    pixdim = struct.unpack("<8f", decompressed[76:108])
    tr = pixdim[4] if len(pixdim) > 4 else 0.0

    return shape, tr


def _extract_imaging_metrics(
    ds: SparseDataset,
    bold_files: list[str],
    result: dict[str, Any],
    errors: list[str],
) -> None:
    """Extract imaging metrics from BOLD files.

    For gzipped NIfTI files over HTTP, we read ~1MB of data
    to decompress and parse the header. This avoids downloading
    the entire file while still extracting shape and TR.

    Args:
        ds: SparseDataset instance
        bold_files: List of BOLD file paths
        result: Result dict to update in place
        errors: List to accumulate error messages
    """
    import numpy as np

    durations = []
    voxel_counts = []

    for bold_file in bold_files:
        try:
            with ds.open_file(bold_file) as f:
                header_info = _extract_nifti_header_from_gzip_stream(f)
                if header_info is None:
                    logger.debug(f"Could not extract header from {bold_file}")
                    continue

                shape, tr = header_info

                # Calculate voxels (X * Y * Z)
                voxels = int(np.prod(shape[:3]))
                voxel_counts.append(voxels)

                # Calculate duration if TR available
                if tr and tr > 0 and len(shape) > 3:
                    n_volumes = shape[3]
                    duration = float(tr) * n_volumes
                    durations.append(duration)

        except NetworkError:
            # Network error after retries - propagate to fail extraction
            raise
        except Exception as e:
            # Other errors (corrupt file, invalid format) - accumulate and continue
            # CRITICAL: Log at WARNING level AND accumulate error per Constitution Principle V
            error_msg = f"Failed to extract imaging metrics from {bold_file}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    if voxel_counts:
        result["bold_voxels_total"] = sum(voxel_counts)
        result["bold_voxels_mean"] = sum(voxel_counts) / len(voxel_counts)
    elif bold_files:
        # Had BOLD files but failed to extract any metrics - record error
        errors.append(f"Failed to extract imaging metrics from all {len(bold_files)} BOLD files")

    if durations:
        result["bold_duration_total"] = sum(durations)
        result["bold_duration_mean"] = sum(durations) / len(durations)


def extract_subjects_stats(
    source_path: Path,
    source_id: str,
    include_imaging: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract stats for all subjects in a source dataset.

    Args:
        source_path: Path to source dataset
        source_id: Source dataset ID
        include_imaging: Whether to extract voxel/duration metrics

    Returns:
        Tuple of (list of statistics dictionaries, list of error messages)

    Raises:
        RuntimeError: If extraction errors exceed threshold (50% failure rate)
    """
    results: list[dict[str, Any]] = []
    all_errors: list[str] = []

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
                        stats, errors = extract_subject_stats(
                            ds, source_id, subject_name, session_name, include_imaging
                        )
                        results.append(stats)
                        all_errors.extend(errors)
                else:
                    # Single-session: one row per subject
                    stats, errors = extract_subject_stats(
                        ds, source_id, subject_name, None, include_imaging
                    )
                    results.append(stats)
                    all_errors.extend(errors)

    except Exception as e:
        error_msg = f"Failed to extract subjects from {source_path}: {e}"
        logger.warning(error_msg)
        all_errors.append(error_msg)

    # Check if extraction errors exceed threshold
    if all_errors and results:
        # Calculate error rate based on failed operations vs successful subjects
        total_subjects = len(results)
        error_rate = len(all_errors) / total_subjects if total_subjects > 0 else 0

        # Report error summary
        logger.warning(
            f"Extraction completed with {len(all_errors)} errors "
            f"across {total_subjects} subjects/sessions "
            f"(error rate: {error_rate:.1%})"
        )

        # Fail if error rate exceeds 50% (indicates systemic problem)
        if error_rate > 0.5:
            error_summary = "\n".join(all_errors[:10])  # Show first 10 errors
            raise RuntimeError(
                f"Extraction failed: {len(all_errors)} errors across {total_subjects} subjects "
                f"(error rate: {error_rate:.1%} exceeds 50% threshold).\n"
                f"First errors:\n{error_summary}"
            )
    elif all_errors and not results:
        # All extractions failed - critical error
        error_summary = "\n".join(all_errors[:10])
        raise RuntimeError(
            f"Extraction completely failed: {len(all_errors)} errors, no successful extractions.\n"
            f"Errors:\n{error_summary}"
        )

    return results, all_errors
