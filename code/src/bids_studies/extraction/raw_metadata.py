"""Raw dataset metadata extraction.

Extracts metadata from dataset_description.json and git tags for raw
(sourcedata) BIDS datasets within a study.

Moved from openneuro_studies.metadata.summary_extractor (Phase 1) to
bids_studies for reuse across packages (FR-042l, G1 resolution).
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    result: dict[str, Any] = {
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
    all_lead_authors: list[str] = []
    all_senior_authors: list[str] = []
    all_versions: list[str] = []
    all_bids_versions: list[str] = []
    all_hed_versions: list[str] = []

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
