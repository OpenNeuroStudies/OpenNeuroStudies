"""Derivative dataset model."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_core import core_schema


class DerivativeDataset(BaseModel):
    """Represents a processed dataset from OpenNeuroDerivatives or OpenNeuro derivatives.

    Attributes:
        dataset_id: Original derivative dataset ID (e.g., "ds006185")
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

    dataset_id: str = Field(..., pattern=r"^ds\d+$")
    derivative_id: str
    tool_name: str
    version: str
    datalad_uuid: str
    uuid_prefix: Optional[str] = None
    size_stats: Optional[Dict[str, int]] = Field(default_factory=dict)
    execution_metrics: Optional[Dict[str, float]] = Field(default_factory=dict)
    source_datasets: List[str] = Field(..., min_length=1)
    processed_raw_version: Optional[str] = None
    outdatedness: Optional[int] = None

    @field_validator("datalad_uuid")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Validate that datalad_uuid is 36 characters (UUID format)."""
        if len(v) != 36:
            raise ValueError("datalad_uuid must be 36 characters")
        return v

    @field_validator("uuid_prefix", mode="before")
    @classmethod
    def extract_uuid_prefix(
        cls, v: Optional[str], info: core_schema.ValidationInfo
    ) -> Optional[str]:
        """Extract first 8 characters of datalad_uuid as prefix."""
        if v is None and "datalad_uuid" in info.data:
            uuid_value: Any = info.data["datalad_uuid"]
            return str(uuid_value)[:8]
        return v


def generate_derivative_id(
    tool_name: str, version: str, datalad_uuid: str, existing_ids: List[str]
) -> str:
    """Generate unique derivative_id.

    If tool_name-version already exists in existing_ids, append first 8 chars of UUID.

    Args:
        tool_name: Processing tool name
        version: Tool version
        datalad_uuid: DataLad dataset UUID
        existing_ids: List of already-used derivative IDs

    Returns:
        Unique derivative_id string
    """
    base_id = f"{tool_name}-{version}"
    if base_id not in existing_ids:
        return base_id

    uuid_prefix = datalad_uuid[:8]
    return f"{base_id}-{uuid_prefix}"
