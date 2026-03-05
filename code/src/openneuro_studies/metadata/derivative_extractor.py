"""Extract metadata from BIDS derivative datasets.

This module provides functions to extract metadata from derivative datasets
using git tree access only (no annexed content download required).

All extractions work with temporarily installed subdatasets via git ls-files.
"""

import configparser
import json
import logging
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================


def _get_dataset_uuid(path: Path) -> Optional[str]:
    """Get DataLad dataset UUID without full installation.

    Args:
        path: Path to dataset (can be uninitialized subdataset)

    Returns:
        UUID string or None if not a DataLad dataset
    """
    # Try reading .datalad/config file directly
    config_path = path / ".datalad" / "config"
    if config_path.exists():
        try:
            config = configparser.ConfigParser()
            config.read(config_path)
            if config.has_option("datalad.dataset", "id"):
                return config.get("datalad.dataset", "id")
        except Exception as e:
            logger.debug(f"Could not parse .datalad/config at {path}: {e}")

    # Fallback: try git config (works for initialized subdatasets)
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(path), "config", "datalad.dataset.id"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cmd_result.returncode == 0 and cmd_result.stdout.strip():
            return cmd_result.stdout.strip()
    except Exception:
        pass

    return None


def _get_git_version(path: Path) -> str:
    """Get git version string for a dataset.

    Tries git describe first, falls back to short SHA.

    Args:
        path: Path to git repository

    Returns:
        Version string or "n/a"
    """
    # Try git describe first
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(path), "describe", "--always"],
            capture_output=True,
            text=True,
            check=True,
        )
        version = cmd_result.stdout.strip()
        if version:
            return version
    except subprocess.CalledProcessError:
        pass

    # Fallback: use short SHA
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        sha = cmd_result.stdout.strip()
        if sha:
            return sha
    except subprocess.CalledProcessError:
        pass

    return "n/a"


