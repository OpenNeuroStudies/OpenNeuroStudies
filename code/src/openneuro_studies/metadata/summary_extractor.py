"""Extract summary metadata from study datasets.

Implements extraction of:
- Phase 1: Raw dataset metadata (author_lead_raw, author_senior_raw, raw_version,
            raw_bids_version, raw_hed_version)
- Phase 2: Directory-based counts (subjects_num, sessions_*, datatypes)
- Phase 3: File counts (bold_num, t1w_num, t2w_num)
- Phase 4: File sizes from annex keys (bold_size, t1w_size, bold_size_max)
- Phase 5: BOLD imaging metadata (bold_voxels, bold_timepoints, bold_tasks) - requires fsspec

All extraction uses sparse access via git commands and fsspec/datalad-fuse,
avoiding full clones of source datasets.
"""

import csv
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from bids_studies.sparse import SparseDataset
from openneuro_studies.lib.exceptions import ExtractionError, NetworkError

logger = logging.getLogger(__name__)

# Extraction version - increment when extraction logic changes
# Format: MAJOR.MINOR.PATCH (semantic versioning)
# - MAJOR: Breaking schema changes
# - MINOR: New metrics added (backward compatible)
# - PATCH: Bug fixes, no schema changes
EXTRACTION_VERSION = "1.1.0"  # Added: bold_trs, bold_duration_total, nibabel-based parsing


# ============================================================================
# Phase 1: Raw Dataset Metadata
# ============================================================================


