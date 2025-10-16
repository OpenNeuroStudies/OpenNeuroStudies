"""Study dataset creation using DataLad."""

import json
import threading
from pathlib import Path
from typing import Optional

import datalad.api as dl

# Global lock for serializing study dataset creation
# Prevents race conditions when parallel workers create the same study
_study_creation_lock = threading.Lock()


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

    study_path = parent_path / study_id

    try:
        # Use lock to prevent race conditions when parallel workers
        # try to create the same study dataset simultaneously
        # Keep ALL creation steps under lock to ensure atomicity
        # IMPORTANT: Idempotency check must be INSIDE lock to prevent race conditions
        with _study_creation_lock:
            # Check if already exists (idempotency check inside lock)
            if study_path.exists():
                if (study_path / ".datalad").exists():
                    # Already a DataLad dataset - this is fine (idempotent)
                    return study_path
                else:
                    raise StudyCreationError(
                        f"Path {study_path} exists but is not a DataLad dataset"
                    )
            # Create DataLad dataset independently (not as subdataset of parent)
            # This avoids automatic parent commits from DataLad
            # Parent registration is handled separately in batch by caller
            # Use force=True for idempotency when derivative creates study before raw
            dl.create(path=str(study_path), annex=False, force=True)

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
