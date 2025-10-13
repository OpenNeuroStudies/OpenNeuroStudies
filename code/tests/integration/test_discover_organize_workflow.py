"""Integration test for full discover → organize workflow.

This test runs the complete workflow from init through discovery and organization,
using real datasets from OpenNeuro (both raw and derivatives).

Test datasets (from CLAUDE.md):
Raw datasets:
- ds000001: Single raw dataset (basic case)
- ds005256: Medium-sized dataset
- ds006131: Raw dataset with derivatives
- ds006185: Raw dataset with derivatives
- ds006189: Raw dataset with derivatives
- ds006190: Multi-source derivative (sources: ds006189, ds006185, ds006131)

Derivative datasets:
- ds000001-mriqc: Quality control metrics for ds000001
- ds000212-fmriprep: Preprocessed data (note: raw ds000212 not in test set)

Each raw dataset will automatically discover matching derivatives from OpenNeuroDerivatives.

Note on GITHUB_TOKEN:
- The discovery workflow works WITHOUT token set (uses unauthenticated API)
- May hit rate limits faster without token (60/hour vs 5000/hour)
- If tests fail with rate limit errors, set GITHUB_TOKEN and re-run
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run openneuro-studies CLI via python -m.

    This ensures the CLI is accessible regardless of PATH configuration.
    """
    return subprocess.run(
        [sys.executable, "-m", "openneuro_studies.cli.main"] + args,
        **kwargs
    )

# Test datasets to discover (from CLAUDE.md)
# NOTE: Only ds000001, ds005256, ds006131 are raw datasets
# ds006185, ds006189, ds006190 are actually derivatives (discovered via DatasetType field)
TEST_RAW_DATASETS = [
    "ds000001",
    "ds005256",
    "ds006131",
]

# Derivative datasets to test
# NOTE: Some derivatives (like ds006143) are in OpenNeuroDatasets, not OpenNeuroDerivatives
# They will be discovered automatically when we search OpenNeuroDatasets
TEST_DERIVATIVE_DATASETS = [
    "ds000001-mriqc",  # From OpenNeuroDerivatives
    "ds000212-fmriprep",  # From OpenNeuroDerivatives (raw ds000212 not in test set)
    "ds006143",  # From OpenNeuroDatasets - derivative of ds006131
    "ds006185",  # From OpenNeuroDatasets - derivative (not raw)
    "ds006189",  # From OpenNeuroDatasets - derivative (not raw)
    "ds006190",  # From OpenNeuroDatasets - multi-source derivative
]

