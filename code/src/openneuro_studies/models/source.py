"""Source dataset model."""

from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceDataset(BaseModel):
    """Represents a raw BIDS dataset from OpenNeuroDatasets or configured sources.

    Attributes:
        dataset_id: Original dataset ID (e.g., "ds000001")
        url: Git repository URL
        commit_sha: Specific commit SHA to link
        bids_version: BIDS specification version
        license: Dataset license
        authors: Dataset authors
        subjects_num: Number of subjects
        sessions_num: Total number of sessions
        sessions_min: Minimum sessions per subject
        sessions_max: Maximum sessions per subject
    """

    dataset_id: str = Field(..., pattern=r"^ds\d+$")
    url: HttpUrl
    commit_sha: str = Field(..., pattern=r"^[0-9a-f]{40}$")
    bids_version: str
    license: Optional[str] = None
    authors: Optional[List[str]] = Field(default_factory=list)
    subjects_num: Optional[int] = None
    sessions_num: Optional[int] = None
    sessions_min: Optional[int] = None
    sessions_max: Optional[int] = None

    @field_validator("commit_sha")
    @classmethod
    def validate_sha(cls, v: str) -> str:
        """Validate that commit_sha is a 40-character hexadecimal string."""
        if len(v) != 40 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("commit_sha must be 40-character hex string")
        return v
