"""TSV file utilities for hierarchical statistics.

Centralized TSV I/O for both bids_studies and openneuro_studies (FR-042j).
Write uses manual tab-join with sanitization to keep JSON fields unquoted
(e.g., {"2.0":48} not "{""2.0"": 48}"). Read uses csv.DictReader which
handles both quoted and unquoted TSV fields correctly.
"""

import csv
import json
from collections.abc import Mapping
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
    "bold_tasks",
    "bold_timepoints",
    "bold_trs",
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
    "bold_tasks",
    "bold_timepoints",
    "bold_trs",
    "datatypes",
]

# Column definitions for derivative subjects TSV files
DERIVATIVE_SUBJECTS_COLUMNS = [
    "source_id",
    "derivative_id",
    "subject_id",
    "session_id",
    "output_num",
    "output_size",
    "nifti_num",
    "nifti_size",
    "html_num",
]

# Column definitions for derivative datasets TSV files
DERIVATIVE_DATASETS_COLUMNS = [
    "source_id",
    "derivative_id",
    "subjects_num",
    "sessions_num",
    "output_num",
    "output_size",
    "nifti_num",
    "nifti_size",
    "html_num",
]


def compact_json(d: Mapping) -> str:
    """Serialize a dict to compact JSON for TSV storage.

    Sorts keys for deterministic output and uses compact separators
    (no spaces) to keep TSV fields readable without quoting.

    Example: {2.0: 48, 0.75: 413} → '{"0.75":413,"2.0":48}'
    """
    return json.dumps(dict(sorted(d.items())), separators=(",", ":"))


def _na(value: Any) -> str:
    """Convert value to string, using 'n/a' for None."""
    if value is None:
        return "n/a"
    return str(value)


def _sanitize_tsv(value: str) -> str:
    """Sanitize a value for TSV output.

    Replaces characters that would break TSV parsing:
    - tab → space (field delimiter)
    - newline → space (row delimiter)
    - carriage return → removed
    """
    return value.replace("\t", " ").replace("\n", " ").replace("\r", "")


def write_tsv(
    output_path: Path,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Write rows to a TSV file (FR-042j).

    Uses manual tab-join so JSON fields remain unquoted (e.g., {"2.0":48}).
    Values are sanitized to replace tab/newline characters that would break
    TSV parsing.

    Args:
        output_path: Path to output TSV file
        columns: List of column names (header)
        rows: List of row dictionaries
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("\t".join(columns) + "\n")
        for row in rows:
            values = [_sanitize_tsv(_na(row.get(col))) for col in columns]
            f.write("\t".join(values) + "\n")


def read_tsv(input_path: Path) -> list[dict[str, str]]:
    """Read rows from a TSV file using csv.DictReader (FR-042j).

    Args:
        input_path: Path to input TSV file

    Returns:
        List of row dictionaries with string values
    """
    results = []

    with open(input_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(dict(row))

    return results


def write_subjects_tsv(
    output_path: Path,
    subjects_stats: list[dict[str, Any]],
) -> None:
    """Write subjects statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        subjects_stats: List of per-subject statistics
    """
    write_tsv(output_path, SUBJECTS_COLUMNS, subjects_stats)


def write_datasets_tsv(
    output_path: Path,
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write datasets statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        datasets_stats: List of per-dataset statistics
    """
    write_tsv(output_path, DATASETS_COLUMNS, datasets_stats)


def read_subjects_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read subjects statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-subject statistics dictionaries
    """
    raw_rows = read_tsv(input_path)
    results: list[dict[str, Any]] = []

    for row in raw_rows:
        # Convert numeric fields
        for key in ["bold_num", "t1w_num", "t2w_num", "bold_size", "t1w_size",
                     "bold_timepoints"]:
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
    raw_rows = read_tsv(input_path)
    results: list[dict[str, Any]] = []

    for row in raw_rows:
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
            "bold_timepoints",
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


def write_derivative_subjects_tsv(
    output_path: Path,
    subjects_stats: list[dict[str, Any]],
) -> None:
    """Write derivative subjects statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        subjects_stats: List of per-subject derivative statistics
    """
    write_tsv(output_path, DERIVATIVE_SUBJECTS_COLUMNS, subjects_stats)


def write_derivative_datasets_tsv(
    output_path: Path,
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write derivative datasets statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        datasets_stats: List of per-dataset derivative statistics
    """
    write_tsv(output_path, DERIVATIVE_DATASETS_COLUMNS, datasets_stats)


def read_derivative_subjects_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read derivative subjects statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-subject derivative statistics dictionaries
    """
    raw_rows = read_tsv(input_path)
    results: list[dict[str, Any]] = []

    for row in raw_rows:
        # Convert numeric fields
        for key in ["output_num", "output_size", "nifti_num", "nifti_size", "html_num"]:
            if row.get(key) and row[key] != "n/a":
                row[key] = int(row[key])
        results.append(row)

    return results


def read_derivative_datasets_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read derivative datasets statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-dataset derivative statistics dictionaries
    """
    raw_rows = read_tsv(input_path)
    results: list[dict[str, Any]] = []

    for row in raw_rows:
        # Convert numeric fields
        for key in [
            "subjects_num",
            "sessions_num",
            "output_num",
            "output_size",
            "nifti_num",
            "nifti_size",
            "html_num",
        ]:
            if row.get(key) and row[key] != "n/a":
                row[key] = int(row[key])
        results.append(row)

    return results
