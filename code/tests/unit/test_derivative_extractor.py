"""Unit tests for derivative metadata extraction.

Tests all extraction functions in derivative_extractor.py using git tree access
without downloading annexed content.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from openneuro_studies.metadata.derivative_extractor import (
    extract_anat_processed,
    extract_derivative_metadata,
    extract_derivative_stats,
    extract_descriptions,
    extract_func_processed,
    extract_processing_complete,
    extract_tasks_missing,
    extract_tasks_processed,
    extract_template_spaces,
    extract_transform_spaces,
    extract_version_tracking,
)


class TestExtractDerivativeStats:
    """Test git-annex info extraction."""

    def test_extract_stats_basic(self, tmp_path):
        """Test basic stats extraction from git-annex info."""
        # Mock git-annex info output
        annex_info = {
            "size of annexed files in working tree": "1234567890",
            "local annex size": "9876543210",
        }

        with patch("subprocess.run") as mock_run:
            # Mock git annex info call
            mock_run.return_value = Mock(
                stdout=json.dumps(annex_info),
                returncode=0,
            )

            # Call extraction (first call is annex info, second is ls-files)
            mock_run.side_effect = [
                Mock(stdout=json.dumps(annex_info), returncode=0),
                Mock(stdout="file1.nii.gz\nfile2.nii.gz\nfile3.json", returncode=0),
            ]

            result = extract_derivative_stats(tmp_path)

            assert result["size_annexed"] == "1234567890"
            assert result["size_total"] == "9876543210"
            assert result["file_count"] == 3

    def test_extract_stats_no_annex(self, tmp_path):
        """Test stats extraction when git-annex info fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git annex info")

            result = extract_derivative_stats(tmp_path)

            assert result["size_total"] == "n/a"
            assert result["size_annexed"] == "n/a"
            assert result["file_count"] == "n/a"

    def test_extract_stats_empty_output(self, tmp_path):
        """Test stats extraction with empty git-annex output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            result = extract_derivative_stats(tmp_path)

            assert result["size_total"] == "n/a"
            assert result["size_annexed"] == "n/a"
            assert result["file_count"] == "n/a"


class TestVersionTracking:
    """Test version tracking extraction."""

    def test_version_tracking_uptodate(self, tmp_path):
        """Test version tracking when derivative is up-to-date."""
        # Create mock dataset_description.json
        deriv_path = tmp_path / "derivative"
        deriv_path.mkdir()
        dd_path = deriv_path / "dataset_description.json"
        dd_path.write_text(json.dumps({
            "SourceDatasets": [{"Version": "1.0.0"}]
        }))

        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        with patch("subprocess.run") as mock_run:
            # Mock git describe to return matching version
            mock_run.return_value = Mock(stdout="1.0.0\n", returncode=0)

            result = extract_version_tracking(deriv_path, raw_path)

            assert result["processed_raw_version"] == "1.0.0"
            assert result["current_raw_version"] == "1.0.0"
            assert result["uptodate"] is True
            assert result["outdatedness"] == 0

    def test_version_tracking_outdated(self, tmp_path):
        """Test version tracking when derivative is outdated."""
        deriv_path = tmp_path / "derivative"
        deriv_path.mkdir()
        dd_path = deriv_path / "dataset_description.json"
        dd_path.write_text(json.dumps({
            "SourceDatasets": [{"Version": "1.0.0"}]
        }))

        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if "describe" in cmd:
                    return Mock(stdout="1.2.0\n", returncode=0)
                elif "rev-list" in cmd:
                    return Mock(stdout="5\n", returncode=0)
                raise ValueError(f"Unexpected command: {cmd}")

            mock_run.side_effect = side_effect

            result = extract_version_tracking(deriv_path, raw_path)

            assert result["processed_raw_version"] == "1.0.0"
            assert result["current_raw_version"] == "1.2.0"
            assert result["uptodate"] is False
            assert result["outdatedness"] == 5

    def test_version_tracking_no_source_datasets(self, tmp_path):
        """Test version tracking when dataset_description.json has no SourceDatasets."""
        deriv_path = tmp_path / "derivative"
        deriv_path.mkdir()
        dd_path = deriv_path / "dataset_description.json"
        dd_path.write_text(json.dumps({"Name": "Test Derivative"}))

        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="1.0.0\n", returncode=0)

            result = extract_version_tracking(deriv_path, raw_path)

            assert result["processed_raw_version"] == "n/a"
            assert result["current_raw_version"] == "1.0.0"
            assert result["uptodate"] is False
            assert result["outdatedness"] == "n/a"

    def test_version_tracking_no_dd_file(self, tmp_path):
        """Test version tracking when dataset_description.json doesn't exist."""
        deriv_path = tmp_path / "derivative"
        deriv_path.mkdir()

        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="1.0.0\n", returncode=0)

            result = extract_version_tracking(deriv_path, raw_path)

            assert result["processed_raw_version"] == "n/a"
            assert result["current_raw_version"] == "1.0.0"


