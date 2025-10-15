"""Unit tests for discover command update mode."""

import json
from pathlib import Path

import pytest

from openneuro_studies.discovery.dataset_finder import DatasetFinder
from openneuro_studies.models import DerivativeDataset, SourceDataset


@pytest.mark.ai_generated
def test_save_discovered_update_mode_merges_with_existing(tmp_path: Path) -> None:
    """Test that update mode merges new datasets with existing ones."""
    output_file = tmp_path / "discovered-datasets.json"

    # Create initial discovered datasets
    initial_raw = SourceDataset(
        dataset_id="ds000001",
        url="https://github.com/OpenNeuroDatasets/ds000001.git",
        commit_sha="a" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 1"],
    )
    initial_derivative = DerivativeDataset(
        dataset_id="ds000001-mriqc",
        derivative_id="mriqc-0.16.1",
        tool_name="mriqc",
        version="0.16.1",
        url="https://github.com/OpenNeuroDerivatives/ds000001-mriqc.git",
        commit_sha="b" * 40,  # Valid 40-character SHA
        datalad_uuid=None,
        source_datasets=["ds000001"],
    )

    # Save initial datasets in overwrite mode
    initial_discovered = {"raw": [initial_raw], "derivative": [initial_derivative]}

    # Create a mock finder (we only need save_discovered method)
    class MockFinder:
        def save_discovered(self, discovered, output_path, mode="update"):
            # Use the actual implementation from DatasetFinder
            DatasetFinder.save_discovered(self, discovered, output_path, mode)

    finder = MockFinder()
    finder.save_discovered(initial_discovered, str(output_file), mode="overwrite")

    # Verify initial file was created
    assert output_file.exists()
    with open(output_file) as f:
        initial_data = json.load(f)
    assert len(initial_data["raw"]) == 1
    assert len(initial_data["derivative"]) == 1

    # Create new datasets to discover
    new_raw = SourceDataset(
        dataset_id="ds000113",
        url="https://github.com/OpenNeuroDatasets/ds000113.git",
        commit_sha="c" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 2"],
    )

    # Save with update mode - should merge with existing
    new_discovered = {"raw": [new_raw], "derivative": []}
    finder.save_discovered(new_discovered, str(output_file), mode="update")

    # Verify both datasets are present
    with open(output_file) as f:
        merged_data = json.load(f)

    assert len(merged_data["raw"]) == 2
    assert len(merged_data["derivative"]) == 1

    # Check both raw datasets are present
    raw_ids = {d["dataset_id"] for d in merged_data["raw"]}
    assert raw_ids == {"ds000001", "ds000113"}

    # Check derivative is still there
    assert merged_data["derivative"][0]["dataset_id"] == "ds000001-mriqc"


@pytest.mark.ai_generated
def test_save_discovered_update_mode_deduplicates(tmp_path: Path) -> None:
    """Test that update mode deduplicates datasets by (dataset_id, url) tuple."""
    output_file = tmp_path / "discovered-datasets.json"

    # Create initial dataset
    initial_raw = SourceDataset(
        dataset_id="ds000001",
        url="https://github.com/OpenNeuroDatasets/ds000001.git",
        commit_sha="a" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 1"],
    )

    class MockFinder:
        def save_discovered(self, discovered, output_path, mode="update"):
            DatasetFinder.save_discovered(self, discovered, output_path, mode)

    finder = MockFinder()
    finder.save_discovered(
        {"raw": [initial_raw], "derivative": []}, str(output_file), mode="overwrite"
    )

    # Try to save the same dataset again in update mode
    # Should NOT create duplicate
    duplicate_raw = SourceDataset(
        dataset_id="ds000001",
        url="https://github.com/OpenNeuroDatasets/ds000001.git",
        commit_sha="b" * 40,  # Different commit SHA (valid 40-character)
        bids_version="1.1.0",  # Different version
        license="CC0",
        authors=["Author 1", "Author 2"],  # Different authors
    )

    finder.save_discovered(
        {"raw": [duplicate_raw], "derivative": []}, str(output_file), mode="update"
    )

    # Verify only one dataset exists (original should be kept)
    with open(output_file) as f:
        data = json.load(f)

    assert len(data["raw"]) == 1
    # Should keep the original commit SHA
    assert data["raw"][0]["commit_sha"] == "a" * 40


@pytest.mark.ai_generated
def test_save_discovered_overwrite_mode_replaces(tmp_path: Path) -> None:
    """Test that overwrite mode replaces all existing datasets."""
    output_file = tmp_path / "discovered-datasets.json"

    # Create initial dataset
    initial_raw = SourceDataset(
        dataset_id="ds000001",
        url="https://github.com/OpenNeuroDatasets/ds000001.git",
        commit_sha="a" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 1"],
    )

    class MockFinder:
        def save_discovered(self, discovered, output_path, mode="update"):
            DatasetFinder.save_discovered(self, discovered, output_path, mode)

    finder = MockFinder()
    finder.save_discovered(
        {"raw": [initial_raw], "derivative": []}, str(output_file), mode="overwrite"
    )

    # Save new dataset with overwrite mode - should replace
    new_raw = SourceDataset(
        dataset_id="ds000113",
        url="https://github.com/OpenNeuroDatasets/ds000113.git",
        commit_sha="b" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 2"],
    )

    finder.save_discovered({"raw": [new_raw], "derivative": []}, str(output_file), mode="overwrite")

    # Verify only new dataset exists
    with open(output_file) as f:
        data = json.load(f)

    assert len(data["raw"]) == 1
    assert data["raw"][0]["dataset_id"] == "ds000113"


@pytest.mark.ai_generated
def test_save_discovered_update_mode_no_existing_file(tmp_path: Path) -> None:
    """Test that update mode works when no existing file exists."""
    output_file = tmp_path / "discovered-datasets.json"

    # File doesn't exist yet
    assert not output_file.exists()

    # Save in update mode - should work like overwrite when file doesn't exist
    new_raw = SourceDataset(
        dataset_id="ds000001",
        url="https://github.com/OpenNeuroDatasets/ds000001.git",
        commit_sha="a" * 40,  # Valid 40-character SHA
        bids_version="1.0.0",
        license="CC0",
        authors=["Author 1"],
    )

    class MockFinder:
        def save_discovered(self, discovered, output_path, mode="update"):
            DatasetFinder.save_discovered(self, discovered, output_path, mode)

    finder = MockFinder()
    finder.save_discovered({"raw": [new_raw], "derivative": []}, str(output_file), mode="update")

    # Verify file was created with the dataset
    assert output_file.exists()
    with open(output_file) as f:
        data = json.load(f)

    assert len(data["raw"]) == 1
    assert data["raw"][0]["dataset_id"] == "ds000001"
