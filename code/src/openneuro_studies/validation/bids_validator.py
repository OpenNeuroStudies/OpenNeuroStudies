"""BIDS validator integration.

Implements FR-015: Run bids-validator-deno on study datasets and store
JSON and text outputs under derivatives/bids-validator/.

Output structure:
    derivatives/bids-validator/
        version.txt   - Validator version (from --version)
        report.json   - Machine-readable validation results
        report.txt    - Human-readable summary
"""

import csv
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Output directory name under derivatives/
VALIDATOR_OUTPUT_DIR = "bids-validator"


class ValidationStatus(Enum):
    """BIDS validation status values for studies.tsv."""

    VALID = "valid"
    WARNINGS = "warnings"
    ERRORS = "errors"
    NOT_AVAILABLE = "n/a"


@dataclass
class ValidationResult:
    """Result of BIDS validation."""

    status: ValidationStatus
    error_count: int
    warning_count: int
    json_output: Optional[dict] = None
    text_output: Optional[str] = None
    validator_version: Optional[str] = None


def find_validator() -> Optional[tuple[list[str], str]]:
    """Find the BIDS validator executable.

    Tries in order:
    1. uvx bids-validator-deno (preferred, fast via uv)
    2. bids-validator-deno (pip-installed deno version)
    3. deno run with @bids/validator from jsr
    4. npx bids-validator (node version, slower)

    Returns:
        Tuple of (command_args, validator_type) or None if not found
    """
    # Try uvx (fastest, recommended)
    uvx = shutil.which("uvx")
    if uvx:
        return ([uvx, "bids-validator-deno"], "uvx")

    # Try pip-installed bids-validator-deno
    bids_validator = shutil.which("bids-validator-deno")
    if bids_validator:
        return ([bids_validator], "bids-validator-deno")

    # Try deno direct execution
    deno = shutil.which("deno")
    if deno:
        return (
            [
                deno,
                "run",
                "--allow-read",
                "--allow-env",
                "jsr:@bids/validator",
            ],
            "deno",
        )

    # Try npx (slower, but widely available)
    npx = shutil.which("npx")
    if npx:
        return ([npx, "-y", "bids-validator"], "npx")

    return None