def _extract_processed_version_from_derivative_sourcedata(
    derivative_path: Path,
    raw_path: Path,
) -> str:
    """Extract the version of raw data that was processed.

    Strategy:
    1. Get UUID of the raw dataset
    2. Find matching UUID in derivative's .gitmodules
    3. Extract commit SHA from gitlink for that submodule

    Args:
        derivative_path: Path to derivative dataset
        raw_path: Path to raw sourcedata dataset

    Returns:
        Git version string (commit SHA) or "n/a"
    """
    # Get raw dataset UUID
    raw_uuid = _get_dataset_uuid(raw_path)
    if not raw_uuid:
        logger.debug(f"Could not get UUID for raw dataset {raw_path}")
        return "n/a"

    # Read derivative's .gitmodules (from git tree if needed)
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(derivative_path), "show", "HEAD:.gitmodules"],
            capture_output=True,
            text=True,
            check=True,
        )
        if cmd_result.returncode != 0 or not cmd_result.stdout.strip():
            return "n/a"
        gitmodules_content = cmd_result.stdout
    except subprocess.CalledProcessError:
        return "n/a"

    # Parse .gitmodules to find sourcedata submodules
    config = configparser.ConfigParser()
    try:
        config.read_string(gitmodules_content)
    except configparser.Error as e:
        logger.debug(f"Failed to parse .gitmodules for {derivative_path}: {e}")
        return "n/a"

    # Find submodule with matching datalad-id
    for section in config.sections():
        if not section.startswith("submodule"):
            continue

        # Check if this is a sourcedata submodule
        path = config.get(section, "path", fallback="")
        if not path.startswith("sourcedata/"):
            continue

        # Check datalad-id
        submodule_uuid = config.get(section, "datalad-id", fallback="")
        if submodule_uuid == raw_uuid:
            # Found matching UUID - extract commit SHA from gitlink
            try:
                cmd_result = subprocess.run(
                    ["git", "-C", str(derivative_path), "ls-tree", "HEAD", path],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if cmd_result.stdout.strip():
                    # Output format: "160000 commit <SHA>\t<path>"
                    parts = cmd_result.stdout.strip().split()
                    if len(parts) >= 3 and parts[0] == "160000":
                        commit_sha = parts[2]
                        logger.debug(
                            f"Found processed version {commit_sha} for {derivative_path.name} "
                            f"from {path} (UUID match)"
                        )
                        return commit_sha
            except subprocess.CalledProcessError as e:
                logger.debug(f"Failed to extract gitlink SHA for {path}: {e}")

    return "n/a"


# ============================================================================
# Basic Stats (git-annex info)
# ============================================================================


def extract_derivative_stats(derivative_path: Path) -> dict[str, Any]:
    """Extract size and file count stats from derivative using git-annex info.

    Args:
        derivative_path: Path to derivative subdataset (must be installed)

    Returns:
        Dict with size_total, size_annexed, file_count
    """
    result = {
        "size_total": "n/a",
        "size_annexed": "n/a",
        "file_count": "n/a",
    }

    try:
        # Run git-annex info --json --bytes to get numeric byte counts
        cmd_result = subprocess.run(
            ["git", "-C", str(derivative_path), "annex", "info", "--json", "--bytes"],
            capture_output=True,
            text=True,
            check=True,
        )

        if cmd_result.stdout.strip():
            info = json.loads(cmd_result.stdout)

            # Extract stats from git-annex info output
            # With --bytes, values are numeric instead of humanized strings
            # Keys depend on git-annex version, check both old and new formats
            if "size of annexed files in working tree" in info:
                size_value = info["size of annexed files in working tree"]
                result["size_annexed"] = str(size_value) if isinstance(size_value, int) else size_value

            if "local annex size" in info:
                size_value = info["local annex size"]
                result["size_total"] = str(size_value) if isinstance(size_value, int) else size_value
            elif "size of annexed files in working tree" in info:
                # Use annexed size as total if no separate total
                size_value = info["size of annexed files in working tree"]
                result["size_total"] = str(size_value) if isinstance(size_value, int) else size_value

            # Count files via git ls-files (more reliable than annex info)
            files_result = subprocess.run(
                ["git", "-C", str(derivative_path), "ls-files"],
                capture_output=True,
                text=True,
                check=True,
            )
            if files_result.stdout.strip():
                file_count = len(files_result.stdout.strip().split("\n"))
                result["file_count"] = file_count

    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to extract stats for {derivative_path}: {e}")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse git-annex info for {derivative_path}: {e}")

    return result


# ============================================================================
# Version Tracking
# ============================================================================


def extract_version_tracking(
    derivative_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    """Extract version tracking metadata.

    Args:
        derivative_path: Path to derivative subdataset
        raw_path: Path to raw sourcedata subdataset

    Returns:
        Dict with processed_raw_version, current_raw_version, uptodate, outdatedness
    """
    # Strategy 1: Try dataset_description.json SourceDatasets.Version
    processed_version = "n/a"

    # Use git show to read file from git tree (works with sparse datasets)
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(derivative_path), "show", "HEAD:dataset_description.json"],
            capture_output=True,
            text=True,
            check=True,
        )
        if cmd_result.returncode == 0 and cmd_result.stdout.strip():
            dd = json.loads(cmd_result.stdout)
            # Parse SourceDatasets for version info
            sources = dd.get("SourceDatasets", [])
            if sources and isinstance(sources, list):
                # Extract version from first source
                first_source = sources[0]
                if isinstance(first_source, dict):
                    processed_version = first_source.get("Version", "n/a")
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        logger.debug(f"Could not parse dataset_description.json for {derivative_path}: {e}")

    # Strategy 2: If still n/a, check derivative's sourcedata/ for UUID match
    if processed_version == "n/a" and raw_path:
        processed_version = _extract_processed_version_from_derivative_sourcedata(
            derivative_path, raw_path
        )

    # Get current version from raw dataset
    current_version = _get_git_version(raw_path) if raw_path else "n/a"

    # Calculate outdatedness
    uptodate = False
    outdatedness = "n/a"

    if processed_version != "n/a" and current_version != "n/a":
        if processed_version == current_version:
            uptodate = True
            outdatedness = 0
        else:
            # Count commits between versions
            try:
                cmd_result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(raw_path),
                        "rev-list",
                        "--count",
                        f"{processed_version}..{current_version}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                outdatedness = int(cmd_result.stdout.strip())
                uptodate = outdatedness == 0
            except (subprocess.CalledProcessError, ValueError):
                # Versions might not be in same git history
                outdatedness = "n/a"

    return {
        "processed_raw_version": processed_version,
        "current_raw_version": current_version,
        "uptodate": uptodate,
        "outdatedness": outdatedness,
    }


