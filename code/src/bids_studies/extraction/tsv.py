"""TSV file utilities for hierarchical statistics."""

import csv
from pathlib import Path
from typing import Any

# Column definitions for subjects TSV files
SUBJECTS_COLUMNS = [
    "source_id",
    "subject_id",
    "session_id",
    "bold_num",
    "t1w_num",
    "t2w_num",
    "bold_size",
    "t1w_size",
    "bold_duration_total",
    "bold_duration_mean",
    "bold_voxels_total",
    "bold_voxels_mean",
    "datatypes",
]

# Column definitions for datasets TSV files
DATASETS_COLUMNS = [
    "source_id",
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
    "bold_duration_total",
    "bold_duration_mean",
    "bold_voxels_total",
    "bold_voxels_mean",
    "datatypes",
]


def _na(value: Any) -> str:
    """Convert value to string, using 'n/a' for None."""
    if value is None:
        return "n/a"
    return str(value)


def write_subjects_tsv(
    output_path: Path,
    subjects_stats: list[dict[str, Any]],
) -> None:
    """Write subjects statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        subjects_stats: List of per-subject statistics
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUBJECTS_COLUMNS, delimiter="\t")
        writer.writeheader()

        for stats in subjects_stats:
            row = {col: _na(stats.get(col)) for col in SUBJECTS_COLUMNS}
            writer.writerow(row)


def write_datasets_tsv(
    output_path: Path,
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write datasets statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        datasets_stats: List of per-dataset statistics
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DATASETS_COLUMNS, delimiter="\t")
        writer.writeheader()

        for stats in datasets_stats:
            row = {col: _na(stats.get(col)) for col in DATASETS_COLUMNS}
            writer.writerow(row)


def read_subjects_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read subjects statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-subject statistics dictionaries
    """
    results = []

    with open(input_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            # Convert numeric fields
            for key in ["bold_num", "t1w_num", "t2w_num", "bold_size", "t1w_size"]:
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
            results.append(row)

    return results


def read_datasets_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read datasets statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-dataset statistics dictionaries
    """
    results = []

    with open(input_path, newline="") as f:
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
            results.append(row)

    return results
