"""Study dataset provisioner.

Provisions study datasets with templated content:
- code/run-bids-validator: Script to run BIDS validation via datalad run
- README.md: Study dataset overview
- .openneuro-studies/template-version: Tracks which template version was applied

Future extension: Use copier for more sophisticated template management.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openneuro_studies import __version__

logger = logging.getLogger(__name__)

# Directory and file to track template version in provisioned studies
# Using .openneuro-studies/ directory allows for future extensibility
TEMPLATE_VERSION_DIR = ".openneuro-studies"
TEMPLATE_VERSION_FILE = ".openneuro-studies/template-version"

# Current template version (increment when template changes)
TEMPLATE_VERSION = "1.0.0"


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


def provision_study(
    study_path: Path,
    force: bool = False,
    dry_run: bool = False,
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

    Returns:
        ProvisionResult with details of changes
    """
    study_id = study_path.name
    files_created: list[str] = []
    files_updated: list[str] = []

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
            TEMPLATE_VERSION_FILE,  # .openneuro-studies/template-version
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
        # Create code/ directory
        code_dir = study_path / "code"
        code_dir.mkdir(exist_ok=True)

        # Create run-bids-validator script
        validator_script = code_dir / "run-bids-validator"
        script_existed = validator_script.exists()
        _write_validator_script(validator_script)
        if script_existed:
            files_updated.append("code/run-bids-validator")
        else:
            files_created.append("code/run-bids-validator")

        # Create README.md
        readme_file = study_path / "README.md"
        readme_existed = readme_file.exists()
        _write_readme(readme_file, study_id)
        if readme_existed:
            files_updated.append("README.md")
        else:
            files_created.append("README.md")

        # Create .openneuro-studies/ directory and write template version file
        openneuro_studies_dir = study_path / TEMPLATE_VERSION_DIR
        openneuro_studies_dir.mkdir(exist_ok=True)

        version_file = study_path / TEMPLATE_VERSION_FILE
        version_existed = version_file.exists()
        version_file.write_text(f"{TEMPLATE_VERSION}\n")
        if version_existed:
            files_updated.append(TEMPLATE_VERSION_FILE)
        else:
            files_created.append(TEMPLATE_VERSION_FILE)

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


def _write_validator_script(path: Path) -> None:
    """Write the run-bids-validator script.

    This script is designed to be run via `datalad run code/run-bids-validator`
    for provenance tracking.
    """
    script = '''#!/bin/bash
# Run BIDS validator on this study dataset
# Usage: datalad run code/run-bids-validator
#
# Outputs are stored in derivatives/bids-validator/:
#   version.txt  - Validator version
#   report.json  - Machine-readable results
#   report.txt   - Human-readable summary

set -eu

# Output directory
od=derivatives/bids-validator

# Command to run (prefer uvx for speed)
if command -v uvx >/dev/null 2>&1; then
    cmd="uvx bids-validator"
elif command -v bids-validator >/dev/null 2>&1; then
    cmd="bids-validator"
elif command -v deno >/dev/null 2>&1; then
    cmd="deno run --allow-read --allow-env https://deno.land/x/bids_validator/bids-validator.ts"
elif command -v npx >/dev/null 2>&1; then
    cmd="npx -y bids-validator"
else
    echo "Error: No BIDS validator found. Install with: pip install bids-validator"
    exit 1
fi

# Create output directory
mkdir -p "$od"

# Save validator version
$cmd --version > "$od/version.txt" 2>&1 || echo "unknown" > "$od/version.txt"

# Run validation with JSON output
echo "Running BIDS validation..."
$cmd --json . > "$od/report.json" 2>&1 || true

# Generate text summary
{
    echo "BIDS Validation Summary"
    echo "============================================================"
    echo ""

    if [ -f "$od/report.json" ]; then
        # Extract error and warning counts from JSON
        errors=$(jq -r '.issues.errors | length // 0' "$od/report.json" 2>/dev/null || echo "0")
        warnings=$(jq -r '.issues.warnings | length // 0' "$od/report.json" 2>/dev/null || echo "0")

        echo "Errors: $errors"
        echo "Warnings: $warnings"
        echo ""

        if [ "$errors" = "0" ] && [ "$warnings" = "0" ]; then
            echo "Dataset is BIDS valid!"
        fi
    else
        echo "No JSON output available"
    fi

    echo ""
    echo "Validator version: $(cat "$od/version.txt")"
} > "$od/report.txt"

echo "Validation complete. Results in $od/"
'''
    path.write_text(script)
    path.chmod(0o755)
    logger.debug(f"Created validator script: {path}")


def _write_readme(path: Path, study_id: str) -> None:
    """Write study README.md template."""
    # Extract dataset ID from study ID (study-ds000001 -> ds000001)
    dataset_id = study_id.replace("study-", "") if study_id.startswith("study-") else study_id

    readme = f"""# {study_id}

BIDS study dataset aggregating OpenNeuro dataset [{dataset_id}](https://openneuro.org/datasets/{dataset_id}) and its derivatives.

## Dataset Structure

This is a BIDS [DatasetType: "study"](https://bids.neuroimaging.io/extensions/beps/bep_035.html) that organizes:

- **Raw data**: Original BIDS dataset from OpenNeuro
- **Derivatives**: Processed outputs (fmriprep, mriqc, etc.) linked as submodules

## Contents

- `rawdata/` - Link to raw BIDS dataset (git submodule)
- `derivatives/` - Processed data derivatives:
  - `bids-validator/` - BIDS validation results
  - Other derivatives linked as submodules
- `code/` - Analysis scripts including `run-bids-validator`
- `dataset_description.json` - BIDS dataset description

## Running BIDS Validation

To run BIDS validation with provenance tracking:

```bash
datalad run code/run-bids-validator
```

Results are stored in `derivatives/bids-validator/`:
- `version.txt` - Validator version
- `report.json` - Machine-readable results
- `report.txt` - Human-readable summary

## Links

- **OpenNeuro**: https://openneuro.org/datasets/{dataset_id}
- **BIDS BEP035**: https://bids.neuroimaging.io/extensions/beps/bep_035.html
- **OpenNeuroStudies**: https://github.com/OpenNeuroStudies

## License

Dataset licenses vary. Check individual source datasets for license information.
"""
    path.write_text(readme)
    logger.debug(f"Created README: {path}")
