"""Unit tests for subdataset_manager module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openneuro_studies.lib.subdataset_manager import (
    _find_immediate_parent_repo,
    get_uninitialized_sourcedata,
    initialize_subdatasets,
    is_subdataset_initialized,
    restore_initialization_state,
    snapshot_initialization_state,
)


class TestIsSubdatasetInitialized:
    """Tests for is_subdataset_initialized function."""

    def test_nonexistent_path_returns_false(self):
        """Nonexistent subdataset path should return False."""
        assert not is_subdataset_initialized(Path("/nonexistent/path"))

    def test_no_git_directory_returns_false(self, tmp_path):
        """Subdataset without .git should return False."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        assert not is_subdataset_initialized(subdir)

    @patch("subprocess.run")
    def test_own_repo_with_files_returns_true(self, mock_run, tmp_path):
        """Subdataset that is its own repo with files should return True."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".git").mkdir()
        (subdir / "file.txt").write_text("content")

        # Mock rev-parse returning this path
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"{subdir}\n"
        )
        assert is_subdataset_initialized(subdir)

    @patch("subprocess.run")
    def test_parent_repo_returns_false(self, mock_run, tmp_path):
        """Directory inside parent repo should return False (regression test).

        This is the critical bug fix - previously git status would succeed
        by finding the parent repository, causing false positives.
        """
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".git").mkdir()

        subdir = parent / "subdir"
        subdir.mkdir()
        (subdir / ".git").touch()  # Gitlink file

        # Mock rev-parse returning PARENT path (not subdir)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"{parent}\n"  # Returns parent, not subdir
        )

        # Should return False because git root != subdataset path
        assert not is_subdataset_initialized(subdir)

    @patch("subprocess.run")
    def test_own_repo_but_empty_returns_false(self, mock_run, tmp_path):
        """Subdataset that is its own repo but has no files should return False."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".git").mkdir()
        # No other files created

        # Mock rev-parse returning this path
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"{subdir}\n"
        )

        # Should return False because no files in working tree
        assert not is_subdataset_initialized(subdir)

    @patch("subprocess.run")
    def test_git_command_fails_returns_false(self, mock_run, tmp_path):
        """Subdataset with failing git command should return False."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".git").touch()

        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        assert not is_subdataset_initialized(subdir)

    @patch("subprocess.run")
    def test_git_timeout_returns_false(self, mock_run, tmp_path):
        """Subdataset with timeout should return False."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".git").touch()

        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)
        assert not is_subdataset_initialized(subdir)


