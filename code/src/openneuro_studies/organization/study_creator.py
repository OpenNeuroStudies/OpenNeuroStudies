"""Study dataset creation using DataLad."""

import json
from pathlib import Path
from typing import Optional

import datalad.api as dl


class StudyCreationError(Exception):
    """Raised when study dataset creation fails."""

    pass


def create_study_dataset(
    study_id: str,
    github_org: str = "OpenNeuroStudies",
    parent_path: Optional[Path] = None,
) -> Path:
    """Create a study dataset using DataLad.

    Creates a new DataLad dataset (git repository without git-annex) for organizing
    a study with sourcedata/ and derivatives/ subdirectories.

    Args:
        study_id: Study identifier (e.g., "study-ds000001")
        github_org: GitHub organization for study repository URL
        parent_path: Parent directory for study dataset (default: current directory)

    Returns:
        Path to created study dataset

    Raises:
        StudyCreationError: If dataset creation fails or already exists

    Examples:
        >>> study_path = create_study_dataset("study-ds000001")
        >>> assert (study_path / ".datalad").exists()
        >>> assert (study_path / "sourcedata").exists()
    """
    if parent_path is None:
        parent_path = Path.cwd()

    study_path = parent_path / study_id

    # Check if already exists (idempotency)
    if study_path.exists():
        if (study_path / ".datalad").exists():
            # Already a DataLad dataset - this is fine (idempotent)
            return study_path
        else:
            raise StudyCreationError(f"Path {study_path} exists but is not a DataLad dataset")

    try:
        # Create DataLad dataset without annex
        dl.create(path=str(study_path), annex=False)

        # Create sourcedata and derivatives directories
        sourcedata_dir = study_path / "sourcedata"
        derivatives_dir = study_path / "derivatives"
        sourcedata_dir.mkdir(exist_ok=True)
        derivatives_dir.mkdir(exist_ok=True)

        # Generate initial dataset_description.json
        dataset_description = {
            "Name": f"Study dataset for {study_id}",
            "BIDSVersion": "1.10.1",
            "DatasetType": "study",
            "License": "CC0",
            "Authors": ["OpenNeuroStudies Contributors"],
            "ReferencesAndLinks": [
                "https://openneuro.org",
                f"https://github.com/{github_org}/{study_id}",
                "https://bids.neuroimaging.io/extensions/beps/bep_035.html",
            ],
        }

        desc_file = study_path / "dataset_description.json"
        desc_file.write_text(json.dumps(dataset_description, indent=2) + "\n")

        # Save initial commit
        dl.save(
            path=str(study_path),
            message=f"Initialize {study_id} study dataset\n\n"
            f"Created by openneuro-studies organize command",
        )

        return study_path

    except Exception as e:
        raise StudyCreationError(f"Failed to create study dataset {study_id}: {e}") from e
