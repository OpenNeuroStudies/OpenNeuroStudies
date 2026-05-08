"""TSV file utilities for hierarchical statistics.

All TSV writing uses manual tab-separated output (not csv.DictWriter) to avoid
CSV escaping artifacts per FR-HE-080. Values are never quoted or escaped.
"""

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


def _na(value: Any) -> str:
    """Convert value to string, using 'n/a' for None."""
    if value is None:
        return "n/a"
    return str(value)


def _write_tsv(
    output_path: Path,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Write rows to a TSV file using manual tab-separated output.

    Uses raw string formatting (not csv.DictWriter) to prevent CSV escaping
    of values like JSON fields. See FR-HE-080.

    Args:
        output_path: Path to output TSV file
        columns: List of column names (header)
        rows: List of row dictionaries
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        # Write header
        f.write("\t".join(columns) + "\n")
        # Write rows
        for row in rows:
            fields = [_na(row.get(col)) for col in columns]
            f.write("\t".join(fields) + "\n")


def _read_tsv(input_path: Path) -> list[dict[str, str]]:
    """Read rows from a TSV file using manual parsing.

    Uses raw string splitting (not csv.DictReader) for consistency with
    the manual write approach. See FR-HE-080.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of row dictionaries with string values
    """
    results = []

    with open(input_path) as f:
        header_line = f.readline().rstrip("\n")
        if not header_line:
            return results
        columns = header_line.split("\t")

        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            values = line.split("\t")
            # Pad with empty strings if fewer values than columns
            while len(values) < len(columns):
                values.append("")
            row = dict(zip(columns, values))
            results.append(row)

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
    _write_tsv(output_path, SUBJECTS_COLUMNS, subjects_stats)


def write_datasets_tsv(
    output_path: Path,
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write datasets statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        datasets_stats: List of per-dataset statistics
    """
    _write_tsv(output_path, DATASETS_COLUMNS, datasets_stats)


def read_subjects_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read subjects statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-subject statistics dictionaries
    """
    raw_rows = _read_tsv(input_path)
    results: list[dict[str, Any]] = []

    for row in raw_rows:
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
    raw_rows = _read_tsv(input_path)
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
    _write_tsv(output_path, DERIVATIVE_SUBJECTS_COLUMNS, subjects_stats)


def write_derivative_datasets_tsv(
    output_path: Path,
    datasets_stats: list[dict[str, Any]],
) -> None:
    """Write derivative datasets statistics to TSV file.

    Args:
        output_path: Path to output TSV file
        datasets_stats: List of per-dataset derivative statistics
    """
    _write_tsv(output_path, DERIVATIVE_DATASETS_COLUMNS, datasets_stats)


def read_derivative_subjects_tsv(input_path: Path) -> list[dict[str, Any]]:
    """Read derivative subjects statistics from TSV file.

    Args:
        input_path: Path to input TSV file

    Returns:
        List of per-subject derivative statistics dictionaries
    """
    raw_rows = _read_tsv(input_path)
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
    raw_rows = _read_tsv(input_path)
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
