"""BIDS metadata extraction at multiple hierarchical levels.

Provides extraction functions for:
- Per-subject statistics (sourcedata and derivatives)
- Per-dataset aggregation
- Per-study aggregation
"""

from bids_studies.extraction.dataset import aggregate_to_dataset
from bids_studies.extraction.raw_metadata import extract_raw_metadata
from bids_studies.extraction.derivative import (
    aggregate_derivative_to_dataset,
    extract_derivative_subject_stats,
    extract_derivative_subjects_stats,
)
from bids_studies.extraction.study import (
    aggregate_to_study,
    extract_all_derivatives_stats,
    extract_derivative_stats,
    extract_study_stats,
)
from bids_studies.extraction.subject import (
    extract_nifti_header_from_gzip_stream,
    extract_subject_stats,
    extract_subjects_stats,
)
from bids_studies.extraction.tsv import (
    DATASETS_COLUMNS,
    DERIVATIVE_DATASETS_COLUMNS,
    DERIVATIVE_SUBJECTS_COLUMNS,
    SUBJECTS_COLUMNS,
    read_tsv,
    write_datasets_tsv,
    write_derivative_datasets_tsv,
    write_derivative_subjects_tsv,
    write_subjects_tsv,
    write_tsv,
)

__all__ = [
    "extract_nifti_header_from_gzip_stream",
    "extract_subject_stats",
    "extract_subjects_stats",
    "aggregate_to_dataset",
    "extract_raw_metadata",
    "aggregate_to_study",
    "extract_study_stats",
    "write_subjects_tsv",
    "write_datasets_tsv",
    "SUBJECTS_COLUMNS",
    "DATASETS_COLUMNS",
    # Derivative extraction
    "extract_derivative_subject_stats",
    "extract_derivative_subjects_stats",
    "aggregate_derivative_to_dataset",
    "extract_derivative_stats",
    "extract_all_derivatives_stats",
    "write_derivative_subjects_tsv",
    "write_derivative_datasets_tsv",
    "DERIVATIVE_SUBJECTS_COLUMNS",
    "DERIVATIVE_DATASETS_COLUMNS",
    # Generic TSV I/O
    "write_tsv",
    "read_tsv",
]