class TestTasksExtraction:
    """Test task extraction from func/ directory."""

    def test_tasks_processed_multiple_tasks(self, tmp_path):
        """Test extraction of multiple tasks from derivative."""
        files = [
            "sub-01/func/sub-01_task-rest_bold.nii.gz",
            "sub-01/func/sub-01_task-rest_bold.json",
            "sub-01/func/sub-01_task-finger_bold.nii.gz",
            "sub-02/func/sub-02_task-rest_bold.nii.gz",
            "sub-02/func/sub-02_task-nback_bold.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_tasks_processed(tmp_path)

            # Should be sorted and unique
            assert result == "finger,nback,rest"

    def test_tasks_processed_no_func(self, tmp_path):
        """Test extraction when no func/ directory exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            result = extract_tasks_processed(tmp_path)

            assert result == "n/a"

    def test_tasks_processed_only_confounds(self, tmp_path):
        """Test extraction when func/ has only confounds (no data files)."""
        files = [
            "sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv",
            "sub-02/func/sub-02_task-rest_desc-confounds_timeseries.tsv",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_tasks_processed(tmp_path)

            # Confounds don't count as processed data
            assert result == "n/a"

    def test_tasks_missing_all_complete(self, tmp_path):
        """Test tasks_missing when all raw tasks are in derivative."""
        deriv_path = tmp_path / "derivative"
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            # Both have same tasks
            mock_run.return_value = Mock(
                stdout="sub-01/func/sub-01_task-rest_bold.nii.gz",
                returncode=0,
            )

            result = extract_tasks_missing(deriv_path, raw_path, "rest")

            assert result == ""  # Empty means all tasks processed

    def test_tasks_missing_partial(self, tmp_path):
        """Test tasks_missing when some tasks are missing."""
        deriv_path = tmp_path / "derivative"
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if str(raw_path) in str(cmd):
                    # Raw has rest and finger
                    return Mock(
                        stdout="sub-01/func/sub-01_task-rest_bold.nii.gz\n"
                               "sub-01/func/sub-01_task-finger_bold.nii.gz",
                        returncode=0,
                    )
                # Derivative only has rest
                return Mock(stdout="sub-01/func/sub-01_task-rest_bold.nii.gz", returncode=0)

            mock_run.side_effect = side_effect

            result = extract_tasks_missing(deriv_path, raw_path, "rest")

            assert result == "finger"

    def test_tasks_missing_no_raw_func(self, tmp_path):
        """Test tasks_missing when raw has no func/ directory."""
        deriv_path = tmp_path / "derivative"
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            result = extract_tasks_missing(deriv_path, raw_path, "rest")

            assert result == ""  # No raw func means nothing missing


class TestModalityExtraction:
    """Test anatomical and functional modality detection."""

    def test_anat_processed_with_desc(self, tmp_path):
        """Test anat detection with desc- entity."""
        files = [
            "sub-01/anat/sub-01_desc-preproc_T1w.nii.gz",
            "sub-01/anat/sub-01_desc-brain_mask.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_anat_processed(tmp_path)

            assert result is True

    def test_anat_processed_with_space(self, tmp_path):
        """Test anat detection with space- entity."""
        files = [
            "sub-01/anat/sub-01_space-MNI152NLin2009cAsym_T1w.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_anat_processed(tmp_path)

            assert result is True

    def test_anat_processed_with_segmentation(self, tmp_path):
        """Test anat detection with segmentation files."""
        files = [
            "sub-01/anat/sub-01_dseg.nii.gz",
            "sub-01/anat/sub-01_probseg.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_anat_processed(tmp_path)

            assert result is True

    def test_anat_processed_only_raw(self, tmp_path):
        """Test anat detection with only raw anatomicals (no processing)."""
        files = [
            "sub-01/anat/sub-01_T1w.nii.gz",
            "sub-01/anat/sub-01_T1w.json",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_anat_processed(tmp_path)

            assert result is False

    def test_anat_processed_only_transforms(self, tmp_path):
        """Test anat detection with only transforms (not data)."""
        files = [
            "sub-01/anat/sub-01_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_anat_processed(tmp_path)

            assert result is False

    def test_func_processed_with_preproc(self, tmp_path):
        """Test func detection with desc-preproc."""
        files = [
            "sub-01/func/sub-01_task-rest_desc-preproc_bold.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_func_processed(tmp_path)

            assert result is True

    def test_func_processed_with_space(self, tmp_path):
        """Test func detection with space- entity."""
        files = [
            "sub-01/func/sub-01_task-rest_space-MNI152NLin2009cAsym_bold.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_func_processed(tmp_path)

            assert result is True

    def test_func_processed_with_boldref(self, tmp_path):
        """Test func detection with boldref files."""
        files = [
            "sub-01/func/sub-01_task-rest_boldref.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_func_processed(tmp_path)

            assert result is True

    def test_func_processed_no_func(self, tmp_path):
        """Test func detection when no func/ directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)

            result = extract_func_processed(tmp_path)

            assert result is False


