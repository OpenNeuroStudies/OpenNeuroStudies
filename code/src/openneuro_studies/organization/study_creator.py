"""Study dataset creation using DataLad."""

import json
from pathlib import Path
from typing import Optional

import datalad.api as dl

from .locks import parent_repo_lock


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
    a study with sourcedata/ and derivatives/ subdirectories. The study dataset is
    created and initialized with a commit, but NOT registered in the parent repository.
    Parent registration should be done separately in a batch operation (see FR-039).

    Args:
        study_id: Study identifier (e.g., "study-ds000001")
        github_org: GitHub organization for study repository URL
        parent_path: Parent directory for study dataset (default: current directory)

    Returns:
        Path to created study dataset

    Raises:
        StudyCreationError: If dataset creation fails or already exists

    Note:
        This function only creates the study subdataset and commits its initial state.
        It does NOT commit the parent repository. Caller is responsible for registering
        the study in parent .gitmodules and committing to parent in a batch operation.

    Examples:
        >>> study_path = create_study_dataset("study-ds000001")
        >>> assert (study_path / ".datalad").exists()
        >>> assert (study_path / "sourcedata").exists()
    """
    if parent_path is None:
        parent_path = Path.cwd()
    topds = dl.Dataset(parent_path)

    study_path = parent_path / study_id

    # Check if already exists (idempotency)
    if study_path.exists():
        if (study_path / ".datalad").exists():
            # Already a DataLad dataset - this is fine (idempotent)
            return study_path
        else:
            raise StudyCreationError(f"Path {study_path} exists but is not a DataLad dataset")

    try:
        # Use lock to serialize parent repository modifications
        # This prevents git index.lock conflicts when parallel workers
        # create study datasets in the same parent repository
        with parent_repo_lock:
            # Create DataLad dataset without annex
            # Use force=True to handle case where study is already registered as subdataset
            # (can happen when derivative creates study before raw dataset does)
            topds.create(path=str(study_path), annex=False, force=True)

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

        # Commit initial state within the study dataset only (not parent)
        # Parent registration is handled by organize command in batch
        study_ds = dl.Dataset(study_path)
        study_ds.save(
            message=f"Initialize {study_id} study dataset\n\n"
            f"Created by openneuro-studies organize command"
        )

        return study_path

    except Exception as e:
        raise StudyCreationError(f"Failed to create study dataset {study_id}: {e}") from e
