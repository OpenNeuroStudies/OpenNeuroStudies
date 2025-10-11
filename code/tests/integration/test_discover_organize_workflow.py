"""Integration test for full discover → organize workflow.

This test runs the complete workflow from init through discovery and organization,
using real datasets from OpenNeuro (both raw and derivatives).

Test datasets (from CLAUDE.md):
- ds000001: Single raw dataset (basic case)
- ds000010: Standard raw dataset
- ds005256: Medium-sized dataset
- ds006131: Raw dataset with derivatives
- ds006185: Raw dataset with derivatives
- ds006189: Raw dataset with derivatives
- ds006190: Multi-source derivative (sources: ds006189, ds006185, ds006131)

Each raw dataset will include any matching derivatives from OpenNeuroDerivatives
(e.g., ds000001-fmriprep, ds000001-mriqc).
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Test datasets to discover (from CLAUDE.md)
TEST_RAW_DATASETS = [
    "ds000001",
    "ds000010",
    "ds005256",
    "ds006131",
    "ds006185",
    "ds006189",
    "ds006190",
]

# Note: ds006190 is a special case - it's a multi-source derivative
# in OpenNeuroDerivatives, but we list it here for discovery


@pytest.fixture
def test_workspace(tmp_path: Path) -> Path:
    """Create temporary workspace for integration test.

    Args:
        tmp_path: pytest temporary directory fixture

    Returns:
        Path to test workspace
    """
    workspace = tmp_path / "openneuro-test"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.mark.integration
@pytest.mark.ai_generated
def test_full_workflow(test_workspace: Path) -> None:
    """Test complete workflow: init → discover → organize.

    This integration test:
    1. Initializes a new OpenNeuroStudies repository
    2. Discovers test datasets from GitHub (raw and derivatives)
    3. Organizes them into study structures
    4. Verifies proper submodule registration at both levels

    Args:
        test_workspace: Temporary test workspace path
    """
    # Save current directory
    original_cwd = Path.cwd()

    try:
        # Change to test workspace
        import os
        os.chdir(test_workspace)

        # Step 1: Initialize repository
        print("\n=== Step 1: Initialize repository ===")
        result = subprocess.run(
            ["openneuro-studies", "init"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0
        assert (test_workspace / ".openneuro-studies" / "config.yaml").exists()
        assert (test_workspace / ".git").exists()

        # Step 2: Discover datasets (with filter for test datasets)
        print("\n=== Step 2: Discover datasets ===")
        discover_args = ["openneuro-studies", "discover"]
        for dataset_id in TEST_RAW_DATASETS:
            discover_args.extend(["--test-filter", dataset_id])

        result = subprocess.run(
            discover_args,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0

        # Check discovered datasets file
        discovered_file = test_workspace / ".openneuro-studies" / "discovered-datasets.json"
        assert discovered_file.exists()

        with open(discovered_file) as f:
            discovered = json.load(f)

        raw_count = len(discovered.get("raw", []))
        deriv_count = len(discovered.get("derivative", []))

        print(f"Discovered: {raw_count} raw, {deriv_count} derivatives")
        assert raw_count > 0, "Should discover at least one raw dataset"

        # Verify we found the expected datasets
        raw_ids = {d["dataset_id"] for d in discovered.get("raw", [])}
        for expected_id in TEST_RAW_DATASETS:
            if expected_id != "ds006190":  # ds006190 is a derivative
                assert expected_id in raw_ids, f"Should discover {expected_id}"

        # Step 3: Organize datasets
        print("\n=== Step 3: Organize datasets ===")
        result = subprocess.run(
            ["openneuro-studies", "organize"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0

        # Step 4: Verify organization structure
        print("\n=== Step 4: Verify organization ===")

        # Check parent .gitmodules exists and has entries
        parent_gitmodules = test_workspace / ".gitmodules"
        assert parent_gitmodules.exists(), "Parent .gitmodules should exist"

        gitmodules_content = parent_gitmodules.read_text()

        # Check each raw dataset has a corresponding study
        for dataset_id in raw_ids:
            study_id = f"study-{dataset_id}"
            study_path = test_workspace / study_id

            # Study directory should exist
            assert study_path.exists(), f"{study_id} directory should exist"

            # Study should be a git repository
            assert (study_path / ".git").exists(), f"{study_id} should be a git repo"

            # Study should be registered in parent .gitmodules
            assert f'[submodule "{study_id}"]' in gitmodules_content, \
                f"{study_id} should be in parent .gitmodules"
            assert f"https://github.com/OpenNeuroStudies/{study_id}.git" in gitmodules_content, \
                f"{study_id} should point to OpenNeuroStudies organization"

            # Study should have its own .gitmodules with raw dataset
            study_gitmodules = study_path / ".gitmodules"
            assert study_gitmodules.exists(), f"{study_id} should have .gitmodules"

            study_gitmodules_content = study_gitmodules.read_text()
            assert "sourcedata/raw" in study_gitmodules_content, \
                f"{study_id} should have sourcedata/raw submodule"

            # Check raw dataset submodule status
            result = subprocess.run(
                ["git", "submodule", "status"],
                cwd=study_path,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "sourcedata/raw" in result.stdout, \
                f"{study_id} should have sourcedata/raw submodule registered"

        # Step 5: Verify parent submodule status
        print("\n=== Step 5: Verify parent submodule status ===")
        result = subprocess.run(
            ["git", "submodule", "status"],
            cwd=test_workspace,
            capture_output=True,
            text=True,
            check=True,
        )

        # Check that studies are listed as submodules
        for dataset_id in raw_ids:
            study_id = f"study-{dataset_id}"
            assert study_id in result.stdout, \
                f"{study_id} should be registered as parent submodule"

        # Step 6: Check git status is clean (all changes committed)
        print("\n=== Step 6: Verify git status ===")
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_workspace,
            capture_output=True,
            text=True,
            check=True,
        )

        # Git status should show studies as modified (because they have submodules)
        # but no untracked files
        status_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for line in status_lines:
            # Should only see modified submodules, not untracked files
            assert line.startswith(" M ") or line.startswith("?? study-"), \
                f"Unexpected git status: {line}"

        print("\n=== Integration test PASSED ===")
        print(f"Workspace: {test_workspace}")
        print(f"Raw datasets organized: {raw_count}")
        print(f"Derivatives discovered: {deriv_count}")

    finally:
        # Restore original directory
        os.chdir(original_cwd)


@pytest.mark.integration
@pytest.mark.ai_generated
def test_persistent_test_directory() -> None:
    """Create/update persistent test directory at /tmp/openneuro-test-discover.

    This is not a typical test - it's a helper to maintain a persistent
    test workspace for manual inspection and development.
    """
    test_dir = Path("/tmp/openneuro-test-discover")

    # Clean if exists
    if test_dir.exists():
        print(f"Cleaning existing {test_dir}")
        shutil.rmtree(test_dir)

    test_dir.mkdir(parents=True, exist_ok=True)

    # Save current directory
    original_cwd = Path.cwd()

    try:
        import os
        os.chdir(test_dir)

        # Initialize
        print("\n=== Initializing /tmp/openneuro-test-discover ===")
        subprocess.run(["openneuro-studies", "init"], check=True)

        # Discover with test filter
        print("\n=== Discovering test datasets ===")
        discover_args = ["openneuro-studies", "discover"]
        for dataset_id in TEST_RAW_DATASETS:
            discover_args.extend(["--test-filter", dataset_id])

        subprocess.run(discover_args, check=True)

        # Organize
        print("\n=== Organizing datasets ===")
        subprocess.run(["openneuro-studies", "organize"], check=True)

        # Report results
        discovered_file = test_dir / ".openneuro-studies" / "discovered-datasets.json"
        with open(discovered_file) as f:
            discovered = json.load(f)

        print(f"\n✓ Created {test_dir}")
        print(f"✓ Raw datasets: {len(discovered.get('raw', []))}")
        print(f"✓ Derivatives: {len(discovered.get('derivative', []))}")
        print(f"✓ Studies created: {len(list(test_dir.glob('study-*')))}")

    finally:
        os.chdir(original_cwd)