class TestProcessingComplete:
    """Test processing completeness detection."""

    def test_processing_complete_all_done(self, tmp_path):
        """Test completeness when all modalities processed."""
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            # Raw has anat and func
            mock_run.return_value = Mock(
                stdout="040000 tree anat\n040000 tree func\n",
                returncode=0,
            )

            result = extract_processing_complete(
                tasks_missing="",
                anat_processed=True,
                func_processed=True,
                raw_path=raw_path,
            )

            assert result is True

    def test_processing_complete_missing_tasks(self, tmp_path):
        """Test completeness when tasks are missing."""
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="040000 tree anat\n040000 tree func\n",
                returncode=0,
            )

            result = extract_processing_complete(
                tasks_missing="finger,memory",
                anat_processed=True,
                func_processed=True,
                raw_path=raw_path,
            )

            assert result is False

    def test_processing_complete_missing_anat(self, tmp_path):
        """Test completeness when anat not processed."""
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="040000 tree anat\n040000 tree func\n",
                returncode=0,
            )

            result = extract_processing_complete(
                tasks_missing="",
                anat_processed=False,
                func_processed=True,
                raw_path=raw_path,
            )

            assert result is False

    def test_processing_complete_missing_func(self, tmp_path):
        """Test completeness when func not processed."""
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stdout="040000 tree anat\n040000 tree func\n",
                returncode=0,
            )

            result = extract_processing_complete(
                tasks_missing="",
                anat_processed=True,
                func_processed=False,
                raw_path=raw_path,
            )

            assert result is False

    def test_processing_complete_anat_only_dataset(self, tmp_path):
        """Test completeness for anat-only dataset."""
        raw_path = tmp_path / "raw"

        with patch("subprocess.run") as mock_run:
            # Raw has only anat
            mock_run.return_value = Mock(
                stdout="040000 tree anat\n",
                returncode=0,
            )

            result = extract_processing_complete(
                tasks_missing="",
                anat_processed=True,
                func_processed=False,
                raw_path=raw_path,
            )

            assert result is True


