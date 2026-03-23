#!/usr/bin/env python3
"""Hierarchical error tracking system.

Provides structured error logging with temporal tracking, deduplication,
and hierarchical organization across study/dataset/subject/session/file levels.

Storage format: JSONL (newline-delimited JSON)
Location: study-*/sourcedata/errors.jsonl
Retention: Keep unresolved forever, resolved for 30 days (gc removes old resolved)

Schema:
    {
        "timestamp": "2026-03-23T10:30:15",
        "study_id": "study-ds001506",
        "dataset_id": "ds001506",
        "dataset_version": "0bd43a59",
        "level": "file",  # study|dataset|subject|session|file
        "subject_id": "sub-01",
        "session_id": "ses-imagery01",
        "error_type": "expected",  # operational|expected
        "error_category": "missing_url",
        "file_path": "sub-01/ses-imagery01/func/..._bold.nii.gz",
        "message": "No remote URL found for file",
        "count": 1,
        "resolved": false,
        "first_seen": "2026-03-23T10:30:15",
        "last_seen": "2026-03-23T10:30:15"
    }
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from openneuro_studies.lib.error_classification import ErrorType, classify_error

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


class ErrorRecord(BaseModel):
    """Structured error record for hierarchical tracking."""

    timestamp: str = Field(..., description="ISO 8601 timestamp of this record update")
    study_id: str = Field(..., pattern=r"^study-ds\d+$")
    dataset_id: str = Field(..., pattern=r"^ds\d+")
    dataset_version: str | None = Field(None, description="Git SHA of dataset version")
    level: ErrorLevel = Field(..., description="Hierarchy level of error")
    subject_id: str | None = Field(None, description="Subject ID if applicable")
    session_id: str | None = Field(None, description="Session ID if applicable")
    error_type: ErrorType = Field(..., description="operational or expected")
    error_category: ErrorCategory = Field(..., description="Error category")
    file_path: str | None = Field(None, description="Relative path to file if applicable")
    message: str = Field(..., description="Error message")
    count: int = Field(default=1, ge=1, description="Number of occurrences")
    resolved: bool = Field(default=False, description="Whether error is resolved")
    first_seen: str = Field(..., description="ISO 8601 timestamp of first occurrence")
    last_seen: str = Field(..., description="ISO 8601 timestamp of last occurrence")
    resolved_at: str | None = Field(None, description="ISO 8601 timestamp when resolved")

    def get_dedup_key(self) -> tuple[str, ...]:
        """Generate deduplication key for this error.

        Errors are considered duplicates if they have the same:
        - study_id, dataset_id, level, subject_id, session_id, file_path
        - error_category, message

        Returns:
            Tuple of values forming unique key
        """
        return (
            self.study_id,
            self.dataset_id,
            self.level,
            self.subject_id or "",
            self.session_id or "",
            self.file_path or "",
            self.error_category,
            self.message,
        )


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

    # Create new record
    new_record = ErrorRecord(
        timestamp=now,
        study_id=study_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        level=level,
        subject_id=subject_id,
        session_id=session_id,
        error_type=error_type,
        error_category=error_category,
        file_path=file_path,
        message=error_msg,
        count=1,
        resolved=False,
        first_seen=now,
        last_seen=now,
    )

    # Read existing records and deduplicate
    existing_records: dict[tuple[str, ...], ErrorRecord] = {}
    if error_log_path.exists():
        with open(error_log_path) as f:
            for line in f:
                if line.strip():
                    record = ErrorRecord.model_validate_json(line)
                    existing_records[record.get_dedup_key()] = record

    # Check if this error already exists
    dedup_key = new_record.get_dedup_key()
    if dedup_key in existing_records:
        # Update existing record
        existing = existing_records[dedup_key]
        existing.count += 1
        existing.last_seen = now
        existing.timestamp = now
        # Don't change resolved status - if it was resolved, this is a regression
        logger.debug(
            f"Updated existing error (count={existing.count}): {error_category} in {study_id}"
        )
    else:
        # Add new record
        existing_records[dedup_key] = new_record
        logger.info(f"Logged new error: {error_category} in {study_id}/{level}")

    # Write all records back (sorted by first_seen for readability)
    error_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(error_log_path, "w") as f:
        for record in sorted(existing_records.values(), key=lambda r: r.first_seen):
            f.write(record.model_dump_json() + "\n")


def mark_resolved(
    error_log_path: Path,
    study_id: str,
    dataset_id: str,
    error_category: ErrorCategory | None = None,
    level: ErrorLevel | None = None,
    subject_id: str | None = None,
) -> int:
    """Mark errors as resolved in the error log.

    Args:
        error_log_path: Path to errors.jsonl file
        study_id: Study identifier
        dataset_id: Dataset identifier
        error_category: Optional category filter (resolve only this category)
        level: Optional level filter (resolve only this level)
        subject_id: Optional subject filter (resolve only this subject)

    Returns:
        Number of errors marked as resolved
    """
    if not error_log_path.exists():
        return 0

    now = datetime.now().isoformat()
    records = []
    resolved_count = 0

    with open(error_log_path) as f:
        for line in f:
            if line.strip():
                record = ErrorRecord.model_validate_json(line)

                # Check if this record matches filters
                matches = (
                    record.study_id == study_id
                    and record.dataset_id == dataset_id
                    and not record.resolved
                )
                if error_category:
                    matches = matches and record.error_category == error_category
                if level:
                    matches = matches and record.level == level
                if subject_id:
                    matches = matches and record.subject_id == subject_id

                if matches:
                    record.resolved = True
                    record.resolved_at = now
                    record.timestamp = now
                    resolved_count += 1

                records.append(record)

    # Write updated records
    with open(error_log_path, "w") as f:
        for record in sorted(records, key=lambda r: r.first_seen):
            f.write(record.model_dump_json() + "\n")

    logger.info(f"Marked {resolved_count} errors as resolved in {study_id}/{dataset_id}")
    return resolved_count


def garbage_collect(error_log_path: Path, days: int = 30) -> int:
    """Remove resolved errors older than N days.

    Args:
        error_log_path: Path to errors.jsonl file
        days: Number of days to retain resolved errors (default 30)

    Returns:
        Number of errors removed
    """
    if not error_log_path.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    records = []
    removed_count = 0

    with open(error_log_path) as f:
        for line in f:
            if line.strip():
                record = ErrorRecord.model_validate_json(line)

                # Remove if resolved and older than cutoff
                if record.resolved and record.resolved_at:
                    resolved_dt = datetime.fromisoformat(record.resolved_at)
                    if resolved_dt < cutoff:
                        removed_count += 1
                        continue  # Don't add to records list

                records.append(record)

    # Write remaining records
    if removed_count > 0:
        with open(error_log_path, "w") as f:
            for record in sorted(records, key=lambda r: r.first_seen):
                f.write(record.model_dump_json() + "\n")

    logger.info(f"Garbage collected {removed_count} resolved errors from {error_log_path}")
    return removed_count


def get_error_summary(error_log_path: Path) -> dict[str, Any]:
    """Get summary statistics from error log.

    Args:
        error_log_path: Path to errors.jsonl file

    Returns:
        Dictionary with summary stats:
        - total_errors: Total number of error records
        - unresolved_errors: Number of unresolved errors
        - resolved_errors: Number of resolved errors
        - by_category: Dict mapping category to count
        - by_type: Dict mapping type to count
        - by_level: Dict mapping level to count
    """
    if not error_log_path.exists():
        return {
            "total_errors": 0,
            "unresolved_errors": 0,
            "resolved_errors": 0,
            "by_category": {},
            "by_type": {},
            "by_level": {},
        }

    total = 0
    unresolved = 0
    resolved = 0
    by_category: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_level: dict[str, int] = {}

    with open(error_log_path) as f:
        for line in f:
            if line.strip():
                record = ErrorRecord.model_validate_json(line)
                total += 1

                if record.resolved:
                    resolved += 1
                else:
                    unresolved += 1

                by_category[record.error_category] = by_category.get(record.error_category, 0) + 1
                by_type[record.error_type] = by_type.get(record.error_type, 0) + 1
                by_level[record.level] = by_level.get(record.level, 0) + 1

    return {
        "total_errors": total,
        "unresolved_errors": unresolved,
        "resolved_errors": resolved,
        "by_category": by_category,
        "by_type": by_type,
        "by_level": by_level,
    }
