#!/usr/bin/env python3
"""Summarize extraction errors across all studies.

Analyzes extraction_errors.log files in study directories and creates
a centralized summary showing which datasets have the most issues.
"""

import re
from collections import defaultdict
from pathlib import Path


def parse_error_log(log_path: Path) -> dict:
    """Parse an extraction_errors.log file.

    Returns:
        dict with keys: total_errors, error_rate, dataset_id, first_errors
    """
    with open(log_path) as f:
        content = f.read()

    # Parse header: "ds001506: Extraction failed: 1190 errors across 154 subjects (error rate: 772.7% exceeds 50% threshold)."
    dataset_match = re.search(r'^(\w+): Extraction (?:failed|completed)', content, re.MULTILINE)
    dataset_id = dataset_match.group(1) if dataset_match else "unknown"

    errors_match = re.search(r'(\d+) errors across (\d+) subjects', content)
    total_errors = int(errors_match.group(1)) if errors_match else 0
    total_subjects = int(errors_match.group(2)) if errors_match else 0

    rate_match = re.search(r'error rate: ([\d.]+)%', content)
    error_rate = float(rate_match.group(1)) if rate_match else 0.0

    # Extract first few errors
    first_errors = []
    for line in content.split('\n'):
        if 'Failed to extract' in line:
            first_errors.append(line.strip())
            if len(first_errors) >= 5:
                break

    return {
        'dataset_id': dataset_id,
        'total_errors': total_errors,
        'total_subjects': total_subjects,
        'error_rate': error_rate,
        'first_errors': first_errors,
        'log_path': log_path,
    }


def categorize_errors(errors: list[str]) -> dict[str, int]:
    """Categorize errors by type.

    Returns:
        dict mapping error type to count
    """
    categories = defaultdict(int)

    for error in errors:
        if 'No remote URL found' in error:
            categories['missing_remote_url'] += 1
        elif 'Network' in error or 'Connection' in error:
            categories['network_error'] += 1
        elif 'Permission denied' in error:
            categories['permission_error'] += 1
        elif 'git-annex' in error:
            categories['git_annex_error'] += 1
        else:
            categories['other'] += 1

    return categories


def main():
    """Generate error summary report."""
    print("# Extraction Error Summary\n")
    print(f"Generated: {Path.cwd()}\n")

    # Find all extraction_errors.log files
    error_logs = sorted(Path('.').glob('study-*/sourcedata/extraction_errors.log'))

    if not error_logs:
        print("No extraction_errors.log files found.")
        return

    print(f"Found {len(error_logs)} studies with extraction errors:\n")

    # Parse all logs
    results = []
    for log_path in error_logs:
        study_id = log_path.parts[0]
        data = parse_error_log(log_path)
        data['study_id'] = study_id
        results.append(data)

    # Sort by total errors (descending)
    results.sort(key=lambda x: x['total_errors'], reverse=True)

    # Print summary table
    print("## Studies with Errors (sorted by count)")
    print()
    print(f"{'Study':<20} {'Dataset':<15} {'Errors':<10} {'Subjects':<10} {'Rate':<10}")
    print("-" * 75)

    total_errors_all = 0
    for r in results:
        print(f"{r['study_id']:<20} {r['dataset_id']:<15} {r['total_errors']:<10} "
              f"{r['total_subjects']:<10} {r['error_rate']:.1f}%")
        total_errors_all += r['total_errors']

    print()
    print(f"Total errors across all studies: {total_errors_all}")

    # Categorize all errors
    print("\n## Error Breakdown by Type\n")
    all_first_errors = []
    for r in results:
        all_first_errors.extend(r['first_errors'])

    categories = categorize_errors(all_first_errors)
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"{category:.<30} {count}")

    # Show top problematic datasets
    print("\n## Top 5 Most Problematic Datasets\n")
    for i, r in enumerate(results[:5], 1):
        print(f"{i}. {r['study_id']} ({r['dataset_id']})")
        print(f"   Errors: {r['total_errors']} across {r['total_subjects']} subjects ({r['error_rate']:.1f}%)")
        print(f"   Log: {r['log_path']}")
        if r['first_errors']:
            print(f"   First error: {r['first_errors'][0][:100]}...")
        print()

    # Generate TSV output
    tsv_path = Path('logs/extraction_errors.tsv')
    tsv_path.parent.mkdir(exist_ok=True)

    with open(tsv_path, 'w') as f:
        f.write("study_id\tdataset_id\ttotal_errors\ttotal_subjects\terror_rate\tlog_path\n")
        for r in results:
            f.write(f"{r['study_id']}\t{r['dataset_id']}\t{r['total_errors']}\t"
                   f"{r['total_subjects']}\t{r['error_rate']:.1f}\t{r['log_path']}\n")

    print(f"✓ Detailed summary written to: {tsv_path}")


if __name__ == '__main__':
    main()
