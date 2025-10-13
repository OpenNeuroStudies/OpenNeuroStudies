"""Derivative dataset model."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class DerivativeDataset(BaseModel):
    """Represents a processed dataset from OpenNeuroDerivatives or OpenNeuro derivatives.

    Attributes:
        dataset_id: Repository/dataset ID (e.g., "ds006185" or "ds000001-mriqc")
                   - OpenNeuroDatasets derivatives: numeric only (ds006185)
                   - OpenNeuroDerivatives: includes tool suffix (ds000001-mriqc)
        derivative_id: Unique identifier for tracking (tool-version[-uuid_prefix])
        tool_name: Processing tool name (e.g., "fmriprep")
        version: Tool version
        datalad_uuid: DataLad dataset UUID from .datalad/config
        uuid_prefix: First 8 chars of UUID (for disambiguation)
        size_stats: Size statistics from git annex info
        execution_metrics: Runtime metrics if available (from con-duct/duct)
        source_datasets: IDs of source datasets processed
        processed_raw_version: Version of raw dataset when processed
        outdatedness: Commits behind current raw version (0 = up-to-date)
    """

    dataset_id: str = Field(..., pattern=r"^ds\d+(-[a-z0-9]+)?$")
    derivative_id: str
    tool_name: str
    version: str
    url: str  # GitHub clone URL for the derivative repository
    commit_sha: str  # Git commit SHA to reference
    datalad_uuid: Optional[str] = None  # UUID from .datalad/config (for disambiguation)
    uuid_prefix: Optional[str] = None
    size_stats: Optional[Dict[str, int]] = Field(default_factory=dict)
    execution_metrics: Optional[Dict[str, float]] = Field(default_factory=dict)
    source_datasets: List[str] = Field(..., min_length=1)
    processed_raw_version: Optional[str] = None
    outdatedness: Optional[int] = None

    @field_validator("datalad_uuid")
    @classmethod
    def validate_uuid(cls, v: Optional[str]) -> Optional[str]:
        """Validate that datalad_uuid is 36 characters (UUID format) if provided.

        UUID is used for disambiguation when multiple derivative datasets exist
        with the same tool-version combination (e.g., two fmriprep-21.0.1 datasets
        processed with different parameters).

        TODO: Fetch UUID from .datalad/config via GitHub API or during cloning.
        Without cloning, we'd need to use GitHub raw content API to read
        .datalad/config from the repository.
        """
        if v is not None and len(v) != 36:
            raise ValueError("datalad_uuid must be 36 characters")
        return v

    @model_validator(mode="after")
    def extract_uuid_prefix(self) -> "DerivativeDataset":
        """Extract first 8 characters of datalad_uuid as prefix if available."""
        if self.datalad_uuid is not None and self.uuid_prefix is None:
            self.uuid_prefix = self.datalad_uuid[:8]
        return self


def generate_derivative_id(
    tool_name: str, version: str, datalad_uuid: Optional[str], existing_ids: List[str]
) -> str:
    """Generate unique derivative_id.

    If tool_name-version already exists in existing_ids, append first 8 chars of UUID
    if available. Without UUID, returns base_id even if it exists (will need manual
    disambiguation later when UUIDs are fetched).

    Args:
        tool_name: Processing tool name
        version: Tool version
        datalad_uuid: DataLad dataset UUID (optional, needed for disambiguation)
        existing_ids: List of already-used derivative IDs

    Returns:
        Unique derivative_id string
    """
    base_id = f"{tool_name}-{version}"
    if base_id not in existing_ids:
        return base_id

    # Need UUID for disambiguation
    if datalad_uuid is None:
        # TODO: Log warning that UUID is needed for proper disambiguation
        return base_id

    uuid_prefix = datalad_uuid[:8]
    return f"{base_id}-{uuid_prefix}"
