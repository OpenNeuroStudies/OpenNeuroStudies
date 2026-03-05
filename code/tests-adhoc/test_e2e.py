#!/usr/bin/env python3
"""End-to-end testing of derivative extraction and studies.tsv generation."""

import sys
from pathlib import Path

# Add code/src to path
sys.path.insert(0, str(Path(__file__).parent / "code" / "src"))

from openneuro_studies.metadata.studies_plus_derivatives_tsv import (
    collect_derivatives_for_study,
    generate_studies_derivatives_tsv,
    generate_studies_derivatives_json,
)
from openneuro_studies.metadata.studies_tsv import (
    collect_study_metadata,
    generate_studies_tsv,
    generate_studies_json,
)


def test_part1_derivative_extraction():
    """Part 1: Test derivative extraction (studies+derivatives.tsv)."""
    print("\n" + "=" * 80)
    print("PART 1: DERIVATIVE EXTRACTION (studies+derivatives.tsv)")
    print("=" * 80)

    # Test studies
    test_studies = ["study-ds000001", "study-ds006131"]

    for study_id in test_studies:
        study_path = Path(study_id)
        if not study_path.exists():
            print(f"\n⚠️  {study_id} not found - skipping")
            continue

        print(f"\n--- Testing {study_id} ---")

        # Collect derivatives
        try:
            derivatives = collect_derivatives_for_study(study_path)
            print(f"Found {len(derivatives)} derivative(s)")

            for deriv in derivatives:
                print(f"\n  Derivative: {deriv.get('derivative_id', 'UNKNOWN')}")
                print(f"    tool_name: {deriv.get('tool_name', 'n/a')}")
                print(f"    tool_version: {deriv.get('tool_version', 'n/a')}")
                print(f"    size_total: {deriv.get('size_total', 'n/a')}")
                print(f"    file_count: {deriv.get('file_count', 'n/a')}")
                print(f"    processed_raw_version: {deriv.get('processed_raw_version', 'n/a')}")
                print(f"    uptodate: {deriv.get('uptodate', 'n/a')}")
                print(f"    tasks_processed: {deriv.get('tasks_processed', 'n/a')}")
                print(f"    anat_processed: {deriv.get('anat_processed', 'n/a')}")
                print(f"    func_processed: {deriv.get('func_processed', 'n/a')}")
                print(f"    template_spaces: {deriv.get('template_spaces', 'n/a')}")

        except Exception as e:
            print(f"  ❌ Error collecting derivatives: {e}")
            import traceback
            traceback.print_exc()

    # Generate full TSV
    print("\n\n--- Generating studies+derivatives.tsv ---")
    try:
        output_path = Path("studies+derivatives.tsv")
        study_paths = [Path(s) for s in test_studies]
        generate_studies_derivatives_tsv(studies=study_paths, output_path=output_path)
        print(f"✅ Generated {output_path}")

        # Read and display sample
        if output_path.exists():
            with open(output_path) as f:
                lines = f.readlines()
            print(f"\nFirst 10 lines of output:")
            for line in lines[:10]:
                print(f"  {line.rstrip()}")

    except Exception as e:
        print(f"❌ Error generating TSV: {e}")
        import traceback
        traceback.print_exc()


def test_part2_studies_tsv():
    """Part 2: Test studies.tsv column updates."""
    print("\n" + "=" * 80)
    print("PART 2: STUDIES.TSV COLUMN UPDATES")
    print("=" * 80)

    test_studies = ["study-ds000001", "study-ds006131"]

    for study_id in test_studies:
        study_path = Path(study_id)
        if not study_path.exists():
            print(f"\n⚠️  {study_id} not found - skipping")
            continue

        print(f"\n--- Testing {study_id} ---")

        try:
            metadata = collect_study_metadata(study_path, stage="imaging")

            print(f"  raw_bids_version: {metadata.get('raw_bids_version', 'n/a')}")
            print(f"  raw_hed_version: {metadata.get('raw_hed_version', 'n/a')}")
            print(f"  bold_voxels: {metadata.get('bold_voxels', 'n/a')}")
            print(f"  bold_timepoints: {metadata.get('bold_timepoints', 'n/a')}")
            print(f"  bold_tasks: {metadata.get('bold_tasks', 'n/a')}")

            # Check for n/a values
            issues = []
            if metadata.get('bold_voxels') == 'n/a':
                issues.append("bold_voxels is n/a")
            if metadata.get('bold_timepoints') == 'n/a':
                issues.append("bold_timepoints is n/a")
            if metadata.get('bold_tasks') == 'n/a':
                issues.append("bold_tasks is n/a")

            if issues:
                print(f"  ⚠️  Issues: {', '.join(issues)}")
            else:
                print("  ✅ All BOLD metadata extracted")

        except Exception as e:
            print(f"  ❌ Error collecting metadata: {e}")
            import traceback
            traceback.print_exc()

    # Generate full TSV
    print("\n\n--- Generating studies.tsv ---")
    try:
        output_path = Path("studies.tsv")
        study_paths = [Path(s) for s in test_studies]
        generate_studies_tsv(studies=study_paths, output_path=output_path, stage="imaging")
        print(f"✅ Generated {output_path}")

        # Read and display sample
        if output_path.exists():
            with open(output_path) as f:
                lines = f.readlines()
            print(f"\nFirst 5 lines of output:")
            for line in lines[:5]:
                print(f"  {line.rstrip()}")

    except Exception as e:
        print(f"❌ Error generating TSV: {e}")
        import traceback
        traceback.print_exc()


def test_part3_integration():
    """Part 3: Integration testing."""
    print("\n" + "=" * 80)
    print("PART 3: INTEGRATION TESTING")
    print("=" * 80)

    print("\n--- Checking for temporary subdataset installations ---")
    test_studies = ["study-ds000001", "study-ds006131"]

    for study_id in test_studies:
        study_path = Path(study_id)
        if not study_path.exists():
            continue

        deriv_path = study_path / "derivatives"
        if not deriv_path.exists():
            continue

        # Check if any derivatives are installed
        installed = []
        for item in deriv_path.iterdir():
            if item.is_dir() and (item / "dataset_description.json").exists():
                # Check if it has actual content (not just git metadata)
                file_count = sum(1 for _ in item.rglob("*") if _.is_file())
                if file_count > 5:  # More than just git/datalad files
                    installed.append(item.name)

        if installed:
            print(f"  ⚠️  {study_id}: Found installed derivatives: {', '.join(installed)}")
        else:
            print(f"  ✅ {study_id}: No derivatives permanently installed")

    print("\n--- Final file check ---")
    expected_files = [
        "studies.tsv",
        "studies.json",
        "studies+derivatives.tsv",
        "studies+derivatives.json",
    ]

    for filename in expected_files:
        path = Path(filename)
        if path.exists():
            size = path.stat().st_size
            print(f"  ✅ {filename} ({size:,} bytes)")
        else:
            print(f"  ❌ {filename} not found")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("END-TO-END TESTING: Derivative Extraction & Studies.tsv")
    print("=" * 80)

    test_part1_derivative_extraction()
    test_part2_studies_tsv()
    test_part3_integration()

    print("\n" + "=" * 80)
    print("TESTING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
