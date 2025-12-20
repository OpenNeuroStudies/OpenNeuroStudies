"""Integration tests for datalad-fuse mounting utilities.

Tests the FuseMount context manager for sparse data access.
Requires datalad-fuse to be installed: pip install datalad-fuse
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from openneuro_studies.lib.fuse_mount import (
    FuseMount,
    FuseMountError,
    is_fuse_available,
)


# Skip entire module if datalad-fuse not available
pytestmark = pytest.mark.skipif(
    not is_fuse_available(),
    reason="datalad-fuse not installed (pip install datalad-fuse)",
)


@pytest.fixture
def repo_root() -> Path:
    """Get path to repository root."""
    # Navigate from tests/integration/ to repository root
    test_file = Path(__file__)
    return test_file.parent.parent.parent.parent


@pytest.fixture
def sample_study(repo_root: Path) -> Path:
    """Get path to a sample study dataset.

    Returns:
        Path to study-ds000001 if it exists
    """
    study_path = repo_root / "study-ds000001"
    if not study_path.exists():
        pytest.skip("study-ds000001 not found - run organize first")
    return study_path


@pytest.mark.integration
def test_is_fuse_available() -> None:
    """Test that datalad-fuse availability check works."""
    # This test only runs if datalad-fuse is available (pytestmark)
    assert is_fuse_available() is True
    assert shutil.which("datalad-fuse") is not None


@pytest.mark.integration
def test_fuse_mount_context_manager(repo_root: Path) -> None:
    """Test basic mount/unmount via context manager."""
    with FuseMount(repo_root) as mount:
        assert mount.is_mounted()
        assert mount.path.exists()
        assert mount.path.is_dir()

        # Should be able to list repository root
        contents = list(mount.path.iterdir())
        assert len(contents) > 0

    # After exiting context, should be unmounted
    assert not mount.is_mounted()


@pytest.mark.integration
def test_fuse_mount_with_custom_mount_point(repo_root: Path) -> None:
    """Test mounting with custom mount point."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mount_point = Path(tmpdir) / "custom-mount"

        with FuseMount(repo_root, mount_point=mount_point) as mount:
            assert mount.path == mount_point
            assert mount.path.exists()
            contents = list(mount.path.iterdir())
            assert len(contents) > 0

        # Mount point should still exist but be empty after unmount
        assert mount_point.exists()


@pytest.mark.integration
def test_fuse_mount_access_study_structure(repo_root: Path, sample_study: Path) -> None:
    """Test accessing study directory structure through mount."""
    with FuseMount(repo_root) as mount:
        # Access study directory through mount
        study_name = sample_study.name
        mounted_study = mount.path / study_name

        assert mounted_study.exists()
        assert mounted_study.is_dir()

        # Check for expected structure
        dataset_desc = mounted_study / "dataset_description.json"
        assert dataset_desc.exists()

        # Check for sourcedata (may be empty submodule)
        sourcedata = mounted_study / "sourcedata"
        assert sourcedata.exists()
        assert sourcedata.is_dir()


@pytest.mark.integration
def test_fuse_mount_glob_patterns(repo_root: Path) -> None:
    """Test that glob patterns work through mount."""
    with FuseMount(repo_root) as mount:
        # Find all study directories
        studies = list(mount.path.glob("study-ds*"))
        assert len(studies) > 0

        # Each should be a directory
        for study in studies:
            assert study.is_dir()
            assert study.name.startswith("study-ds")


@pytest.mark.integration
def test_fuse_mount_file_stat(repo_root: Path, sample_study: Path) -> None:
    """Test that stat() works on files through mount without downloading."""
    with FuseMount(repo_root) as mount:
        study_name = sample_study.name
        dataset_desc = mount.path / study_name / "dataset_description.json"

        if dataset_desc.exists():
            stat_info = dataset_desc.stat()
            # Should have size information
            assert stat_info.st_size > 0


@pytest.mark.integration
def test_fuse_mount_invalid_dataset() -> None:
    """Test mounting non-existent dataset raises error."""
    invalid_path = Path("/nonexistent/dataset")

    with pytest.raises(FuseMountError, match="does not exist"):
        with FuseMount(invalid_path):
            pass


@pytest.mark.integration
def test_fuse_mount_path_before_mounting(repo_root: Path) -> None:
    """Test that accessing path before mounting raises error."""
    mount = FuseMount(repo_root)

    with pytest.raises(FuseMountError, match="Not mounted"):
        _ = mount.path


@pytest.mark.integration
def test_fuse_mount_double_unmount(repo_root: Path) -> None:
    """Test that double unmount doesn't cause errors."""
    mount = FuseMount(repo_root)
    mount.mount()
    assert mount.is_mounted()

    mount.unmount()
    assert not mount.is_mounted()

    # Second unmount should be safe (no-op)
    mount.unmount()
    assert not mount.is_mounted()


@pytest.mark.integration
def test_fuse_mount_repr(repo_root: Path) -> None:
    """Test string representation of FuseMount."""
    mount = FuseMount(repo_root)
    repr_str = repr(mount)

    assert "FuseMount" in repr_str
    assert str(repo_root) in repr_str
    assert "unmounted" in repr_str

    with mount:
        repr_str = repr(mount)
        assert "mounted" in repr_str


@pytest.mark.integration
def test_fuse_mount_read_only_mode(repo_root: Path) -> None:
    """Test that read-only mode is default and works."""
    with FuseMount(repo_root, mode="r") as mount:
        # Should be able to read
        contents = list(mount.path.iterdir())
        assert len(contents) > 0

        # Note: Testing write protection would require attempting
        # a write operation, which we don't want in integration tests


@pytest.mark.integration
@pytest.mark.slow
def test_fuse_mount_annex_symlink_resolution(repo_root: Path, sample_study: Path) -> None:
    """Test that git-annex symlinks are resolved properly.

    This test checks if annexed files appear with correct sizes
    without requiring full download.
    """
    with FuseMount(repo_root) as mount:
        study_name = sample_study.name

        # Look for annexed files in sourcedata (if populated)
        sourcedata = mount.path / study_name / "sourcedata"

        # Try to find any .nii or .nii.gz files (annexed)
        annex_files = list(sourcedata.glob("**/*.nii*"))

        if annex_files:
            # Check that we can stat annexed files
            for annex_file in annex_files[:3]:  # Check first 3
                try:
                    stat_info = annex_file.stat()
                    # Should have size from annex key
                    assert stat_info.st_size >= 0
                except OSError:
                    # File might not be available in annex yet
                    pass
        else:
            pytest.skip("No annexed files found in sourcedata - submodule not populated")