# ============================================================================
# Task and Modality Tracking
# ============================================================================


def extract_tasks_processed(derivative_path: Path) -> str:
    """Extract task names from derivative func/ directory.

    Args:
        derivative_path: Path to derivative subdataset

    Returns:
        Comma-separated sorted task names, or 'n/a' if none found
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return "n/a"

        # Filter for func/ files (handles both session and non-session structures)
        all_files = result.stdout.strip().split("\n")
        files = [f for f in all_files if "/func/" in f]

        if not files:
            return "n/a"

        # Extract task entities: _task-{label}_
        task_pattern = re.compile(r"_task-([a-zA-Z0-9]+)_")
        tasks = set()

        for filepath in files:
            # Only consider data files (not transforms, not events.tsv, etc.)
            if any(
                filepath.endswith(ext)
                for ext in [
                    "_bold.nii.gz",
                    "_bold.json",
                    "_cbv.nii.gz",
                    "_cbv.json",
                    "_sbref.nii.gz",
                    "_sbref.json",
                ]
            ):
                match = task_pattern.search(filepath)
                if match:
                    tasks.add(match.group(1))

        if tasks:
            return ",".join(sorted(tasks))
        return "n/a"

    except subprocess.CalledProcessError:
        return "n/a"


def extract_tasks_missing(
    derivative_path: Path,
    raw_path: Path,
    tasks_processed: str,
) -> str:
    """Extract tasks that exist in raw but not in derivative.

    Args:
        derivative_path: Path to derivative subdataset
        raw_path: Path to raw sourcedata subdataset
        tasks_processed: Already-extracted tasks from derivative

    Returns:
        Comma-separated missing task names, or empty string if none missing
    """
    # Parse tasks_processed
    if tasks_processed == "n/a":
        deriv_tasks = set()
    else:
        deriv_tasks = set(tasks_processed.split(","))

    # Extract tasks from raw sourcedata
    try:
        result = subprocess.run(
            ["git", "-C", str(raw_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return ""  # No raw func data

        # Filter for func/ files (handles both session and non-session structures)
        all_files = result.stdout.strip().split("\n")
        files = [f for f in all_files if "/func/" in f]

        if not files:
            return ""  # No raw func data
        task_pattern = re.compile(r"_task-([a-zA-Z0-9]+)_")
        raw_tasks = set()

        for filepath in files:
            if filepath.endswith("_bold.nii.gz"):
                match = task_pattern.search(filepath)
                if match:
                    raw_tasks.add(match.group(1))

        # Calculate missing
        missing = raw_tasks - deriv_tasks

        if missing:
            return ",".join(sorted(missing))
        return ""  # All tasks processed

    except subprocess.CalledProcessError:
        return "n/a"  # Cannot determine


def extract_anat_processed(derivative_path: Path) -> bool:
    """Check if anatomical processing outputs exist.

    Considers anatomical processed if ANY _desc- entity present in anat/ NIfTI files.

    Args:
        derivative_path: Path to derivative subdataset

    Returns:
        True if anatomical outputs with processing indicators found, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return False

        # Filter for anat/ files (handles both session and non-session structures)
        all_files = result.stdout.strip().split("\n")
        files = [f for f in all_files if "/anat/" in f]

        if not files:
            return False

        # Check for processing indicators
        for filepath in files:
            # NIfTI files only (exclude JSON sidecars)
            if not filepath.endswith(".nii.gz"):
                continue

            # Any desc- entity indicates processing
            if "_desc-" in filepath:
                return True

            # Space normalization indicates processing
            if "_space-" in filepath and "_from-" not in filepath:  # Exclude transforms
                return True

            # Segmentation outputs indicate processing
            if any(seg in filepath for seg in ["_dseg.nii.gz", "_probseg.nii.gz"]):
                return True

        return False

    except subprocess.CalledProcessError:
        return False


