"""Unorganized dataset tracking model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from openneuro_studies.models.derivative import DerivativeDataset


class UnorganizedReason(str, Enum):
    """Reasons why a dataset could not be organized."""

    RAW_DATASET_NOT_FOUND = "raw_dataset_not_found"
    INVALID_SOURCE_REFERENCE = "invalid_source_reference"
    MULTI_SOURCE_INCOMPLETE = "multi_source_incomplete"
    ORGANIZATION_ERROR = "organization_error"
    UNKNOWN = "unknown"


class UnorganizedDataset(BaseModel):
    """Represents a discovered dataset that could not be organized.

    Attributes:
        dataset_id: Original dataset ID (can be any string, e.g., "ds000212",
                    "ds000212-fmriprep", "myanalysis-results")
        derivative_id: Derivative identifier if applicable (e.g., "fmriprep-21.0.1")
        tool_name: Processing tool name if derivative
        version: Tool version if derivative
        url: Repository URL
        commit_sha: Git commit SHA
        datalad_uuid: DataLad dataset UUID if available
        source_datasets: List of source dataset IDs (discovered from dataset_description.json
                        SourceDatasets field or git submodules in sourcedata/)
        reason: Why this dataset could not be organized
        discovered_at: ISO 8601 timestamp when dataset was discovered
        notes: Additional context or error details
    """

    dataset_id: str
    derivative_id: Optional[str] = None
    tool_name: Optional[str] = None
    version: Optional[str] = None
    url: str
    commit_sha: str
    datalad_uuid: Optional[str] = None
    source_datasets: List[str] = Field(default_factory=list)
    reason: UnorganizedReason
    discovered_at: str  # ISO 8601 timestamp
    notes: Optional[str] = None

    @classmethod
    def from_derivative_dataset(
        cls,
        derivative: DerivativeDataset,
        reason: UnorganizedReason,
        notes: Optional[str] = None,
    ) -> UnorganizedDataset:
        """Create UnorganizedDataset from a DerivativeDataset.

        Args:
            derivative: The derivative dataset that couldn't be organized
            reason: Why it couldn't be organized
            notes: Additional context

        Returns:
            UnorganizedDataset instance
        """
        return cls(
            dataset_id=derivative.dataset_id,
            derivative_id=derivative.derivative_id,
            tool_name=derivative.tool_name,
            version=derivative.version,
            url=derivative.url,
            commit_sha=derivative.commit_sha,
            datalad_uuid=derivative.datalad_uuid,
            source_datasets=derivative.source_datasets,
            reason=reason,
            discovered_at=datetime.now().isoformat(),
            notes=notes,
        )
