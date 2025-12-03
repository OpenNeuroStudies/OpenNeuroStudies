"""Generate studies_derivatives.tsv and studies_derivatives.json.

Implements FR-010 and FR-011:
- FR-010: Generate studies_derivatives.tsv (tall format) with study-derivative pairs
- FR-011: Generate studies_derivatives.json describing column purposes
"""

import configparser
import csv
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Column definitions for studies_derivatives.tsv (FR-010)
STUDIES_DERIVATIVES_COLUMNS = [
    "study_id",
    "derivative_id",
    "tool_name",
    "tool_version",
    "datalad_uuid",
    "url",
    "size_total",
    "size_annexed",
    "file_count",
    "outdatedness",
    "processed_raw_version",
]

# JSON sidecar descriptions (FR-011)
STUDIES_DERIVATIVES_JSON = {
    "study_id": {
        "Description": "Unique identifier for the study dataset containing this derivative"
    },
    "derivative_id": {
        "Description": "Identifier for the derivative directory (e.g., fMRIPrep-24.1.1)"
    },
    "tool_name": {
        "Description": "Name of the processing tool/pipeline"
    },
    "tool_version": {
        "Description": "Version of the processing tool"
    },
    "datalad_uuid": {
        "Description": "DataLad dataset UUID for disambiguation, or 'n/a'"
    },
    "url": {
        "Description": "Git URL of the derivative dataset"
    },
    "size_total": {
        "Description": "Total size of the derivative dataset in bytes"
    },
    "size_annexed": {
        "Description": "Size of annexed (large) files in bytes"
    },
    "file_count": {
        "Description": "Number of files in the derivative dataset"
    },
    "outdatedness": {
        "Description": "Number of commits the processed raw version is behind current raw version"
    },
    "processed_raw_version": {
        "Description": "Version/commit of the raw dataset that was processed"
    },
}


def _parse_gitmodules(gitmodules_path: Path) -> dict[str, dict[str, str]]:
    """Parse .gitmodules file into a dictionary."""
    if not gitmodules_path.exists():
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    result = {}
    for section in config.sections():
        if section.startswith('submodule "'):
            name = section[11:-1]
            result[name] = dict(config[section])

    return result


def _parse_derivative_name(deriv_dir: str) -> tuple[str, str]:
    """Parse derivative directory name into tool name and version.

    Args:
        deriv_dir: Derivative directory name (e.g., "fMRIPrep-24.1.1")

    Returns:
        Tuple of (tool_name, version)
    """
    # Handle custom-{dataset_id} format
    if deriv_dir.startswith("custom-"):
        return "custom", deriv_dir[7:]

    # Standard format: {tool_name}-{version}
    # Find the last hyphen followed by a digit (version likely starts there)
    parts = deriv_dir.rsplit("-", 1)
    if len(parts) == 2 and parts[1] and parts[1][0].isdigit():
        return parts[0], parts[1]

    # Fallback: try splitting on first hyphen
    parts = deriv_dir.split("-", 1)
    if len(parts) == 2:
        return parts[0], parts[1]

    return deriv_dir, "unknown"


def collect_derivatives_for_study(study_path: Path) -> list[dict[str, Any]]:
    """Collect derivative metadata for a study.

    Args:
        study_path: Path to study directory

    Returns:
        List of derivative metadata dictionaries
    """
    study_id = study_path.name
    gitmodules_path = study_path / ".gitmodules"
    submodules = _parse_gitmodules(gitmodules_path)

    derivatives = []
    for name, config in submodules.items():
        path = config.get("path", "")
        url = config.get("url", "")
        datalad_id = config.get("datalad-id", "n/a")

        # Only include derivatives
        if not path.startswith("derivatives/"):
            continue

        deriv_dir = path.split("/")[-1]
        tool_name, tool_version = _parse_derivative_name(deriv_dir)

        derivatives.append({
            "study_id": study_id,
            "derivative_id": deriv_dir,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "datalad_uuid": datalad_id,
            "url": url,
            "size_total": "n/a",  # TODO: Get from git-annex info
            "size_annexed": "n/a",
            "file_count": "n/a",
            "outdatedness": "n/a",  # TODO: Implement (FR-028-030)
            "processed_raw_version": "n/a",  # TODO: Implement
        })

    return derivatives


def generate_studies_derivatives_tsv(
    studies: list[Path],
    output_path: Path,
) -> Path:
    """Generate studies_derivatives.tsv from list of study directories.

    Args:
        studies: List of study directory paths
        output_path: Path to output studies_derivatives.tsv

    Returns:
        Path to generated file
    """
    rows = []
    for study_path in sorted(studies, key=lambda p: p.name):
        try:
            derivatives = collect_derivatives_for_study(study_path)
            rows.extend(derivatives)
        except Exception as e:
            logger.warning(f"Failed to collect derivatives for {study_path.name}: {e}")

    # Sort by study_id, then derivative_id
    rows.sort(key=lambda r: (r["study_id"], r["derivative_id"]))

    # Write TSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STUDIES_DERIVATIVES_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Generated {output_path} with {len(rows)} derivative entries")
    return output_path


def generate_studies_derivatives_json(output_path: Path) -> Path:
    """Generate studies_derivatives.json sidecar.

    Args:
        output_path: Path to output studies_derivatives.json

    Returns:
        Path to generated file
    """
    with open(output_path, "w") as f:
        json.dump(STUDIES_DERIVATIVES_JSON, f, indent=2)
        f.write("\n")

    logger.info(f"Generated {output_path}")
    return output_path
