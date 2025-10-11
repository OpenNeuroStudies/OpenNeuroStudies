"""Git submodule operations without cloning."""

import subprocess
from pathlib import Path
from typing import Optional


class SubmoduleLinkError(Exception):
    """Raised when submodule linking fails."""

    pass


def link_submodule(
    parent_repo: Path,
    submodule_path: str,
    url: str,
    commit_sha: str,
    submodule_name: Optional[str] = None,
    datalad_id: Optional[str] = None,
) -> None:
    """Add a git submodule without cloning it.

    Uses git configuration and update-index to create submodule reference
    without cloning the actual content. This is much faster for organizing
    1000+ datasets where immediate content access isn't needed.

    Args:
        parent_repo: Path to parent repository
        submodule_path: Relative path where submodule should appear (e.g., "sourcedata/raw")
        url: URL of submodule repository
        commit_sha: Specific commit SHA to reference
        submodule_name: Name for submodule (defaults to path with slashes replaced)
        datalad_id: DataLad UUID (optional, for DataLad datasets)

    Raises:
        SubmoduleLinkError: If submodule linking fails

    Examples:
        >>> link_submodule(
        ...     parent_repo=Path("study-ds000001"),
        ...     submodule_path="sourcedata/raw",
        ...     url="https://github.com/OpenNeuroDatasets/ds000001",
        ...     commit_sha="f8e27ac909e50b5b5e311f6be271f0b1757ebb7b",
        ...     datalad_id="9850e7d6-100e-11e5-96f6-002590c1b0b6"
        ... )
    """
    if submodule_name is None:
        # Use path as name, removing slashes
        submodule_name = submodule_path.replace("/", "-")

    try:
        # 1. Ensure parent directory for submodule exists
        # (e.g., "sourcedata" must exist for "sourcedata/raw")
        submodule_dir = parent_repo / submodule_path
        submodule_dir.parent.mkdir(parents=True, exist_ok=True)

        # Note: We do NOT create the submodule directory itself. Git handles this
        # when the submodule is cloned. Creating an empty directory causes:
        # "error: 'sourcedata/raw' does not have a commit checked out"

        # 2. Configure .gitmodules - path
        subprocess.run(
            [
                "git",
                "-C",
                str(parent_repo),
                "config",
                "-f",
                ".gitmodules",
                f"submodule.{submodule_name}.path",
                submodule_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Configure .gitmodules - url
        subprocess.run(
            [
                "git",
                "-C",
                str(parent_repo),
                "config",
                "-f",
                ".gitmodules",
                f"submodule.{submodule_name}.url",
                url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Add DataLad-specific fields if provided
        if datalad_id:
            # datalad-id
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent_repo),
                    "config",
                    "-f",
                    ".gitmodules",
                    f"submodule.{submodule_name}.datalad-id",
                    datalad_id,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # datalad-url (same as url for GitHub datasets)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent_repo),
                    "config",
                    "-f",
                    ".gitmodules",
                    f"submodule.{submodule_name}.datalad-url",
                    url,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        # 3. Stage .gitmodules
        subprocess.run(
            ["git", "-C", str(parent_repo), "add", ".gitmodules"],
            check=True,
            capture_output=True,
            text=True,
        )

        # 4. Add gitlink with specific commit SHA
        # Mode 160000 = gitlink (submodule reference)
        subprocess.run(
            [
                "git",
                "-C",
                str(parent_repo),
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{commit_sha},{submodule_path}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as e:
        raise SubmoduleLinkError(
            f"Failed to link submodule {submodule_name} at {submodule_path}: "
            f"{e.stderr if e.stderr else str(e)}"
        ) from e
    except Exception as e:
        raise SubmoduleLinkError(f"Unexpected error linking submodule {submodule_name}: {e}") from e


def is_submodule_linked(parent_repo: Path, submodule_path: str) -> bool:
    """Check if a submodule is already linked.

    Args:
        parent_repo: Path to parent repository
        submodule_path: Relative path of submodule to check

    Returns:
        True if submodule is already linked, False otherwise

    Examples:
        >>> is_submodule_linked(Path("study-ds000001"), "sourcedata/raw")
        True
    """
    try:
        # Check if .gitmodules contains this path
        result = subprocess.run(
            [
                "git",
                "-C",
                str(parent_repo),
                "config",
                "-f",
                ".gitmodules",
                "--get-regexp",
                "^submodule\\..*\\.path$",
                submodule_path,
            ],
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit (means not found)
        )
        return result.returncode == 0
    except Exception:
        return False
