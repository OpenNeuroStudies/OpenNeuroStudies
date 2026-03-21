"""Error classification for extraction errors.

Distinguishes between operational errors (must fail) and expected failures
(can be tolerated and logged).
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

ErrorType = Literal["operational", "expected"]


def classify_error(error_msg: str, exception: Exception | None = None) -> ErrorType:
    """Classify an error as operational (must fail) or expected (can tolerate).

    Operational Errors (MUST fail immediately):
    - Git/git-annex initialization failures
    - Subdataset not initialized
    - I/O errors (permissions, disk full)
    - Malformed BIDS structure (missing dataset_description.json)
    - Network failures during git operations

    Expected Failures (CAN tolerate with logging):
    - Individual file missing remote URL (file exists but not annexed/public)
    - Missing optional imaging metrics
    - Corrupt/invalid individual files
    - Empty subjects/sessions (valid BIDS but no data)

    Args:
        error_msg: Error message string
        exception: Optional exception object for type checking

    Returns:
        "operational" or "expected"
    """
    error_lower = error_msg.lower()

    # Operational errors - git/infrastructure issues
    operational_phrases = [
        "git-annex: first run",
        "not a git repository",
        "fatal: not a git repository",
        "subdataset not initialized",
        "failed to initialize",
        "permission denied",
        "cannot access",
        "connection refused",
        "network unreachable",
    ]

    if any(phrase in error_lower for phrase in operational_phrases):
        return "operational"

    # Special case: missing dataset_description.json is operational
    if "no such file or directory" in error_lower and "dataset_description.json" in error_lower:
        return "operational"

    # Exception type-based classification
    if exception is not None:
        exception_type = type(exception).__name__

        # Operational: Infrastructure failures
        if exception_type in [
            "PermissionError",
            "OSError",  # Disk full, I/O errors
            "TimeoutError",
            "ConnectionError",
            "RuntimeError",  # Used for initialization failures
        ]:
            # But NOT if it's a file-level issue
            if "no remote url found" not in error_lower:
                return "operational"

    # Expected failures - file-level issues
    if any(
        phrase in error_lower
        for phrase in [
            "no remote url found",  # File exists but not public/annexed
            "failed to extract imaging metrics from",  # Individual file issue
            "corrupt",
            "invalid format",
            "not a valid",
            "failed to extract derivative",  # Derivative extraction (optional)
        ]
    ):
        return "expected"

    # Default: treat as operational (fail-safe)
    # This ensures new error types are noticed and classified explicitly
    logger.warning(
        f"Unclassified error (defaulting to operational): {error_msg[:100]}"
    )
    return "operational"


def aggregate_errors(
    errors: list[str], exceptions: list[Exception | None] | None = None
) -> tuple[list[str], list[str]]:
    """Aggregate errors into operational and expected categories.

    Args:
        errors: List of error messages
        exceptions: Optional list of exceptions corresponding to errors

    Returns:
        Tuple of (operational_errors, expected_errors)
    """
    if exceptions is None:
        exceptions = [None] * len(errors)

    operational = []
    expected = []

    for error_msg, exc in zip(errors, exceptions):
        classification = classify_error(error_msg, exc)
        if classification == "operational":
            operational.append(error_msg)
        else:
            expected.append(error_msg)

    return operational, expected
