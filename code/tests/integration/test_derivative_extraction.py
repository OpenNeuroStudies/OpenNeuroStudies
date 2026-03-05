"""Integration tests for derivative metadata extraction.

Tests extraction against real study datasets with derivatives.
"""

import json
from pathlib import Path

import pytest
from datalad.distribution.dataset import Dataset

from openneuro_studies.metadata.derivative_extractor import (
    extract_anat_processed,
    extract_derivative_metadata,
    extract_descriptions,
    extract_func_processed,
    extract_tasks_processed,
    extract_template_spaces,
)
from openneuro_studies.metadata.studies_plus_derivatives_tsv import (
    STUDIES_DERIVATIVES_COLUMNS,
    collect_derivatives_for_study,
)

# Repository root for test datasets
REPO_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.fixture
def repo_root():
    """Return repository root path."""
    return REPO_ROOT


class TestRealDerivativeExtraction:
    """Test extraction against real derivative datasets."""

    def test_ds006131_fmriprep_extraction(self, repo_root):
        """Test extraction from ds006131 fMRIPrep derivative."""
        study_path = repo_root / "study-ds006131"
        deriv_path = study_path / "derivatives" / "fMRIPrep-24.1.1"
        raw_path = study_path / "sourcedata" / "ds006131"

        # Skip if derivative not installed
        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        raw_ds = Dataset(str(raw_path))
        if not raw_ds.is_installed():
            pytest.skip(f"Raw dataset not installed: {raw_path}")

        # Extract metadata
        result = extract_derivative_metadata(deriv_path, raw_path)

        # Verify basic structure
        assert "size_total" in result
        assert "size_annexed" in result
        assert "file_count" in result

        # Verify version tracking
        assert "processed_raw_version" in result
        assert "current_raw_version" in result
        assert "uptodate" in result
        assert "outdatedness" in result

        # Verify completeness
        assert "tasks_processed" in result
        assert "tasks_missing" in result
        assert "anat_processed" in result
        assert "func_processed" in result
        assert "processing_complete" in result

        # Verify spaces
        assert "template_spaces" in result
        assert "transform_spaces" in result

        # Verify descriptions
        assert "descriptions" in result

        # fMRIPrep should have processed anatomical data
        assert result["anat_processed"] is True

        # fMRIPrep should have functional data if raw has it
        # (we need to check raw to know for sure)

        # Descriptions should be valid JSON
        if result["descriptions"] != "n/a":
            desc_dict = json.loads(result["descriptions"])
            assert isinstance(desc_dict, dict)

    def test_ds000001_fmriprep_extraction(self, repo_root):
        """Test extraction from ds000001 fMRIPrep derivative."""
        study_path = repo_root / "study-ds000001"
        deriv_path = study_path / "derivatives" / "fMRIPrep-21.0.1"
        raw_path = study_path / "sourcedata" / "ds000001"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        raw_ds = Dataset(str(raw_path))
        if not raw_ds.is_installed():
            pytest.skip(f"Raw dataset not installed: {raw_path}")

        result = extract_derivative_metadata(deriv_path, raw_path)

        # Basic checks
        assert result["anat_processed"] is True
        assert result["func_processed"] is True

        # Tasks should be extracted
        tasks = result["tasks_processed"]
        if tasks != "n/a":
            # Should be comma-separated
            assert "," in tasks or tasks.isalnum()

    def test_ds006131_mriqc_extraction(self, repo_root):
        """Test extraction from ds006131 MRIQC derivative."""
        study_path = repo_root / "study-ds006131"
        deriv_path = study_path / "derivatives" / "MRIQC-25.0.0rc0"
        raw_path = study_path / "sourcedata" / "ds006131"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        raw_ds = Dataset(str(raw_path))
        if not raw_ds.is_installed():
            pytest.skip(f"Raw dataset not installed: {raw_path}")

        result = extract_derivative_metadata(deriv_path, raw_path)

        # MRIQC produces quality control outputs
        # Check that extraction doesn't fail
        assert "descriptions" in result


class TestSubdatasetInstallation:
    """Test temporary subdataset installation."""

    def test_collect_derivatives_ds006131(self, repo_root):
        """Test collecting derivatives for ds006131 with temporary installation."""
        study_path = repo_root / "study-ds006131"

        study_ds = Dataset(str(study_path))
        if not study_ds.is_installed():
            pytest.skip(f"Study not installed: {study_path}")

        # Get initial state of derivatives
        initial_installed = {}
        for deriv_name in ["fMRIPrep-24.1.1", "MRIQC-25.0.0rc0", "ASLPrep-0.7.5", "qsiprep-1.0.1.dev0+gee9aa2e.d20250115"]:
            deriv_path = study_path / "derivatives" / deriv_name
            if deriv_path.exists():
                ds = Dataset(str(deriv_path))
                initial_installed[deriv_name] = ds.is_installed()

        # Collect derivatives (should handle installation temporarily)
        derivatives = collect_derivatives_for_study(study_path)

        # Should have found derivatives from .gitmodules
        assert len(derivatives) > 0

        # Check that all expected columns are present
        for deriv in derivatives:
            for col in STUDIES_DERIVATIVES_COLUMNS:
                assert col in deriv, f"Missing column: {col}"

        # Verify derivative IDs
        deriv_ids = {d["derivative_id"] for d in derivatives}
        # Should have at least fMRIPrep and MRIQC
        assert any("fMRIPrep" in d for d in deriv_ids)
        assert any("MRIQC" in d for d in deriv_ids)

        # Check final state matches initial state (temporary installation)
        for deriv_name, was_installed in initial_installed.items():
            deriv_path = study_path / "derivatives" / deriv_name
            if deriv_path.exists():
                ds = Dataset(str(deriv_path))
                is_installed = ds.is_installed()
                # Should match initial state
                assert is_installed == was_installed, \
                    f"{deriv_name} installation state changed: {was_installed} -> {is_installed}"

    def test_collect_derivatives_ds000001(self, repo_root):
        """Test collecting derivatives for ds000001."""
        study_path = repo_root / "study-ds000001"

        study_ds = Dataset(str(study_path))
        if not study_ds.is_installed():
            pytest.skip(f"Study not installed: {study_path}")

        derivatives = collect_derivatives_for_study(study_path)

        # Should have found derivatives
        assert len(derivatives) > 0

        # Check structure
        for deriv in derivatives:
            assert deriv["study_id"] == "study-ds000001"
            assert "derivative_id" in deriv
            assert "tool_name" in deriv
            assert "tool_version" in deriv
            assert "url" in deriv


