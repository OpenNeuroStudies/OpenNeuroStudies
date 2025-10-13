"""Unit tests for unorganized dataset tracking."""

from pathlib import Path

import pytest

from openneuro_studies.models import DerivativeDataset, UnorganizedDataset, UnorganizedReason
from openneuro_studies.organization.unorganized_tracker import (
    add_unorganized_dataset,
    get_unorganized_summary,
    load_unorganized_datasets,
    save_unorganized_datasets,
)


@pytest.mark.unit
@pytest.mark.ai_generated
def test_save_and_load_unorganized_datasets(tmp_path: Path) -> None:
    """Test saving and loading unorganized datasets."""
    config_dir = tmp_path / ".openneuro-studies"

    # Create test unorganized dataset
    unorganized = UnorganizedDataset(
        dataset_id="ds000212",
        derivative_id="fmriprep-21.0.1",
        tool_name="fmriprep",
        version="21.0.1",
        url="https://github.com/OpenNeuroDerivatives/ds000212-fmriprep",
        commit_sha="a" * 40,
        source_datasets=["ds000212"],
        reason=UnorganizedReason.RAW_DATASET_NOT_FOUND,
        discovered_at="2025-10-13T10:00:00",
        notes="Raw dataset ds000212 not found in discovered datasets",
    )

    # Save
    save_unorganized_datasets([unorganized], config_dir)

    # Verify file exists
    unorganized_file = config_dir / "unorganized-datasets.json"
    assert unorganized_file.exists()

    # Load and verify
    loaded = load_unorganized_datasets(config_dir)
    assert len(loaded) == 1
    assert loaded[0].dataset_id == "ds000212"
    assert loaded[0].reason == UnorganizedReason.RAW_DATASET_NOT_FOUND


@pytest.mark.unit
@pytest.mark.ai_generated
def test_add_unorganized_dataset(tmp_path: Path) -> None:
    """Test adding unorganized dataset (avoiding duplicates)."""
    config_dir = tmp_path / ".openneuro-studies"

    unorganized1 = UnorganizedDataset(
        dataset_id="ds000212",
        derivative_id="fmriprep-21.0.1",
        tool_name="fmriprep",
        version="21.0.1",
        url="https://github.com/OpenNeuroDerivatives/ds000212-fmriprep",
        commit_sha="a" * 40,
        source_datasets=["ds000212"],
        reason=UnorganizedReason.RAW_DATASET_NOT_FOUND,
        discovered_at="2025-10-13T10:00:00",
    )

    # Add first time
    add_unorganized_dataset(unorganized1, config_dir)
    loaded = load_unorganized_datasets(config_dir)
    assert len(loaded) == 1

    # Try adding same dataset_id again (should be skipped)
    add_unorganized_dataset(unorganized1, config_dir)
    loaded = load_unorganized_datasets(config_dir)
    assert len(loaded) == 1  # Still only one

    # Add different dataset
    unorganized2 = UnorganizedDataset(
        dataset_id="ds000213",
        url="https://github.com/OpenNeuroDerivatives/ds000213-mriqc",
        commit_sha="b" * 40,
        source_datasets=["ds000213"],
        reason=UnorganizedReason.INVALID_SOURCE_REFERENCE,
        discovered_at="2025-10-13T11:00:00",
    )
    add_unorganized_dataset(unorganized2, config_dir)
    loaded = load_unorganized_datasets(config_dir)
    assert len(loaded) == 2


@pytest.mark.unit
@pytest.mark.ai_generated
def test_get_unorganized_summary(tmp_path: Path) -> None:
    """Test getting summary counts by reason."""
    config_dir = tmp_path / ".openneuro-studies"

    unorganized_datasets = [
        UnorganizedDataset(
            dataset_id="ds000212",
            url="https://github.com/OpenNeuroDerivatives/ds000212-fmriprep",
            commit_sha="a" * 40,
            source_datasets=["ds000212"],
            reason=UnorganizedReason.RAW_DATASET_NOT_FOUND,
            discovered_at="2025-10-13T10:00:00",
        ),
        UnorganizedDataset(
            dataset_id="ds000213",
            url="https://github.com/OpenNeuroDerivatives/ds000213-fmriprep",
            commit_sha="b" * 40,
            source_datasets=["ds000213"],
            reason=UnorganizedReason.RAW_DATASET_NOT_FOUND,
            discovered_at="2025-10-13T10:01:00",
        ),
        UnorganizedDataset(
            dataset_id="ds000214",
            url="https://github.com/OpenNeuroDerivatives/ds000214-mriqc",
            commit_sha="c" * 40,
            source_datasets=["ds000214"],
            reason=UnorganizedReason.ORGANIZATION_ERROR,
            discovered_at="2025-10-13T10:02:00",
        ),
    ]

    save_unorganized_datasets(unorganized_datasets, config_dir)

    summary = get_unorganized_summary(config_dir)
    assert summary["raw_dataset_not_found"] == 2
    assert summary["organization_error"] == 1


@pytest.mark.unit
@pytest.mark.ai_generated
def test_from_derivative_dataset() -> None:
    """Test creating UnorganizedDataset from DerivativeDataset."""
    derivative = DerivativeDataset(
        dataset_id="ds000212",
        derivative_id="fmriprep-21.0.1",
        tool_name="fmriprep",
        version="21.0.1",
        url="https://github.com/OpenNeuroDerivatives/ds000212-fmriprep",
        commit_sha="a" * 40,
        datalad_uuid="12345678-1234-5678-1234-567812345678",
        source_datasets=["ds000212"],
    )

    unorganized = UnorganizedDataset.from_derivative_dataset(
        derivative,
        reason=UnorganizedReason.RAW_DATASET_NOT_FOUND,
        notes="Test note",
    )

    assert unorganized.dataset_id == derivative.dataset_id
    assert unorganized.derivative_id == derivative.derivative_id
    assert unorganized.tool_name == derivative.tool_name
    assert unorganized.version == derivative.version
    assert unorganized.url == derivative.url
    assert unorganized.commit_sha == derivative.commit_sha
    assert unorganized.datalad_uuid == derivative.datalad_uuid
    assert unorganized.source_datasets == derivative.source_datasets
    assert unorganized.reason == UnorganizedReason.RAW_DATASET_NOT_FOUND
    assert unorganized.notes == "Test note"
    assert unorganized.discovered_at  # Should be set


@pytest.mark.unit
@pytest.mark.ai_generated
def test_load_nonexistent_file(tmp_path: Path) -> None:
    """Test loading when unorganized-datasets.json doesn't exist."""
    config_dir = tmp_path / ".openneuro-studies"
    loaded = load_unorganized_datasets(config_dir)
    assert loaded == []
