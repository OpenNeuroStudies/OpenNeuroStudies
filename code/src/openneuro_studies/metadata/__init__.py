"""Metadata generation for OpenNeuroStudies.

This module provides functions for generating:
- dataset_description.json for each study (FR-005 to FR-008)
- studies.tsv and studies.json at top level (FR-009, FR-011)
- studies+derivatives.tsv and studies+derivatives.json (FR-010, FR-011)
- Summary extraction from source datasets (FR-031 to FR-033)

Note: The '+' naming convention follows BIDS issue #2273 for TSV files
with compound primary keys (e.g., study_id + derivative_id).
See: https://github.com/bids-standard/bids-specification/issues/2273
"""

from openneuro_studies.metadata.dataset_description import generate_dataset_description
from openneuro_studies.metadata.studies_plus_derivatives_tsv import (
    collect_derivative_cache_entries,
    collect_derivatives_for_study,
    generate_studies_derivatives_json,
    generate_studies_derivatives_tsv,
)
from openneuro_studies.metadata.studies_tsv import (
    collect_study_metadata,
    generate_studies_json,
    generate_studies_tsv,
    merge_extracts_into_studies_tsv,
)
from openneuro_studies.metadata.summary_extractor import (
    extract_all_summaries,
    extract_raw_metadata,
)

__all__ = [
    "generate_dataset_description",
    "generate_studies_tsv",
    "generate_studies_json",
    "generate_studies_derivatives_tsv",
    "generate_studies_derivatives_json",
    "collect_study_metadata",
    "collect_derivative_cache_entries",
    "collect_derivatives_for_study",
    "merge_extracts_into_studies_tsv",
    "extract_all_summaries",
    "extract_raw_metadata",
]
