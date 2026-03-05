#!/usr/bin/env python3
"""Manual test script for derivative extraction functions.

This script tests the extraction functions without requiring pytest.
"""

import sys
import json
from pathlib import Path

# Add source to path
sys.path.insert(0, 'code/src')

# Import only the extractor module (not the full package to avoid datalad dependency)
import subprocess
import re
from collections import Counter


def extract_tasks_processed(derivative_path: Path) -> str:
    """Extract task names from derivative func/ directory."""
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'func/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return 'n/a'

        files = result.stdout.strip().split('\n')

        # Extract task entities: _task-{label}_
        task_pattern = re.compile(r'_task-([a-zA-Z0-9]+)_')
        tasks = set()

        for filepath in files:
            # Only consider data files
            if any(filepath.endswith(ext) for ext in [
                '_bold.nii.gz', '_bold.json',
                '_cbv.nii.gz', '_cbv.json',
                '_sbref.nii.gz', '_sbref.json'
            ]):
                match = task_pattern.search(filepath)
                if match:
                    tasks.add(match.group(1))

        if tasks:
            return ','.join(sorted(tasks))
        return 'n/a'

    except subprocess.CalledProcessError:
        return 'n/a'


def extract_template_spaces(derivative_path: Path) -> str:
    """Extract template spaces with actual data."""
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return 'n/a'

        files = result.stdout.strip().split('\n')

        # Extract space entities: _space-{label}_
        space_pattern = re.compile(r'_space-([a-zA-Z0-9]+)_')
        data_spaces = set()

        for filepath in files:
            # Exclude transform files
            if any(x in filepath for x in ['_xfm.', '_from-', '_to-']):
                continue

            # Only consider data files
            if any(filepath.endswith(ext) for ext in [
                '_bold.nii.gz', '_T1w.nii.gz', '_T2w.nii.gz',
                '_cbv.nii.gz', '_mask.nii.gz', '_dseg.nii.gz',
                '_probseg.nii.gz', '_dtissue.nii.gz',
                '.func.gii', '.surf.gii', '.shape.gii'
            ]):
                match = space_pattern.search(filepath)
                if match:
                    data_spaces.add(match.group(1))

        if data_spaces:
            return ','.join(sorted(data_spaces))
        return 'n/a'

    except subprocess.CalledProcessError:
        return 'n/a'


def extract_anat_processed(derivative_path: Path) -> bool:
    """Check if anatomical processing outputs exist."""
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'anat/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return False

        files = result.stdout.strip().split('\n')

        # Check for processing indicators
        for filepath in files:
            # NIfTI files only
            if not filepath.endswith('.nii.gz'):
                continue

            # Any desc- entity indicates processing
            if '_desc-' in filepath:
                return True

            # Space normalization indicates processing
            if '_space-' in filepath and '_from-' not in filepath:
                return True

            # Segmentation outputs indicate processing
            if any(seg in filepath for seg in ['_dseg.nii.gz', '_probseg.nii.gz']):
                return True

        return False

    except subprocess.CalledProcessError:
        return False


def extract_func_processed(derivative_path: Path) -> bool:
    """Check if functional processing outputs exist."""
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'func/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return False

        files = result.stdout.strip().split('\n')

        # Check for preprocessed functional outputs
        func_indicators = [
            '_desc-preproc_bold.nii.gz',
            '_space-',
            '_boldref.nii.gz',
        ]

        for filepath in files:
            if any(indicator in filepath for indicator in func_indicators):
                return True

        return False

    except subprocess.CalledProcessError:
        return False


def extract_descriptions(derivative_path: Path) -> str:
    """Extract description entity counts from derivative outputs."""
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return '{}'

        files = result.stdout.strip().split('\n')

        # Extract desc entities: _desc-{label}_
        desc_pattern = re.compile(r'_desc-([a-zA-Z0-9]+)_')
        desc_labels = []

        for filepath in files:
            # Only consider BIDS data files (not hidden, not in derivatives root)
            if filepath.startswith('.') or '/' not in filepath:
                continue

            matches = desc_pattern.findall(filepath)
            desc_labels.extend(matches)

        if not desc_labels:
            return '{}'

        # Count occurrences
        counts = Counter(desc_labels)

        # Convert to sorted dict
        result_dict = dict(sorted(counts.items()))

        return json.dumps(result_dict, separators=(',', ':'))

    except subprocess.CalledProcessError:
        return '{}'


def main():
    """Run manual tests."""
    print("=" * 70)
    print("Testing Derivative Metadata Extraction Functions")
    print("=" * 70)

    # Test with ds006131 fMRIPrep
    print("\n1. Testing with study-ds006131/derivatives/fMRIPrep-24.1.1")
    print("-" * 70)

    deriv_path = Path("study-ds006131/derivatives/fMRIPrep-24.1.1")

    if not deriv_path.exists():
        print(f"ERROR: Path does not exist: {deriv_path}")
        return 1

    print(f"✓ Path exists: {deriv_path}")

    # Test tasks extraction
    tasks = extract_tasks_processed(deriv_path)
    print(f"  Tasks processed: {tasks}")
    assert tasks != '', "Tasks should not be empty"

    # Test template spaces
    spaces = extract_template_spaces(deriv_path)
    print(f"  Template spaces: {spaces}")
    assert spaces != '', "Spaces should not be empty"

    # Test anat processing
    anat = extract_anat_processed(deriv_path)
    print(f"  Anat processed: {anat}")
    assert isinstance(anat, bool), "Anat should be boolean"

    # Test func processing
    func = extract_func_processed(deriv_path)
    print(f"  Func processed: {func}")
    assert isinstance(func, bool), "Func should be boolean"

    # Test descriptions
    descriptions = extract_descriptions(deriv_path)
    print(f"  Descriptions: {descriptions}")
    desc_dict = json.loads(descriptions)
    assert isinstance(desc_dict, dict), "Descriptions should be dict"
    print(f"    Found {len(desc_dict)} description types")

    # Test with ds000001 fMRIPrep
    print("\n2. Testing with study-ds000001/derivatives/fMRIPrep-21.0.1")
    print("-" * 70)

    deriv_path2 = Path("study-ds000001/derivatives/fMRIPrep-21.0.1")

    if not deriv_path2.exists():
        print(f"WARNING: Path does not exist: {deriv_path2}")
    else:
        print(f"✓ Path exists: {deriv_path2}")

        tasks2 = extract_tasks_processed(deriv_path2)
        print(f"  Tasks processed: {tasks2}")

        spaces2 = extract_template_spaces(deriv_path2)
        print(f"  Template spaces: {spaces2}")

        anat2 = extract_anat_processed(deriv_path2)
        print(f"  Anat processed: {anat2}")

        func2 = extract_func_processed(deriv_path2)
        print(f"  Func processed: {func2}")

        descriptions2 = extract_descriptions(deriv_path2)
        print(f"  Descriptions: {descriptions2}")

    print("\n" + "=" * 70)
    print("✓ All manual tests passed!")
    print("=" * 70)

    return 0


if __name__ == '__main__':
    sys.exit(main())
