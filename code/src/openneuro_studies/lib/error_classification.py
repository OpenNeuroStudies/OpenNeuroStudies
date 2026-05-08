"""Error classification for extraction errors.

Re-exports from bids_studies.error_classification for backward compatibility.
The canonical implementation now lives in bids_studies per FR-HE-071.
"""

from bids_studies.error_classification import (  # noqa: F401
    ErrorType,
    aggregate_errors,
    classify_error,
)

__all__ = ["ErrorType", "classify_error", "aggregate_errors"]