class TestGetUninitializedSourcedata:
    """Tests for get_uninitialized_sourcedata function."""

    def test_no_sourcedata_directory_returns_empty(self, tmp_path):
        """Study without sourcedata/ should return empty list."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()
        assert get_uninitialized_sourcedata(study_path) == []

    @patch("openneuro_studies.lib.subdataset_manager.is_subdataset_initialized")
    def test_finds_uninitialized_subdatasets(self, mock_is_init, tmp_path):
        """Should return paths to uninitialized sourcedata subdatasets."""
        study_path = tmp_path / "study-ds000001"
        sourcedata_dir = study_path / "sourcedata"
        sourcedata_dir.mkdir(parents=True)

        # Create two sourcedata subdatasets
        (sourcedata_dir / "ds000001").mkdir()
        (sourcedata_dir / "ds000002").mkdir()

        # Mock: first is uninitialized, second is initialized
        mock_is_init.side_effect = [False, True]

        result = get_uninitialized_sourcedata(study_path)

        assert len(result) == 1
        assert result[0] == sourcedata_dir / "ds000001"

    @patch("openneuro_studies.lib.subdataset_manager.is_subdataset_initialized")
    def test_returns_sorted_paths(self, mock_is_init, tmp_path):
        """Should return paths in sorted order."""
        study_path = tmp_path / "study-ds000001"
        sourcedata_dir = study_path / "sourcedata"
        sourcedata_dir.mkdir(parents=True)

        # Create subdatasets in reverse order
        (sourcedata_dir / "ds000003").mkdir()
        (sourcedata_dir / "ds000001").mkdir()
        (sourcedata_dir / "ds000002").mkdir()

        # All uninitialized
        mock_is_init.return_value = False

        result = get_uninitialized_sourcedata(study_path)

        assert len(result) == 3
        assert result[0].name == "ds000001"
        assert result[1].name == "ds000002"
        assert result[2].name == "ds000003"


class TestInitializeSubdatasets:
    """Tests for initialize_subdatasets function."""

    def test_empty_list_returns_empty_dict(self):
        """Empty subdataset list should return empty results."""
        assert initialize_subdatasets([]) == {}

    @patch("subprocess.run")
    def test_successful_initialization(self, mock_run, tmp_path):
        """Should successfully initialize subdataset."""
        mock_run.return_value = MagicMock(returncode=0)

        # Create .gitmodules that registers the subdataset
        (tmp_path / ".gitmodules").write_text(
            "[submodule \"ds000001\"]\n"
            "\tpath = sourcedata/ds000001\n"
            "\turl = https://example.com/ds000001.git\n"
        )

        subdataset = tmp_path / "sourcedata" / "ds000001"
        result = initialize_subdatasets([subdataset], parent_path=tmp_path)

        assert result == {subdataset: True}
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_failed_initialization(self, mock_run, tmp_path):
        """Should handle initialization failure gracefully."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        # Create .gitmodules
        (tmp_path / ".gitmodules").write_text(
            "[submodule \"ds000001\"]\n"
            "\tpath = sourcedata/ds000001\n"
            "\turl = https://example.com/ds000001.git\n"
        )

        subdataset = tmp_path / "sourcedata" / "ds000001"
        result = initialize_subdatasets([subdataset], parent_path=tmp_path)

        assert result == {subdataset: False}

    @patch("subprocess.run")
    def test_timeout_initialization(self, mock_run, tmp_path):
        """Should handle timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 300)

        # Create .gitmodules
        (tmp_path / ".gitmodules").write_text(
            "[submodule \"ds000001\"]\n"
            "\tpath = sourcedata/ds000001\n"
            "\turl = https://example.com/ds000001.git\n"
        )

        subdataset = tmp_path / "sourcedata" / "ds000001"
        result = initialize_subdatasets([subdataset], parent_path=tmp_path)

        assert result == {subdataset: False}

    @patch("subprocess.run")
    def test_parallel_initialization(self, mock_run, tmp_path):
        """Should initialize multiple subdatasets in parallel."""
        mock_run.return_value = MagicMock(returncode=0)

        # Create .gitmodules that registers all subdatasets
        (tmp_path / ".gitmodules").write_text(
            "[submodule \"ds000001\"]\n"
            "\tpath = sourcedata/ds000001\n"
            "\turl = https://example.com/ds000001.git\n"
            "[submodule \"ds000002\"]\n"
            "\tpath = sourcedata/ds000002\n"
            "\turl = https://example.com/ds000002.git\n"
            "[submodule \"ds000003\"]\n"
            "\tpath = sourcedata/ds000003\n"
            "\turl = https://example.com/ds000003.git\n"
        )

        subdatasets = [
            tmp_path / "sourcedata" / "ds000001",
            tmp_path / "sourcedata" / "ds000002",
            tmp_path / "sourcedata" / "ds000003",
        ]

        result = initialize_subdatasets(subdatasets, parent_path=tmp_path, jobs=2)

        assert len(result) == 3
        assert all(success for success in result.values())


class TestSnapshotInitializationState:
    """Tests for snapshot_initialization_state function."""

    @patch("openneuro_studies.lib.subdataset_manager.is_subdataset_initialized")
    def test_captures_initialized_subdatasets(self, mock_is_init, tmp_path):
        """Should capture paths of initialized subdatasets."""
        study_path = tmp_path / "study-ds000001"
        sourcedata_dir = study_path / "sourcedata"
        sourcedata_dir.mkdir(parents=True)

        (sourcedata_dir / "ds000001").mkdir()
        (sourcedata_dir / "ds000002").mkdir()

        # Mock: first is initialized, second is not
        mock_is_init.side_effect = [True, False]

        result = snapshot_initialization_state([study_path])

        assert len(result) == 1
        assert sourcedata_dir / "ds000001" in result
        assert sourcedata_dir / "ds000002" not in result

    def test_no_sourcedata_returns_empty(self, tmp_path):
        """Study without sourcedata should return empty set."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        result = snapshot_initialization_state([study_path])

        assert result == set()

    @patch("openneuro_studies.lib.subdataset_manager.is_subdataset_initialized")
    def test_multiple_studies(self, mock_is_init, tmp_path):
        """Should snapshot multiple studies."""
        study1 = tmp_path / "study-ds000001"
        study2 = tmp_path / "study-ds000002"

        (study1 / "sourcedata" / "ds000001").mkdir(parents=True)
        (study2 / "sourcedata" / "ds000002").mkdir(parents=True)

        # Both initialized
        mock_is_init.return_value = True

        result = snapshot_initialization_state([study1, study2])

        assert len(result) == 2


