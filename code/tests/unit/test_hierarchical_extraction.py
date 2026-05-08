"""Unit tests for hierarchical extraction.

Tests cover:
- Session validation (filtering datatype directories)
- Session counting in aggregation
- Imaging metrics parameter
- Study-level aggregation
- BIDS datatype constants
- Derivative extraction and aggregation
- TSV round-trip (write + read)
- Error classification
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from bids_studies.extraction.subject import extract_subjects_stats, BIDS_DATATYPES
from bids_studies.extraction.dataset import aggregate_to_dataset
from bids_studies.extraction.study import aggregate_to_study
from bids_studies.extraction.derivative import (
    extract_derivative_subject_stats,
    aggregate_derivative_to_dataset,
)
from bids_studies.extraction.tsv import (
    _na,
    write_subjects_tsv,
    read_subjects_tsv,
    write_datasets_tsv,
    read_datasets_tsv,
    write_derivative_subjects_tsv,
    read_derivative_subjects_tsv,
    write_derivative_datasets_tsv,
    read_derivative_datasets_tsv,
    SUBJECTS_COLUMNS,
    DATASETS_COLUMNS,
    DERIVATIVE_SUBJECTS_COLUMNS,
    DERIVATIVE_DATASETS_COLUMNS,
)


class TestSessionValidation:
    """Test that only valid ses-* directories are treated as sessions."""

    def test_filter_datatype_folders_from_sessions(self):
        """Test that anat/fmap/func are not treated as sessions."""
        mock_ds = Mock()
        mock_ds.list_dirs.return_value = [
            "sub-01/ses-01",
            "sub-01/ses-02",
            "sub-01/anat",  # Should be filtered out
            "sub-01/func",  # Should be filtered out
            "sub-01/fmap",  # Should be filtered out
        ]
        mock_ds.list_files.return_value = []

        with patch('bids_studies.extraction.subject.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            mock_ds.list_dirs.side_effect = lambda pattern: {
                "sub-*": ["sub-01"],
                "sub-01/ses-*": [
                    "sub-01/ses-01",
                    "sub-01/ses-02",
                    "sub-01/anat",  # Invalid
                    "sub-01/func",  # Invalid
                ],
            }.get(pattern, [])

            results, errors = extract_subjects_stats(
                Path("/fake"), "ds000001", include_imaging=False
            )

        # Should have exactly 2 rows (ses-01 and ses-02), not 4
        assert len(results) == 2
        session_ids = [r["session_id"] for r in results]
        assert "ses-01" in session_ids
        assert "ses-02" in session_ids
        assert "anat" not in session_ids
        assert "func" not in session_ids
        assert "fmap" not in session_ids

    def test_single_session_dataset(self):
        """Test single-session dataset (no ses-* folders)."""
        mock_ds = Mock()
        mock_ds.list_files.return_value = []

        with patch('bids_studies.extraction.subject.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            mock_ds.list_dirs.side_effect = lambda pattern: {
                "sub-*": ["sub-01", "sub-02"],
                "sub-01/ses-*": [],
                "sub-02/ses-*": [],
            }.get(pattern, [])

            results, errors = extract_subjects_stats(
                Path("/fake"), "ds000001", include_imaging=False
            )

        assert len(results) == 2
        assert all(r["session_id"] == "n/a" for r in results)

    def test_multi_session_dataset(self):
        """Test multi-session dataset with proper ses-* folders."""
        mock_ds = Mock()
        mock_ds.list_files.return_value = []

        with patch('bids_studies.extraction.subject.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            mock_ds.list_dirs.side_effect = lambda pattern: {
                "sub-*": ["sub-01"],
                "sub-01/ses-*": ["sub-01/ses-scan1", "sub-01/ses-scan2"],
            }.get(pattern, [])

            results, errors = extract_subjects_stats(
                Path("/fake"), "ds002843", include_imaging=False
            )

        assert len(results) == 2
        session_ids = [r["session_id"] for r in results]
        assert "ses-scan1" in session_ids
        assert "ses-scan2" in session_ids


class TestSessionCounting:
    """Test that sessions are counted correctly."""

    def test_count_valid_sessions_only(self):
        """Test that only valid ses-* sessions are counted."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
            {"subject_id": "sub-01", "session_id": "ses-02", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
            # These should not be in the data anymore, but test defensively
            {"subject_id": "sub-01", "session_id": "anat", "bold_num": 0, "t1w_num": 0,
             "t2w_num": 0, "bold_size": 0, "t1w_size": 0, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "n/a"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds002843")

        # Should count only the 2 valid sessions
        assert result["sessions_num"] == 2
        assert result["sessions_min"] == 2
        assert result["sessions_max"] == 2

    def test_single_session_per_subject(self):
        """Test counting when each subject has one session."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
            {"subject_id": "sub-02", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds000001")

        assert result["sessions_num"] == 2  # Total sessions across all subjects
        assert result["sessions_min"] == 1  # Min per subject
        assert result["sessions_max"] == 1  # Max per subject

    def test_no_sessions_dataset(self):
        """Test that single-session datasets show n/a for session counts."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "n/a", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
            {"subject_id": "sub-02", "session_id": "n/a", "bold_num": 3, "t1w_num": 1,
             "t2w_num": 0, "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None,
             "bold_voxels_total": None, "datatypes": "anat,func"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds000001")

        assert result["sessions_num"] == "n/a"
        assert result["sessions_min"] == "n/a"
        assert result["sessions_max"] == "n/a"


class TestImagingMetrics:
    """Test that imaging metrics parameter is respected."""

    def test_include_imaging_parameter(self):
        """Test that include_imaging parameter defaults to True."""
        from bids_studies.extraction.study import extract_study_stats
        import inspect

        sig = inspect.signature(extract_study_stats)
        assert sig.parameters['include_imaging'].default is True, \
            "include_imaging should default to True to enable BOLD statistics"

    def test_imaging_metrics_with_mock_data(self):
        """Test imaging metrics extraction with simpler mock."""
        mock_ds = Mock()
        mock_ds.list_files.return_value = [
            "sub-01/func/sub-01_task-rest_bold.nii.gz"
        ]
        mock_ds.get_file_size.return_value = 50000000

        with patch('bids_studies.extraction.subject.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            mock_ds.list_dirs.side_effect = lambda pattern: {
                "sub-*": ["sub-01"],
                "sub-01/ses-*": [],
            }.get(pattern, [])

            results, errors = extract_subjects_stats(
                Path("/fake"), "ds000001", include_imaging=False
            )

        assert len(results) == 1
        result = results[0]

        assert result["bold_num"] == 1
        assert result["bold_size"] == 50000000
        assert result["bold_voxels_total"] is None
        assert result["bold_voxels_mean"] is None
        assert result["bold_duration_total"] is None
        assert result["bold_duration_mean"] is None


class TestStudyAggregation:
    """Test study-level aggregation."""

    def test_aggregate_multi_session_to_study(self):
        """Test aggregating multi-session datasets to study level."""
        datasets_stats = [
            {
                "source_id": "ds002843",
                "subjects_num": 166,
                "sessions_num": 1431,
                "sessions_min": 4,
                "sessions_max": 10,
                "bold_num": 2630,
                "t1w_num": 293,
                "t2w_num": 290,
                "bold_size": 78668149917,
                "t1w_size": 2559851481,
                "bold_size_max": 46784733,
                "bold_duration_total": 290821.0,
                "bold_duration_mean": 110.6,
                "bold_voxels_total": 217088,
                "bold_voxels_mean": 82.5,
                "datatypes": "anat,dwi,fmap,func",
            }
        ]

        result = aggregate_to_study(datasets_stats)

        assert result["subjects_num"] == 166
        assert result["sessions_num"] == 1431
        assert result["sessions_min"] == 4
        assert result["sessions_max"] == 10
        assert result["bold_duration_total"] == 290821.0
        assert result["bold_voxels_total"] == 217088

    def test_aggregate_empty_datasets(self):
        """Test aggregation with no datasets."""
        result = aggregate_to_study([])
        assert result == {}

    def test_aggregate_multiple_datasets(self):
        """Test aggregation across multiple sourcedata datasets."""
        datasets_stats = [
            {
                "source_id": "ds000001",
                "subjects_num": 10,
                "sessions_num": "n/a",
                "sessions_min": "n/a",
                "sessions_max": "n/a",
                "bold_num": 30,
                "t1w_num": 10,
                "t2w_num": 0,
                "bold_size": 5000,
                "t1w_size": 1000,
                "bold_size_max": 200,
                "bold_duration_total": 3000.0,
                "bold_duration_mean": 100.0,
                "bold_voxels_total": 90000,
                "bold_voxels_mean": 3000.0,
                "datatypes": "anat,func",
            },
            {
                "source_id": "ds000002",
                "subjects_num": 5,
                "sessions_num": "n/a",
                "sessions_min": "n/a",
                "sessions_max": "n/a",
                "bold_num": 15,
                "t1w_num": 5,
                "t2w_num": 0,
                "bold_size": 2500,
                "t1w_size": 500,
                "bold_size_max": 180,
                "bold_duration_total": 1500.0,
                "bold_duration_mean": 100.0,
                "bold_voxels_total": 45000,
                "bold_voxels_mean": 3000.0,
                "datatypes": "anat,func,dwi",
            },
        ]

        result = aggregate_to_study(datasets_stats)

        assert result["subjects_num"] == 15  # 10 + 5
        assert result["bold_num"] == 45  # 30 + 15
        assert result["t1w_num"] == 15  # 10 + 5
        assert result["bold_size"] == 7500  # 5000 + 2500
        assert result["bold_duration_total"] == 4500.0  # 3000 + 1500
        assert result["bold_voxels_total"] == 135000  # 90000 + 45000
        assert result["datatypes"] == "anat,dwi,func"  # Union, sorted


class TestDatasetTypes:
    """Test that BIDS_DATATYPES constant is used for filtering."""

    def test_all_standard_datatypes_recognized(self):
        """Test that all standard BIDS datatypes are in BIDS_DATATYPES."""
        standard_datatypes = {
            "anat", "func", "dwi", "fmap", "perf",
            "meg", "eeg", "ieeg", "beh", "pet",
            "micr", "nirs", "motion"
        }

        assert standard_datatypes.issubset(BIDS_DATATYPES)


class TestDerivativeExtraction:
    """Test derivative per-subject extraction and aggregation."""

    def test_extract_derivative_subject_stats(self):
        """Test extracting stats for a single derivative subject."""
        mock_ds = Mock()
        mock_ds.list_files.return_value = [
            "sub-01/anat/sub-01_space-MNI_desc-preproc_T1w.nii.gz",
            "sub-01/func/sub-01_task-rest_space-MNI_desc-preproc_bold.nii.gz",
            "sub-01/func/sub-01_task-rest_space-MNI_boldref.nii.gz",
            "sub-01/figures/sub-01_desc-summary.html",
        ]
        mock_ds.get_file_size.side_effect = lambda f: {
            "sub-01/anat/sub-01_space-MNI_desc-preproc_T1w.nii.gz": 5000000,
            "sub-01/func/sub-01_task-rest_space-MNI_desc-preproc_bold.nii.gz": 20000000,
            "sub-01/func/sub-01_task-rest_space-MNI_boldref.nii.gz": 1000000,
            "sub-01/figures/sub-01_desc-summary.html": 50000,
        }.get(f, None)

        result = extract_derivative_subject_stats(
            mock_ds, "ds000001", "fmriprep-24.0.0", "sub-01"
        )

        assert result["source_id"] == "ds000001"
        assert result["derivative_id"] == "fmriprep-24.0.0"
        assert result["subject_id"] == "sub-01"
        assert result["session_id"] == "n/a"
        assert result["output_num"] == 4
        assert result["nifti_num"] == 3  # 3 .nii.gz files
        assert result["html_num"] == 1
        assert result["output_size"] == 26050000  # Sum of all sizes
        assert result["nifti_size"] == 26000000  # Sum of nifti sizes

    def test_extract_derivative_subject_stats_with_session(self):
        """Test extracting derivative stats for a subject with session."""
        mock_ds = Mock()
        mock_ds.list_files.return_value = [
            "sub-01/ses-01/func/sub-01_ses-01_bold.nii.gz",
        ]
        mock_ds.get_file_size.return_value = 10000000

        result = extract_derivative_subject_stats(
            mock_ds, "ds000001", "fmriprep-24.0.0", "sub-01", "ses-01"
        )

        assert result["session_id"] == "ses-01"
        assert result["output_num"] == 1
        assert result["nifti_num"] == 1

    def test_aggregate_derivative_to_dataset(self):
        """Test aggregating derivative subject stats to dataset level."""
        subjects_stats = [
            {
                "source_id": "ds000001",
                "derivative_id": "mriqc-25.0.0",
                "subject_id": "sub-01",
                "session_id": "n/a",
                "output_num": 10,
                "output_size": 5000,
                "nifti_num": 3,
                "nifti_size": 4000,
                "html_num": 2,
            },
            {
                "source_id": "ds000001",
                "derivative_id": "mriqc-25.0.0",
                "subject_id": "sub-02",
                "session_id": "n/a",
                "output_num": 8,
                "output_size": 4000,
                "nifti_num": 2,
                "nifti_size": 3000,
                "html_num": 2,
            },
        ]

        result = aggregate_derivative_to_dataset(
            subjects_stats, "ds000001", "mriqc-25.0.0"
        )

        assert result["source_id"] == "ds000001"
        assert result["derivative_id"] == "mriqc-25.0.0"
        assert result["subjects_num"] == 2
        assert result["sessions_num"] == "n/a"
        assert result["output_num"] == 18  # 10 + 8
        assert result["output_size"] == 9000  # 5000 + 4000
        assert result["nifti_num"] == 5  # 3 + 2
        assert result["nifti_size"] == 7000  # 4000 + 3000
        assert result["html_num"] == 4  # 2 + 2

    def test_aggregate_derivative_empty(self):
        """Test aggregating empty derivative stats."""
        result = aggregate_derivative_to_dataset([], "ds000001", "mriqc-25.0.0")

        assert result["subjects_num"] == 0
        assert result["sessions_num"] == "n/a"
        assert result["output_num"] == 0

    def test_aggregate_derivative_with_sessions(self):
        """Test aggregating derivative stats with sessions."""
        subjects_stats = [
            {
                "source_id": "ds000001",
                "derivative_id": "fmriprep-24.0.0",
                "subject_id": "sub-01",
                "session_id": "ses-01",
                "output_num": 5,
                "output_size": 2500,
                "nifti_num": 2,
                "nifti_size": 2000,
                "html_num": 1,
            },
            {
                "source_id": "ds000001",
                "derivative_id": "fmriprep-24.0.0",
                "subject_id": "sub-01",
                "session_id": "ses-02",
                "output_num": 5,
                "output_size": 2500,
                "nifti_num": 2,
                "nifti_size": 2000,
                "html_num": 1,
            },
        ]

        result = aggregate_derivative_to_dataset(
            subjects_stats, "ds000001", "fmriprep-24.0.0"
        )

        assert result["subjects_num"] == 1  # Only 1 unique subject
        assert result["sessions_num"] == 2  # 2 sessions for sub-01


class TestTsvRoundTrip:
    """Test TSV write + read produces consistent data."""

    def test_subjects_tsv_roundtrip(self, tmp_path):
        """Test writing and reading subjects TSV."""
        stats = [
            {
                "source_id": "ds000001",
                "subject_id": "sub-01",
                "session_id": "n/a",
                "bold_num": 3,
                "t1w_num": 1,
                "t2w_num": 0,
                "bold_size": 50000000,
                "t1w_size": 10000000,
                "bold_duration_total": 360.0,
                "bold_duration_mean": 120.0,
                "bold_voxels_total": 90000,
                "bold_voxels_mean": 30000.0,
                "datatypes": "anat,func",
            },
        ]

        tsv_path = tmp_path / "sourcedata" / "sourcedata+subjects.tsv"
        write_subjects_tsv(tsv_path, stats)
        read_back = read_subjects_tsv(tsv_path)

        assert len(read_back) == 1
        row = read_back[0]
        assert row["source_id"] == "ds000001"
        assert row["subject_id"] == "sub-01"
        assert row["session_id"] == "n/a"
        assert row["bold_num"] == 3
        assert row["t1w_num"] == 1
        assert row["bold_size"] == 50000000
        assert row["bold_duration_total"] == 360.0
        assert row["bold_voxels_total"] == 90000.0  # Read as float
        assert row["datatypes"] == "anat,func"

    def test_datasets_tsv_roundtrip(self, tmp_path):
        """Test writing and reading datasets TSV."""
        stats = [
            {
                "source_id": "ds000001",
                "subjects_num": 16,
                "sessions_num": "n/a",
                "sessions_min": "n/a",
                "sessions_max": "n/a",
                "bold_num": 48,
                "t1w_num": 16,
                "t2w_num": 0,
                "bold_size": 800000000,
                "t1w_size": 160000000,
                "bold_size_max": 50000000,
                "bold_duration_total": 5760.0,
                "bold_duration_mean": 120.0,
                "bold_voxels_total": 1440000,
                "bold_voxels_mean": 30000.0,
                "datatypes": "anat,func",
            },
        ]

        tsv_path = tmp_path / "sourcedata" / "sourcedata.tsv"
        write_datasets_tsv(tsv_path, stats)
        read_back = read_datasets_tsv(tsv_path)

        assert len(read_back) == 1
        row = read_back[0]
        assert row["source_id"] == "ds000001"
        assert row["subjects_num"] == 16
        assert row["bold_num"] == 48
        assert row["sessions_num"] == "n/a"

    def test_derivative_subjects_tsv_roundtrip(self, tmp_path):
        """Test writing and reading derivative subjects TSV."""
        stats = [
            {
                "source_id": "ds000001",
                "derivative_id": "mriqc-25.0.0",
                "subject_id": "sub-01",
                "session_id": "n/a",
                "output_num": 10,
                "output_size": 5000,
                "nifti_num": 3,
                "nifti_size": 4000,
                "html_num": 2,
            },
        ]

        tsv_path = tmp_path / "derivatives" / "mriqc-25.0.0" / "derivatives+subjects.tsv"
        write_derivative_subjects_tsv(tsv_path, stats)
        read_back = read_derivative_subjects_tsv(tsv_path)

        assert len(read_back) == 1
        row = read_back[0]
        assert row["derivative_id"] == "mriqc-25.0.0"
        assert row["output_num"] == 10
        assert row["nifti_size"] == 4000

    def test_derivative_datasets_tsv_roundtrip(self, tmp_path):
        """Test writing and reading derivative datasets TSV."""
        stats = [
            {
                "source_id": "ds000001",
                "derivative_id": "mriqc-25.0.0",
                "subjects_num": 16,
                "sessions_num": "n/a",
                "output_num": 160,
                "output_size": 80000,
                "nifti_num": 48,
                "nifti_size": 64000,
                "html_num": 32,
            },
        ]

        tsv_path = tmp_path / "derivatives" / "mriqc-25.0.0" / "derivatives+datasets.tsv"
        write_derivative_datasets_tsv(tsv_path, stats)
        read_back = read_derivative_datasets_tsv(tsv_path)

        assert len(read_back) == 1
        row = read_back[0]
        assert row["subjects_num"] == 16
        assert row["output_num"] == 160

    def test_tsv_no_csv_escaping(self, tmp_path):
        """Test that TSV output does not have CSV escaping artifacts.

        Per FR-HE-080, values must not be quoted or escaped.
        """
        stats = [
            {
                "source_id": "ds000001",
                "subject_id": "sub-01",
                "session_id": "n/a",
                "bold_num": 3,
                "t1w_num": 1,
                "t2w_num": 0,
                "bold_size": 50000000,
                "t1w_size": 10000000,
                "bold_duration_total": None,
                "bold_duration_mean": None,
                "bold_voxels_total": None,
                "bold_voxels_mean": None,
                "datatypes": "anat,func",
            },
        ]

        tsv_path = tmp_path / "test.tsv"
        write_subjects_tsv(tsv_path, stats)

        content = tsv_path.read_text()
        # No quotes should appear anywhere in the file
        assert '"' not in content
        # Comma in datatypes should not trigger quoting
        assert "anat,func" in content
        # n/a values should be written literally
        assert "n/a" in content

    def test_na_helper(self):
        """Test the _na helper function."""
        assert _na(None) == "n/a"
        assert _na(42) == "42"
        assert _na(3.14) == "3.14"
        assert _na("hello") == "hello"
        assert _na("n/a") == "n/a"
        assert _na(0) == "0"


class TestErrorClassification:
    """Test that bids_studies has its own error classification."""

    def test_classify_expected_error(self):
        """Test classifying expected errors."""
        from bids_studies.error_classification import classify_error

        assert classify_error("No remote URL found for file") == "expected"
        assert classify_error("Failed to extract imaging metrics from bold.nii.gz") == "expected"

    def test_classify_operational_error(self):
        """Test classifying operational errors."""
        from bids_studies.error_classification import classify_error

        assert classify_error("fatal: not a git repository") == "operational"
        assert classify_error("Permission denied") == "operational"

    def test_aggregate_errors(self):
        """Test aggregating errors into categories."""
        from bids_studies.error_classification import aggregate_errors

        errors = [
            "No remote URL found for sub-01/func/bold.nii.gz",
            "fatal: not a git repository",
            "Failed to extract imaging metrics from bold.nii.gz: corrupt",
        ]

        operational, expected = aggregate_errors(errors)

        assert len(operational) == 1
        assert "not a git repository" in operational[0]
        assert len(expected) == 2


class TestLibraryBoundary:
    """Test that bids_studies does not import from openneuro_studies at module level."""

    def test_no_openneuro_imports_in_extraction(self):
        """Verify extraction modules use bids_studies.* imports."""
        import bids_studies.extraction.subject as subj_mod
        import bids_studies.extraction.derivative as deriv_mod
        import bids_studies.extraction.study as study_mod
        import bids_studies.sparse.access as access_mod

        # Check that modules loaded without openneuro_studies imports
        # by inspecting their module-level imports
        import inspect

        for mod in [subj_mod, deriv_mod, study_mod, access_mod]:
            source = inspect.getsource(mod)
            # Look for module-level (non-indented) imports from openneuro_studies
            for line in source.split("\n"):
                # Skip comments, docstrings, and indented lines (inside functions)
                stripped = line.lstrip()
                if not stripped.startswith("from openneuro_studies") and \
                   not stripped.startswith("import openneuro_studies"):
                    continue
                # If we reach here, check if it's indented (inside a function)
                if line.startswith(" ") or line.startswith("\t"):
                    # It's inside a function - acceptable for lazy imports
                    continue
                # Module-level import from openneuro_studies - violation
                pytest.fail(
                    f"Module {mod.__name__} has module-level import from "
                    f"openneuro_studies: {line.strip()}"
                )

    def test_bids_studies_exceptions(self):
        """Test that bids_studies has its own exception classes."""
        from bids_studies.exceptions import NetworkError, BidsStudiesError

        # NetworkError should be a BidsStudiesError
        assert issubclass(NetworkError, BidsStudiesError)

        # Should be constructable
        err = NetworkError("test error", url="http://example.com", attempts=3)
        assert "test error" in str(err)
        assert err.url == "http://example.com"
        assert err.attempts == 3