class TestColumnCompleteness:
    """Test that all required columns are extracted."""

    def test_all_columns_present(self, repo_root):
        """Test that all STUDIES_DERIVATIVES_COLUMNS are populated."""
        study_path = repo_root / "study-ds006131"

        study_ds = Dataset(str(study_path))
        if not study_ds.is_installed():
            pytest.skip(f"Study not installed: {study_path}")

        derivatives = collect_derivatives_for_study(study_path)

        if not derivatives:
            pytest.skip("No derivatives found")

        # Check first derivative
        deriv = derivatives[0]

        # All columns should be present
        for col in STUDIES_DERIVATIVES_COLUMNS:
            assert col in deriv, f"Missing column: {col}"

        # Specific column checks
        assert deriv["study_id"] == "study-ds006131"
        assert deriv["derivative_id"] != ""
        assert deriv["tool_name"] != ""
        assert deriv["tool_version"] != ""
        assert deriv["datalad_uuid"] != ""
        assert deriv["url"] != ""

        # Metadata columns should have values (not necessarily valid data)
        # They can be "n/a" or actual values
        assert "size_total" in deriv
        assert "size_annexed" in deriv
        assert "file_count" in deriv
        assert "processed_raw_version" in deriv
        assert "current_raw_version" in deriv
        assert "uptodate" in deriv
        assert "outdatedness" in deriv
        assert "tasks_processed" in deriv
        assert "tasks_missing" in deriv
        assert "anat_processed" in deriv
        assert "func_processed" in deriv
        assert "processing_complete" in deriv
        assert "template_spaces" in deriv
        assert "transform_spaces" in deriv
        assert "descriptions" in deriv


class TestErrorHandling:
    """Test error handling in extraction."""

    def test_extraction_with_missing_raw(self, repo_root, tmp_path):
        """Test extraction when raw dataset is not accessible."""
        study_path = repo_root / "study-ds006131"
        deriv_path = study_path / "derivatives" / "fMRIPrep-24.1.1"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        # Use non-existent raw path
        fake_raw_path = tmp_path / "nonexistent"

        # Should not crash, should return n/a values
        result = extract_derivative_metadata(deriv_path, fake_raw_path)

        # Should still have basic structure
        assert "tasks_processed" in result
        assert "anat_processed" in result
        assert "func_processed" in result

        # Version tracking should handle missing raw gracefully
        assert result["current_raw_version"] == "n/a"


class TestSpecificExtractions:
    """Test specific extraction functions with real data."""

    def test_tasks_extraction_ds006131(self, repo_root):
        """Test task extraction from real fMRIPrep derivative."""
        deriv_path = repo_root / "study-ds006131" / "derivatives" / "fMRIPrep-24.1.1"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        tasks = extract_tasks_processed(deriv_path)

        # Should extract tasks or n/a
        assert tasks != ""
        if tasks != "n/a":
            # Should be comma-separated and sorted
            task_list = tasks.split(",")
            assert task_list == sorted(task_list)

    def test_template_spaces_ds006131(self, repo_root):
        """Test template space extraction from real fMRIPrep derivative."""
        deriv_path = repo_root / "study-ds006131" / "derivatives" / "fMRIPrep-24.1.1"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        spaces = extract_template_spaces(deriv_path)

        # Should extract spaces or n/a
        assert spaces != ""
        if spaces != "n/a":
            # Should be comma-separated and sorted
            space_list = spaces.split(",")
            assert space_list == sorted(space_list)

    def test_descriptions_ds006131(self, repo_root):
        """Test description extraction from real fMRIPrep derivative."""
        deriv_path = repo_root / "study-ds006131" / "derivatives" / "fMRIPrep-24.1.1"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        descriptions = extract_descriptions(deriv_path)

        # Should return valid JSON
        if descriptions != "{}":
            desc_dict = json.loads(descriptions)
            assert isinstance(desc_dict, dict)

            # All keys should be strings, all values should be integers
            for key, value in desc_dict.items():
                assert isinstance(key, str)
                assert isinstance(value, int)
                assert value > 0

    def test_modality_flags_ds006131(self, repo_root):
        """Test modality flags from real fMRIPrep derivative."""
        deriv_path = repo_root / "study-ds006131" / "derivatives" / "fMRIPrep-24.1.1"

        ds = Dataset(str(deriv_path))
        if not ds.is_installed():
            pytest.skip(f"Derivative not installed: {deriv_path}")

        anat_processed = extract_anat_processed(deriv_path)
        func_processed = extract_func_processed(deriv_path)

        # fMRIPrep should process at least one modality
        assert anat_processed is True or func_processed is True

        # Both should be booleans
        assert isinstance(anat_processed, bool)
        assert isinstance(func_processed, bool)
