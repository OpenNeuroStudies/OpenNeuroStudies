#!/usr/bin/env python3
"""Unit tests for hierarchical error tracking."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from openneuro_studies.lib.error_tracking import (
    ErrorCategory,
    ErrorLevel,
    ErrorRecord,
    categorize_error,
    garbage_collect,
    get_error_summary,
    log_error,
    mark_resolved,
)


def test_error_record_validation():
    """Test ErrorRecord Pydantic model validation."""
    record = ErrorRecord(
        timestamp="2026-03-23T10:30:15",
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="file",
        error_type="expected",
        error_category="missing_url",
        message="No remote URL found",
        first_seen="2026-03-23T10:30:15",
        last_seen="2026-03-23T10:30:15",
    )

    assert record.study_id == "study-ds001506"
    assert record.dataset_id == "ds001506"
    assert record.level == "file"
    assert record.count == 1  # default
    assert not record.resolved  # default


def test_categorize_error():
    """Test error categorization logic."""
    assert categorize_error("No remote URL found for file") == "missing_url"
    assert categorize_error("Network connection failed") == "network_error"
    assert categorize_error("Permission denied accessing file") == "permission_error"
    assert categorize_error("git-annex: failed to get") == "git_annex_error"
    assert categorize_error("Failed to parse JSON") == "parse_error"
    assert categorize_error("BIDS validation failed") == "validation_error"
    assert categorize_error("Unknown error occurred") == "other"


def test_log_error_basic(tmp_path: Path):
    """Test basic error logging."""
    error_log = tmp_path / "errors.jsonl"

    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="No remote URL found for file.nii.gz",
        level="file",
        subject_id="sub-01",
        file_path="sub-01/func/file.nii.gz",
    )

    # Verify file created
    assert error_log.exists()

    # Read and verify content
    with open(error_log) as f:
        line = f.readline()
        record = ErrorRecord.model_validate_json(line)

    assert record.study_id == "study-ds001506"
    assert record.dataset_id == "ds001506"
    assert record.level == "file"
    assert record.subject_id == "sub-01"
    assert record.file_path == "sub-01/func/file.nii.gz"
    assert record.error_category == "missing_url"
    assert record.count == 1


def test_log_error_deduplication(tmp_path: Path):
    """Test error deduplication - same error should increment count."""
    error_log = tmp_path / "errors.jsonl"

    # Log same error twice
    for _ in range(2):
        log_error(
            error_log_path=error_log,
            study_id="study-ds001506",
            dataset_id="ds001506",
            error_msg="No remote URL found for file.nii.gz",
            level="file",
            subject_id="sub-01",
            file_path="sub-01/func/file.nii.gz",
        )

    # Should have only one record with count=2
    with open(error_log) as f:
        lines = f.readlines()

    assert len(lines) == 1
    record = ErrorRecord.model_validate_json(lines[0])
    assert record.count == 2


def test_log_error_different_files_no_dedup(tmp_path: Path):
    """Test that different files create separate records."""
    error_log = tmp_path / "errors.jsonl"

    # Log errors for different files
    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="No remote URL found",
        level="file",
        file_path="sub-01/func/file1.nii.gz",
    )

    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="No remote URL found",
        level="file",
        file_path="sub-01/func/file2.nii.gz",
    )

    # Should have two separate records
    with open(error_log) as f:
        lines = f.readlines()

    assert len(lines) == 2


def test_mark_resolved(tmp_path: Path):
    """Test marking errors as resolved."""
    error_log = tmp_path / "errors.jsonl"

    # Log some errors
    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="Network error",
        level="dataset",
    )

    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="Missing URL",
        level="file",
    )

    # Mark network errors as resolved
    count = mark_resolved(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_category="network_error",
    )

    assert count == 1

    # Verify resolved status
    with open(error_log) as f:
        for line in f:
            record = ErrorRecord.model_validate_json(line)
            if record.error_category == "network_error":
                assert record.resolved
                assert record.resolved_at is not None
            else:
                assert not record.resolved


def test_garbage_collect(tmp_path: Path):
    """Test garbage collection of old resolved errors."""
    error_log = tmp_path / "errors.jsonl"

    # Create an old resolved error
    old_time = (datetime.now() - timedelta(days=35)).isoformat()
    old_record = ErrorRecord(
        timestamp=old_time,
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="dataset",
        error_type="expected",
        error_category="missing_url",
        message="Old error",
        first_seen=old_time,
        last_seen=old_time,
        resolved=True,
        resolved_at=old_time,
    )

    # Create a recent resolved error
    recent_time = (datetime.now() - timedelta(days=10)).isoformat()
    recent_record = ErrorRecord(
        timestamp=recent_time,
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="dataset",
        error_type="expected",
        error_category="network_error",
        message="Recent error",
        first_seen=recent_time,
        last_seen=recent_time,
        resolved=True,
        resolved_at=recent_time,
    )

    # Create an unresolved error
    unresolved_time = datetime.now().isoformat()
    unresolved_record = ErrorRecord(
        timestamp=unresolved_time,
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="dataset",
        error_type="expected",
        error_category="other",
        message="Unresolved error",
        first_seen=unresolved_time,
        last_seen=unresolved_time,
        resolved=False,
    )

    # Write all records
    with open(error_log, "w") as f:
        f.write(old_record.model_dump_json() + "\n")
        f.write(recent_record.model_dump_json() + "\n")
        f.write(unresolved_record.model_dump_json() + "\n")

    # Garbage collect (30 day threshold)
    removed = garbage_collect(error_log, days=30)

    assert removed == 1

    # Verify only old resolved error was removed
    with open(error_log) as f:
        lines = f.readlines()

    assert len(lines) == 2

    remaining_messages = {ErrorRecord.model_validate_json(line).message for line in lines}
    assert "Recent error" in remaining_messages
    assert "Unresolved error" in remaining_messages
    assert "Old error" not in remaining_messages


def test_get_error_summary(tmp_path: Path):
    """Test error summary statistics."""
    error_log = tmp_path / "errors.jsonl"

    # Log various errors
    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="Missing URL error 1",
        level="file",
    )

    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="Missing URL error 2",
        level="file",
    )

    log_error(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_msg="Network connection failed",
        level="dataset",
    )

    # Mark one as resolved
    mark_resolved(
        error_log_path=error_log,
        study_id="study-ds001506",
        dataset_id="ds001506",
        error_category="network_error",
    )

    # Get summary
    summary = get_error_summary(error_log)

    assert summary["total_errors"] == 3
    assert summary["unresolved_errors"] == 2
    assert summary["resolved_errors"] == 1
    assert summary["by_category"]["missing_url"] == 2
    assert summary["by_category"]["network_error"] == 1
    assert summary["by_level"]["file"] == 2
    assert summary["by_level"]["dataset"] == 1


def test_dedup_key_generation():
    """Test deduplication key generation."""
    record1 = ErrorRecord(
        timestamp="2026-03-23T10:30:15",
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="file",
        subject_id="sub-01",
        session_id="ses-01",
        file_path="file.nii.gz",
        error_type="expected",
        error_category="missing_url",
        message="No remote URL",
        first_seen="2026-03-23T10:30:15",
        last_seen="2026-03-23T10:30:15",
    )

    record2 = ErrorRecord(
        timestamp="2026-03-23T11:00:00",  # different timestamp
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="file",
        subject_id="sub-01",
        session_id="ses-01",
        file_path="file.nii.gz",
        error_type="expected",
        error_category="missing_url",
        message="No remote URL",
        first_seen="2026-03-23T10:30:15",
        last_seen="2026-03-23T11:00:00",  # different last_seen
        count=2,  # different count
    )

    # Same dedup key despite different timestamps/counts
    assert record1.get_dedup_key() == record2.get_dedup_key()

    # Different dedup key if file_path differs
    record3 = ErrorRecord(
        timestamp="2026-03-23T10:30:15",
        study_id="study-ds001506",
        dataset_id="ds001506",
        level="file",
        subject_id="sub-01",
        session_id="ses-01",
        file_path="different_file.nii.gz",  # different
        error_type="expected",
        error_category="missing_url",
        message="No remote URL",
        first_seen="2026-03-23T10:30:15",
        last_seen="2026-03-23T10:30:15",
    )

    assert record1.get_dedup_key() != record3.get_dedup_key()
