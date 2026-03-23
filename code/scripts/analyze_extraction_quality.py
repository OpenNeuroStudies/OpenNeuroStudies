#!/usr/bin/env python3
"""Analyze extraction quality across all studies.

Shows which datasets have incomplete imaging metrics (n/a values)
indicating missing remote URLs or other extraction issues.
"""

import json
from pathlib import Path
from collections import defaultdict


def analyze_study(json_path: Path) -> dict:
    """Analyze a single study's extraction results.

    Returns:
        dict with metrics about extraction quality
    """
    with open(json_path) as f:
        data = json.load(f)

    study_id = json_path.stem.replace('.json', '')

    # Check for n/a values in imaging metrics
    imaging_fields = [
        'bold_voxels_total',
        'bold_voxels_mean',
        'bold_duration_total',
        'bold_duration_mean',
    ]

    missing_imaging = sum(1 for field in imaging_fields if data.get(field) == 'n/a')
    has_bold = data.get('bold_num', 'n/a') != 'n/a' and data.get('bold_num', 0) > 0

    # Determine status
    if missing_imaging == len(imaging_fields) and has_bold:
        status = 'missing_imaging_metrics'
    elif missing_imaging > 0 and has_bold:
        status = 'partial_imaging_metrics'
    elif not has_bold:
        status = 'no_bold'
    else:
        status = 'complete'

    return {
        'study_id': study_id,
        'status': status,
        'subjects_num': data.get('subjects_num', 'n/a'),
        'bold_num': data.get('bold_num', 'n/a'),
        't1w_num': data.get('t1w_num', 'n/a'),
        'bold_voxels_mean': data.get('bold_voxels_mean', 'n/a'),
        'bold_duration_mean': data.get('bold_duration_mean', 'n/a'),
        'missing_count': missing_imaging,
    }


def main():
    """Generate extraction quality report."""
    print("# Extraction Quality Analysis\n")

    # Find all extraction JSON files
    json_files = sorted(Path('.snakemake/extracted').glob('study-*.json'))

    if not json_files:
        print("No extraction JSON files found in .snakemake/extracted/")
        return

    print(f"Analyzing {len(json_files)} studies...\n")

    # Analyze all studies
    results = []
    for json_path in json_files:
        try:
            data = analyze_study(json_path)
            results.append(data)
        except Exception as e:
            print(f"Warning: Failed to analyze {json_path}: {e}")

    # Group by status
    by_status = defaultdict(list)
    for r in results:
        by_status[r['status']].append(r)

    # Print summary
    print("## Summary by Status\n")
    print(f"{'Status':<30} {'Count':<10}")
    print("-" * 40)
    for status in ['complete', 'partial_imaging_metrics', 'missing_imaging_metrics', 'no_bold']:
        count = len(by_status[status])
        if count > 0:
            print(f"{status:<30} {count:<10}")

    # Show datasets with missing imaging metrics
    if by_status['missing_imaging_metrics']:
        print(f"\n## Datasets Missing Imaging Metrics ({len(by_status['missing_imaging_metrics'])})\n")
        print("These likely have 'No remote URL' errors for all BOLD files:\n")
        print(f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'T1w Files':<10}")
        print("-" * 67)

        for r in sorted(by_status['missing_imaging_metrics'], key=lambda x: x['study_id']):
            print(f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                  f"{str(r['bold_num']):<12} {str(r['t1w_num']):<10}")

    # Show datasets with partial metrics
    if by_status['partial_imaging_metrics']:
        print(f"\n## Datasets with Partial Imaging Metrics ({len(by_status['partial_imaging_metrics'])})\n")
        print("Some BOLD files have remote URLs, others don't:\n")
        print(f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'Missing Fields':<15}")
        print("-" * 72)

        for r in sorted(by_status['partial_imaging_metrics'], key=lambda x: x['study_id']):
            print(f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                  f"{str(r['bold_num']):<12} {r['missing_count']}/4")

    # Write detailed TSV
    tsv_path = Path('logs/extraction_quality.tsv')
    tsv_path.parent.mkdir(exist_ok=True)

    with open(tsv_path, 'w') as f:
        f.write("study_id\tstatus\tsubjects_num\tbold_num\tt1w_num\t"
                "bold_voxels_mean\tbold_duration_mean\n")
        for r in sorted(results, key=lambda x: x['study_id']):
            f.write(f"{r['study_id']}\t{r['status']}\t{r['subjects_num']}\t"
                   f"{r['bold_num']}\t{r['t1w_num']}\t{r['bold_voxels_mean']}\t"
                   f"{r['bold_duration_mean']}\n")

    print(f"\n✓ Detailed report written to: {tsv_path}")
    print(f"\nTo investigate specific datasets:")
    print(f"  cat logs/extraction_quality.tsv | grep missing_imaging_metrics")


if __name__ == '__main__':
    main()
