"""Library utilities for OpenNeuroStudies."""

from openneuro_studies.lib.datalad_utils import (
    datalad_run,
    datalad_save,
    generate_stats_message,
    run_with_provenance,
    save_with_stats,
)
from openneuro_studies.lib.exceptions import (
    DatasetNotFoundError,
    ExtractionError,
    GitHubAPIError,
    NetworkError,
    OpenNeuroStudiesError,
    ValidationError,
)
from openneuro_studies.lib.retry import retry_on_network_error
from openneuro_studies.lib.sparse_access import (
    SparseDataset,
    is_sparse_access_available,
)

__all__ = [
    "datalad_run",
    "datalad_save",
    "generate_stats_message",
    "run_with_provenance",
    "save_with_stats",
    "DatasetNotFoundError",
    "ExtractionError",
    "GitHubAPIError",
    "NetworkError",
    "OpenNeuroStudiesError",
    "ValidationError",
    "retry_on_network_error",
    "SparseDataset",
    "is_sparse_access_available",
]
