"""Tests for custom exception classes."""

import pytest

from openneuro_studies.lib.exceptions import (
    DatasetNotFoundError,
    ExtractionError,
    GitHubAPIError,
    NetworkError,
    OpenNeuroStudiesError,
    ValidationError,
)


def test_base_exception():
    """Test base OpenNeuroStudiesError."""
    exc = OpenNeuroStudiesError("Base error")
    assert str(exc) == "Base error"
    assert isinstance(exc, Exception)


def test_network_error_basic():
    """Test NetworkError with basic message."""
    exc = NetworkError("Network failed")
    assert "Network failed" in str(exc)


def test_network_error_with_url():
    """Test NetworkError with URL information."""
    exc = NetworkError(
        message="Failed to fetch",
        url="https://example.com/data.nii.gz",
    )
    message = str(exc)
    assert "Failed to fetch" in message
    assert "https://example.com/data.nii.gz" in message


def test_network_error_with_attempts():
    """Test NetworkError with retry attempts."""
    exc = NetworkError(
        message="Network failed",
        attempts=5,
    )
    message = str(exc)
    assert "Network failed" in message
    assert "Failed after 5 attempts" in message


def test_network_error_with_last_error():
    """Test NetworkError with last error information."""
    last_error = OSError("Connection timeout")
    exc = NetworkError(
        message="Network failed",
        url="https://example.com/data.nii.gz",
        attempts=3,
        last_error=last_error,
    )
    message = str(exc)
    assert "Network failed" in message
    assert "https://example.com/data.nii.gz" in message
    assert "Failed after 3 attempts" in message
    assert "OSError" in message
    assert "Connection timeout" in message


def test_extraction_error_basic():
    """Test ExtractionError with basic message."""
    exc = ExtractionError("Extraction failed")
    assert "Extraction failed" in str(exc)


def test_extraction_error_with_file_path():
    """Test ExtractionError with file path."""
    exc = ExtractionError(
        message="Invalid header",
        file_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
    )
    message = str(exc)
    assert "Invalid header" in message
    assert "sub-01/func/sub-01_task-rest_bold.nii.gz" in message


def test_extraction_error_with_field():
    """Test ExtractionError with field name."""
    exc = ExtractionError(
        message="Failed to extract",
        field="bold_voxels",
    )
    message = str(exc)
    assert "Failed to extract" in message
    assert "bold_voxels" in message


def test_extraction_error_with_all_info():
    """Test ExtractionError with all information."""
    exc = ExtractionError(
        message="Invalid NIfTI header",
        file_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
        field="shape",
    )
    message = str(exc)
    assert "Invalid NIfTI header" in message
    assert "sub-01/func/sub-01_task-rest_bold.nii.gz" in message
    assert "shape" in message


def test_dataset_not_found_error():
    """Test DatasetNotFoundError."""
    exc = DatasetNotFoundError("Dataset ds000001 not found")
    assert "ds000001" in str(exc)
    assert isinstance(exc, OpenNeuroStudiesError)


def test_github_api_error():
    """Test GitHubAPIError."""
    exc = GitHubAPIError("API rate limit exceeded")
    assert "rate limit" in str(exc)
    assert isinstance(exc, OpenNeuroStudiesError)


def test_validation_error():
    """Test ValidationError."""
    exc = ValidationError("BIDS validation failed")
    assert "validation failed" in str(exc)
    assert isinstance(exc, OpenNeuroStudiesError)


def test_exception_hierarchy():
    """Test that all exceptions inherit from base."""
    exceptions = [
        NetworkError("test"),
        ExtractionError("test"),
        DatasetNotFoundError("test"),
        GitHubAPIError("test"),
        ValidationError("test"),
    ]

    for exc in exceptions:
        assert isinstance(exc, OpenNeuroStudiesError)
        assert isinstance(exc, Exception)


def test_network_error_attributes():
    """Test NetworkError attribute access."""
    last_error = OSError("Connection timeout")
    exc = NetworkError(
        message="Network failed",
        url="https://example.com",
        attempts=5,
        last_error=last_error,
    )

    assert exc.message == "Network failed"
    assert exc.url == "https://example.com"
    assert exc.attempts == 5
    assert exc.last_error is last_error


def test_extraction_error_attributes():
    """Test ExtractionError attribute access."""
    exc = ExtractionError(
        message="Extraction failed",
        file_path="/path/to/file",
        field="field_name",
    )

    assert exc.message == "Extraction failed"
    assert exc.file_path == "/path/to/file"
    assert exc.field == "field_name"


def test_exception_can_be_raised_and_caught():
    """Test that exceptions can be raised and caught normally."""
    with pytest.raises(NetworkError) as exc_info:
        raise NetworkError("Test error")

    assert "Test error" in str(exc_info.value)

    with pytest.raises(ExtractionError) as exc_info:
        raise ExtractionError("Test extraction error")

    assert "Test extraction error" in str(exc_info.value)
