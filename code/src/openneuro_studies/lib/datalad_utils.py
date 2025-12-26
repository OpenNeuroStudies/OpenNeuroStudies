"""DataLad utility functions for provenance-tracked operations.

Provides unified commit behavior using datalad run/save for operations
that modify the repository state.
"""

import logging
from pathlib import Path
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def datalad_save(
    message: str,
    paths: Optional[list[Path]] = None,
    dataset: str = ".",
    recursive: bool = False,
) -> bool:
    """Save changes using datalad save.

    Args:
        message: Commit message
        paths: Specific paths to save (None = all changes)
        dataset: Dataset path or "^" for superdataset
        recursive: Save recursively into subdatasets

    Returns:
        True if save was successful, False otherwise
    """
    try:
        import datalad.api as dl

        path_args = [str(p) for p in paths] if paths else None
        dl.save(
            path=path_args,
            dataset=dataset,
            message=message,
            recursive=recursive,
        )
        return True
    except Exception as e:
        logger.error(f"datalad save failed: {e}")
        return False


def datalad_run(
    cmd: list[str],
    message: str,
    inputs: Optional[list[str]] = None,
    outputs: Optional[list[str]] = None,
    dataset: str = ".",
    dry_run: bool = False,
) -> tuple[bool, Optional[str]]:
    """Execute a command with datalad run for provenance tracking.

    Args:
        cmd: Command to execute as list of strings
        message: Commit message describing what the command does
        inputs: Input files the command reads (for locking)
        outputs: Output files the command produces (for unlocking/tracking)
        dataset: Dataset path
        dry_run: If True, show what would be run without executing

    Returns:
        Tuple of (success, error_message)
    """
    try:
        import datalad.api as dl

        if dry_run:
            logger.info(f"[DRY RUN] Would run: {' '.join(cmd)}")
            logger.info(f"  Message: {message}")
            if inputs:
                logger.info(f"  Inputs: {inputs}")
            if outputs:
                logger.info(f"  Outputs: {outputs}")
            return True, None

        dl.run(
            cmd=cmd,
            message=message,
            inputs=inputs,
            outputs=outputs,
            dataset=dataset,
        )
        return True, None

    except Exception as e:
        logger.error(f"datalad run failed: {e}")
        return False, str(e)


def run_with_provenance(
    operation: Callable[[], T],
    message: str,
    outputs: Optional[list[Path]] = None,
    dataset: str = ".",
    commit: bool = True,
) -> tuple[T, bool]:
    """Run an operation and optionally commit results with datalad save.

    This is useful for Python operations that can't be wrapped with datalad run
    (e.g., in-process metadata generation).

    Args:
        operation: Callable that performs the work
        message: Commit message if committing
        outputs: Paths that will be modified
        dataset: Dataset path
        commit: Whether to commit after operation

    Returns:
        Tuple of (operation result, commit success)
    """
    # Run the operation
    result = operation()

    # Commit if requested
    commit_success = True
    if commit and outputs:
        commit_success = datalad_save(
            message=message,
            paths=outputs,
            dataset=dataset,
        )

    return result, commit_success


def generate_stats_message(
    base_message: str,
    stats: dict[str, int | str],
) -> str:
    """Generate a commit message with statistics.

    Args:
        base_message: Base commit message (first line)
        stats: Dictionary of stat name -> value

    Returns:
        Formatted commit message with stats

    Example:
        >>> generate_stats_message("Generate metadata", {"studies": 7, "files": 4})
        'Generate metadata\\n\\nStatistics:\\n  studies: 7\\n  files: 4'
    """
    lines = [base_message, "", "Statistics:"]
    for key, value in stats.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def save_with_stats(
    message: str,
    stats: dict[str, int | str],
    paths: Optional[list[Path]] = None,
    dataset: str = ".",
) -> bool:
    """Save changes with a statistics-enhanced commit message.

    Args:
        message: Base commit message
        stats: Statistics to include in message
        paths: Paths to save
        dataset: Dataset path

    Returns:
        True if save succeeded
    """
    full_message = generate_stats_message(message, stats)
    return datalad_save(
        message=full_message,
        paths=paths,
        dataset=dataset,
    )
