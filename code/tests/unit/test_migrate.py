"""Tests for the migrate CLI command."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def study_with_old_naming(tmp_path: Path) -> Path:
    """Create a study directory with old naming conventions for testing migration.

    Creates:
    - sourcedata/raw (should become sourcedata/ds000001)
    - derivatives/Custom code-unknown (should become derivatives/custom-ds999999)

    Args:
        tmp_path: pytest temporary directory fixture

    Returns:
        Path to study directory
    """
    study_path = tmp_path / "study-ds000001"
    study_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=study_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=study_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=study_path,
        check=True,
        capture_output=True,
    )

    # Create .gitmodules with old naming
    gitmodules_content = """\
[submodule "ds000001-raw"]
\tpath = sourcedata/raw
\turl = https://github.com/OpenNeuroDatasets/ds000001.git
[submodule "ds999999"]
\tpath = derivatives/Custom code-unknown
\turl = https://github.com/OpenNeuroDatasets/ds999999.git
"""
    (study_path / ".gitmodules").write_text(gitmodules_content)

    # Create directories for submodules
    (study_path / "sourcedata" / "raw").mkdir(parents=True)
    (study_path / "derivatives" / "Custom code-unknown").mkdir(parents=True)

    # Create fake gitlinks (mode 160000) using update-index
    # Use a valid dummy SHA for testing (git rejects all-zeros SHA)
    dummy_sha = "1234567890" * 4
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{dummy_sha},sourcedata/raw",
        ],
        cwd=study_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{dummy_sha},derivatives/Custom code-unknown",
        ],
        cwd=study_path,
        check=True,
        capture_output=True,
    )

    # Stage and commit
    subprocess.run(
        ["git", "add", ".gitmodules"],
        cwd=study_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with old naming"],
        cwd=study_path,
        check=True,
        capture_output=True,
    )

    return study_path


@pytest.mark.unit
@pytest.mark.ai_generated
def test_migrate_sourcedata_raw_to_dataset_id(study_with_old_naming: Path) -> None:
    """Test that sourcedata/raw is renamed to sourcedata/{dataset_id}.

    Args:
        study_with_old_naming: Fixture providing study with old naming
    """
    from openneuro_studies.cli.migrate import _parse_gitmodules, _rename_submodule_path

    study_path = study_with_old_naming
    gitmodules_path = study_path / ".gitmodules"

    # Verify initial state
    submodules = _parse_gitmodules(gitmodules_path)
    assert "ds000001-raw" in submodules
    assert submodules["ds000001-raw"]["path"] == "sourcedata/raw"

    # Perform rename
    result = _rename_submodule_path(
        repo_path=study_path,
        old_path="sourcedata/raw",
        new_path="sourcedata/ds000001",
        submodule_name="ds000001-raw",
        dry_run=False,
    )

    assert result is True

    # Verify .gitmodules was updated
    submodules = _parse_gitmodules(gitmodules_path)
    assert submodules["ds000001-raw"]["path"] == "sourcedata/ds000001"

    # Verify git status shows the rename staged
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=study_path,
        capture_output=True,
        text=True,
    )
    # Should show renamed files staged
    assert "sourcedata/ds000001" in status.stdout or "M  .gitmodules" in status.stdout


@pytest.mark.unit
@pytest.mark.ai_generated
def test_migrate_custom_code_to_custom_dataset_id(study_with_old_naming: Path) -> None:
    """Test that derivatives/Custom code-unknown is renamed to derivatives/custom-{dataset_id}.

    Args:
        study_with_old_naming: Fixture providing study with old naming
    """
    from openneuro_studies.cli.migrate import _parse_gitmodules, _rename_submodule_path

    study_path = study_with_old_naming
    gitmodules_path = study_path / ".gitmodules"

    # Verify initial state
    submodules = _parse_gitmodules(gitmodules_path)
    assert "ds999999" in submodules
    assert submodules["ds999999"]["path"] == "derivatives/Custom code-unknown"

    # Perform rename
    result = _rename_submodule_path(
        repo_path=study_path,
        old_path="derivatives/Custom code-unknown",
        new_path="derivatives/custom-ds999999",
        submodule_name="ds999999",
        dry_run=False,
    )

    assert result is True

    # Verify .gitmodules was updated
    submodules = _parse_gitmodules(gitmodules_path)
    assert submodules["ds999999"]["path"] == "derivatives/custom-ds999999"


@pytest.mark.unit
@pytest.mark.ai_generated
def test_migrate_dry_run_makes_no_changes(study_with_old_naming: Path) -> None:
    """Test that dry_run=True shows what would be done without making changes.

    Args:
        study_with_old_naming: Fixture providing study with old naming
    """
    from openneuro_studies.cli.migrate import _parse_gitmodules, _rename_submodule_path

    study_path = study_with_old_naming
    gitmodules_path = study_path / ".gitmodules"

    # Get initial content
    initial_content = gitmodules_path.read_text()

    # Perform dry run rename
    result = _rename_submodule_path(
        repo_path=study_path,
        old_path="sourcedata/raw",
        new_path="sourcedata/ds000001",
        submodule_name="ds000001-raw",
        dry_run=True,
    )

    assert result is True

    # Verify no changes were made
    assert gitmodules_path.read_text() == initial_content

    # Verify submodule path is still the old one
    submodules = _parse_gitmodules(gitmodules_path)
    assert submodules["ds000001-raw"]["path"] == "sourcedata/raw"


@pytest.mark.unit
@pytest.mark.ai_generated
def test_sanitize_name_preserves_valid_characters() -> None:
    """Test that sanitize_name keeps alphanumerics, -, _, ., and +."""
    from openneuro_studies.organization import sanitize_name

    # These should be unchanged
    assert sanitize_name("xcp_d-0.10.6") == "xcp_d-0.10.6"
    assert sanitize_name("fMRIPrep-24.1.1") == "fMRIPrep-24.1.1"
    assert sanitize_name("qsiprep-1.0.1.dev0+gee9aa2e.d20250115") == "qsiprep-1.0.1.dev0+gee9aa2e.d20250115"
    assert sanitize_name("MRIQC-25.0.0rc0") == "MRIQC-25.0.0rc0"


@pytest.mark.unit
@pytest.mark.ai_generated
def test_sanitize_name_replaces_spaces_and_special_chars() -> None:
    """Test that sanitize_name replaces spaces and special characters with +."""
    from openneuro_studies.organization import sanitize_name

    # These should be sanitized
    assert sanitize_name("Custom code") == "Custom+code"
    assert sanitize_name("Custom code-unknown") == "Custom+code-unknown"
    assert sanitize_name("tool with spaces") == "tool+with+spaces"
    assert sanitize_name("name@with#special$chars") == "name+with+special+chars"
    # Multiple special chars in a row become single +
    assert sanitize_name("a  b") == "a+b"
    assert sanitize_name("a   b") == "a+b"


@pytest.mark.unit
@pytest.mark.ai_generated
def test_get_derivative_dir_name_standard_case() -> None:
    """Test get_derivative_dir_name for standard tool-version cases."""
    from openneuro_studies.organization import get_derivative_dir_name

    assert get_derivative_dir_name("fMRIPrep", "24.1.1", "ds006185") == "fMRIPrep-24.1.1"
    assert get_derivative_dir_name("xcp_d", "0.10.6", "ds006182") == "xcp_d-0.10.6"
    assert (
        get_derivative_dir_name("qsiprep", "1.0.1.dev0+gee9aa2e.d20250115", "ds006182")
        == "qsiprep-1.0.1.dev0+gee9aa2e.d20250115"
    )


@pytest.mark.unit
@pytest.mark.ai_generated
def test_get_derivative_dir_name_custom_code() -> None:
    """Test get_derivative_dir_name for Custom code/unknown cases."""
    from openneuro_studies.organization import get_derivative_dir_name

    assert get_derivative_dir_name("Custom code", "unknown", "ds006191") == "custom-ds006191"
    assert get_derivative_dir_name("unknown", "unknown", "ds006191") == "custom-ds006191"
    assert get_derivative_dir_name("", "1.0", "ds006191") == "custom-ds006191"


@pytest.mark.unit
@pytest.mark.ai_generated
def test_get_derivative_dir_name_sanitizes_spaces() -> None:
    """Test get_derivative_dir_name sanitizes spaces in tool name."""
    from openneuro_studies.organization import get_derivative_dir_name

    assert get_derivative_dir_name("tool with spaces", "1.0", "ds000001") == "tool+with+spaces-1.0"
