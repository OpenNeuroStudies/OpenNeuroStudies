"""Unit tests for bids_studies.subdatasets module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from bids_studies.subdatasets import (
    iter_sourcedata_subdatasets,
    get_subdataset_states,
    ensure_subdatasets_installed,
    drop_subdatasets,
    TemporarySubdatasetInstall,
    extract_study_with_subdatasets,
)


@pytest.fixture
def mock_dataset():
    """Mock DataLad Dataset."""
    with patch('bids_studies.subdatasets.Dataset') as mock_ds_class:
        yield mock_ds_class


class TestIterSourcedataSubdatasets:
    """Tests for iter_sourcedata_subdatasets()."""

    def test_yields_sourcedata_subdatasets(self, mock_dataset, tmp_path):
        """Should yield only sourcedata subdatasets."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # Mock dataset instance
        ds_instance = Mock()
        ds_instance.is_installed.return_value = True
        ds_instance.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
            {'path': str(study_path / 'derivatives' / 'fmriprep')},
            {'path': str(study_path / 'sourcedata' / 'ds000002')},
        ]
        mock_dataset.return_value = ds_instance

        result = list(iter_sourcedata_subdatasets(study_path))

        assert len(result) == 2
        assert all('sourcedata' in str(p) for p in result)
        assert study_path / 'sourcedata' / 'ds000001' in result
        assert study_path / 'sourcedata' / 'ds000002' in result

    def test_returns_empty_if_not_installed(self, mock_dataset, tmp_path):
        """Should return empty if study not installed."""
        study_path = tmp_path / "study-ds000001"

        ds_instance = Mock()
        ds_instance.is_installed.return_value = False
        mock_dataset.return_value = ds_instance

        result = list(iter_sourcedata_subdatasets(study_path))

        assert result == []


class TestGetSubdatasetStates:
    """Tests for get_subdataset_states()."""

    def test_returns_states_dict(self, mock_dataset, tmp_path):
        """Should return dict mapping paths to states."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # Mock parent dataset
        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
            {'path': str(study_path / 'sourcedata' / 'ds000002')},
        ]

        # Mock child datasets - one installed, one not
        child_ds1 = Mock()
        child_ds1.is_installed.return_value = True
        child_ds2 = Mock()
        child_ds2.is_installed.return_value = False

        mock_dataset.side_effect = [parent_ds, child_ds1, child_ds2]

        result = get_subdataset_states(study_path)

        assert len(result) == 2
        assert result[study_path / 'sourcedata' / 'ds000001'] == 'present'
        assert result[study_path / 'sourcedata' / 'ds000002'] == 'absent'


class TestEnsureSubdatasetsInstalled:
    """Tests for ensure_subdatasets_installed()."""

    def test_installs_only_uninstalled(self, mock_dataset, tmp_path):
        """Should install only uninstalled subdatasets."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # Mock parent dataset
        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
            {'path': str(study_path / 'sourcedata' / 'ds000002')},
        ]
        parent_ds.get.return_value = None  # Successful install

        # Mock child datasets - one installed, one not
        child_ds1 = Mock()
        child_ds1.is_installed.return_value = True  # Already installed
        child_ds2 = Mock()
        child_ds2.is_installed.return_value = False  # Needs install

        mock_dataset.side_effect = [parent_ds, child_ds1, child_ds2]

        newly, existing = ensure_subdatasets_installed(study_path)

        assert len(newly) == 1
        assert study_path / 'sourcedata' / 'ds000002' in newly
        assert len(existing) == 1
        assert study_path / 'sourcedata' / 'ds000001' in existing

        # Verify get was called only once (for uninstalled)
        parent_ds.get.assert_called_once()

    def test_retries_on_transient_error(self, mock_dataset, tmp_path):
        """Should retry on transient errors."""
        from datalad.support.exceptions import IncompleteResultsError

        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
        ]

        # First call fails, second succeeds
        parent_ds.get.side_effect = [
            IncompleteResultsError("Network error"),
            None  # Success
        ]

        child_ds = Mock()
        child_ds.is_installed.return_value = False

        mock_dataset.side_effect = [parent_ds, child_ds]

        with patch('bids_studies.subdatasets.time.sleep'):  # Skip actual sleep
            newly, existing = ensure_subdatasets_installed(study_path, max_retries=3)

        assert len(newly) == 1
        assert parent_ds.get.call_count == 2  # First failed, second succeeded

    def test_raises_after_max_retries(self, mock_dataset, tmp_path):
        """Should raise after exceeding max retries."""
        from datalad.support.exceptions import IncompleteResultsError

        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
        ]
        parent_ds.get.side_effect = IncompleteResultsError("Network error")

        child_ds = Mock()
        child_ds.is_installed.return_value = False

        mock_dataset.side_effect = [parent_ds, child_ds]

        with patch('bids_studies.subdatasets.time.sleep'):
            with pytest.raises(RuntimeError, match="Installation failed after .* retries"):
                ensure_subdatasets_installed(study_path, max_retries=2)


