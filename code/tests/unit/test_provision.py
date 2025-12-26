"""Unit tests for study dataset provisioning (FR-041)."""

import pytest
from pathlib import Path

from openneuro_studies.provision import (
    TEMPLATE_VERSION_DIR,
    TEMPLATE_VERSION_FILE,
    ProvisionResult,
    needs_provisioning,
    provision_study,
)
from openneuro_studies.provision.provisioner import (
    TEMPLATE_VERSION,
    get_template_version,
)


class TestTemplateVersionTracking:
    """Tests for template version tracking (FR-041a)."""

    def test_template_version_file_path(self):
        """Template version should be stored in .openneuro-studies/ directory."""
        assert TEMPLATE_VERSION_DIR == ".openneuro-studies"
        assert TEMPLATE_VERSION_FILE == ".openneuro-studies/template-version"
        assert TEMPLATE_VERSION_FILE.startswith(TEMPLATE_VERSION_DIR)

    def test_get_template_version_missing(self, tmp_path: Path):
        """Should return None if no template version file exists."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        assert get_template_version(study_path) is None

    def test_get_template_version_exists(self, tmp_path: Path):
        """Should return version string from template version file."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        version_dir = study_path / TEMPLATE_VERSION_DIR
        version_dir.mkdir()
        version_file = study_path / TEMPLATE_VERSION_FILE
        version_file.write_text("1.0.0\n")

        assert get_template_version(study_path) == "1.0.0"

    def test_needs_provisioning_no_version_file(self, tmp_path: Path):
        """Should need provisioning if no version file exists."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        assert needs_provisioning(study_path) is True

    def test_needs_provisioning_outdated_version(self, tmp_path: Path):
        """Should need provisioning if version is outdated."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        version_dir = study_path / TEMPLATE_VERSION_DIR
        version_dir.mkdir()
        version_file = study_path / TEMPLATE_VERSION_FILE
        version_file.write_text("0.9.0\n")  # Older than current

        assert needs_provisioning(study_path) is True

    def test_needs_provisioning_current_version(self, tmp_path: Path):
        """Should not need provisioning if version is current."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        version_dir = study_path / TEMPLATE_VERSION_DIR
        version_dir.mkdir()
        version_file = study_path / TEMPLATE_VERSION_FILE
        version_file.write_text(f"{TEMPLATE_VERSION}\n")

        assert needs_provisioning(study_path) is False

    def test_needs_provisioning_force(self, tmp_path: Path):
        """Should need provisioning if force=True regardless of version."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        version_dir = study_path / TEMPLATE_VERSION_DIR
        version_dir.mkdir()
        version_file = study_path / TEMPLATE_VERSION_FILE
        version_file.write_text(f"{TEMPLATE_VERSION}\n")

        assert needs_provisioning(study_path, force=True) is True


