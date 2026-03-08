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
from typing import Any, Iterator

from datalad.distribution.dataset import Dataset

from openneuro_studies.metadata.derivative_extractor import (
    _extract_datalad_uuid,
    extract_derivative_metadata,
)

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
    "processed_raw_version",
    "current_raw_version",
    "uptodate",
    "outdatedness",
    "tasks_processed",
    "tasks_missing",
    "anat_processed",
    "func_processed",
    "processing_complete",
    "template_spaces",
    "transform_spaces",
    "descriptions",
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
    "processed_raw_version": {
        "Description": "Version/commit of the raw dataset that was processed (from dataset_description.json SourceDatasets)"
    },
    "current_raw_version": {
        "Description": "Current version/commit of the raw dataset (from git describe)"
    },
    "uptodate": {
        "Description": "Boolean indicating if processed_raw_version matches current_raw_version"
    },
    "outdatedness": {
        "Description": "Number of commits the processed raw version is behind current raw version, or 'n/a' if uptodate"
    },
    "tasks_processed": {
        "Description": "Comma-separated list of task labels found in derivative func/ outputs, or 'n/a'"
    },
    "tasks_missing": {
        "Description": "Comma-separated list of tasks present in raw but missing from derivative, or 'n/a'"
    },
    "anat_processed": {
        "Description": "Boolean indicating if anatomical data was processed (any _desc- entity found in anat/)"
    },
    "func_processed": {
        "Description": "Boolean indicating if functional data was processed (BOLD outputs found in func/)"
    },
    "processing_complete": {
        "Description": "Boolean indicating if all raw data was processed (no missing tasks, anat processed, func processed)"
    },
    "template_spaces": {
        "Description": "Comma-separated list of template space labels (_space- entity) in data files (excluding transforms)"
    },
    "transform_spaces": {
        "Description": "Comma-separated list of space labels found ONLY in transforms (not in data files)"
    },
    "descriptions": {
        "Description": "JSON dictionary with counts of each _desc- entity (e.g., {\"preproc\":180,\"brain\":40,\"confounds\":60})"
    },
}


def _iter_derivative_subdatasets(study_path: Path) -> Iterator[tuple[str, Path]]:
    """Iterate over derivative subdatasets in a study.

    Yields:
        Tuple of (derivative_id, derivative_path) for each derivative
    """
    parent_ds = Dataset(str(study_path))
    if not parent_ds.is_installed():
        return

    try:
        subdatasets = list(parent_ds.subdatasets(result_renderer='disabled'))
        for sd in subdatasets:
            sd_path = Path(sd['path'])
            # Filter for derivatives subdatasets
            if 'derivatives' in sd_path.parts:
                derivative_id = sd_path.name
                yield derivative_id, sd_path
    except Exception as e:
        logger.warning(f"Failed to list derivative subdatasets of {study_path}: {e}")


def _ensure_derivative_installed(derivative_path: Path, study_path: Path) -> bool:
    """Install a derivative subdataset if not already installed.

    Args:
        derivative_path: Path to derivative subdataset (can be absolute or relative)
        study_path: Parent study path (can be absolute or relative)

    Returns:
        True if newly installed, False if already installed
    """
    ds = Dataset(str(derivative_path))
    if ds.is_installed():
        return False

    # Install using parent dataset's get method
    # DataLad needs path relative to the parent dataset
    parent_ds = Dataset(str(study_path))
    try:
        # Compute relative path from study to derivative
        # derivative_path might be study-ds006131/derivatives/fMRIPrep-24.1.1
        # We need just "derivatives/fMRIPrep-24.1.1"
        if derivative_path.is_absolute():
            abs_study = study_path.resolve()
            abs_deriv = derivative_path.resolve()
            rel_path = abs_deriv.relative_to(abs_study)
        else:
            # For relative paths, make them relative to study_path
            rel_path = derivative_path.relative_to(study_path)

        parent_ds.get(str(rel_path), get_data=False, result_renderer='disabled')
        logger.info(f"Installed derivative subdataset: {derivative_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to install derivative {derivative_path}: {e}")
        raise