def extract_raw_metadata(study_path: Path) -> dict[str, Any]:
    """Extract metadata from raw source datasets.

    Gets author_lead_raw, author_senior_raw, raw_bids_version, and
    raw_hed_version from source dataset's dataset_description.json,
    and raw_version from git tags.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with author_lead_raw, author_senior_raw, raw_version,
        raw_bids_version, raw_hed_version
    """
    result = {
        "author_lead_raw": "n/a",
        "author_senior_raw": "n/a",
        "raw_version": "n/a",
        "raw_bids_version": "n/a",
        "raw_hed_version": "n/a",
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

    # Collect metadata from all sources
    all_lead_authors = []
    all_senior_authors = []
    all_versions = []
    all_bids_versions = []
    all_hed_versions = []

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

                # Extract BIDSVersion
                bids_version = desc.get("BIDSVersion")
                if bids_version:
                    all_bids_versions.append(bids_version)

                # Extract HEDVersion
                hed_version = desc.get("HEDVersion")
                if hed_version:
                    all_hed_versions.append(hed_version)

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
        if all_bids_versions:
            result["raw_bids_version"] = all_bids_versions[0]
        if all_hed_versions:
            result["raw_hed_version"] = all_hed_versions[0]
    else:
        # Multiple sources - check for consistency
        if all_lead_authors and len(set(all_lead_authors)) == 1:
            result["author_lead_raw"] = all_lead_authors[0]
        if all_senior_authors and len(set(all_senior_authors)) == 1:
            result["author_senior_raw"] = all_senior_authors[0]
        if all_bids_versions and len(set(all_bids_versions)) == 1:
            result["raw_bids_version"] = all_bids_versions[0]
        if all_hed_versions and len(set(all_hed_versions)) == 1:
            result["raw_hed_version"] = all_hed_versions[0]
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
# Phase 5: BOLD Imaging Metadata (requires sparse access)
# ============================================================================


def _extract_nifti_header_from_gzip_stream(f: Any) -> Optional[tuple[tuple[int, ...], float]]:
    """Extract NIfTI header info from a gzipped HTTP stream using nibabel.

    For gzipped NIfTI files over HTTP, we need to read enough data
    to decompress the header (first 352 bytes). This function reads
    10KB which is sufficient to decompress NIfTI headers.

    Args:
        f: File-like object (HTTP stream)

    Returns:
        Tuple of (shape, tr) or None if extraction fails
    """
    import zlib
    from io import BytesIO
    import nibabel as nib

    # Read enough gzip data to decompress header
    # 10KB is sufficient for gzip-compressed NIfTI headers (tested on OpenNeuro datasets)
    chunk_size = 10 * 1024  # 10KB (100x reduction from previous 1MB)
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

    # Parse NIfTI header using nibabel
    try:
        header = nib.Nifti1Header.from_fileobj(BytesIO(decompressed))
        shape = header.get_data_shape()
        zooms = header.get_zooms()

        # TR is the 4th dimension of zooms (time axis)
        tr = float(zooms[3]) if len(shape) > 3 else 0.0

        return tuple(shape), tr

    except Exception as e:
        logger.debug(f"Failed to parse NIfTI header with nibabel: {e}")
        return None


def _extract_task_from_filename(filename: str) -> Optional[str]:
    """Extract task label from BIDS filename.

    Args:
        filename: BIDS filename (e.g., 'sub-01_task-rest_bold.nii.gz')

    Returns:
        Task label or None if not found
    """
    import re

    # Match task-<label> pattern in filename
    match = re.search(r"_task-([a-zA-Z0-9]+)", filename)
    if match:
        return match.group(1)
    return None


def extract_bold_imaging_metadata(study_path: Path) -> dict[str, Any]:
    """Extract BOLD imaging metadata via sparse access.

    Extracts:
    - bold_voxels: Maximum voxel count across all BOLD files (X * Y * Z)
    - bold_timepoints: Sum of timepoints across all BOLD runs
    - bold_tasks: Sorted comma-separated set of task labels
    - bold_trs: Dict of {TR: count} showing TR distribution
    - bold_duration_total: Total acquisition time in seconds (sum of TR × volumes)

    For gzipped NIfTI files over HTTP, reads 10KB of data per file
    to decompress and parse the header using nibabel. This avoids downloading
    the entire file while still extracting shape and timing info.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with BOLD imaging metrics
    """
    import numpy as np

    result: dict[str, Any] = {
        "bold_voxels": "n/a",
        "bold_timepoints": "n/a",
        "bold_tasks": "n/a",
        "bold_trs": "n/a",
        "bold_duration_total": "n/a",
    }

    # Find sourcedata subdatasets
    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        logger.debug(f"Sourcedata path does not exist: {sourcedata_path}")
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        logger.debug(f"No sourcedata subdatasets found in {sourcedata_path}")
        return result

    max_voxels = 0
    total_timepoints = 0
    total_duration = 0.0
    task_labels = set()
    tr_distribution: dict[float, int] = {}  # {TR: count}
    files_processed = 0

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                bold_files = ds.list_files("*_bold.nii*")

                for bold_file in bold_files:
                    # Extract task label from filename
                    task = _extract_task_from_filename(bold_file)
                    if task:
                        task_labels.add(task)

                    try:
                        with ds.open_file(bold_file) as f:
                            header_info = _extract_nifti_header_from_gzip_stream(f)
                            if header_info is None:
                                logger.debug(f"Could not extract header from {bold_file}")
                                continue

                            shape, tr = header_info

                            # Calculate spatial voxels (X * Y * Z, not including time dimension)
                            voxels = int(np.prod(shape[:3]))
                            max_voxels = max(max_voxels, voxels)

                            # Extract timepoints (4th dimension if present)
                            if len(shape) > 3:
                                timepoints = shape[3]
                                total_timepoints += timepoints

                                # Track TR distribution (round to 3 decimals to avoid float precision issues)
                                if tr > 0:
                                    tr_rounded = round(tr, 3)
                                    tr_distribution[tr_rounded] = tr_distribution.get(tr_rounded, 0) + 1

                                    # Calculate duration: TR * volumes
                                    duration = tr * timepoints
                                    total_duration += duration

                            files_processed += 1

                    except NetworkError:
                        # Network errors are retriable, but if retry fails, propagate
                        # This will bubble up and fail the entire extraction
                        raise
                    except Exception as e:
                        # Other errors (corrupt file, invalid format) - log and continue
                        logger.debug(f"Failed to read NIfTI header from {bold_file}: {e}")
                        continue

        except NetworkError:
            # Network error after retries - propagate to fail extraction
            raise
        except Exception as e:
            logger.warning(f"Failed to extract BOLD imaging metadata from {source_dir}: {e}")
            continue

    if files_processed > 0:
        result["bold_voxels"] = max_voxels

    if total_timepoints > 0:
        result["bold_timepoints"] = total_timepoints

    if task_labels:
        result["bold_tasks"] = ",".join(sorted(task_labels))

    if tr_distribution:
        # Convert to sorted dict and serialize to JSON string (like descriptions field)
        tr_dict = dict(sorted(tr_distribution.items()))
        result["bold_trs"] = json.dumps(tr_dict, separators=(",", ":"))

    if total_duration > 0:
        result["bold_duration_total"] = round(total_duration, 1)

    return result


# ============================================================================
# Combined Extraction
# ============================================================================


def _extract_bold_tasks_and_timepoints(study_path: Path) -> dict[str, Any]:
    """Extract BOLD tasks, timepoints, and TRs (not in hierarchical TSV).

    This is a lighter version of extract_bold_imaging_metadata() that only
    extracts task labels, timepoints, and TR distribution (which aren't in
    the hierarchical TSV files).

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with task labels, timepoints, and TR distribution
    """
    result: dict[str, Any] = {
        "bold_timepoints": "n/a",
        "bold_tasks": "n/a",
        "bold_trs": "n/a",
    }

    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return result

    total_timepoints = 0
    task_labels = set()
    tr_distribution: dict[float, int] = {}

    for source_dir in source_dirs:
        try:
            with SparseDataset(source_dir) as ds:
                bold_files = ds.list_files("*_bold.nii*")

                for bold_file in bold_files:
                    # Extract task label
                    task = _extract_task_from_filename(bold_file)
                    if task:
                        task_labels.add(task)

                    # Extract timepoints and TR from header
                    try:
                        with ds.open_file(bold_file) as f:
                            header_info = _extract_nifti_header_from_gzip_stream(f)
                            if header_info is None:
                                continue

                            shape, tr = header_info

                            # Timepoints (4th dimension)
                            if len(shape) > 3:
                                total_timepoints += shape[3]

                            # TR distribution
                            if tr and tr > 0:
                                tr_rounded = round(tr, 3)
                                tr_distribution[tr_rounded] = tr_distribution.get(tr_rounded, 0) + 1

                    except NetworkError:
                        raise
                    except Exception as e:
                        logger.debug(f"Failed to read BOLD header from {bold_file}: {e}")
                        continue

        except Exception as e:
            logger.warning(f"Failed to access sourcedata {source_dir.name}: {e}")
            continue

    # Set results
    if total_timepoints > 0:
        result["bold_timepoints"] = total_timepoints

    if task_labels:
        result["bold_tasks"] = ",".join(sorted(task_labels))

    if tr_distribution:
        tr_dict = dict(sorted(tr_distribution.items()))
        result["bold_trs"] = json.dumps(tr_dict, separators=(",", ":"))

    return result


def _aggregate_from_hierarchical_files(study_path: Path) -> dict[str, Any]:
    """Aggregate study-level stats from hierarchical TSV files.

    Reads from sourcedata.tsv and aggregates to study level.
    This is much faster than direct extraction.

    Args:
        study_path: Path to study directory

    Returns:
        Dictionary with aggregated study-level statistics
    """
    sourcedata_tsv = study_path / "sourcedata" / "sourcedata.tsv"

    # Read sourcedata.tsv
    datasets_stats = []
    with open(sourcedata_tsv, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            # Convert numeric fields
            for key in [
                "subjects_num",
                "sessions_num",
                "sessions_min",
                "sessions_max",
                "bold_num",
                "t1w_num",
                "t2w_num",
                "bold_size",
                "t1w_size",
                "bold_size_max",
            ]:
                if row.get(key) and row[key] != "n/a":
                    row[key] = int(row[key])
            for key in [
                "bold_duration_total",
                "bold_duration_mean",
                "bold_voxels_total",
                "bold_voxels_mean",
            ]:
                if row.get(key) and row[key] != "n/a":
                    row[key] = float(row[key])
            datasets_stats.append(row)

    # Aggregate to study level (same logic as aggregate_to_study from bids_studies)
    if not datasets_stats:
        return {}

    # Sum across all datasets
    total_subjects = sum(
        d["subjects_num"] for d in datasets_stats if isinstance(d["subjects_num"], int)
    )
    total_bold_num = sum(d["bold_num"] for d in datasets_stats if isinstance(d["bold_num"], int))
    total_t1w_num = sum(d["t1w_num"] for d in datasets_stats if isinstance(d["t1w_num"], int))
    total_t2w_num = sum(d["t2w_num"] for d in datasets_stats if isinstance(d["t2w_num"], int))
    total_bold_size = sum(d["bold_size"] for d in datasets_stats if isinstance(d["bold_size"], int))
    total_t1w_size = sum(d["t1w_size"] for d in datasets_stats if isinstance(d["t1w_size"], int))

    # Session stats
    session_nums = [d["sessions_num"] for d in datasets_stats if d["sessions_num"] != "n/a"]
    session_mins = [d["sessions_min"] for d in datasets_stats if d["sessions_min"] != "n/a"]
    session_maxs = [d["sessions_max"] for d in datasets_stats if d["sessions_max"] != "n/a"]

    # Max bold size
    bold_size_maxs = [d["bold_size_max"] for d in datasets_stats if d["bold_size_max"] != "n/a"]

    # Duration and voxels (weighted by bold_num)
    total_duration = 0.0
    total_voxels = 0
    duration_weights = 0
    voxels_weights = 0

    for d in datasets_stats:
        if d["bold_duration_total"] != "n/a" and isinstance(d["bold_duration_total"], (int, float)):
            total_duration += d["bold_duration_total"]
            duration_weights += d["bold_num"]
        if d["bold_voxels_total"] != "n/a" and isinstance(d["bold_voxels_total"], (int, float)):
            total_voxels += int(d["bold_voxels_total"])
            voxels_weights += d["bold_num"]

    # Collect all datatypes
    all_datatypes = set()
    for d in datasets_stats:
        if d["datatypes"] and d["datatypes"] != "n/a":
            for dt in d["datatypes"].split(","):
                all_datatypes.add(dt)

    return {
        "subjects_num": total_subjects if total_subjects > 0 else "n/a",
        "sessions_num": sum(session_nums) if session_nums else "n/a",
        "sessions_min": min(session_mins) if session_mins else "n/a",
        "sessions_max": max(session_maxs) if session_maxs else "n/a",
        "bold_num": total_bold_num,
        "t1w_num": total_t1w_num,
        "t2w_num": total_t2w_num,
        "bold_size": total_bold_size if total_bold_size > 0 else "n/a",
        "t1w_size": total_t1w_size if total_t1w_size > 0 else "n/a",
        "bold_size_max": max(bold_size_maxs) if bold_size_maxs else "n/a",
        "bold_duration_total": total_duration if duration_weights > 0 else "n/a",
        "bold_voxels": total_voxels if voxels_weights > 0 else "n/a",
        "datatypes": ",".join(sorted(all_datatypes)) if all_datatypes else "n/a",
        # Note: bold_timepoints and bold_tasks still come from direct extraction
        # since they're not in the hierarchical TSV files currently
    }


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
            - "imaging": + BOLD imaging metadata (voxels, timepoints, tasks) via sparse access

    Returns:
        Dictionary with all extracted metadata
    """
    result = {}

    # Phase 1: Raw metadata (always)
    result.update(extract_raw_metadata(study_path))

    if stage in ("counts", "sizes", "imaging"):
        # Try reading from hierarchical TSV files first (FR-042f)
        # This is much faster than direct extraction
        sourcedata_tsv = study_path / "sourcedata" / "sourcedata.tsv"
        if sourcedata_tsv.exists():
            logger.debug(f"Reading from hierarchical TSV: {sourcedata_tsv}")
            result.update(_aggregate_from_hierarchical_files(study_path))

            # Still need to extract task/timepoints metadata (not in hierarchical TSV)
            if stage == "imaging":
                # Extract only BOLD tasks and timepoints (smaller subset)
                result.update(_extract_bold_tasks_and_timepoints(study_path))
        else:
            # Fall back to direct extraction (backwards compatibility)
            logger.debug(f"Hierarchical TSV not found, using direct extraction for {study_path.name}")
            # Phase 2: Directory counts
            result.update(extract_directory_summary(study_path))

            # Phase 3: File counts
            result.update(extract_file_counts(study_path))

            if stage in ("sizes", "imaging"):
                # Phase 4: File sizes
                result.update(extract_file_sizes(study_path))

            if stage == "imaging":
                # Phase 5: BOLD imaging metadata
                result.update(extract_bold_imaging_metadata(study_path))

    return result