class TestProvisionStudy:
    """Tests for provision_study function."""

    def test_provision_creates_files(self, tmp_path: Path):
        """Provisioning should create all required files."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        result = provision_study(study_path)

        assert result.provisioned is True
        assert result.error is None
        assert "code/run-bids-validator" in result.files_created
        assert "README.md" in result.files_created
        assert TEMPLATE_VERSION_FILE in result.files_created

    def test_provision_creates_validator_script(self, tmp_path: Path):
        """Provisioning should create executable validator script."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        script_path = study_path / "code" / "run-bids-validator"
        assert script_path.exists()
        assert script_path.is_file()

        # Check script is executable
        import stat

        mode = script_path.stat().st_mode
        assert mode & stat.S_IXUSR  # User execute permission

        # Check script content has shebang and key elements
        content = script_path.read_text()
        assert content.startswith("#!/bin/bash")
        assert "bids-validator" in content
        assert "derivatives/bids-validator" in content
        assert "version.txt" in content
        assert "report.json" in content
        assert "report.txt" in content

    def test_provision_creates_readme(self, tmp_path: Path):
        """Provisioning should create README with study info."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        readme_path = study_path / "README.md"
        assert readme_path.exists()

        content = readme_path.read_text()
        assert "study-ds000001" in content
        assert "ds000001" in content  # Dataset ID extracted from study ID
        assert "openneuro.org" in content
        assert "BIDS" in content
        assert "datalad run" in content

    def test_provision_creates_version_file(self, tmp_path: Path):
        """Provisioning should create version file in .openneuro-studies/."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        version_dir = study_path / TEMPLATE_VERSION_DIR
        assert version_dir.exists()
        assert version_dir.is_dir()

        version_file = study_path / TEMPLATE_VERSION_FILE
        assert version_file.exists()
        assert version_file.read_text().strip() == TEMPLATE_VERSION

    def test_provision_nonexistent_study(self, tmp_path: Path):
        """Provisioning nonexistent study should return error."""
        study_path = tmp_path / "study-ds000001"
        # Don't create the directory

        result = provision_study(study_path)

        assert result.provisioned is False
        assert result.error is not None
        assert "does not exist" in result.error

    def test_provision_already_current(self, tmp_path: Path):
        """Provisioning up-to-date study should skip."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # First provision
        provision_study(study_path)

        # Second provision should skip
        result = provision_study(study_path)

        assert result.provisioned is False
        assert "Already up-to-date" in result.error

    def test_provision_force_reprovision(self, tmp_path: Path):
        """Force provisioning should update even if current."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        # First provision
        provision_study(study_path)

        # Modify README to test re-provisioning
        readme_path = study_path / "README.md"
        readme_path.write_text("Modified content")

        # Force re-provision
        result = provision_study(study_path, force=True)

        assert result.provisioned is True
        assert "README.md" in result.files_updated

        # Verify README was restored
        content = readme_path.read_text()
        assert "study-ds000001" in content

    def test_provision_dry_run(self, tmp_path: Path):
        """Dry run should not create files."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        result = provision_study(study_path, dry_run=True)

        assert result.provisioned is True
        assert "code/run-bids-validator" in result.files_created

        # Files should NOT actually exist
        assert not (study_path / "code" / "run-bids-validator").exists()
        assert not (study_path / "README.md").exists()
        assert not (study_path / TEMPLATE_VERSION_FILE).exists()


class TestValidatorScriptContent:
    """Tests for the generated validator script content."""

    def test_script_uses_uvx_first(self, tmp_path: Path):
        """Validator script should prefer uvx over other methods."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        script_path = study_path / "code" / "run-bids-validator"
        content = script_path.read_text()

        # uvx should be checked first
        uvx_pos = content.find("uvx")
        npx_pos = content.find("npx")

        assert uvx_pos < npx_pos, "uvx should be checked before npx"

    def test_script_outputs_to_correct_directory(self, tmp_path: Path):
        """Script should output to derivatives/bids-validator/."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        script_path = study_path / "code" / "run-bids-validator"
        content = script_path.read_text()

        assert "od=derivatives/bids-validator" in content
        assert "version.txt" in content
        assert "report.json" in content
        assert "report.txt" in content

    def test_script_has_error_handling(self, tmp_path: Path):
        """Script should have proper error handling."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        script_path = study_path / "code" / "run-bids-validator"
        content = script_path.read_text()

        assert "set -eu" in content or "set -e" in content


class TestReadmeContent:
    """Tests for the generated README content."""

    def test_readme_has_openneuro_link(self, tmp_path: Path):
        """README should link to OpenNeuro dataset page."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        readme_path = study_path / "README.md"
        content = readme_path.read_text()

        assert "https://openneuro.org/datasets/ds000001" in content

    def test_readme_has_bids_study_link(self, tmp_path: Path):
        """README should link to BIDS BEP035 spec."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        readme_path = study_path / "README.md"
        content = readme_path.read_text()

        assert "bep_035" in content or "BEP035" in content

    def test_readme_explains_datalad_run(self, tmp_path: Path):
        """README should explain how to run validation with datalad."""
        study_path = tmp_path / "study-ds000001"
        study_path.mkdir()

        provision_study(study_path)

        readme_path = study_path / "README.md"
        content = readme_path.read_text()

        assert "datalad run" in content
        assert "code/run-bids-validator" in content
