"""FUSE mount utilities for sparse data access.

Provides context manager for datalad-fuse mounts to access annexed content
without full clones. Supports FR-032/033 for imaging metrics extraction.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FuseMountError(Exception):
    """Raised when FUSE mount operations fail."""

    pass


def _find_datalad_cmd() -> Optional[str]:
    """Find datalad command path.

    Checks:
    1. In PATH via shutil.which()
    2. In same venv as current Python interpreter

    Returns:
        Path to datalad command or None
    """
    # Try PATH first
    datalad_path = shutil.which("datalad")
    if datalad_path:
        return datalad_path

    # Try same directory as Python interpreter (venv)
    python_dir = Path(sys.executable).parent
    datalad_venv = python_dir / "datalad"
    if datalad_venv.exists() and datalad_venv.is_file():
        return str(datalad_venv)

    return None


def is_fuse_available() -> bool:
    """Check if datalad fusefs is available.

    Returns:
        True if datalad fusefs command is available
    """
    datalad_cmd = _find_datalad_cmd()
    if datalad_cmd is None:
        return False

    try:
        result = subprocess.run(
            [datalad_cmd, "fusefs", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


class FuseMount:
    """Context manager for datalad-fuse mounts.

    Provides lazy access to git-annex content via FUSE filesystem.
    Files are fetched on-demand when accessed, avoiding full clones.

    Example:
        >>> with FuseMount(repo_path) as mount:
        ...     subjects = list(mount.path.glob("study-*/sourcedata/*/sub-*"))
        ...     print(f"Found {len(subjects)} subjects")

    Args:
        dataset_path: Path to DataLad dataset to mount
        mount_point: Optional mount point (creates temp dir if None)
        foreground: Run in foreground for debugging (default: False)
        mode: Mount mode - "r" for read-only (default)

    Raises:
        FuseMountError: If datalad-fuse is not available or mount fails
    """

    def __init__(
        self,
        dataset_path: Path,
        mount_point: Optional[Path] = None,
        foreground: bool = False,
        mode: str = "r",
    ):
        """Initialize FUSE mount configuration.

        Args:
            dataset_path: Path to dataset to mount
            mount_point: Optional mount point (temp dir if None)
            foreground: Run in foreground (for debugging)
            mode: Mount mode ("r" for read-only)
        """
        self.dataset_path = Path(dataset_path).resolve()
        self.mount_point = Path(mount_point) if mount_point else None
        self.foreground = foreground
        self.mode = mode

        self._temp_mount_dir: Optional[tempfile.TemporaryDirectory] = None
        self._mount_process: Optional[subprocess.Popen] = None
        self._is_mounted = False

    @property
    def path(self) -> Path:
        """Get the mount point path.

        Returns:
            Path to mounted filesystem

        Raises:
            FuseMountError: If not mounted
        """
        if not self._is_mounted or self.mount_point is None:
            raise FuseMountError("Not mounted - use within context manager")
        return self.mount_point

    def __enter__(self) -> "FuseMount":
        """Mount the dataset via datalad-fuse.

        Returns:
            Self with mounted filesystem

        Raises:
            FuseMountError: If mount fails
        """
        self.mount()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Unmount the filesystem on context exit."""
        self.unmount()

    def mount(self) -> None:
        """Mount the dataset via datalad-fuse.

        Raises:
            FuseMountError: If mount fails or datalad-fuse not available
        """
        if not is_fuse_available():
            raise FuseMountError(
                "datalad fusefs not available. Install with: pip install datalad-fuse"
            )

        if not self.dataset_path.exists():
            raise FuseMountError(f"Dataset path does not exist: {self.dataset_path}")

        # Create mount point if not specified
        if self.mount_point is None:
            self._temp_mount_dir = tempfile.TemporaryDirectory(prefix="fuse-mount-")
            self.mount_point = Path(self._temp_mount_dir.name)
        else:
            # Ensure mount point exists
            self.mount_point.mkdir(parents=True, exist_ok=True)

        # Find datalad command
        datalad_cmd = _find_datalad_cmd()
        if datalad_cmd is None:
            raise FuseMountError("datalad command not found")

        # Build datalad fusefs command
        cmd = [
            datalad_cmd,
            "fusefs",
            "--dataset", str(self.dataset_path),
            "--mode-transparent",  # Expose .git directory
        ]

        if self.foreground:
            cmd.append("--foreground")

        # Mount point is the final positional argument
        cmd.append(str(self.mount_point))

        logger.info(f"Mounting {self.dataset_path} at {self.mount_point}")
        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            if self.foreground:
                # Run in foreground (blocking)
                subprocess.run(cmd, check=True)
                self._is_mounted = True
            else:
                # Run in background
                self._mount_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                # Wait for mount to be ready
                self._wait_for_mount()
                self._is_mounted = True

            logger.info(f"Mounted successfully at {self.mount_point}")

        except subprocess.CalledProcessError as e:
            self._cleanup()
            raise FuseMountError(f"Failed to mount: {e}") from e
        except Exception as e:
            self._cleanup()
            raise FuseMountError(f"Mount error: {e}") from e

    def _wait_for_mount(self, timeout: float = 10.0, poll_interval: float = 0.1) -> None:
        """Wait for FUSE mount to be ready.

        Args:
            timeout: Maximum wait time in seconds
            poll_interval: Time between checks in seconds

        Raises:
            FuseMountError: If mount doesn't become ready in time
        """
        if self.mount_point is None:
            raise FuseMountError("Mount point not initialized")

        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if mount point is accessible
            try:
                # Try to list the mount point
                list(self.mount_point.iterdir())
                return  # Mount is ready
            except (OSError, PermissionError):
                # Not ready yet
                pass

            # Check if process has failed
            if self._mount_process and self._mount_process.poll() is not None:
                stdout, stderr = self._mount_process.communicate()
                raise FuseMountError(
                    f"Mount process exited prematurely:\nstdout: {stdout}\nstderr: {stderr}"
                )

            time.sleep(poll_interval)

        raise FuseMountError(f"Mount did not become ready within {timeout}s")

    def unmount(self) -> None:
        """Unmount the FUSE filesystem."""
        if not self._is_mounted:
            logger.debug("Not mounted, nothing to unmount")
            return

        logger.info(f"Unmounting {self.mount_point}")

        try:
            # Use fusermount -u to unmount
            if self.mount_point and self.mount_point.exists():
                subprocess.run(
                    ["fusermount", "-u", str(self.mount_point)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("Unmounted successfully")

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to unmount cleanly: {e.stderr}")
            # Try to continue cleanup anyway

        except FileNotFoundError:
            logger.warning("fusermount not found, mount may not be cleaned up")

        finally:
            # Terminate background process if running
            if self._mount_process:
                if self._mount_process.poll() is None:
                    self._mount_process.terminate()
                    try:
                        self._mount_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning("Mount process did not terminate, killing")
                        self._mount_process.kill()
                        self._mount_process.wait()

            self._cleanup()
            self._is_mounted = False

    def _cleanup(self) -> None:
        """Clean up temporary mount directory."""
        if self._temp_mount_dir:
            try:
                self._temp_mount_dir.cleanup()
            except Exception as e:
                logger.warning(f"Failed to cleanup temp mount dir: {e}")
            finally:
                self._temp_mount_dir = None

    def is_mounted(self) -> bool:
        """Check if filesystem is currently mounted.

        Returns:
            True if mounted
        """
        return self._is_mounted

    def __repr__(self) -> str:
        """String representation of mount."""
        status = "mounted" if self._is_mounted else "unmounted"
        return f"FuseMount({self.dataset_path} -> {self.mount_point}, {status})"
