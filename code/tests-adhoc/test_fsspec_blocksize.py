#!/usr/bin/env python3
"""Test block_size impact on NIfTI header extraction speed.

Tests different block_size values to find optimal setting for sparse access.
"""

import sys
import time
import statistics
from pathlib import Path

# Add code to path
sys.path.insert(0, '/home/yoh/proj/openneuro/OpenNeuroStudies/code/src')

from bids_studies.sparse.access import SparseDataset


def test_header_extraction(study_path: Path, block_size: int, num_runs: int = 5) -> dict:
    """Time header extraction with given block_size.

    Args:
        study_path: Path to sourcedata subdataset
        block_size: Block size in bytes for fsspec
        num_runs: Number of timing runs

    Returns:
        Dict with timing stats and file count
    """
    times = []

    for run in range(num_runs):
        start = time.time()

        # Extract metadata using our internal function
        with SparseDataset(study_path, block_size=block_size) as ds:
            bold_files = ds.list_files("*_bold.nii*")

            # Limit to first 10 files for faster testing
            for bold_file in bold_files[:10]:
                try:
                    with ds.open_file(bold_file) as f:
                        # Read enough to get header (simulating what our code does)
                        chunk_size = 1024 * 1024  # 1MB
                        _ = f.read(chunk_size)
                except Exception as e:
                    print(f"  Warning: Failed to read {bold_file}: {e}")
                    continue

        elapsed = time.time() - start
        times.append(elapsed)

    return {
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'stdev': statistics.stdev(times) if len(times) > 1 else 0,
        'min': min(times),
        'max': max(times),
        'runs': times,
        'file_count': min(10, len(bold_files))
    }


def main():
    # Test on one of the ds006185 sourcedata subdatasets
    study_path = Path('/home/yoh/proj/openneuro/OpenNeuroStudies/study-ds006191/sourcedata/ds006185')

    if not study_path.exists():
        print(f"Error: {study_path} does not exist")
        sys.exit(1)

    print(f"Testing block_size impact on: {study_path.name}")
    print(f"=" * 80)

    # Test different block sizes
    block_sizes = {
        '1 KB': 1 * 1024,
        '10 KB': 10 * 1024,
        '50 KB': 50 * 1024,
        '100 KB': 100 * 1024,
        '1 MB': 1024 * 1024,
        'Default (6 MB)': None,  # Will use fsspec default
    }

    results = {}

    for label, block_size in block_sizes.items():
        print(f"\nTesting {label} block_size...")

        try:
            stats = test_header_extraction(study_path, block_size, num_runs=10)
            results[label] = stats

            print(f"  Files processed: {stats['file_count']}")
            print(f"  Mean time: {stats['mean']:.3f}s")
            print(f"  Median time: {stats['median']:.3f}s")
            print(f"  Std dev: {stats['stdev']:.3f}s")
            print(f"  Range: {stats['min']:.3f}s - {stats['max']:.3f}s")
            print(f"  Individual runs: {[f'{t:.3f}s' for t in stats['runs']]}")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Summary comparison
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"{'Block Size':<20} {'Mean Time':<15} {'Speedup vs Default':<20}")
    print(f"{'-' * 80}")

    default_time = results.get('Default (6 MB)', {}).get('mean')

    for label, stats in results.items():
        mean_time = stats['mean']
        if default_time and label != 'Default (6 MB)':
            speedup = default_time / mean_time
            speedup_str = f"{speedup:.2f}x"
        else:
            speedup_str = "baseline"

        print(f"{label:<20} {mean_time:>7.3f}s        {speedup_str:<20}")


if __name__ == '__main__':
    main()