def extract_func_processed(derivative_path: Path) -> bool:
    """Check if functional processing outputs exist.

    Args:
        derivative_path: Path to derivative subdataset

    Returns:
        True if functional outputs found, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return False

        # Filter for func/ files (handles both session and non-session structures)
        all_files = result.stdout.strip().split("\n")
        files = [f for f in all_files if "/func/" in f]

        if not files:
            return False

        # Check for preprocessed functional outputs
        func_indicators = [
            "_desc-preproc_bold.nii.gz",
            "_space-",  # Any space-normalized functional
            "_boldref.nii.gz",
        ]

        for filepath in files:
            if any(indicator in filepath for indicator in func_indicators):
                return True

        return False

    except subprocess.CalledProcessError:
        return False


def extract_processing_complete(
    tasks_missing: str,
    anat_processed: bool,
    func_processed: bool,
    raw_path: Path,
) -> bool:
    """Determine if processing is complete.

    Args:
        tasks_missing: Already-extracted missing tasks
        anat_processed: Already-extracted anat flag
        func_processed: Already-extracted func flag
        raw_path: Path to raw sourcedata

    Returns:
        True if processing complete, False if partial
    """
    # Check tasks completeness
    if tasks_missing and tasks_missing != "n/a":
        return False  # Missing tasks means incomplete

    # Check if raw has anat/func
    try:
        result = subprocess.run(
            ["git", "-C", str(raw_path), "ls-tree", "-d", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )

        raw_dirs = result.stdout.strip().split("\n")
        raw_has_anat = any("anat" in line for line in raw_dirs)
        raw_has_func = any("func" in line for line in raw_dirs)

        # If raw has modality, derivative must have processed it
        if raw_has_anat and not anat_processed:
            return False

        if raw_has_func and not func_processed:
            return False

        # All checks passed
        return True

    except subprocess.CalledProcessError:
        return False  # Cannot determine, mark as incomplete


# ============================================================================
# Space Tracking
# ============================================================================


def extract_template_spaces(derivative_path: Path) -> str:
    """Extract template spaces with actual data.

    Args:
        derivative_path: Path to derivative subdataset

    Returns:
        Comma-separated sorted space names, or 'n/a' if none
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return "n/a"

        files = result.stdout.strip().split("\n")

        # Extract space entities: _space-{label}_
        space_pattern = re.compile(r"_space-([a-zA-Z0-9]+)_")
        data_spaces = set()

        for filepath in files:
            # Exclude transform files
            if any(x in filepath for x in ["_xfm.", "_from-", "_to-"]):
                continue

            # Only consider data files
            if any(
                filepath.endswith(ext)
                for ext in [
                    "_bold.nii.gz",
                    "_T1w.nii.gz",
                    "_T2w.nii.gz",
                    "_cbv.nii.gz",
                    "_mask.nii.gz",
                    "_dseg.nii.gz",
                    "_probseg.nii.gz",
                    "_dtissue.nii.gz",
                    ".func.gii",
                    ".surf.gii",
                    ".shape.gii",  # Surface files
                ]
            ):
                match = space_pattern.search(filepath)
                if match:
                    data_spaces.add(match.group(1))

        if data_spaces:
            return ",".join(sorted(data_spaces))
        return "n/a"

    except subprocess.CalledProcessError:
        return "n/a"


