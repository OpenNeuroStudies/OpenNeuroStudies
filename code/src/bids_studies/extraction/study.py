"""Study-level aggregation from dataset statistics.

Aggregates dataset-level stats to study level for inclusion
in study metadata files.
"""

import logging
from pathlib import Path
from typing import Any

from bids_studies.extraction.dataset import aggregate_to_dataset
from bids_studies.extraction.derivative import (
    aggregate_derivative_to_dataset,
    extract_derivative_subjects_stats,
)
from bids_studies.extraction.subject import extract_subjects_stats
from bids_studies.extraction.tsv import (
    write_datasets_tsv,
    write_derivative_datasets_tsv,
    write_derivative_subjects_tsv,
    write_subjects_tsv,
)
from bids_studies.schemas import get_schema_path

logger = logging.getLogger(__name__)


def aggregate_to_study(
    datasets_stats: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate dataset-level stats to study level.

    Args:
        datasets_stats: List of per-dataset statistics

    Returns:
        Study-level aggregated statistics
    """
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
        "bold_duration_mean": (
            total_duration / duration_weights if duration_weights > 0 else "n/a"
        ),
        "bold_voxels_total": total_voxels if voxels_weights > 0 else "n/a",
        "bold_voxels_mean": (total_voxels / voxels_weights if voxels_weights > 0 else "n/a"),
        "datatypes": ",".join(sorted(all_datatypes)) if all_datatypes else "n/a",
    }


def extract_study_stats(
    study_path: Path,
    sourcedata_subdir: str = "sourcedata",
    include_imaging: bool = True,  # Changed to True to enable BOLD statistics
    write_files: bool = True,
) -> dict[str, Any]:
    """Extract hierarchical stats for a study.

    Extracts per-subject stats, aggregates to per-dataset, then to study level.
    Optionally writes intermediate TSV files.

    Args:
        study_path: Path to study directory
        sourcedata_subdir: Name of sourcedata subdirectory
        include_imaging: Whether to extract voxel/duration metrics
        write_files: Whether to write TSV files

    Returns:
        Dictionary with aggregated study-level statistics
    """
    sourcedata_path = study_path / sourcedata_subdir
    if not sourcedata_path.exists():
        return {}

    # Find all source datasets
    source_dirs = [
        d for d in sourcedata_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    if not source_dirs:
        return {}

    # Extract per-subject stats for all sources
    all_subjects_stats = []
    datasets_stats = []
    all_extraction_errors = []

    for source_dir in source_dirs:
        source_id = source_dir.name

        # Extract subjects (returns tuple: results, errors)
        try:
            subjects_stats, errors = extract_subjects_stats(source_dir, source_id, include_imaging)
            all_subjects_stats.extend(subjects_stats)
            all_extraction_errors.extend(errors)

            # Aggregate to dataset level
            dataset_stats = aggregate_to_dataset(subjects_stats, source_id)
            datasets_stats.append(dataset_stats)
        except RuntimeError as e:
            # Extraction failed for this dataset - log and continue
            logger.error(f"Extraction failed for {source_id}: {e}")
            all_extraction_errors.append(f"{source_id}: {e}")
            # Continue with other datasets rather than failing completely

    # Report extraction errors if any
    if all_extraction_errors:
        logger.error(
            f"Study extraction completed with {len(all_extraction_errors)} errors. "
            f"First 5 errors:\n" + "\n".join(all_extraction_errors[:5])
        )
        # Write errors to file
        errors_file = sourcedata_path / "extraction_errors.log"
        try:
            with open(errors_file, "w") as f:
                f.write(f"Extraction Errors ({len(all_extraction_errors)} total)\n")
                f.write("=" * 60 + "\n\n")
                for error in all_extraction_errors:
                    f.write(f"{error}\n")
            logger.error(f"Full error log written to: {errors_file}")
        except Exception as e:
            logger.warning(f"Failed to write error log: {e}")

    # Write TSV files
    if write_files and all_subjects_stats:
        _write_sourcedata_files(sourcedata_path, all_subjects_stats, datasets_stats)

    # Aggregate to study level
    study_stats = aggregate_to_study(datasets_stats)

    # Fail if no data was extracted (complete failure)
    if not datasets_stats and all_extraction_errors:
        raise RuntimeError(
            f"Study extraction completely failed: {len(all_extraction_errors)} errors, "
            f"no datasets extracted successfully"
        )

    return study_stats


def _write_sourcedata_files(
    sourcedata_path: Path,
    subjects_stats: list[dict[str, Any]],
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write sourcedata TSV and JSON files.

    Args:
        sourcedata_path: Path to sourcedata directory
        subjects_stats: Per-subject statistics
        datasets_stats: Per-dataset statistics
    """
    import shutil

    # Check if multi-session
    has_sessions = any(s["session_id"] != "n/a" for s in subjects_stats)

    if has_sessions:
        subjects_tsv = sourcedata_path / "sourcedata+subjects+sessions.tsv"
    else:
        subjects_tsv = sourcedata_path / "sourcedata+subjects.tsv"

    write_subjects_tsv(subjects_tsv, subjects_stats)
    logger.info(f"Wrote {len(subjects_stats)} rows to {subjects_tsv}")

    # Copy JSON sidecar
    schema_path = get_schema_path("sourcedata+subjects")
    if schema_path.exists():
        json_path = subjects_tsv.with_suffix(".json")
        shutil.copy(schema_path, json_path)

    if datasets_stats:
        datasets_tsv = sourcedata_path / "sourcedata.tsv"
        write_datasets_tsv(datasets_tsv, datasets_stats)
        logger.info(f"Wrote {len(datasets_stats)} rows to {datasets_tsv}")

        # Copy JSON sidecar
        schema_path = get_schema_path("sourcedata")
        if schema_path.exists():
            json_path = datasets_tsv.with_suffix(".json")
            shutil.copy(schema_path, json_path)


def extract_derivative_stats(
    derivative_path: Path,
    source_id: str,
    derivative_id: str,
    write_files: bool = True,
) -> dict[str, Any]:
    """Extract hierarchical stats for a single derivative.

    Extracts per-subject derivative stats and aggregates to dataset level.
    Optionally writes intermediate TSV files.

    Args:
        derivative_path: Path to derivative directory
        source_id: Source dataset ID (e.g., "ds000001")
        derivative_id: Derivative ID (e.g., "mriqc-25.0.0")
        write_files: Whether to write TSV files

    Returns:
        Dictionary with aggregated derivative dataset-level statistics
    """
    if not derivative_path.exists():
        return {}

    # Extract per-subject derivative stats
    subjects_stats = extract_derivative_subjects_stats(
        derivative_path, source_id, derivative_id
    )

    if not subjects_stats:
        return {}

    # Aggregate to dataset level
    dataset_stats = aggregate_derivative_to_dataset(
        subjects_stats, source_id, derivative_id
    )

    # Write TSV files
    if write_files:
        _write_derivative_files(derivative_path, subjects_stats, [dataset_stats])

    return dataset_stats


def _write_derivative_files(
    derivative_path: Path,
    subjects_stats: list[dict[str, Any]],
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write derivative TSV and JSON files.

    Args:
        derivative_path: Path to derivative directory
        subjects_stats: Per-subject derivative statistics
        datasets_stats: Per-dataset derivative statistics
    """
    import shutil

    # Check if multi-session
    has_sessions = any(s["session_id"] != "n/a" for s in subjects_stats)

    if has_sessions:
        subjects_tsv = derivative_path / "derivatives+subjects+sessions.tsv"
    else:
        subjects_tsv = derivative_path / "derivatives+subjects.tsv"

    write_derivative_subjects_tsv(subjects_tsv, subjects_stats)
    logger.info(f"Wrote {len(subjects_stats)} rows to {subjects_tsv}")

    # Copy JSON sidecar
    schema_path = get_schema_path("derivatives+subjects")
    if schema_path.exists():
        json_path = subjects_tsv.with_suffix(".json")
        shutil.copy(schema_path, json_path)

    if datasets_stats:
        datasets_tsv = derivative_path / "derivatives+datasets.tsv"
        write_derivative_datasets_tsv(datasets_tsv, datasets_stats)
        logger.info(f"Wrote {len(datasets_stats)} rows to {datasets_tsv}")

        # Copy JSON sidecar
        schema_path = get_schema_path("derivatives+datasets")
        if schema_path.exists():
            json_path = datasets_tsv.with_suffix(".json")
            shutil.copy(schema_path, json_path)