def _drop_derivative(derivative_path: Path, study_path: Path) -> None:
    """Drop (uninstall) a derivative subdataset.

    Args:
        derivative_path: Path to derivative subdataset (can be absolute or relative)
        study_path: Parent study path (can be absolute or relative)
    """
    parent_ds = Dataset(str(study_path))
    try:
        # Compute relative path from study to derivative
        if derivative_path.is_absolute():
            abs_study = study_path.resolve()
            abs_deriv = derivative_path.resolve()
            rel_path = abs_deriv.relative_to(abs_study)
        else:
            rel_path = derivative_path.relative_to(study_path)

        parent_ds.drop(str(rel_path), what='datasets',
                      reckless='kill', recursive=True, result_renderer='disabled')
        logger.info(f"Dropped derivative subdataset: {derivative_path}")
    except Exception as e:
        logger.warning(f"Failed to drop derivative {derivative_path}: {e}")
        raise


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
    """Collect derivative metadata for a study with temporary subdataset installation.

    Args:
        study_path: Path to study directory

    Returns:
        List of derivative metadata dictionaries
    """
    study_id = study_path.name
    gitmodules_path = study_path / ".gitmodules"
    submodules = _parse_gitmodules(gitmodules_path)

    # Get raw dataset path (sourcedata subdataset)
    raw_path = None
    for _name, config in submodules.items():
        path = config.get("path", "")
        if path.startswith("sourcedata/"):
            raw_path = study_path / path
            break

    derivatives = []
    for _name, config in submodules.items():
        path = config.get("path", "")
        url = config.get("url", "")
        datalad_id_from_gitmodules = config.get("datalad-id", "n/a")

        # Only include derivatives
        if not path.startswith("derivatives/"):
            continue

        deriv_dir = path.split("/")[-1]
        tool_name, tool_version = _parse_derivative_name(deriv_dir)
        derivative_path = study_path / path

        # Basic metadata (always available from .gitmodules)
        deriv_metadata = {
            "study_id": study_id,
            "derivative_id": deriv_dir,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "datalad_uuid": datalad_id_from_gitmodules,  # Will be updated after installation
            "url": url,
        }

        # Extract additional metadata with temporary installation
        try:
            # Track if we install it
            newly_installed = _ensure_derivative_installed(derivative_path, study_path)

            # Extract DataLad UUID from .datalad/config (more reliable than .gitmodules)
            # This must happen AFTER installation when .datalad/config is available
            datalad_uuid = _extract_datalad_uuid(derivative_path)
            if datalad_uuid != "n/a":
                deriv_metadata["datalad_uuid"] = datalad_uuid
            # else keep the .gitmodules value we already set

            # Also ensure raw dataset is installed if needed
            raw_newly_installed = False
            if raw_path:
                raw_newly_installed = _ensure_derivative_installed(raw_path, study_path)

            # Extract metadata
            extracted = extract_derivative_metadata(derivative_path, raw_path)
            deriv_metadata.update(extracted)

            # Clean up: drop if we installed it
            if newly_installed:
                _drop_derivative(derivative_path, study_path)
            if raw_newly_installed:
                _drop_derivative(raw_path, study_path)

        except Exception as e:
            logger.warning(
                f"Failed to extract metadata for {deriv_dir}: {e}. "
                f"Using n/a values."
            )
            # Fill with n/a values for all extracted columns
            deriv_metadata.update({
                "size_total": "n/a",
                "size_annexed": "n/a",
                "file_count": "n/a",
                "processed_raw_version": "n/a",
                "current_raw_version": "n/a",
                "uptodate": "n/a",
                "outdatedness": "n/a",
                "tasks_processed": "n/a",
                "tasks_missing": "n/a",
                "anat_processed": False,
                "func_processed": False,
                "processing_complete": False,
                "template_spaces": "n/a",
                "transform_spaces": "n/a",
                "descriptions": "n/a",
            })

        derivatives.append(deriv_metadata)

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

    # Write TSV manually to avoid CSV escaping of JSON strings
    # Using csv.writer with QUOTE_NONE would escape quotes in JSON, creating "\{\"key\":\"value\"\}"
    # Instead, write raw tab-separated values
    with open(output_path, "w", newline="") as f:
        # Write header
        f.write("\t".join(STUDIES_DERIVATIVES_COLUMNS) + "\n")

        # Write rows
        for row in rows:
            # Convert each field to string, replacing None with empty string
            fields = [str(row.get(col, "")) if row.get(col) is not None else "" for col in STUDIES_DERIVATIVES_COLUMNS]
            f.write("\t".join(fields) + "\n")

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