def extract_transform_spaces(
    derivative_path: Path,
    template_spaces: str,
) -> str:
    """Extract spaces with only transformations.

    Args:
        derivative_path: Path to derivative subdataset
        template_spaces: Already-extracted data spaces

    Returns:
        Comma-separated sorted space names, or empty string if none
    """
    # Parse template_spaces
    if template_spaces == "n/a":
        data_spaces = set()
    else:
        data_spaces = set(template_spaces.split(","))

    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return ""

        files = result.stdout.strip().split("\n")

        # Extract spaces from transforms
        to_pattern = re.compile(r"_to-([a-zA-Z0-9]+)_")
        from_pattern = re.compile(r"_from-([a-zA-Z0-9]+)_")
        space_pattern = re.compile(r"_space-([a-zA-Z0-9]+)_")

        transform_spaces_all = set()

        for filepath in files:
            # Only consider transform files
            if "_xfm." in filepath or "_from-" in filepath or "_to-" in filepath:
                # Extract all space references
                for pattern in [to_pattern, from_pattern, space_pattern]:
                    matches = pattern.findall(filepath)
                    transform_spaces_all.update(matches)

        # Exclude spaces that have data
        transform_only = transform_spaces_all - data_spaces

        if transform_only:
            return ",".join(sorted(transform_only))
        return ""

    except subprocess.CalledProcessError:
        return ""


# ============================================================================
# Description Tracking
# ============================================================================


def extract_descriptions(derivative_path: Path) -> str:
    """Extract description entity counts from derivative outputs.

    Args:
        derivative_path: Path to derivative subdataset

    Returns:
        JSON string of desc counts, or '{}' if none found
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(derivative_path), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return "{}"

        files = result.stdout.strip().split("\n")

        # Extract desc entities: _desc-{label}_
        desc_pattern = re.compile(r"_desc-([a-zA-Z0-9]+)_")
        desc_labels = []

        for filepath in files:
            # Only consider BIDS data files (not hidden, not in derivatives root)
            if filepath.startswith(".") or "/" not in filepath:
                continue

            matches = desc_pattern.findall(filepath)
            desc_labels.extend(matches)

        if not desc_labels:
            return "{}"

        # Count occurrences
        counts = Counter(desc_labels)

        # Convert to sorted dict for consistent output
        result_dict = dict(sorted(counts.items()))

        return json.dumps(result_dict, separators=(",", ":"))

    except subprocess.CalledProcessError:
        return "{}"


# ============================================================================
# Combined Extraction
# ============================================================================


def extract_derivative_metadata(
    derivative_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    """Extract all metadata for a derivative dataset.

    Args:
        derivative_path: Path to derivative subdataset (must be installed)
        raw_path: Path to raw sourcedata subdataset (must be installed)

    Returns:
        Dictionary with all derivative metadata
    """
    result = {}

    # Basic stats
    result.update(extract_derivative_stats(derivative_path))

    # Version tracking
    result.update(extract_version_tracking(derivative_path, raw_path))

    # Extract independent completeness metrics
    tasks_processed = extract_tasks_processed(derivative_path)
    template_spaces = extract_template_spaces(derivative_path)
    descriptions = extract_descriptions(derivative_path)
    anat_processed = extract_anat_processed(derivative_path)
    func_processed = extract_func_processed(derivative_path)

    result["tasks_processed"] = tasks_processed
    result["template_spaces"] = template_spaces
    result["descriptions"] = descriptions
    result["anat_processed"] = anat_processed
    result["func_processed"] = func_processed

    # Extract dependent metrics
    tasks_missing = extract_tasks_missing(derivative_path, raw_path, tasks_processed)
    transform_spaces = extract_transform_spaces(derivative_path, template_spaces)
    processing_complete = extract_processing_complete(
        tasks_missing, anat_processed, func_processed, raw_path
    )

    result["tasks_missing"] = tasks_missing
    result["transform_spaces"] = transform_spaces
    result["processing_complete"] = processing_complete

    return result
