"""Study dataset model."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from openneuro_studies.models.derivative import DerivativeDataset
from openneuro_studies.models.source import SourceDataset


class StudyState(str, Enum):
    """Processing state of a study dataset."""

    DISCOVERED = "discovered"
    ORGANIZED = "organized"
    METADATA_GENERATED = "metadata_generated"
    VALIDATED = "validated"


class StudyDataset(BaseModel):
    """Represents a BIDS study folder (study-{id}) containing source and derivative datasets.

    Attributes:
        study_id: Unique identifier (e.g., "study-ds000001")
        name: Human-readable study name
        version: Study dataset version (calendar-based: 0.YYYYMMDD.PATCH)
        raw_version: Source dataset version/tag ("n/a" if multiple sources or no release)
        title: Full study title
        authors: Study dataset authors (from git shortlog of study dataset)
        author_lead_raw: Lead author of raw dataset (first element from Authors array)
        author_senior_raw: Senior author of raw dataset (last element from Authors array)
        bids_version: BIDS specification version
        hed_version: HED schema version if applicable
        license: Dataset license
        source_datasets: Raw datasets under sourcedata/ (at least 1 required)
        derivative_datasets: Processed datasets under derivatives/ (0 or more)
        github_url: Published repository URL
        datatypes: BIDS datatypes present (e.g., ["anat", "func"])
        state: Processing state
    """

    study_id: str = Field(..., pattern=r"^study-ds\d+$")
    name: str
    version: Optional[str] = Field(None, pattern=r"^0\.\d{8}\.\d+$")
    raw_version: Optional[str] = "n/a"
    title: str
    authors: List[str]
    author_lead_raw: Optional[str] = None
    author_senior_raw: Optional[str] = None
    bids_version: str
    hed_version: Optional[str] = None
    license: Optional[str] = None
    source_datasets: List[SourceDataset]
    derivative_datasets: List[DerivativeDataset] = Field(default_factory=list)
    github_url: str = Field(..., pattern=r"^https://github\.com/[\w-]+/study-ds\d+$")
    datatypes: List[str] = Field(default_factory=list)
    state: StudyState

    @field_validator("source_datasets")
    @classmethod
    def must_have_sources(cls, v: List[SourceDataset]) -> List[SourceDataset]:
        """Validate that study has at least one source dataset."""
        if not v:
            raise ValueError("Study must have at least one source dataset")
        return v


def transition_state(study: StudyDataset, new_state: StudyState) -> StudyDataset:
    """Transition study to new state with validation.

    Args:
        study: Study dataset to transition
        new_state: Target state

    Returns:
        Study dataset with updated state

    Raises:
        ValueError: If transition is invalid
    """
    valid_transitions = {
        StudyState.DISCOVERED: [StudyState.ORGANIZED],
        StudyState.ORGANIZED: [StudyState.METADATA_GENERATED],
        StudyState.METADATA_GENERATED: [StudyState.VALIDATED],
    }

    if new_state not in valid_transitions.get(study.state, []):
        raise ValueError(f"Invalid transition: {study.state} → {new_state}")

    study.state = new_state
    return study
