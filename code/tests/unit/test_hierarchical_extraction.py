"""Unit tests for hierarchical extraction fixes."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from bids_studies.extraction.subject import extract_subjects_stats, BIDS_DATATYPES
from bids_studies.extraction.dataset import aggregate_to_dataset
from bids_studies.extraction.study import aggregate_to_study


class TestSessionValidation:
    """Test that only valid ses-* directories are treated as sessions."""

    def test_filter_datatype_folders_from_sessions(self):
        """Test that anat/fmap/func are not treated as sessions."""
        # Mock a dataset that has both sessions and datatype folders
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

            results, errors = extract_subjects_stats(Path("/fake"), "ds000001", include_imaging=False)

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
                "sub-01/ses-*": [],  # No sessions
                "sub-02/ses-*": [],  # No sessions
            }.get(pattern, [])

            results, errors = extract_subjects_stats(Path("/fake"), "ds000001", include_imaging=False)

        # Should have 2 rows (one per subject)
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

            results, errors = extract_subjects_stats(Path("/fake"), "ds002843", include_imaging=False)

        # Should have 2 rows (one per session)
        assert len(results) == 2
        session_ids = [r["session_id"] for r in results]
        assert "ses-scan1" in session_ids
        assert "ses-scan2" in session_ids

    def test_no_duplicate_rows_from_derivatives(self):
        """Test that derivative sub-* dirs don't produce duplicate rows.

        Regression test for https://github.com/OpenNeuroStudies/OpenNeuroStudies/issues/6
        SparseDataset.list_dirs("sub-*") matches both root-level subjects
        (sub-01) and derivative subjects (derivatives/mriqc/sub-01). The
        extraction must filter to top-level only.
        """
        mock_ds = Mock()
        mock_ds.list_files.return_value = []

        with patch('bids_studies.extraction.subject.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            # Simulate list_dirs returning BOTH raw and derivative subjects
            mock_ds.list_dirs.side_effect = lambda pattern: {
                "sub-*": [
                    "sub-01",
                    "sub-02",
                    "derivatives/mriqc/sub-01",  # Should be filtered out
                    "derivatives/mriqc/sub-02",  # Should be filtered out
                ],
                "sub-01/ses-*": [],
                "sub-02/ses-*": [],
            }.get(pattern, [])

            results, errors = extract_subjects_stats(Path("/fake"), "ds004636", include_imaging=False)

        # Should have 2 rows (one per real subject), not 4
        assert len(results) == 2
        subject_ids = [r["subject_id"] for r in results]
        assert subject_ids == ["sub-01", "sub-02"]


class TestSessionCounting:
    """Test that sessions are counted correctly."""

    def test_count_valid_sessions_only(self):
        """Test that only valid ses-* sessions are counted."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
            {"subject_id": "sub-01", "session_id": "ses-02", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
            # These should not be in the data anymore, but test defensively
            {"subject_id": "sub-01", "session_id": "anat", "bold_num": 0, "t1w_num": 0, "t2w_num": 0,
             "bold_size": 0, "t1w_size": 0, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "n/a"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds002843")

        # Should count only the 2 valid sessions
        assert result["sessions_num"] == 2
        assert result["sessions_min"] == 2
        assert result["sessions_max"] == 2

    def test_single_session_per_subject(self):
        """Test counting when each subject has one session."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
            {"subject_id": "sub-02", "session_id": "ses-01", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds000001")

        assert result["sessions_num"] == 2  # Total sessions across all subjects
        assert result["sessions_min"] == 1  # Min per subject
        assert result["sessions_max"] == 1  # Max per subject

    def test_no_sessions_dataset(self):
        """Test that single-session datasets show n/a for session counts."""
        subjects_stats = [
            {"subject_id": "sub-01", "session_id": "n/a", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
            {"subject_id": "sub-02", "session_id": "n/a", "bold_num": 3, "t1w_num": 1, "t2w_num": 0,
             "bold_size": 1000, "t1w_size": 100, "bold_duration_total": None, "bold_voxels_total": None,
             "datatypes": "anat,func"},
        ]

        result = aggregate_to_dataset(subjects_stats, "ds000001")

        assert result["sessions_num"] == "n/a"
        assert result["sessions_min"] == "n/a"
        assert result["sessions_max"] == "n/a"


class TestImagingMetrics:
    """Test that imaging metrics parameter is respected."""

    def test_include_imaging_parameter(self):
        """Test that include_imaging parameter is passed through correctly."""
        from bids_studies.extraction.study import extract_study_stats

        # Test that the default is now True
        import inspect
        sig = inspect.signature(extract_study_stats)
        assert sig.parameters['include_imaging'].default is True, \
            "include_imaging should default to True to enable BOLD statistics"

    def test_imaging_metrics_with_mock_data(self):
        """Test imaging metrics extraction with simpler mock."""
        # Test that when BOLD files exist and imaging is enabled,
        # the structure allows for metrics
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

            # Test with imaging disabled (should have None for imaging metrics)
            results, errors = extract_subjects_stats(Path("/fake"), "ds000001", include_imaging=False)

        assert len(results) == 1
        result = results[0]

        # Should have BOLD file count and size
        assert result["bold_num"] == 1
        assert result["bold_size"] == 50000000
        # Imaging metrics should be None when disabled
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
        assert result["sessions_num"] == 1431  # Should not be n/a
        assert result["sessions_min"] == 4
        assert result["sessions_max"] == 10
        assert result["bold_duration_total"] == 290821.0
        assert result["bold_voxels_total"] == 217088


class TestDerivativeExtraction:
    """Test derivative extraction and file placement."""

    def test_extract_derivative_stats_returns_tuple(self, tmp_path):
        """Test that extract_derivative_stats returns (subjects, dataset) tuple."""
        from bids_studies.extraction.study import extract_derivative_stats

        deriv_path = tmp_path / "MRIQC"
        deriv_path.mkdir()

        mock_ds = Mock()
        mock_ds.list_dirs.side_effect = lambda pattern: {
            "sub-*": ["sub-01"],
            "sub-01/ses-*": [],
        }.get(pattern, [])
        mock_ds.list_files.return_value = ["sub-01/anat/sub-01_T1w.nii.gz"]
        mock_ds.get_file_size.return_value = 100

        with patch('bids_studies.extraction.derivative.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            subjects, dataset = extract_derivative_stats(
                deriv_path, "ds000001", "MRIQC"
            )

        assert isinstance(subjects, list)
        assert isinstance(dataset, dict)
        assert len(subjects) == 1
        assert dataset["source_id"] == "ds000001"
        assert dataset["derivative_id"] == "MRIQC"
        assert dataset["subjects_num"] == 1

    def test_extract_derivative_stats_empty_returns_zero_counts(self, tmp_path):
        """Test that uninitialized derivatives return zero counts, not empty dict."""
        from bids_studies.extraction.study import extract_derivative_stats

        deriv_path = tmp_path / "fMRIPrep"
        deriv_path.mkdir()

        mock_ds = Mock()
        mock_ds.list_dirs.return_value = []  # No subjects found
        mock_ds.list_files.return_value = []

        with patch('bids_studies.extraction.derivative.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            subjects, dataset = extract_derivative_stats(
                deriv_path, "ds000001", "fMRIPrep"
            )

        assert subjects == []
        assert dataset["source_id"] == "ds000001"
        assert dataset["derivative_id"] == "fMRIPrep"
        assert dataset["subjects_num"] == 0
        assert dataset["output_num"] == 0

    def test_extract_all_derivatives_writes_to_parent_dir(self, tmp_path):
        """Test that TSV files are written to derivatives/ not inside individual derivative dirs."""
        from bids_studies.extraction.study import extract_all_derivatives_stats

        # Create derivative directories
        derivatives_dir = tmp_path / "derivatives"
        mriqc_dir = derivatives_dir / "MRIQC-25.0.0"
        fmriprep_dir = derivatives_dir / "fMRIPrep-24.1.1"
        bidsval_dir = derivatives_dir / "bids-validator"
        mriqc_dir.mkdir(parents=True)
        fmriprep_dir.mkdir(parents=True)
        bidsval_dir.mkdir(parents=True)

        mock_ds = Mock()
        mock_ds.list_dirs.side_effect = lambda pattern: {
            "sub-*": ["sub-01"],
            "sub-01/ses-*": [],
        }.get(pattern, [])
        mock_ds.list_files.return_value = ["sub-01/anat/sub-01_T1w.nii.gz"]
        mock_ds.get_file_size.return_value = 100

        with patch('bids_studies.extraction.derivative.SparseDataset') as MockSparse:
            MockSparse.return_value.__enter__.return_value = mock_ds
            results = extract_all_derivatives_stats(
                derivatives_dir, source_id="ds000001", write_files=True
            )

        # Should have dataset stats for both derivatives (not bids-validator)
        assert len(results) == 2
        deriv_ids = [r["derivative_id"] for r in results]
        assert "MRIQC-25.0.0" in deriv_ids
        assert "fMRIPrep-24.1.1" in deriv_ids
        assert "bids-validator" not in deriv_ids

        # Files should be at derivatives/ level, NOT inside individual derivative dirs
        assert (derivatives_dir / "derivatives+datasets.tsv").exists()
        assert (derivatives_dir / "derivatives+subjects.tsv").exists()

        # Files should NOT be inside individual derivative dirs
        assert not list(mriqc_dir.glob("derivatives+*"))
        assert not list(fmriprep_dir.glob("derivatives+*"))

    def test_extract_all_derivatives_includes_uninitialized(self, tmp_path):
        """Test that uninitialized derivatives still appear in datasets TSV with zero counts."""
        from bids_studies.extraction.study import extract_all_derivatives_stats

        derivatives_dir = tmp_path / "derivatives"
        mriqc_dir = derivatives_dir / "MRIQC"
        fmriprep_dir = derivatives_dir / "fMRIPrep"
        mriqc_dir.mkdir(parents=True)
        fmriprep_dir.mkdir(parents=True)

        # MRIQC returns subjects; fMRIPrep returns nothing (uninitialized)
        call_count = [0]

        def mock_sparse_init(path):
            cm = MagicMock()
            mock_ds = Mock()
            if "MRIQC" in str(path):
                mock_ds.list_dirs.side_effect = lambda p: {"sub-*": ["sub-01"], "sub-01/ses-*": []}.get(p, [])
                mock_ds.list_files.return_value = ["sub-01/file.html"]
                mock_ds.get_file_size.return_value = 50
            else:
                mock_ds.list_dirs.return_value = []
                mock_ds.list_files.return_value = []
            cm.__enter__ = Mock(return_value=mock_ds)
            cm.__exit__ = Mock(return_value=False)
            return cm

        with patch('bids_studies.extraction.derivative.SparseDataset', side_effect=mock_sparse_init):
            results = extract_all_derivatives_stats(
                derivatives_dir, source_id="ds006131", write_files=True
            )

        # Both derivatives should appear in results
        assert len(results) == 2
        mriqc_stats = next(r for r in results if r["derivative_id"] == "MRIQC")
        fmriprep_stats = next(r for r in results if r["derivative_id"] == "fMRIPrep")

        assert mriqc_stats["subjects_num"] == 1
        assert fmriprep_stats["subjects_num"] == 0
        assert fmriprep_stats["output_num"] == 0

        # datasets TSV should exist and contain both derivatives
        datasets_tsv = derivatives_dir / "derivatives+datasets.tsv"
        assert datasets_tsv.exists()
        content = datasets_tsv.read_text()
        assert "MRIQC" in content
        assert "fMRIPrep" in content


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
