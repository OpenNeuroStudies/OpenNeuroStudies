"""BIDS-Studies: Generic BIDS dataset metadata extraction and aggregation.

This package provides tools for:
- Sparse access to git-annex BIDS datasets
- Hierarchical metadata extraction (per-subject, per-dataset, per-study)
- TSV generation with JSON sidecars

Example usage:

    from bids_studies.sparse import SparseDataset
    from bids_studies.extraction import extract_subjects_stats, aggregate_to_dataset

    with SparseDataset("/path/to/dataset") as ds:
        subjects = ds.list_dirs("sub-*")

    stats = extract_subjects_stats(source_path, source_id)
    dataset_stats = aggregate_to_dataset(stats, source_id)
"""

__version__ = "0.1.0"
