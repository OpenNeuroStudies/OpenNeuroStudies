"""Git utilities for SHA-based dependency tracking.

Provides functions to extract git object SHAs for:
- Submodule commits (gitlinks)
- File blobs
- Directory trees

These SHAs serve as content-based checksums for Snakemake's
params-based rerun triggers.
"""

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1000)
def get_gitlink_sha(submodule_path: str, repo_path: str = ".") -> str:
    """Get commit SHA of a git submodule (gitlink).

    Args:
        submodule_path: Path to submodule relative to repo root
        repo_path: Path to the parent repository

    Returns:
        40-character hexadecimal commit SHA

    Raises:
        subprocess.CalledProcessError: If path is not a submodule
    """
    result = subprocess.run(
        ["git", "-C", repo_path, "ls-tree", "HEAD", submodule_path],
        capture_output=True,
        text=True,
        check=True,
    )
    # Output format: "160000 commit <sha>\t<path>"
    parts = result.stdout.split()
    if len(parts) < 3:
        raise ValueError(f"Not a valid git object: {submodule_path}")
    return parts[2]


@lru_cache(maxsize=1000)
def get_file_blob_sha(file_path: str, repo_path: str = ".") -> str:
    """Get git blob SHA for a specific file.

    Args:
        file_path: Path to file relative to repo root
        repo_path: Path to the repository

    Returns:
        40-character hexadecimal blob SHA

    Raises:
        subprocess.CalledProcessError: If file not in git
    """
    result = subprocess.run(
        ["git", "-C", repo_path, "ls-tree", "HEAD", file_path],
        capture_output=True,
        text=True,
        check=True,
    )
    # Output format: "100644 blob <sha>\t<path>"
    parts = result.stdout.split()
    if len(parts) < 3:
        raise ValueError(f"Not a valid git object: {file_path}")
    return parts[2]


@lru_cache(maxsize=1000)
def get_tree_sha(dir_path: str = ".", repo_path: str = ".") -> str:
    """Get git tree SHA for a directory.

    The tree SHA is a content-based checksum: two directories with
    identical contents will have the same tree SHA regardless of
    when they were created.

    Args:
        dir_path: Path to directory relative to repo root (use "." for root)
        repo_path: Path to the repository

    Returns:
        40-character hexadecimal tree SHA

    Raises:
        subprocess.CalledProcessError: If directory not in git
    """
    # Handle root directory
    ref = "HEAD" if dir_path == "." else f"HEAD:{dir_path}"

    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", ref],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_sourcedata_shas(study_path: str, repo_path: str = ".") -> dict[str, str]:
    """Get git SHAs for all sourcedata subdatasets in a study.

    Since studies are themselves submodules, we need to look inside the
    study submodule to find its nested sourcedata submodules.

    Args:
        study_path: Path to study directory (e.g., "study-ds000001")
        repo_path: Path to the repository root

    Returns:
        Dictionary mapping source dataset names to their commit SHAs
    """
    # The study is a submodule, so we need to query git from inside it
    study_full_path = Path(repo_path) / study_path
    sourcedata_path = study_full_path / "sourcedata"

    if not sourcedata_path.exists():
        return {}

    shas = {}
    for source_dir in sourcedata_path.iterdir():
        if source_dir.is_dir() and not source_dir.name.startswith("."):
            # Query from inside the study submodule
            rel_path = f"sourcedata/{source_dir.name}"
            try:
                # Look up the gitlink SHA from inside the study submodule
                shas[source_dir.name] = get_gitlink_sha(rel_path, str(study_full_path))
            except (subprocess.CalledProcessError, ValueError):
                # Not a submodule, try as regular directory
                try:
                    shas[source_dir.name] = get_tree_sha(rel_path, str(study_full_path))
                except subprocess.CalledProcessError:
                    pass

    return shas


def clear_sha_cache() -> None:
    """Clear the SHA lookup caches.

    Call this if git state has changed during workflow execution.
    """
    get_gitlink_sha.cache_clear()
    get_file_blob_sha.cache_clear()
    get_tree_sha.cache_clear()


def get_head_sha(repo_path: str = ".") -> str:
    """Get the current HEAD commit SHA.

    Args:
        repo_path: Path to the repository

    Returns:
        40-character hexadecimal commit SHA
    """
    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
