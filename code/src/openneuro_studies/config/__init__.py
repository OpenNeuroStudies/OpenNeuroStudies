"""Configuration module for OpenNeuroStudies."""

from openneuro_studies.config.loader import (
    ConfigLoadError,
    create_example_config,
    load_config,
)
from openneuro_studies.config.models import (
    OpenNeuroStudiesConfig,
    SourceSpecification,
    SourceType,
)

__all__ = [
    "OpenNeuroStudiesConfig",
    "SourceSpecification",
    "SourceType",
    "load_config",
    "create_example_config",
    "ConfigLoadError",
]
