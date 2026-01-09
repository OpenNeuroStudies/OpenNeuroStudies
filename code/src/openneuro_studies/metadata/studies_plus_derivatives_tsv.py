"""Generate studies+derivatives.tsv and studies+derivatives.json.

Implements FR-010 and FR-011:
- FR-010: Generate studies+derivatives.tsv (tall format) with study-derivative pairs
- FR-011: Generate studies+derivatives.json describing column purposes

Note: The '+' naming convention follows BIDS issue #2273 for TSV files
with compound primary keys (e.g., study_id + derivative_id).
See: https://github.com/bids-standard/bids-specification/issues/2273

As this naming convention is not yet part of the BIDS standard,
studies+derivatives.tsv must be listed in .bidsignore.
"""

import configparser
import csv
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Column definitions for studies+derivatives.tsv (FR-010)
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
    "tool_name": {"Description": "Name of the processing tool/pipeline"},
    "tool_version": {"Description": "Version of the processing tool"},
    "datalad_uuid": {"Description": "DataLad dataset UUID for disambiguation, or 'n/a'"},
    "url": {"Description": "Git URL of the derivative dataset"},
    "size_total": {"Description": "Total size of the derivative dataset in bytes"},
    "size_annexed": {"Description": "Size of annexed (large) files in bytes"},
    "file_count": {"Description": "Number of files in the derivative dataset"},
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
    for _name, config in submodules.items():
        path = config.get("path", "")
        url = config.get("url", "")
        datalad_id = config.get("datalad-id", "n/a")

        # Only include derivatives
        if not path.startswith("derivatives/"):
            continue

        deriv_dir = path.split("/")[-1]
        tool_name, tool_version = _parse_derivative_name(deriv_dir)

        derivatives.append(
            {
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
            }
        )

    return derivatives


def _load_existing_derivatives(output_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load existing studies+derivatives.tsv entries indexed by (study_id, derivative_id).

    Args:
        output_path: Path to existing studies+derivatives.tsv

    Returns:
        Dictionary mapping (study_id, derivative_id) to row data
    """
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    if output_path.exists():
        with open(output_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                key = (row.get("study_id", ""), row.get("derivative_id", ""))
                if key[0] and key[1]:
                    existing[key] = dict(row)
    return existing


def generate_studies_derivatives_tsv(
    studies: list[Path],
    output_path: Path,
) -> Path:
    """Generate studies+derivatives.tsv from list of study directories.

    This function implements FR-012a: when updating specific studies,
    existing entries for other studies are preserved. New/updated entries
    are merged with existing data rather than replacing the entire file.

    Note: Output filename should be studies+derivatives.tsv per BIDS #2273.

    Args:
        studies: List of study directory paths
        output_path: Path to output studies+derivatives.tsv

    Returns:
        Path to generated file
    """
    # Load existing entries (FR-012a: preserve unmodified studies)
    existing = _load_existing_derivatives(output_path)

    # Track which studies are being updated
    updated_study_ids: set[str] = set()

    for study_path in studies:
        try:
            study_id = study_path.name
            updated_study_ids.add(study_id)

            # Remove old entries for this study (will be replaced)
            keys_to_remove = [k for k in existing if k[0] == study_id]
            for key in keys_to_remove:
                del existing[key]

            # Add new entries
            derivatives = collect_derivatives_for_study(study_path)
            for deriv in derivatives:
                key = (deriv["study_id"], deriv["derivative_id"])
                existing[key] = deriv

        except Exception as e:
            logger.warning(f"Failed to collect derivatives for {study_path.name}: {e}")

    # Sort by study_id, then derivative_id
    rows = [existing[k] for k in sorted(existing.keys())]

    # Write TSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STUDIES_DERIVATIVES_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    preserved_count = len([k for k in existing if k[0] not in updated_study_ids])
    logger.info(
        f"Generated {output_path} with {len(rows)} derivative entries "
        f"({len(updated_study_ids)} studies updated, {preserved_count} entries preserved)"
    )
    return output_path


def generate_studies_derivatives_json(output_path: Path) -> Path:
    """Generate studies+derivatives.json sidecar.

    Note: Output filename should be studies+derivatives.json per BIDS #2273.

    Args:
        output_path: Path to output studies+derivatives.json

    Returns:
        Path to generated file
    """
    with open(output_path, "w") as f:
        json.dump(STUDIES_DERIVATIVES_JSON, f, indent=2)
        f.write("\n")

    logger.info(f"Generated {output_path}")
    return output_path
