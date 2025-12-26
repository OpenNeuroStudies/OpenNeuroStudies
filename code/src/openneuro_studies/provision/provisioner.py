"""Study dataset provisioner.

Provisions study datasets with templated content:
- code/run-bids-validator: Script to run BIDS validation via datalad run
- README.md: Study dataset overview
- .openneuro-studies/template-version: Tracks which template version was applied

Uses copier templates from templates/study/ directory.
"""

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directory and file to track template version in provisioned studies
# Using .openneuro-studies/ directory allows for future extensibility
TEMPLATE_VERSION_DIR = ".openneuro-studies"
TEMPLATE_VERSION_FILE = ".openneuro-studies/template-version"

# Current template version (increment when template changes)
TEMPLATE_VERSION = "1.2.0"

# Path to copier template (relative to this module)
TEMPLATE_DIR = Path(__file__).parent / "templates" / "study"


@dataclass
class ProvisionResult:
    """Result of provisioning a study."""

    study_id: str
    provisioned: bool
    files_created: list[str]
    files_updated: list[str]
    template_version: str
    error: Optional[str] = None


def get_template_version(study_path: Path) -> Optional[str]:
    """Get the template version applied to a study.

    Args:
        study_path: Path to study directory

    Returns:
        Version string or None if not provisioned
    """
    version_file = study_path / TEMPLATE_VERSION_FILE
    if version_file.exists():
        return version_file.read_text().strip()
    return None


def needs_provisioning(study_path: Path, force: bool = False) -> bool:
    """Check if a study needs provisioning.

    Returns True if:
    - No template version file exists
    - Template version is older than current
    - force=True

    Args:
        study_path: Path to study directory
        force: Force re-provisioning

    Returns:
        True if provisioning should be run
    """
    if force:
        return True

    current_version = get_template_version(study_path)
    if current_version is None:
        return True

    # Simple version comparison (could be more sophisticated)
    return current_version != TEMPLATE_VERSION


def _get_copier_cmd() -> list[str]:
    """Get command to run copier.

    Prefers copier from PATH, falls back to python -m copier.
    """
    if shutil.which("copier") is not None:
        return ["copier"]
    return [sys.executable, "-m", "copier"]


def _run_copier(
    study_path: Path,
    study_id: str,
    dataset_id: str,
    github_org: str = "OpenNeuroStudies",
) -> tuple[list[str], list[str]]:
    """Run copier to provision study from template.

    Args:
        study_path: Path to study directory
        study_id: Study identifier
        dataset_id: Dataset identifier
        github_org: GitHub organization

    Returns:
        Tuple of (files_created, files_updated)

    Raises:
        RuntimeError: If copier fails
    """
    files_created: list[str] = []
    files_updated: list[str] = []

    # Track existing files before copier runs
    files_to_check = [
        "code/run-bids-validator",
        "README.md",
        TEMPLATE_VERSION_FILE,
    ]
    existing_files = {f for f in files_to_check if (study_path / f).exists()}

    # Run copier with answers
    cmd = _get_copier_cmd() + [
        "copy",
        "--force",  # Overwrite existing files
        "--data",
        f"study_id={study_id}",
        "--data",
        f"dataset_id={dataset_id}",
        "--data",
        f"template_version={TEMPLATE_VERSION}",
        "--data",
        f"github_org={github_org}",
        str(TEMPLATE_DIR),
        str(study_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"copier failed: {result.stderr}")

    # Determine which files were created vs updated
    for f in files_to_check:
        if (study_path / f).exists():
            if f in existing_files:
                files_updated.append(f)
            else:
                files_created.append(f)

    # Make script executable
    script_path = study_path / "code" / "run-bids-validator"
    if script_path.exists():
        script_path.chmod(0o755)

    return files_created, files_updated


def provision_study(
    study_path: Path,
    force: bool = False,
    dry_run: bool = False,
    github_org: str = "OpenNeuroStudies",
) -> ProvisionResult:
    """Provision a study dataset with templated content.

    Creates:
    - code/run-bids-validator: Validation script for datalad run
    - README.md: Study dataset overview
    - .openneuro-studies/template-version: Template version tracking

    Args:
        study_path: Path to study directory
        force: Force re-provisioning even if already up-to-date
        dry_run: Only check what would be done
        github_org: GitHub organization for links

    Returns:
        ProvisionResult with details of changes
    """
    study_id = study_path.name
    files_created: list[str] = []
    files_updated: list[str] = []

    # Extract dataset ID from study ID (study-ds000001 -> ds000001)
    dataset_id = study_id.replace("study-", "") if study_id.startswith("study-") else study_id

    if not study_path.exists():
        return ProvisionResult(
            study_id=study_id,
            provisioned=False,
            files_created=[],
            files_updated=[],
            template_version=TEMPLATE_VERSION,
            error=f"Study path does not exist: {study_path}",
        )

    if not needs_provisioning(study_path, force=force):
        return ProvisionResult(
            study_id=study_id,
            provisioned=False,
            files_created=[],
            files_updated=[],
            template_version=TEMPLATE_VERSION,
            error="Already up-to-date (use --force to re-provision)",
        )

    if dry_run:
        # Check what would be created
        files_to_check = [
            "code/run-bids-validator",
            "README.md",
            TEMPLATE_VERSION_FILE,
        ]
        for file in files_to_check:
            file_path = study_path / file
            if file_path.exists():
                files_updated.append(file)
            else:
                files_created.append(file)

        return ProvisionResult(
            study_id=study_id,
            provisioned=True,
            files_created=files_created,
            files_updated=files_updated,
            template_version=TEMPLATE_VERSION,
        )

    try:
        logger.info(f"Provisioning {study_id} with copier template")
        files_created, files_updated = _run_copier(study_path, study_id, dataset_id, github_org)

        return ProvisionResult(
            study_id=study_id,
            provisioned=True,
            files_created=files_created,
            files_updated=files_updated,
            template_version=TEMPLATE_VERSION,
        )

    except Exception as e:
        logger.error(f"Failed to provision {study_id}: {e}")
        return ProvisionResult(
            study_id=study_id,
            provisioned=False,
            files_created=files_created,
            files_updated=files_updated,
            template_version=TEMPLATE_VERSION,
            error=str(e),
        )
