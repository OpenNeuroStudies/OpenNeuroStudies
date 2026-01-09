"""Generate studies.tsv and studies.json for the repository.

Implements FR-009 and FR-011:
- FR-009: Generate studies.tsv with all required columns
- FR-011: Generate studies.json describing column purposes
"""

import configparser
import csv
import json
import logging
from pathlib import Path
from typing import Any

from openneuro_studies.metadata.summary_extractor import extract_all_summaries

logger = logging.getLogger(__name__)

# Column definitions for studies.tsv (FR-009)
STUDIES_COLUMNS = [
    "study_id",
    "name",
    "version",
    "raw_version",
    "bids_version",
    "hed_version",
    "license",
    "authors",
    "author_lead_raw",
    "author_senior_raw",
    "source_count",
    "source_types",
    "derivative_count",
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
    "bold_voxels",
    "datatypes",
    "derivative_ids",
    "bids_valid",
]

# JSON sidecar descriptions (FR-011)
STUDIES_JSON = {
    "study_id": {"Description": "Unique identifier for the study dataset (e.g., study-ds000001)"},
    "name": {"Description": "Human-readable name of the study dataset"},
    "version": {"Description": "Version of the study dataset"},
    "raw_version": {
        "Description": "Version/tag of the raw source dataset, or 'n/a' if multiple sources or no release"
    },
    "bids_version": {"Description": "BIDS specification version used by the study"},
    "hed_version": {"Description": "HED schema version if applicable, or 'n/a'"},
    "license": {"Description": "License for the study dataset"},
    "authors": {"Description": "Authors of the study dataset from git shortlog"},
    "author_lead_raw": {
        "Description": "First author from raw dataset's Authors field, or 'n/a' if multiple conflicting sources"
    },
    "author_senior_raw": {
        "Description": "Last author from raw dataset's Authors field, or 'n/a' if multiple conflicting sources"
    },
    "source_count": {"Description": "Number of sourcedata subdatasets"},
    "source_types": {
        "Description": "Comma-separated set of BIDS DatasetTypes from source datasets (e.g., 'raw', 'derivative', 'raw,derivative')"
    },
    "derivative_count": {"Description": "Number of derivative subdatasets"},
    "subjects_num": {"Description": "Number of subjects in the raw dataset"},
    "sessions_num": {"Description": "Total number of sessions across all subjects"},
    "sessions_min": {"Description": "Minimum number of sessions per subject"},
    "sessions_max": {"Description": "Maximum number of sessions per subject"},
    "bold_num": {"Description": "Number of BOLD fMRI files"},
    "t1w_num": {"Description": "Number of T1-weighted structural files"},
    "t2w_num": {"Description": "Number of T2-weighted structural files"},
    "bold_size": {"Description": "Total size of BOLD files in bytes"},
    "t1w_size": {"Description": "Total size of T1w files in bytes"},
    "bold_size_max": {"Description": "Size of largest BOLD file in bytes"},
    "bold_voxels": {"Description": "Total number of voxels across all BOLD files"},
    "datatypes": {
        "Description": "Comma-separated list of BIDS datatypes present (e.g., 'anat,func,dwi')"
    },
    "derivative_ids": {"Description": "Comma-separated list of derivative identifiers"},
    "bids_valid": {
        "Description": "BIDS validation status: 'valid', 'warnings', 'errors', or 'n/a'"
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


def _count_submodules(study_path: Path) -> tuple[int, int, list[str]]:
    """Count source and derivative submodules.

    Args:
        study_path: Path to study directory

    Returns:
        Tuple of (source_count, derivative_count, derivative_ids)
    """
    gitmodules_path = study_path / ".gitmodules"
    submodules = _parse_gitmodules(gitmodules_path)

    # Track unique paths to handle duplicate submodule entries
    source_paths: set[str] = set()
    derivative_paths: set[str] = set()
    derivative_ids: list[str] = []

    for _name, config in submodules.items():
        path = config.get("path", "")
        if path.startswith("sourcedata/"):
            source_paths.add(path)
        elif path.startswith("derivatives/"):
            if path not in derivative_paths:
                derivative_paths.add(path)
                # Extract derivative ID from path
                deriv_name = path.split("/")[-1]
                derivative_ids.append(deriv_name)

    return len(source_paths), len(derivative_paths), derivative_ids


def _get_source_types(study_path: Path) -> str:
    """Determine source dataset types (raw, derivative, etc.).

    For now, assumes all sources in sourcedata/ are 'raw'.
    TODO: Fetch DatasetType from source dataset_description.json

    Args:
        study_path: Path to study directory

    Returns:
        Comma-separated list of source types
    """
    # TODO: Actually fetch DatasetType from each source's dataset_description.json
    # For now, assume 'raw' for all sources
    gitmodules_path = study_path / ".gitmodules"
    submodules = _parse_gitmodules(gitmodules_path)

    source_types = set()
    for _name, config in submodules.items():
        path = config.get("path", "")
        if path.startswith("sourcedata/"):
            # Default to 'raw' - would need to fetch actual type
            source_types.add("raw")

    return ",".join(sorted(source_types)) if source_types else "n/a"


def _load_dataset_description(study_path: Path) -> dict[str, Any]:
    """Load dataset_description.json from study."""
    desc_path = study_path / "dataset_description.json"
    if desc_path.exists():
        with open(desc_path) as f:
            data: dict[str, Any] = json.load(f)
            return data
    return {}


def collect_study_metadata(
    study_path: Path,
    stage: str = "basic",
) -> dict[str, Any]:
    """Collect all metadata for a study for studies.tsv.

    Args:
        study_path: Path to study directory
        stage: Extraction stage for summary data
            - "basic": Only cached metadata
            - "counts": + directory/file counts
            - "sizes": + file sizes from annex keys
            - "imaging": + voxel counts via nibabel

    Returns:
        Dictionary with all column values
    """
    study_id = study_path.name
    desc = _load_dataset_description(study_path)

    source_count, derivative_count, derivative_ids = _count_submodules(study_path)
    source_types = _get_source_types(study_path)

    # Get authors as comma-separated string
    authors_list = desc.get("Authors", [])
    authors = ", ".join(authors_list) if authors_list else "n/a"

    # Extract summary metadata using sparse access
    summaries = extract_all_summaries(study_path, stage=stage)

    return {
        "study_id": study_id,
        "name": desc.get("Name", f"Study dataset for {study_id}"),
        "version": "n/a",  # TODO: Get from git tag
        "raw_version": summaries.get("raw_version", "n/a"),
        "bids_version": desc.get("BIDSVersion", "n/a"),
        "hed_version": desc.get("HEDVersion", "n/a"),
        "license": desc.get("License", "n/a"),
        "authors": authors,
        "author_lead_raw": summaries.get("author_lead_raw", "n/a"),
        "author_senior_raw": summaries.get("author_senior_raw", "n/a"),
        "source_count": source_count,
        "source_types": source_types,
        "derivative_count": derivative_count,
        "subjects_num": summaries.get("subjects_num", "n/a"),
        "sessions_num": summaries.get("sessions_num", "n/a"),
        "sessions_min": summaries.get("sessions_min", "n/a"),
        "sessions_max": summaries.get("sessions_max", "n/a"),
        "bold_num": summaries.get("bold_num", "n/a"),
        "t1w_num": summaries.get("t1w_num", "n/a"),
        "t2w_num": summaries.get("t2w_num", "n/a"),
        "bold_size": summaries.get("bold_size", "n/a"),
        "t1w_size": summaries.get("t1w_size", "n/a"),
        "bold_size_max": summaries.get("bold_size_max", "n/a"),
        "bold_voxels": summaries.get("bold_voxels", "n/a"),
        "datatypes": summaries.get("datatypes", "n/a"),
        "derivative_ids": ",".join(derivative_ids) if derivative_ids else "n/a",
        "bids_valid": "n/a",  # Set by validation command
    }


def _load_existing_studies(output_path: Path) -> dict[str, dict[str, Any]]:
    """Load existing studies.tsv entries indexed by study_id.

    Args:
        output_path: Path to existing studies.tsv

    Returns:
        Dictionary mapping study_id to row data
    """
    existing: dict[str, dict[str, Any]] = {}
    if output_path.exists():
        with open(output_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                study_id = row.get("study_id", "")
                if study_id:
                    existing[study_id] = dict(row)
    return existing


def generate_studies_tsv(
    studies: list[Path],
    output_path: Path,
    stage: str = "basic",
) -> Path:
    """Generate studies.tsv from list of study directories.

    This function implements FR-012a: when updating specific studies,
    existing entries for other studies are preserved. New/updated entries
    are merged with existing data rather than replacing the entire file.

    Args:
        studies: List of study directory paths
        output_path: Path to output studies.tsv
        stage: Extraction stage for summary data
            - "basic": Only cached metadata
            - "counts": + directory/file counts
            - "sizes": + file sizes from annex keys
            - "imaging": + voxel counts via nibabel

    Returns:
        Path to generated file
    """
    # Load existing entries (FR-012a: preserve unmodified studies)
    existing = _load_existing_studies(output_path)

    # Collect metadata for specified studies
    updated_ids: set[str] = set()
    for study_path in studies:
        try:
            metadata = collect_study_metadata(study_path, stage=stage)
            study_id = metadata["study_id"]
            existing[study_id] = metadata
            updated_ids.add(study_id)
        except Exception as e:
            logger.warning(f"Failed to collect metadata for {study_path.name}: {e}")

    # Sort by study_id and write
    rows = [existing[sid] for sid in sorted(existing.keys())]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STUDIES_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    logger.info(
        f"Generated {output_path} with {len(rows)} studies "
        f"({len(updated_ids)} updated, {len(rows) - len(updated_ids)} preserved)"
    )
    return output_path


def generate_studies_json(output_path: Path) -> Path:
    """Generate studies.json sidecar.

    Args:
        output_path: Path to output studies.json

    Returns:
        Path to generated file
    """
    with open(output_path, "w") as f:
        json.dump(STUDIES_JSON, f, indent=2)
        f.write("\n")

    logger.info(f"Generated {output_path}")
    return output_path