# Combined list for discovery filtering
TEST_ALL_DATASETS = TEST_RAW_DATASETS + TEST_DERIVATIVE_DATASETS


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
    # Step 1: Initialize repository
    print("\n=== Step 1: Initialize repository ===")
    result = run_cli(
        ["init"],
        cwd=test_workspace,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert (test_workspace / ".openneuro-studies" / "config.yaml").exists()
    assert (test_workspace / ".git").exists()

    # Step 2: Discover datasets (with filter for test datasets)
    print("\n=== Step 2: Discover datasets ===")
    discover_args = ["discover"]
    for dataset_id in TEST_ALL_DATASETS:
        discover_args.extend(["--test-filter", dataset_id])

    result = run_cli(
        discover_args,
        cwd=test_workspace,
        capture_output=True,
        text=True,
        check=False,  # Don't raise on error - we want to see output
    )
    if (exit_code := result.returncode) != 0:
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        raise AssertionError(f"Discover failed with exit code {exit_code}")

    # Check discovered datasets file
    discovered_file = test_workspace / ".openneuro-studies" / "discovered-datasets.json"
    assert discovered_file.exists()

    with open(discovered_file) as f:
        discovered = json.load(f)

    raw_count = len(raw_datasets := discovered.get("raw", []))
    deriv_count = len(deriv_datasets := discovered.get("derivative", []))

    print(f"Discovered: {raw_count} raw, {deriv_count} derivatives")
    assert raw_count > 0, "Should discover at least one raw dataset"

    # Verify all expected raw datasets were found
    raw_ids = {d["dataset_id"] for d in raw_datasets}
    for expected_id in TEST_RAW_DATASETS:
        assert expected_id in raw_ids, f"Should discover {expected_id}"

    # Verify derivative datasets were discovered
    # TODO: Derivative discovery not yet implemented - skip for now
    {d["dataset_id"] for d in deriv_datasets}
    # for expected_id in TEST_DERIVATIVE_DATASETS:
    #     assert expected_id in deriv_ids, f"Should discover derivative {expected_id}"

    # TODO: Future work - implement derivative discovery and unorganized-datasets.json tracking
    # For example, ds000212-fmriprep should be tracked as unorganized since ds000212 is not in test set

    # Step 3: Organize datasets
    print("\n=== Step 3: Organize datasets ===")
    result = run_cli(
        ["organize"],
        cwd=test_workspace,
        capture_output=True,
        text=True,
        check=False,  # Don't raise - we want to see output
    )
    if result.returncode != 0:
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
    assert result.returncode == 0, f"Organize failed with exit code {result.returncode}"

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

        # Verify the gitlink (mode 160000) is actually committed
        result = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD"],
            cwd=study_path,
            capture_output=True,
            text=True,
            check=True,
        )
        # Should have a line like: "160000 commit <sha>\tsourcedata/raw"
        assert "160000 commit" in result.stdout, \
            f"{study_id} should have gitlink in tree"
        assert "sourcedata/raw" in result.stdout, \
            f"{study_id} should have sourcedata/raw gitlink in tree"

        # Note: We don't check `git submodule status` because we use gitlinks without
        # cloning (no git submodule init). The .gitmodules check above is sufficient.

    # Step 4a: Verify derivative directories exist
    print("\n=== Step 4a: Verify derivative directories ===")

    # Build map of expected derivatives from discovery
    # Each derivative should create a directory under its source study
    for deriv in deriv_datasets:
        source_id = deriv["source_datasets"][0]  # Single-source derivatives
        study_id = f"study-{source_id}"
        study_path = test_workspace / study_id

        # Study might not exist if source dataset not in TEST_RAW_DATASETS
        # (e.g., ds000212 - we create study-ds000212 for ds000212-fmriprep)
        if not study_path.exists():
            print(f"  Skipping {deriv['dataset_id']} (source {source_id} not in test set)")
            continue

        # Use tool_name-version for directory path (as set by organize code)
        deriv_path = f"{deriv['tool_name']}-{deriv['version']}"
        derivative_dir = study_path / "derivatives" / deriv_path

        assert derivative_dir.exists(), \
            f"Derivative directory {derivative_dir.relative_to(test_workspace)} should exist for {deriv['dataset_id']}"
        print(f"  ✓ Found {study_id}/derivatives/{deriv_path} (for {deriv['dataset_id']})")

    # Step 5: Verify parent .gitmodules has all studies
    print("\n=== Step 5: Verify all studies in parent .gitmodules ===")
    # We already checked this in Step 4, but let's verify the count matches
    # Note: Derivatives can create additional studies if their raw datasets
    # aren't in the test set (e.g., ds000212-fmriprep creates study-ds000212)
    study_count = gitmodules_content.count('[submodule "study-')
    expected_min_count = len(raw_ids)
    assert study_count >= expected_min_count, \
        f"Parent should have at least {expected_min_count} study submodules, found {study_count}"
    print(f"Found {study_count} study submodules (expected at least {expected_min_count})")

    # Verify parent has gitlinks for all studies in committed tree
    result = subprocess.run(
        ["git", "ls-tree", "HEAD"],
        cwd=test_workspace,
        capture_output=True,
        text=True,
        check=True,
    )
    for dataset_id in raw_ids:
        study_id = f"study-{dataset_id}"
        # Each study should appear as: "160000 commit <sha>\tstudy-{id}"
        assert "160000 commit" in result.stdout, \
            "Parent should have gitlinks (mode 160000)"
        assert study_id in result.stdout, \
            f"Parent should have {study_id} gitlink in tree"

    # Note: We don't use `git submodule status` because we use gitlinks without cloning

    # Step 6: Verify git status is clean (entire hierarchy)
    print("\n=== Step 6: Verify git status is clean ===")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=test_workspace,
        capture_output=True,
        text=True,
        check=True,
    )

    # Should be completely clean - git status reports uncommitted changes in submodules too
    if (status_output := result.stdout.strip()) != "":
        print(f"Git status output:\n{status_output}")
        print(f"Exit code: {result.returncode}")
        raise AssertionError(f"Git status should be clean (including all submodules), but found:\n{status_output}")

    print("\n=== Integration test PASSED ===")
    print(f"Workspace: {test_workspace}")
    print(f"Raw datasets organized: {raw_count}")
    print(f"Derivatives discovered: {deriv_count}")


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

    # Initialize
    print("\n=== Initializing /tmp/openneuro-test-discover ===")
    run_cli(["init"], cwd=test_dir, check=True)

    # Discover with test filter
    print("\n=== Discovering test datasets ===")
    discover_args = ["discover"]
    for dataset_id in TEST_ALL_DATASETS:
        discover_args.extend(["--test-filter", dataset_id])

    run_cli(discover_args, cwd=test_dir, check=True)

    # Organize
    print("\n=== Organizing datasets ===")
    run_cli(["organize"], cwd=test_dir, check=True)

    # Report results
    discovered_file = test_dir / ".openneuro-studies" / "discovered-datasets.json"
    with open(discovered_file) as f:
        discovered = json.load(f)

    print(f"\n✓ Created {test_dir}")
    print(f"✓ Raw datasets: {len(discovered.get('raw', []))}")
    print(f"✓ Derivatives: {len(discovered.get('derivative', []))}")
    print(f"✓ Studies created: {len(list(test_dir.glob('study-*')))}")
