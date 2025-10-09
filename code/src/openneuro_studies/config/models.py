"""Configuration models for OpenNeuroStudies."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    """Type of dataset source."""

    RAW = "raw"
    DERIVATIVE = "derivative"


class SourceSpecification(BaseModel):
    """Configuration model defining a dataset source to discover.

    Attributes:
        name: Friendly name for the source (e.g., "OpenNeuroDatasets")
        organization_url: GitHub/Forgejo organization URL
        type: Source type (raw or derivative)
        inclusion_patterns: Regex patterns for datasets to include (default: all)
        exclusion_patterns: Regex patterns for datasets to exclude (default: none)
        access_token_env: Environment variable name containing access token
    """

    name: str
    organization_url: HttpUrl
    type: SourceType
    inclusion_patterns: List[str] = Field(default_factory=lambda: [".*"])
    exclusion_patterns: List[str] = Field(default_factory=list)
    access_token_env: Optional[str] = "GITHUB_TOKEN"


class OpenNeuroStudiesConfig(BaseModel):
    """Root configuration model for OpenNeuroStudies.

    Attributes:
        github_org: GitHub organization name for publishing study repositories
        sources: List of source specifications to discover datasets from
    """

    github_org: str = Field(
        default="OpenNeuroStudies",
        description="GitHub organization for publishing study repositories",
    )
    sources: List[SourceSpecification]
