"""BIDS validator integration.

Implements FR-015: Run bids-validator-deno on study datasets and store
JSON and text outputs under derivatives/.
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
    1. bids-validator (pip-installed deno version)
    2. deno run with bids_validator from deno.land
    3. npx bids-validator (node version, slower)

    Returns:
        Tuple of (command_args, validator_type) or None if not found
    """
    # Try pip-installed bids-validator (deno compiled)
    bids_validator = shutil.which("bids-validator")
    if bids_validator:
        return ([bids_validator], "bids-validator")

    # Try deno direct execution
    deno = shutil.which("deno")
    if deno:
        return (
            [
                deno,
                "run",
                "--allow-read",
                "--allow-env",
                "https://deno.land/x/bids_validator/bids-validator.ts",
            ],
            "deno",
        )

    # Try npx (slower, but widely available)
    npx = shutil.which("npx")
    if npx:
        return ([npx, "-y", "bids-validator"], "npx")

    return None


def run_validation(
    study_path: Path,
    validator_cmd: Optional[list[str]] = None,
    timeout: int = 600,
) -> ValidationResult:
    """Run BIDS validation on a study dataset.

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

    # Create derivatives directory if needed
    derivatives_dir = study_path / "derivatives"
    derivatives_dir.mkdir(exist_ok=True)

    json_output_path = derivatives_dir / "bids-validator.json"
    text_output_path = derivatives_dir / "bids-validator.txt"

    # Build command - run validation with JSON output
    # Note: bids-validator v2.x uses --json for JSON to stdout
    # Output file option may vary between versions
    cmd = validator_cmd + [
        str(study_path),
        "--json",
    ]

    logger.info(f"Running: {' '.join(cmd)}")

    try:
        # Run validator
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=study_path.parent,
        )

        # Parse JSON output from stdout
        json_data = None
        if result.stdout and result.stdout.strip():
            try:
                json_data = json.loads(result.stdout)
                # Write to file for persistence
                with open(json_output_path, "w") as f:
                    json.dump(json_data, f, indent=2)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse JSON from stdout: {result.stdout[:200]}")

        # Generate text summary
        text_output = _generate_text_summary(result, json_data)

        # Write text output
        with open(text_output_path, "w") as f:
            f.write(text_output)

        # Determine status from JSON data
        status, error_count, warning_count = _parse_validation_result(json_data, result)

        return ValidationResult(
            status=status,
            error_count=error_count,
            warning_count=warning_count,
            json_output=json_data,
            text_output=text_output,
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
        )


def _generate_text_summary(
    result: subprocess.CompletedProcess,
    json_data: Optional[dict],
) -> str:
    """Generate human-readable text summary of validation."""
    lines = []

    lines.append("BIDS Validation Summary")
    lines.append("=" * 60)
    lines.append("")

    # Always include stdout/stderr if validation didn't produce JSON
    if not json_data and (result.stdout or result.stderr):
        if result.stderr:
            lines.append("STDERR:")
            lines.append(result.stderr[:5000])
            lines.append("")
        if result.stdout:
            lines.append("STDOUT:")
            lines.append(result.stdout[:5000])
            lines.append("")

    if json_data:
        # Parse issues from JSON
        issues = json_data.get("issues", {})

        errors = issues.get("errors", [])
        warnings = issues.get("warnings", [])

        lines.append(f"Errors: {len(errors)}")
        lines.append(f"Warnings: {len(warnings)}")
        lines.append("")

        if errors:
            lines.append("ERRORS:")
            lines.append("-" * 40)
            for error in errors[:20]:  # Limit to first 20
                code = error.get("code", "UNKNOWN")
                msg = error.get("reason", error.get("message", "No message"))
                location = error.get("location", "")
                lines.append(f"  [{code}] {msg}")
                if location:
                    lines.append(f"    at: {location}")
            if len(errors) > 20:
                lines.append(f"  ... and {len(errors) - 20} more errors")
            lines.append("")

        if warnings:
            lines.append("WARNINGS:")
            lines.append("-" * 40)
            for warning in warnings[:20]:  # Limit to first 20
                code = warning.get("code", "UNKNOWN")
                msg = warning.get("reason", warning.get("message", "No message"))
                location = warning.get("location", "")
                lines.append(f"  [{code}] {msg}")
                if location:
                    lines.append(f"    at: {location}")
            if len(warnings) > 20:
                lines.append(f"  ... and {len(warnings) - 20} more warnings")
            lines.append("")

        if not errors and not warnings:
            lines.append("Dataset is BIDS valid!")

    else:
        # No JSON data, use stdout/stderr
        if result.stdout:
            lines.append("STDOUT:")
            lines.append(result.stdout[:5000])  # Limit output
        if result.stderr:
            lines.append("STDERR:")
            lines.append(result.stderr[:5000])

    lines.append("")
    lines.append(f"Exit code: {result.returncode}")

    return "\n".join(lines)


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
