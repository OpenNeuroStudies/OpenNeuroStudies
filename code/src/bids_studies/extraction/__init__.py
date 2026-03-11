"""BIDS metadata extraction at multiple hierarchical levels.

Provides extraction functions for:
- Per-subject statistics (sourcedata and derivatives)
- Per-dataset aggregation
- Per-study aggregation
"""

from bids_studies.extraction.dataset import aggregate_to_dataset
from bids_studies.extraction.derivative import (
    aggregate_derivative_to_dataset,
    extract_derivative_subject_stats,
    extract_derivative_subjects_stats,
)
from bids_studies.extraction.study import (
    aggregate_to_study,
    extract_derivative_stats,
    extract_study_stats,
)
from bids_studies.extraction.subject import (
    extract_subject_stats,
    extract_subjects_stats,
)
from bids_studies.extraction.tsv import (
    DATASETS_COLUMNS,
    DERIVATIVE_DATASETS_COLUMNS,
    DERIVATIVE_SUBJECTS_COLUMNS,
    SUBJECTS_COLUMNS,
    write_datasets_tsv,
    write_derivative_datasets_tsv,
    write_derivative_subjects_tsv,
    write_subjects_tsv,
)

__all__ = [
    "extract_subject_stats",
    "extract_subjects_stats",
    "aggregate_to_dataset",
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
    "write_derivative_subjects_tsv",
    "write_derivative_datasets_tsv",
    "DERIVATIVE_SUBJECTS_COLUMNS",
    "DERIVATIVE_DATASETS_COLUMNS",
]