class TestSpaceExtraction:
    """Test template space extraction."""

    def test_template_spaces_multiple(self, tmp_path):
        """Test extraction of multiple template spaces."""
        files = [
            "sub-01/anat/sub-01_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz",
            "sub-01/func/sub-01_task-rest_space-MNI152NLin2009cAsym_bold.nii.gz",
            "sub-01/func/sub-01_task-rest_space-T1w_bold.nii.gz",
            "sub-01/anat/sub-01_space-fsaverage5_hemi-L_thickness.shape.gii",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_template_spaces(tmp_path)

            # Should be sorted
            assert result == "MNI152NLin2009cAsym,T1w,fsaverage5"

    def test_template_spaces_exclude_transforms(self, tmp_path):
        """Test that transform files don't count as data spaces."""
        files = [
            "sub-01/anat/sub-01_space-MNI152NLin2009cAsym_T1w.nii.gz",
            "sub-01/anat/sub-01_from-T1w_to-MNI152NLin6Asym_mode-image_xfm.h5",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_template_spaces(tmp_path)

            # Only MNI152NLin2009cAsym has data
            assert result == "MNI152NLin2009cAsym"

    def test_template_spaces_none(self, tmp_path):
        """Test extraction when no template spaces exist."""
        files = [
            "sub-01/anat/sub-01_T1w.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_template_spaces(tmp_path)

            assert result == "n/a"

    def test_transform_spaces_only(self, tmp_path):
        """Test extraction of transform-only spaces."""
        files = [
            "sub-01/anat/sub-01_space-MNI152NLin2009cAsym_T1w.nii.gz",
            "sub-01/anat/sub-01_from-T1w_to-MNI152NLin6Asym_mode-image_xfm.h5",
            "sub-01/anat/sub-01_from-fsnative_to-T1w_mode-image_xfm.txt",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_transform_spaces(tmp_path, "MNI152NLin2009cAsym,T1w")

            # MNI152NLin6Asym and fsnative only have transforms
            assert result == "MNI152NLin6Asym,fsnative"

    def test_transform_spaces_none(self, tmp_path):
        """Test extraction when all spaces have data."""
        files = [
            "sub-01/anat/sub-01_space-MNI152NLin2009cAsym_T1w.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_transform_spaces(tmp_path, "MNI152NLin2009cAsym")

            assert result == ""


class TestDescriptions:
    """Test description entity extraction."""

    def test_descriptions_multiple_types(self, tmp_path):
        """Test extraction of multiple description types."""
        files = [
            "sub-01/anat/sub-01_desc-preproc_T1w.nii.gz",
            "sub-01/anat/sub-01_desc-brain_mask.nii.gz",
            "sub-01/func/sub-01_task-rest_desc-preproc_bold.nii.gz",
            "sub-02/func/sub-02_task-rest_desc-preproc_bold.nii.gz",
            "sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv",
            "sub-02/func/sub-02_task-rest_desc-confounds_timeseries.tsv",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_descriptions(tmp_path)

            result_dict = json.loads(result)
            # Sorted by key
            assert result_dict == {
                "brain": 1,
                "confounds": 2,
                "preproc": 3,
            }

    def test_descriptions_none(self, tmp_path):
        """Test extraction when no desc- entities exist."""
        files = [
            "sub-01/anat/sub-01_T1w.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_descriptions(tmp_path)

            assert result == "{}"

    def test_descriptions_exclude_root_files(self, tmp_path):
        """Test that root-level files are excluded."""
        files = [
            "dataset_description.json",
            ".datalad/config",
            "sub-01/anat/sub-01_desc-preproc_T1w.nii.gz",
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="\n".join(files), returncode=0)

            result = extract_descriptions(tmp_path)

            result_dict = json.loads(result)
            assert result_dict == {"preproc": 1}


class TestCombinedExtraction:
    """Test combined metadata extraction."""

    def test_extract_derivative_metadata_complete(self, tmp_path):
        """Test full metadata extraction."""
        deriv_path = tmp_path / "derivative"
        deriv_path.mkdir()
        dd_path = deriv_path / "dataset_description.json"
        dd_path.write_text(json.dumps({
            "SourceDatasets": [{"Version": "1.0.0"}]
        }))

        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]

                # git annex info
                if "annex" in cmd and "info" in cmd:
                    return Mock(
                        stdout=json.dumps({
                            "size of annexed files in working tree": "1000000",
                            "local annex size": "2000000",
                        }),
                        returncode=0,
                    )

                # git ls-files for file count
                if "ls-files" in cmd and len(cmd) == 4:
                    return Mock(stdout="file1\nfile2\nfile3", returncode=0)

                # git describe
                if "describe" in cmd:
                    return Mock(stdout="1.0.0\n", returncode=0)

                # git ls-files func/
                if "func/" in cmd:
                    return Mock(
                        stdout="sub-01/func/sub-01_task-rest_desc-preproc_bold.nii.gz",
                        returncode=0,
                    )

                # git ls-files anat/
                if "anat/" in cmd:
                    return Mock(
                        stdout="sub-01/anat/sub-01_desc-preproc_T1w.nii.gz",
                        returncode=0,
                    )

                # git ls-files (all files)
                if "ls-files" in cmd and len(cmd) == 5:
                    return Mock(
                        stdout="sub-01/anat/sub-01_desc-preproc_T1w.nii.gz\n"
                               "sub-01/func/sub-01_task-rest_desc-preproc_bold.nii.gz",
                        returncode=0,
                    )

                # git ls-tree for raw directories
                if "ls-tree" in cmd:
                    return Mock(
                        stdout="040000 tree anat\n040000 tree func\n",
                        returncode=0,
                    )

                raise ValueError(f"Unexpected command: {cmd}")

            mock_run.side_effect = side_effect

            result = extract_derivative_metadata(deriv_path, raw_path)

            # Check all expected fields
            assert result["size_total"] == "2000000"
            assert result["size_annexed"] == "1000000"
            assert result["file_count"] == 3
            assert result["processed_raw_version"] == "1.0.0"
            assert result["current_raw_version"] == "1.0.0"
            assert result["uptodate"] is True
            assert result["outdatedness"] == 0
            assert result["tasks_processed"] == "rest"
            assert result["tasks_missing"] == ""
            assert result["anat_processed"] is True
            assert result["func_processed"] is True
            assert result["processing_complete"] is True
            assert result["template_spaces"] == "n/a"
            assert result["transform_spaces"] == ""
            assert "preproc" in json.loads(result["descriptions"])
