"""Hierarchical error tracking system for bids_studies.

Provides structured error logging with temporal tracking, deduplication,
and hierarchical organization across study/dataset/subject/session/file levels.

This module lives in bids_studies (not openneuro_studies) to ensure the
library can be used standalone. See FR-HE-071.

Storage format: JSONL (newline-delimited JSON)
Location: study-*/sourcedata/errors.jsonl
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from bids_studies.error_classification import ErrorType, classify_error

logger = logging.getLogger(__name__)

# Error levels in hierarchy
ErrorLevel = Literal["study", "dataset", "subject", "session", "file"]

# Error categories
ErrorCategory = Literal[
    "missing_url",
    "network_error",
    "permission_error",
    "git_annex_error",
    "parse_error",
    "validation_error",
    "other",
]


def categorize_error(error_msg: str, exception: Exception | None = None) -> ErrorCategory:
    """Categorize error based on message and exception type.

    Args:
        error_msg: Error message text
        exception: Optional exception object

    Returns:
        ErrorCategory classification
    """
    error_lower = error_msg.lower()

    if "no remote url" in error_lower or "missing url" in error_lower:
        return "missing_url"

    if "network" in error_lower or "connection" in error_lower or "unreachable" in error_lower:
        return "network_error"

    if "permission denied" in error_lower or "forbidden" in error_lower:
        return "permission_error"

    if "git-annex" in error_lower or "annex" in error_lower:
        return "git_annex_error"

    if "parse" in error_lower or "json" in error_lower or "yaml" in error_lower:
        return "parse_error"

    if "validation" in error_lower or "invalid" in error_lower or "bids" in error_lower:
        return "validation_error"

    return "other"


def log_error(
    error_log_path: Path,
    study_id: str,
    dataset_id: str,
    error_msg: str,
    level: ErrorLevel,
    exception: Exception | None = None,
    dataset_version: str | None = None,
    subject_id: str | None = None,
    session_id: str | None = None,
    file_path: str | None = None,
) -> None:
    """Log an error to the hierarchical error tracking system.

    Deduplicates errors by incrementing count if same error already exists.
    Uses plain dicts and JSON (no Pydantic dependency) for portability.

    Args:
        error_log_path: Path to errors.jsonl file
        study_id: Study identifier (e.g., "study-ds001506")
        dataset_id: Dataset identifier (e.g., "ds001506")
        error_msg: Error message
        level: Hierarchy level (study, dataset, subject, session, file)
        exception: Optional exception object
        dataset_version: Git SHA of dataset
        subject_id: Subject ID if applicable
        session_id: Session ID if applicable
        file_path: Relative file path if applicable
    """
    now = datetime.now().isoformat()

    # Classify and categorize error
    error_type = classify_error(error_msg, exception)
    error_category = categorize_error(error_msg, exception)

    # Create new record as dict
    new_record: dict[str, Any] = {
        "timestamp": now,
        "study_id": study_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "level": level,
        "subject_id": subject_id,
        "session_id": session_id,
        "error_type": error_type,
        "error_category": error_category,
        "file_path": file_path,
        "message": error_msg,
        "count": 1,
        "resolved": False,
        "first_seen": now,
        "last_seen": now,
    }

    def _dedup_key(record: dict[str, Any]) -> tuple[str, ...]:
        return (
            record.get("study_id", ""),
            record.get("dataset_id", ""),
            record.get("level", ""),
            record.get("subject_id") or "",
            record.get("session_id") or "",
            record.get("file_path") or "",
            record.get("error_category", ""),
            record.get("message", ""),
        )

    # Read existing records and deduplicate
    existing_records: dict[tuple[str, ...], dict[str, Any]] = {}
    if error_log_path.exists():
        with open(error_log_path) as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        existing_records[_dedup_key(record)] = record
                    except json.JSONDecodeError:
                        pass

    # Check if this error already exists
    dedup_key = _dedup_key(new_record)
    if dedup_key in existing_records:
        # Update existing record
        existing = existing_records[dedup_key]
        existing["count"] = existing.get("count", 1) + 1
        existing["last_seen"] = now
        existing["timestamp"] = now
        logger.debug(
            f"Updated existing error (count={existing['count']}): "
            f"{error_category} in {study_id}"
        )
    else:
        # Add new record
        existing_records[dedup_key] = new_record
        logger.info(f"Logged new error: {error_category} in {study_id}/{level}")

    # Write all records back (sorted by first_seen for readability)
    error_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(error_log_path, "w") as f:
        for record in sorted(existing_records.values(), key=lambda r: r.get("first_seen", "")):
            f.write(json.dumps(record) + "\n")