class TestRestoreInitializationState:
    """Tests for restore_initialization_state function."""

    @patch("openneuro_studies.lib.subdataset_manager._deinitialize_single_subdataset")
    def test_deinitializes_new_subdatasets(self, mock_deinit, tmp_path):
        """Should deinitialize subdatasets not in desired state."""
        sub1 = tmp_path / "sourcedata" / "ds000001"
        sub2 = tmp_path / "sourcedata" / "ds000002"
        sub3 = tmp_path / "sourcedata" / "ds000003"

        current_state = {sub1, sub2, sub3}
        desired_state = {sub1}  # Only sub1 was originally initialized

        mock_deinit.return_value = (sub2, True)

        restore_initialization_state(current_state, desired_state, parent_path=tmp_path)

        # Should deinitialize sub2 and sub3
        assert mock_deinit.call_count == 2

    @patch("openneuro_studies.lib.subdataset_manager._deinitialize_single_subdataset")
    def test_no_changes_when_states_match(self, mock_deinit, tmp_path):
        """Should not deinitialize when current matches desired."""
        sub1 = tmp_path / "sourcedata" / "ds000001"

        current_state = {sub1}
        desired_state = {sub1}

        restore_initialization_state(current_state, desired_state, parent_path=tmp_path)

        mock_deinit.assert_not_called()

    @patch("openneuro_studies.lib.subdataset_manager._deinitialize_single_subdataset")
    def test_empty_states(self, mock_deinit, tmp_path):
        """Should handle empty states gracefully."""
        restore_initialization_state(set(), set(), parent_path=tmp_path)

        mock_deinit.assert_not_called()


class TestFindImmediateParentRepo:
    """Tests for _find_immediate_parent_repo function."""

    def test_finds_immediate_parent_for_nested_subdataset(self, tmp_path):
        """Should find study repo for sourcedata subdataset."""
        # Create structure:
        # parent/
        #   .gitmodules (contains study-ds000001)
        #   study-ds000001/
        #     .gitmodules (contains sourcedata/ds000001)
        #     sourcedata/
        #       ds000001/

        parent = tmp_path
        study = parent / "study-ds000001"
        sourcedata = study / "sourcedata"
        subdataset = sourcedata / "ds000001"

        study.mkdir()
        sourcedata.mkdir()
        subdataset.mkdir()

        # Create parent .gitmodules
        (parent / ".gitmodules").write_text(
            "[submodule \"study-ds000001\"]\n"
            "\tpath = study-ds000001\n"
            "\turl = https://example.com/study-ds000001.git\n"
        )

        # Create study .gitmodules
        (study / ".gitmodules").write_text(
            "[submodule \"ds000001\"]\n"
            "\tpath = sourcedata/ds000001\n"
            "\turl = https://example.com/ds000001.git\n"
        )

        # Find parent for subdataset
        result = _find_immediate_parent_repo(subdataset, parent)

        assert result == study

    def test_finds_parent_for_top_level_submodule(self, tmp_path):
        """Should find parent repo for top-level study subdataset."""
        # Create structure:
        # parent/
        #   .gitmodules (contains study-ds000001)
        #   study-ds000001/

        parent = tmp_path
        study = parent / "study-ds000001"
        study.mkdir()

        (parent / ".gitmodules").write_text(
            "[submodule \"study-ds000001\"]\n"
            "\tpath = study-ds000001\n"
            "\turl = https://example.com/study-ds000001.git\n"
        )

        result = _find_immediate_parent_repo(study, parent)

        assert result == parent

    def test_returns_none_when_not_registered(self, tmp_path):
        """Should return None if subdataset not in any .gitmodules."""
        # Create structure without .gitmodules entries
        parent = tmp_path
        study = parent / "study-ds000001"
        subdataset = study / "sourcedata" / "ds000001"

        study.mkdir()
        (study / "sourcedata").mkdir()
        subdataset.mkdir()

        result = _find_immediate_parent_repo(subdataset, parent)

        assert result is None

    def test_handles_derivative_subdatasets(self, tmp_path):
        """Should find parent for derivative subdatasets."""
        # Create structure:
        # parent/
        #   study-ds000001/
        #     .gitmodules (contains derivatives/fMRIPrep-21.0.1)
        #     derivatives/
        #       fMRIPrep-21.0.1/

        parent = tmp_path
        study = parent / "study-ds000001"
        derivatives = study / "derivatives"
        subdataset = derivatives / "fMRIPrep-21.0.1"

        study.mkdir()
        derivatives.mkdir()
        subdataset.mkdir()

        (study / ".gitmodules").write_text(
            "[submodule \"fMRIPrep-21.0.1\"]\n"
            "\tpath = derivatives/fMRIPrep-21.0.1\n"
            "\turl = https://example.com/ds000001-fmriprep.git\n"
        )

        result = _find_immediate_parent_repo(subdataset, parent)

        assert result == study