class TestDropSubdatasets:
    """Tests for drop_subdatasets()."""

    def test_drops_specified_subdatasets(self, mock_dataset, tmp_path):
        """Should drop all specified subdatasets."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        parent_ds = Mock()
        parent_ds.drop.return_value = None  # Successful drop

        mock_dataset.return_value = parent_ds

        to_drop = {
            study_path / 'sourcedata' / 'ds000001',
            study_path / 'sourcedata' / 'ds000002',
        }

        dropped = drop_subdatasets(to_drop, study_path)

        assert dropped == to_drop
        assert parent_ds.drop.call_count == 2

    def test_raises_on_permanent_error(self, mock_dataset, tmp_path):
        """Should raise immediately on non-transient errors."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        parent_ds = Mock()
        parent_ds.drop.side_effect = ValueError("Invalid path")  # Non-transient

        mock_dataset.return_value = parent_ds

        to_drop = {study_path / 'sourcedata' / 'ds000001'}

        with pytest.raises(RuntimeError, match="unexpected error"):
            drop_subdatasets(to_drop, study_path)


class TestTemporarySubdatasetInstall:
    """Tests for TemporarySubdatasetInstall context manager."""

    def test_installs_on_enter_drops_on_exit(self, mock_dataset, tmp_path):
        """Should install on entry and drop on exit."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # Setup mocks for install
        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
        ]
        parent_ds.get.return_value = None
        parent_ds.drop.return_value = None

        child_ds = Mock()
        child_ds.is_installed.return_value = False  # Needs install

        mock_dataset.side_effect = [
            parent_ds,  # For iter_sourcedata_subdatasets
            child_ds,   # For checking if installed
            parent_ds,  # For drop_subdatasets
        ]

        with TemporarySubdatasetInstall(study_path) as (newly, existing):
            assert len(newly) == 1
            assert len(existing) == 0
            # Subdataset should be installed now
            parent_ds.get.assert_called_once()

        # After exiting, drop should be called
        parent_ds.drop.assert_called_once()

    def test_preserves_existing_subdatasets(self, mock_dataset, tmp_path):
        """Should not drop subdatasets that were already installed."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = [
            {'path': str(study_path / 'sourcedata' / 'ds000001')},
        ]

        # Subdataset already installed
        child_ds = Mock()
        child_ds.is_installed.return_value = True

        mock_dataset.side_effect = [parent_ds, child_ds]

        with TemporarySubdatasetInstall(study_path) as (newly, existing):
            assert len(newly) == 0
            assert len(existing) == 1

        # Drop should not be called (nothing newly installed)
        parent_ds.drop.assert_not_called()


class TestExtractStudyWithSubdatasets:
    """Tests for extract_study_with_subdatasets() high-level function."""

    def test_calls_extraction_with_managed_subdatasets(self, mock_dataset, tmp_path):
        """Should manage subdatasets and call extraction."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # Mock subdataset management
        parent_ds = Mock()
        parent_ds.is_installed.return_value = True
        parent_ds.subdatasets.return_value = []  # No subdatasets for simplicity

        mock_dataset.return_value = parent_ds

        # Mock extraction
        with patch('bids_studies.subdatasets.collect_study_metadata') as mock_extract:
            mock_extract.return_value = {'study_id': 'study-ds000001', 'subjects_num': 10}

            result = extract_study_with_subdatasets(study_path, stage='sizes')

            assert result['study_id'] == 'study-ds000001'
            assert result['subjects_num'] == 10
            mock_extract.assert_called_once_with(study_path, stage='sizes')
