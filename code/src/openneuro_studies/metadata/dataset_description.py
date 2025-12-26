"""Generate dataset_description.json for study datasets.

Implements FR-005 through FR-008:
- FR-005: Generate dataset_description.json following BIDS 1.10.1 study specification
- FR-006: Populate SourceDatasets with BIDS URIs
- FR-007: Generate GeneratedBy field with code provenance
- FR-008: Copy/collate ReferencesAndLinks, License, Keywords, etc.
"""

import configparser
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from openneuro_studies import __version__

logger = logging.getLogger(__name__)


def _parse_gitmodules(gitmodules_path: Path) -> dict[str, dict[str, str]]:
    """Parse .gitmodules file into a dictionary.

    Args:
        gitmodules_path: Path to .gitmodules file

    Returns:
        Dictionary mapping submodule name to its config (path, url, etc.)
    """
    if not gitmodules_path.exists():
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    result = {}
    for section in config.sections():
        if section.startswith('submodule "'):
            name = section[11:-1]  # Extract name from 'submodule "name"'
            result[name] = dict(config[section])

    return result


def _get_source_datasets(study_path: Path) -> list[dict[str, str]]:
    """Get SourceDatasets array from study's sourcedata submodules.

    Returns array of objects with URL (BIDS URI), DOI (if available), Version.

    Args:
        study_path: Path to study directory

    Returns:
        List of SourceDatasets entries following BIDS specification
    """
    gitmodules_path = study_path / ".gitmodules"
    submodules = _parse_gitmodules(gitmodules_path)

    # Use dict to deduplicate by path (handles duplicate submodule entries)
    source_by_path: dict[str, dict[str, str]] = {}

    for _name, config in submodules.items():
        path = config.get("path", "")
        url = config.get("url", "")

        # Only include sourcedata submodules
        if not path.startswith("sourcedata/"):
            continue

        # Skip if we already have this path
        if path in source_by_path:
            continue

        # Extract dataset_id from path (e.g., "sourcedata/ds000001" -> "ds000001")
        dataset_id = path.split("/")[-1]

        # Create BIDS URI pointing to local sourcedata path
        bids_uri = f"bids::{path}/"

        entry: dict[str, str] = {"URL": bids_uri}

        # Try to get version from git tags (without cloning)
        # For now, we'll leave Version out if not easily available
        # TODO: Implement version extraction from git tags (FR-025, FR-026)

        # Add DOI for OpenNeuro datasets
        if "openneuro" in url.lower() or dataset_id.startswith("ds"):
            # OpenNeuro DOI format
            entry["DOI"] = f"doi:10.18112/openneuro.{dataset_id}"

        source_by_path[path] = entry

    return list(source_by_path.values())


def _get_generated_by() -> list[dict[str, Any]]:
    """Generate GeneratedBy field with code provenance.

    Returns:
        List with single GeneratedBy entry for openneuro-studies
    """
    return [
        {
            "Name": "openneuro-studies",
            "Version": __version__,
            "Description": "OpenNeuroStudies infrastructure for organizing OpenNeuro datasets",
            "CodeURL": "https://github.com/OpenNeuroStudies/OpenNeuroStudies",
        }
    ]


def _get_authors_from_git(study_path: Path) -> list[str]:
    """Get authors from git shortlog of the study dataset.

    Args:
        study_path: Path to study directory

    Returns:
        List of author names, or default if git fails
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(study_path), "shortlog", "-sne", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        authors = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # Format: "   123\tName <email>"
                parts = line.strip().split("\t", 1)
                if len(parts) == 2:
                    name_email = parts[1]
                    # Extract just the name (before <email>)
                    name = name_email.split("<")[0].strip()
                    if name and name not in authors:
                        authors.append(name)
        return authors if authors else ["OpenNeuroStudies Contributors"]
    except subprocess.CalledProcessError:
        return ["OpenNeuroStudies Contributors"]


def _fetch_source_metadata(study_path: Path) -> dict[str, Any]:
    """Fetch metadata from source datasets to collate.

    For now, returns empty dict. Future: fetch dataset_description.json
    from source datasets via GitHub API (FR-008).

    Args:
        study_path: Path to study directory

    Returns:
        Collated metadata from sources (License, Keywords, etc.)
    """
    # TODO: Implement fetching from source datasets
    # This would require GitHub API calls to get dataset_description.json
    # from each sourcedata submodule
    return {}


def generate_dataset_description(
    study_path: Path,
    overwrite: bool = False,
) -> Path:
    """Generate dataset_description.json for a study dataset.

    Args:
        study_path: Path to study directory
        overwrite: If True, overwrite existing file

    Returns:
        Path to generated dataset_description.json

    Raises:
        FileExistsError: If file exists and overwrite=False
    """
    output_path = study_path / "dataset_description.json"

    if output_path.exists() and not overwrite:
        logger.info(f"Updating existing {output_path}")
        # Load existing to preserve any manual additions
        with open(output_path) as f:
            existing = json.load(f)
    else:
        existing = {}

    study_id = study_path.name
    dataset_id = study_id[6:] if study_id.startswith("study-") else study_id

    # Build dataset_description following BIDS 1.10.1
    description: dict[str, Any] = {
        "Name": f"Study dataset for {dataset_id}",
        "BIDSVersion": "1.10.1",
        "DatasetType": "study",
    }

    # SourceDatasets (FR-006)
    source_datasets = _get_source_datasets(study_path)
    if source_datasets:
        description["SourceDatasets"] = source_datasets

    # GeneratedBy (FR-007)
    description["GeneratedBy"] = _get_generated_by()

    # Authors from git shortlog
    description["Authors"] = _get_authors_from_git(study_path)

    # License - default to CC0, can be overridden by source metadata
    description["License"] = existing.get("License", "CC0")

    # ReferencesAndLinks
    description["ReferencesAndLinks"] = [
        "https://openneuro.org",
        f"https://github.com/OpenNeuroStudies/{study_id}",
        "https://bids.neuroimaging.io/extensions/beps/bep_035.html",
    ]

    # Preserve any additional fields from existing file
    for key in ["Keywords", "Acknowledgements", "Funding", "HowToAcknowledge"]:
        if key in existing:
            description[key] = existing[key]

    # Write output
    with open(output_path, "w") as f:
        json.dump(description, f, indent=2)
        f.write("\n")  # Trailing newline

    logger.info(f"Generated {output_path}")
    return output_path
