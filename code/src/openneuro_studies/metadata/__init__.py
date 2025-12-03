"""Metadata generation for OpenNeuroStudies.

This module provides functions for generating:
- dataset_description.json for each study (FR-005 to FR-008)
- studies.tsv and studies.json at top level (FR-009, FR-011)
- studies_derivatives.tsv and studies_derivatives.json (FR-010, FR-011)
"""

from openneuro_studies.metadata.dataset_description import generate_dataset_description
from openneuro_studies.metadata.studies_derivatives_tsv import (
    collect_derivatives_for_study,
    generate_studies_derivatives_json,
    generate_studies_derivatives_tsv,
)
from openneuro_studies.metadata.studies_tsv import (
    collect_study_metadata,
    generate_studies_json,
    generate_studies_tsv,
)

__all__ = [
    "generate_dataset_description",
    "generate_studies_tsv",
    "generate_studies_json",
    "generate_studies_derivatives_tsv",
    "generate_studies_derivatives_json",
    "collect_study_metadata",
    "collect_derivatives_for_study",
]
