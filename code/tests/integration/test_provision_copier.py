"""Integration tests for copier template provisioning.

Tests the copier template rendering to ensure:
- Templates render correctly with variable substitution
- Generated files match expected output
- File permissions are set correctly
- Template structure is valid

These tests require copier to be installed:
    pip install copier
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def is_copier_available() -> bool:
    """Check if copier is installed and available."""
    # Check if copier is in PATH
    if shutil.which("copier") is not None:
        return True
    # Also check if we can run copier via python -m
    try:
        result = subprocess.run(
            [sys.executable, "-m", "copier", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_copier_cmd() -> list[str]:
    """Get the command to run copier."""
    if shutil.which("copier") is not None:
        return ["copier"]
    return [sys.executable, "-m", "copier"]


# Skip entire module if copier not available
pytestmark = pytest.mark.skipif(
    not is_copier_available(),
    reason="copier not installed (pip install copier)",
)


@pytest.fixture
def template_dir() -> Path:
    """Get path to copier template directory."""
    # Navigate from tests/integration/ to src/openneuro_studies/provision/templates/study/
    current_dir = Path(__file__).parent
    template_path = (
        current_dir.parent.parent
        / "src"
        / "openneuro_studies"
        / "provision"
        / "templates"
        / "study"
    )
    if not template_path.exists():
        pytest.skip(f"Template directory not found: {template_path}")
    return template_path


@pytest.fixture
def study_workspace(tmp_path: Path) -> Path:
    """Create temporary study workspace for provisioning."""
    study_path = tmp_path / "study-ds000001"
    study_path.mkdir()
    return study_path


@pytest.mark.integration
def test_copier_template_exists(template_dir: Path) -> None:
    """Verify copier template structure exists."""
    assert (template_dir / "copier.yaml").exists(), "copier.yaml should exist"
    assert (
        template_dir / "code" / "run-bids-validator.jinja"
    ).exists(), "run-bids-validator template should exist"
    assert (
        template_dir / "README.md.jinja"
    ).exists(), "README.md template should exist"
    assert (
        template_dir / ".openneuro-studies" / "template-version.jinja"
    ).exists(), "template-version template should exist"


@pytest.mark.integration
def test_copier_template_renders(template_dir: Path, study_workspace: Path) -> None:
    """Test that copier renders the template correctly."""
    # Run copier
    result = subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        pytest.fail(f"copier failed with exit code {result.returncode}")

    # Verify files were created
    assert (study_workspace / "code" / "run-bids-validator").exists()
    assert (study_workspace / "README.md").exists()
    assert (study_workspace / ".openneuro-studies" / "template-version").exists()


@pytest.mark.integration
def test_copier_template_variable_substitution(
    template_dir: Path, study_workspace: Path
) -> None:
    """Test that template variables are correctly substituted."""
    # Run copier
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify README.md has correct substitutions
    readme = (study_workspace / "README.md").read_text()
    assert "# study-ds000001" in readme, "study_id should be substituted in title"
    assert "[ds000001]" in readme, "dataset_id should be in link text"
    assert "https://openneuro.org/datasets/ds000001" in readme
    assert "https://github.com/OpenNeuroStudies/study-ds000001" in readme
    assert "https://github.com/OpenNeuroStudies" in readme

    # Verify template version
    version = (study_workspace / ".openneuro-studies" / "template-version").read_text()
    assert version.strip() == "1.0.0"


@pytest.mark.integration
def test_copier_template_different_dataset(
    template_dir: Path, tmp_path: Path
) -> None:
    """Test template with different dataset ID to verify all substitutions work."""
    study_workspace = tmp_path / "study-ds005256"
    study_workspace.mkdir()

    # Run copier with different values
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds005256",
            "--data", "dataset_id=ds005256",
            "--data", "template_version=2.0.0",
            "--data", "github_org=MyOrg",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify substitutions
    readme = (study_workspace / "README.md").read_text()
    assert "# study-ds005256" in readme
    assert "[ds005256]" in readme
    assert "https://openneuro.org/datasets/ds005256" in readme
    assert "https://github.com/MyOrg/study-ds005256" in readme
    assert "https://github.com/MyOrg" in readme

    version = (study_workspace / ".openneuro-studies" / "template-version").read_text()
    assert version.strip() == "2.0.0"


@pytest.mark.integration
def test_copier_template_script_content(
    template_dir: Path, study_workspace: Path
) -> None:
    """Test that run-bids-validator script has correct content."""
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    script_path = study_workspace / "code" / "run-bids-validator"
    script_content = script_path.read_text()

    # Verify shebang
    assert script_content.startswith("#!/bin/bash")

    # Verify set -eu for error handling
    assert "set -eu" in script_content

    # Verify output directory
    assert 'od=derivatives/bids-validator' in script_content

    # Verify validator detection order (uvx > bids-validator > deno > npx)
    assert "uvx bids-validator" in script_content
    assert "command -v bids-validator" in script_content
    assert "deno run" in script_content
    assert "npx -y bids-validator" in script_content

    # Verify output files
    assert '"$od/version.txt"' in script_content
    assert '"$od/report.json"' in script_content
    assert '"$od/report.txt"' in script_content


@pytest.mark.integration
def test_copier_excludes_config(template_dir: Path, study_workspace: Path) -> None:
    """Test that copier.yaml is excluded from output."""
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # copier.yaml should NOT be in output
    assert not (study_workspace / "copier.yaml").exists()


@pytest.mark.integration
def test_copier_template_readme_structure(
    template_dir: Path, study_workspace: Path
) -> None:
    """Test that README.md has expected sections."""
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    readme = (study_workspace / "README.md").read_text()

    # Check for expected sections
    assert "## Dataset Structure" in readme
    assert "## Contents" in readme
    assert "## Running BIDS Validation" in readme
    assert "## Links" in readme
    assert "## License" in readme

    # Check for BIDS references
    assert "BEP035" in readme
    assert "BIDS" in readme

    # Check for datalad run command
    assert "datalad run code/run-bids-validator" in readme


@pytest.mark.integration
def test_copier_creates_directories(template_dir: Path, tmp_path: Path) -> None:
    """Test that copier creates necessary directories."""
    # Create empty study directory
    study_workspace = tmp_path / "study-ds000001"
    study_workspace.mkdir()

    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify directory structure
    assert (study_workspace / "code").is_dir()
    assert (study_workspace / ".openneuro-studies").is_dir()


@pytest.mark.integration
def test_copier_idempotent(template_dir: Path, study_workspace: Path) -> None:
    """Test that running copier twice produces same result."""
    # First run
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Capture content
    readme_first = (study_workspace / "README.md").read_text()
    script_first = (study_workspace / "code" / "run-bids-validator").read_text()
    version_first = (
        study_workspace / ".openneuro-studies" / "template-version"
    ).read_text()

    # Second run
    subprocess.run(
        get_copier_cmd() + [
            "copy",
            "--force",
            "--data", "study_id=study-ds000001",
            "--data", "dataset_id=ds000001",
            "--data", "template_version=1.0.0",
            "--data", "github_org=OpenNeuroStudies",
            str(template_dir),
            str(study_workspace),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Compare
    assert (study_workspace / "README.md").read_text() == readme_first
    assert (study_workspace / "code" / "run-bids-validator").read_text() == script_first
    assert (
        study_workspace / ".openneuro-studies" / "template-version"
    ).read_text() == version_first


@pytest.mark.integration
def test_provisioner_copier_integration(study_workspace: Path) -> None:
    """Test provisioner.py integration with copier templates.

    This tests the actual provision_study function using copier.
    """
    from openneuro_studies.provision.provisioner import (
        TEMPLATE_VERSION,
        provision_study,
    )

    # Force use of copier
    result = provision_study(
        study_workspace,
        force=True,
        use_copier=True,
    )

    assert result.provisioned, f"Provisioning should succeed: {result.error}"
    assert result.error is None

    # Verify files created
    assert (study_workspace / "code" / "run-bids-validator").exists()
    assert (study_workspace / "README.md").exists()
    assert (study_workspace / ".openneuro-studies" / "template-version").exists()

    # Verify template version
    version = (
        study_workspace / ".openneuro-studies" / "template-version"
    ).read_text().strip()
    assert version == TEMPLATE_VERSION

    # Verify README content
    readme = (study_workspace / "README.md").read_text()
    assert "study-ds000001" in readme


@pytest.mark.integration
def test_provisioner_copier_vs_inline_parity(tmp_path: Path) -> None:
    """Test that copier and inline templates produce equivalent output."""
    from openneuro_studies.provision.provisioner import (
        TEMPLATE_VERSION,
        provision_study,
    )

    # Create two study workspaces
    copier_study = tmp_path / "study-copier"
    inline_study = tmp_path / "study-inline"
    copier_study.mkdir()
    inline_study.mkdir()

    # Provision with copier
    copier_result = provision_study(
        copier_study,
        force=True,
        use_copier=True,
    )
    assert copier_result.provisioned

    # Provision with inline (fallback)
    inline_result = provision_study(
        inline_study,
        force=True,
        use_copier=False,
    )
    assert inline_result.provisioned

    # Compare template versions
    copier_version = (
        copier_study / ".openneuro-studies" / "template-version"
    ).read_text().strip()
    inline_version = (
        inline_study / ".openneuro-studies" / "template-version"
    ).read_text().strip()
    assert copier_version == inline_version == TEMPLATE_VERSION

    # Compare script content (should be identical)
    copier_script = (copier_study / "code" / "run-bids-validator").read_text()
    inline_script = (inline_study / "code" / "run-bids-validator").read_text()
    assert copier_script == inline_script, "Validator scripts should match"

    # README will differ in study_id, but structure should match
    copier_readme = (copier_study / "README.md").read_text()
    inline_readme = (inline_study / "README.md").read_text()

    # Check same sections exist
    assert "## Dataset Structure" in copier_readme
    assert "## Dataset Structure" in inline_readme
    assert "## Running BIDS Validation" in copier_readme
    assert "## Running BIDS Validation" in inline_readme