def get_validator_version(validator_cmd: list[str], timeout: int = 30) -> Optional[str]:
    """Get the version of the BIDS validator.

    Args:
        validator_cmd: Validator command arguments
        timeout: Timeout in seconds

    Returns:
        Version string or None if failed
    """
    try:
        result = subprocess.run(
            validator_cmd + ["--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()
        return None
    except Exception as e:
        logger.warning(f"Failed to get validator version: {e}")
        return None


def needs_validation(study_path: Path) -> bool:
    """Check if a study needs (re)validation.

    Returns True if:
    - No validation output exists
    - Study has commits newer than the last validation

    Args:
        study_path: Path to study directory

    Returns:
        True if validation should be run
    """
    validator_dir = study_path / "derivatives" / VALIDATOR_OUTPUT_DIR
    version_file = validator_dir / "version.txt"

    # No validation output exists
    if not version_file.exists():
        return True

    try:
        # Get the commit when validation was last run
        # (the commit that added/modified the validation output)
        result = subprocess.run(
            [
                "git",
                "-C",
                str(study_path),
                "log",
                "-1",
                "--format=%H",
                "--",
                f"derivatives/{VALIDATOR_OUTPUT_DIR}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        last_validation_commit = result.stdout.strip()

        if not last_validation_commit:
            # Validation output not tracked in git yet
            return True

        # Check if there are any commits since the validation commit
        # (excluding the validation directory itself)
        result = subprocess.run(
            [
                "git",
                "-C",
                str(study_path),
                "log",
                "--oneline",
                f"{last_validation_commit}..HEAD",
                "--",
                ".",
                f":!derivatives/{VALIDATOR_OUTPUT_DIR}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # If there are commits after validation (excluding validation dir), need to revalidate
        return bool(result.stdout.strip())

    except subprocess.CalledProcessError as e:
        logger.debug(f"Git command failed for {study_path}: {e}")
        # If git fails, assume validation is needed
        return True


def run_validation(
    study_path: Path,
    validator_cmd: Optional[list[str]] = None,
    timeout: int = 600,
) -> ValidationResult:
    """Run BIDS validation on a study dataset.

    Outputs are stored in derivatives/bids-validator/:
        version.txt   - Validator version
        report.json   - Machine-readable results
        report.txt    - Human-readable summary

    Args:
        study_path: Path to study directory
        validator_cmd: Optional validator command (auto-detected if None)
        timeout: Timeout in seconds (default 10 minutes)

    Returns:
        ValidationResult with status and outputs
    """
    # Find validator if not provided
    if validator_cmd is None:
        found = find_validator()
        if found is None:
            logger.warning("No BIDS validator found")
            return ValidationResult(
                status=ValidationStatus.NOT_AVAILABLE,
                error_count=0,
                warning_count=0,
                text_output="No BIDS validator found. Install with: pip install bids-validator",
            )
        validator_cmd, validator_type = found
        logger.info(f"Using {validator_type} for validation")
    else:
        validator_type = "custom"

    # Create output directory: derivatives/bids-validator/
    output_dir = study_path / "derivatives" / VALIDATOR_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    version_path = output_dir / "version.txt"
    json_output_path = output_dir / "report.json"
    text_output_path = output_dir / "report.txt"

    # Get and save validator version
    validator_version = get_validator_version(validator_cmd)
    if validator_version:
        with open(version_path, "w") as f:
            f.write(validator_version + "\n")
        logger.info(f"Validator version: {validator_version}")

    try:
        # Run 1: Get JSON output for machine-readable results
        json_cmd = validator_cmd + [str(study_path), "--json"]
        logger.info(f"Running (JSON): {' '.join(json_cmd)}")

        json_result = subprocess.run(
            json_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=study_path.parent,
        )

        # Parse JSON output from stdout
        json_data = None
        if json_result.stdout and json_result.stdout.strip():
            try:
                json_data = json.loads(json_result.stdout)
                # Write to file for persistence
                with open(json_output_path, "w") as f:
                    json.dump(json_data, f, indent=2)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse JSON from stdout: {json_result.stdout[:200]}")

        # Run 2: Get native text output for human-readable report
        text_cmd = validator_cmd + [str(study_path)]
        logger.info(f"Running (text): {' '.join(text_cmd)}")

        text_result = subprocess.run(
            text_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=study_path.parent,
        )

        # Write native validator text output directly
        text_output = text_result.stdout or text_result.stderr or ""
        with open(text_output_path, "w") as f:
            f.write(text_output)

        # Determine status from JSON data
        status, error_count, warning_count = _parse_validation_result(json_data, json_result)

        return ValidationResult(
            status=status,
            error_count=error_count,
            warning_count=warning_count,
            json_output=json_data,
            text_output=text_output,
            validator_version=validator_version,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Validation timed out after {timeout}s for {study_path.name}")
        text_output = (
            f"Validation timed out after {timeout} seconds.\n"
            "This may happen if:\n"
            "  - The dataset is very large\n"
            "  - Sourcedata submodules are not populated (git-annex content not fetched)\n"
            "  - The validator is trying to read annexed files\n"
            "\nConsider running with --timeout to increase the limit,\n"
            "or ensure sourcedata content is available."
        )
        with open(text_output_path, "w") as f:
            f.write(text_output)
        return ValidationResult(
            status=ValidationStatus.NOT_AVAILABLE,
            error_count=0,
            warning_count=0,
            text_output=text_output,
            validator_version=validator_version,
        )

    except Exception as e:
        logger.error(f"Validation failed for {study_path.name}: {e}")
        text_output = f"Validation failed: {e}"
        with open(text_output_path, "w") as f:
            f.write(text_output)
        return ValidationResult(
            status=ValidationStatus.NOT_AVAILABLE,
            error_count=0,
            warning_count=0,
            text_output=text_output,
            validator_version=validator_version,
        )


def _parse_validation_result(
    json_data: Optional[dict],
    result: subprocess.CompletedProcess,
) -> tuple[ValidationStatus, int, int]:
    """Parse validation result to determine status.

    Returns:
        Tuple of (status, error_count, warning_count)
    """
    if json_data is None:
        # No JSON output - check exit code
        if result.returncode == 0:
            return ValidationStatus.VALID, 0, 0
        else:
            return ValidationStatus.NOT_AVAILABLE, 0, 0

    issues = json_data.get("issues", {})
    errors = issues.get("errors", [])
    warnings = issues.get("warnings", [])

    error_count = len(errors)
    warning_count = len(warnings)

    if error_count > 0:
        return ValidationStatus.ERRORS, error_count, warning_count
    elif warning_count > 0:
        return ValidationStatus.WARNINGS, error_count, warning_count
    else:
        return ValidationStatus.VALID, error_count, warning_count


def update_studies_tsv_validation(
    studies_tsv_path: Path,
    study_id: str,
    status: ValidationStatus,
) -> None:
    """Update the bids_valid column in studies.tsv for a study.

    Args:
        studies_tsv_path: Path to studies.tsv
        study_id: Study ID to update
        status: Validation status to set
    """
    if not studies_tsv_path.exists():
        logger.warning(f"studies.tsv not found at {studies_tsv_path}")
        return

    # Read existing TSV
    rows = []
    fieldnames = None
    with open(studies_tsv_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = reader.fieldnames
        rows = list(reader)

    if fieldnames is None or "bids_valid" not in fieldnames:
        logger.warning("bids_valid column not found in studies.tsv")
        return

    # Update the matching row
    updated = False
    for row in rows:
        if row.get("study_id") == study_id:
            row["bids_valid"] = status.value
            updated = True
            break

    if not updated:
        logger.warning(f"Study {study_id} not found in studies.tsv")
        return

    # Write back
    with open(studies_tsv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Updated bids_valid={status.value} for {study_id} in studies.tsv")
