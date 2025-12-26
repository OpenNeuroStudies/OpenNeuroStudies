"""Hierarchical stats extraction for study datasets.

This module re-exports from bids_studies.extraction for backwards compatibility.
"""

# Re-export from bids_studies
from bids_studies.extraction import (
    DATASETS_COLUMNS,
    SUBJECTS_COLUMNS,
    aggregate_to_dataset,
    aggregate_to_study,
    extract_study_stats,
    extract_subject_stats,
    extract_subjects_stats,
    write_datasets_tsv,
    write_subjects_tsv,
)

# Backwards compatibility alias
extract_study_hierarchical_stats = extract_study_stats
aggregate_subjects_to_dataset = aggregate_to_dataset
aggregate_datasets_to_study = aggregate_to_study

__all__ = [
    "extract_subject_stats",
    "extract_subjects_stats",
    "aggregate_to_dataset",
    "aggregate_to_study",
    "extract_study_stats",
    "extract_study_hierarchical_stats",
    "aggregate_subjects_to_dataset",
    "aggregate_datasets_to_study",
    "write_subjects_tsv",
    "write_datasets_tsv",
    "SUBJECTS_COLUMNS",
    "DATASETS_COLUMNS",
]
